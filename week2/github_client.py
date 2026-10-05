"""GitHub REST, authorization-code OAuth, and a private rotating token cache."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import math
import os
import re
import secrets
import stat
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

AUTH_COMMAND = "uv run python -m week2.github_mcp auth"
AUTH_ACTION = f"Run `{AUTH_COMMAND}`, then restart the MCP connection."
TOKEN_URL = "https://github.com/login/oauth/access_token"
API_BASE = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "week2-github-issues-mcp",
}

# httpx debug output can include the authorization URL and its one-time state.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ServiceError(Exception):
    """Only fixed, non-secret messages cross the MCP boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        action: str = AUTH_ACTION,
        *,
        retryable: bool = False,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(message)
        self.error = {
            "code": code,
            "message": message,
            "retryable": retryable,
            "action": action,
            "http_status": http_status,
            "retry_after_seconds": retry_after_seconds,
        }


@dataclass(frozen=True)
class Settings:
    repository: str
    token_path: Path
    client_id: str = ""
    client_secret: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> Settings:
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", repository
        ) or repository.split("/")[-1] in {".", ".."}:
            raise ServiceError(
                "configuration_error",
                "GITHUB_REPOSITORY must be a single owner/repository name.",
                "Set GITHUB_REPOSITORY to the public sandbox repository and restart.",
            )
        return cls(
            repository=repository,
            token_path=Path(
                os.environ.get(
                    "GITHUB_MCP_TOKEN_PATH", "~/.local/state/week2-github-mcp/token.json"
                )
            ).expanduser(),
            client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
            client_secret=os.environ.get("GITHUB_CLIENT_SECRET", ""),
        )

    def credentials(self, *, secret: bool = True) -> dict[str, str]:
        if not self.client_id or (secret and not self.client_secret):
            raise ServiceError(
                "configuration_error",
                "Required OAuth environment variables are missing.",
                "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET, then restart the MCP connection.",
            )
        return (
            {"client_id": self.client_id, "client_secret": self.client_secret}
            if secret
            else {"client_id": self.client_id}
        )


class TokenPair(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    access_token: str = Field(min_length=1, repr=False)
    refresh_token: str = Field(min_length=1, repr=False)
    access_token_expires_at: float = Field(gt=0, allow_inf_nan=False)
    refresh_token_expires_at: float = Field(gt=0, allow_inf_nan=False)
    scope: list[str]
    login: str = Field(min_length=1)


def check_scope(scope: list[str]) -> None:
    if "public_repo" not in scope:
        raise ServiceError("insufficient_scope", "The token must grant public_repo.")


def read_cache(path: Path) -> TokenPair:
    try:
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError("unsafe directory")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("unsafe file")
            token = TokenPair.model_validate_json(stream.read())
    except FileNotFoundError:
        raise ServiceError("auth_required", "No OAuth token cache was found.") from None
    except (OSError, ValueError, ValidationError):
        raise ServiceError(
            "reauth_required", "The token cache is invalid or its permissions are unsafe."
        ) from None
    check_scope(token.scope)
    return token


def save_cache(path: Path, token: TokenPair) -> None:
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700:
            raise OSError("unsafe directory")
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".token-")
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(token.model_dump_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise ServiceError(
            "configuration_error",
            "Could not save the private token cache.",
            "Use a dedicated token directory with mode 0700, then authenticate again.",
        ) from None
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class GitHubClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http
        # ponytail: one process/account; use a cross-process lock if sharing the cache.
        self.refresh_lock = asyncio.Lock()

    async def token_exchange(self, parameters: dict[str, str], login: str) -> TokenPair:
        parameters = {**self.settings.credentials(), **parameters}
        try:
            response = await self.http.post(
                TOKEN_URL, data=parameters, headers={"Accept": "application/json"}
            )
        except httpx.RequestError:
            raise ServiceError(
                "auth_unavailable",
                "GitHub token exchange is temporarily unavailable.",
                "Try the original safe call later; do not resend a comment with an unknown outcome.",
                retryable=True,
            ) from None
        if response.status_code >= 500 or response.status_code == 429:
            raise ServiceError(
                "auth_unavailable",
                "GitHub token exchange is temporarily unavailable.",
                "Try again later.",
                retryable=True,
                http_status=response.status_code,
            )
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid response")
        except ValueError:
            raise ServiceError(
                "auth_unavailable",
                "GitHub returned an invalid token response.",
                "Try authentication again later.",
                retryable=True,
            ) from None
        if payload.get("error") == "incorrect_client_credentials":
            raise ServiceError(
                "configuration_error",
                "GitHub rejected the OAuth App credentials.",
                "Check GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET, then restart.",
            )
        if payload.get("error") or response.status_code != 200:
            raise ServiceError(
                "reauth_required",
                "GitHub rejected the authorization code or refresh token.",
                http_status=response.status_code,
            )
        try:
            scope = re.split(r"[ ,]+", payload["scope"].strip())
            check_scope(scope)
            now = time.time()
            expires_in = float(payload["expires_in"])
            refresh_expires_in = float(payload["refresh_token_expires_in"])
            if not all(
                math.isfinite(value) and value > 0 for value in (expires_in, refresh_expires_in)
            ):
                raise ValueError("invalid lifetime")
            return TokenPair(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
                access_token_expires_at=now + expires_in,
                refresh_token_expires_at=now + refresh_expires_in,
                scope=scope,
                login=login,
            )
        except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
            raise ServiceError(
                "configuration_error",
                "GitHub did not return a valid expiring token pair.",
                "Enable access token expiration for the OAuth App and run the auth command again.",
            ) from None

    async def access_token(self, rejected_token: str | None = None) -> str:
        self.settings.credentials(secret=False)
        async with self.refresh_lock:
            token = read_cache(self.settings.token_path)
            force = rejected_token is not None and token.access_token == rejected_token
            if not force and token.access_token_expires_at - time.time() >= 60:
                return token.access_token
            if token.refresh_token_expires_at <= time.time():
                raise ServiceError("reauth_required", "The refresh token has expired.")
            updated = await self.token_exchange(
                {"grant_type": "refresh_token", "refresh_token": token.refresh_token}, token.login
            )
            save_cache(self.settings.token_path, updated)
            return updated.access_token

    async def request(self, method: str, path: str, **kwargs):
        token = await self.access_token()
        for attempt in range(2):
            try:
                response = await self.http.request(
                    method,
                    API_BASE + path,
                    headers={**API_HEADERS, "Authorization": f"Bearer {token}"},
                    **kwargs,
                )
            except httpx.RequestError:
                if method == "POST":
                    raise self.unknown_comment() from None
                raise ServiceError(
                    "network_error",
                    "Could not read from GitHub.",
                    "Retry this read later.",
                    retryable=True,
                ) from None
            if response.status_code == 401:
                if attempt == 1:
                    raise ServiceError(
                        "reauth_required",
                        "GitHub rejected the refreshed access token.",
                        http_status=401,
                    )
                token = await self.access_token(rejected_token=token)
                continue
            self.check_response(response, method)
            try:
                return response.json()
            except ValueError:
                if method == "POST":
                    raise self.unknown_comment() from None
                raise ServiceError(
                    "github_unavailable",
                    "GitHub returned an invalid API response.",
                    "Retry this read later.",
                    retryable=True,
                ) from None

    def unknown_comment(self) -> ServiceError:
        return ServiceError(
            "comment_outcome_unknown",
            "The comment may have been created; its outcome is unknown.",
            f"Check https://github.com/{self.settings.repository}/issues before sending another comment. Never automatically retry.",
        )

    def check_response(self, response: httpx.Response, method: str) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if method == "POST" and (status >= 500 or 300 <= status < 400):
            raise self.unknown_comment()
        headers = response.headers
        limited = status == 429 or (
            status == 403
            and ("retry-after" in headers or headers.get("x-ratelimit-remaining") == "0")
        )
        if limited:
            wait = 60
            try:
                wait = max(
                    1,
                    math.ceil(float(headers["retry-after"]))
                    if "retry-after" in headers
                    else math.ceil(float(headers["x-ratelimit-reset"]) - time.time()),
                )
            except (KeyError, ValueError, OverflowError):
                pass
            raise ServiceError(
                "rate_limited",
                "GitHub rate limit reached.",
                "Wait retry_after_seconds before retrying. Never retry an unknown comment outcome.",
                retryable=True,
                http_status=status,
                retry_after_seconds=wait,
            )
        errors = {
            403: (
                "forbidden",
                "GitHub denied this operation.",
                "Check public_repo scope and permissions on the configured repository.",
                False,
            ),
            404: (
                "not_found",
                "The Issue or configured repository was not found.",
                "Call list_issues and use an issue_number returned by it. If listing fails, check repository access.",
                False,
            ),
        }
        code, message, action, retryable = errors.get(
            status,
            (
                "github_unavailable",
                "GitHub is temporarily unavailable.",
                "Retry this read later.",
                True,
            )
            if status >= 500
            else (
                "github_rejected",
                "GitHub rejected the request.",
                "Check the input, repository access and Issue state before trying again.",
                False,
            ),
        )
        raise ServiceError(code, message, action, retryable=retryable, http_status=status)

    @staticmethod
    def summary(raw: dict) -> dict:
        return {
            "issue_number": raw["number"],
            "title": raw["title"],
            "state": raw["state"],
            "author": (raw.get("user") or {}).get("login"),
            "labels": [
                label if isinstance(label, str) else label["name"]
                for label in raw.get("labels", [])
            ],
            "comment_count": raw["comments"],
            "updated_at": raw["updated_at"],
            "url": raw["html_url"],
        }

    async def list_issues(self, state: str, sort: str, direction: str, limit: int) -> dict:
        raw = await self.request(
            "GET",
            f"/repos/{self.settings.repository}/issues",
            params={"state": state, "sort": sort, "direction": direction, "per_page": 100},
        )
        issues = [self.summary(issue) for issue in raw if "pull_request" not in issue][:limit]
        return {
            "status": "ok",
            "repository": self.settings.repository,
            "count": len(issues),
            "issues": issues,
        }

    async def issue_payload(self, issue_number: int) -> dict:
        raw = await self.request("GET", f"/repos/{self.settings.repository}/issues/{issue_number}")
        if "pull_request" in raw:
            raise ServiceError(
                "unsupported_target",
                "This number identifies a Pull Request, not an Issue.",
                "Call list_issues and use a normal Issue number returned by it.",
            )
        return raw

    async def get_issue(self, issue_number: int) -> dict:
        raw = await self.issue_payload(issue_number)
        body = raw.get("body") or ""
        issue = {
            **self.summary(raw),
            "state_reason": raw.get("state_reason"),
            "assignees": [user["login"] for user in raw.get("assignees", [])],
            "body": body[:8000],
            "body_truncated": len(body) > 8000,
            "locked": raw["locked"],
            "created_at": raw["created_at"],
        }
        return {"status": "ok", "repository": self.settings.repository, "issue": issue}

    async def add_issue_comment(self, issue_number: int, body: str, dry_run: bool = True) -> dict:
        if dry_run:
            return {
                "status": "preview",
                "repository": self.settings.repository,
                "issue_number": issue_number,
                "body": body,
                "target_url": f"https://github.com/{self.settings.repository}/issues/{issue_number}",
                "next_step": (
                    "Nothing was posted. Show this exact body to the user and stop. "
                    "Call add_issue_comment with the same issue_number and body only after the "
                    "user explicitly approves this preview."
                ),
            }
        await self.issue_payload(issue_number)
        raw = await self.request(
            "POST",
            f"/repos/{self.settings.repository}/issues/{issue_number}/comments",
            json={"body": body},
        )
        try:
            return {
                "status": "created",
                "repository": self.settings.repository,
                "issue_number": issue_number,
                "comment_id": raw["id"],
                "author": (raw.get("user") or {}).get("login"),
                "created_at": raw["created_at"],
                "url": raw["html_url"],
            }
        except (KeyError, TypeError, AttributeError):
            raise self.unknown_comment() from None

    async def complete_auth(
        self, query: str, expected_state: str, verifier: str, redirect_uri: str
    ) -> str:
        parameters = parse_qs(query, keep_blank_values=True)
        returned_state = parameters.get("state", [])
        if len(returned_state) != 1 or not hmac.compare_digest(
            returned_state[0].encode(), expected_state.encode()
        ):
            raise ServiceError(
                "reauth_required", "OAuth state did not match; authentication was cancelled."
            )
        codes = parameters.get("code", [])
        if "error" in parameters or len(codes) != 1 or not codes[0]:
            raise ServiceError(
                "reauth_required", "OAuth approval was denied or the callback was invalid."
            )
        token = await self.token_exchange(
            {"code": codes[0], "redirect_uri": redirect_uri, "code_verifier": verifier},
            "unverified",
        )
        try:
            response = await self.http.get(
                API_BASE + "/user",
                headers={**API_HEADERS, "Authorization": f"Bearer {token.access_token}"},
            )
        except httpx.RequestError:
            raise ServiceError(
                "auth_unavailable",
                "Could not verify the GitHub account.",
                "Run the auth command again later.",
                retryable=True,
            ) from None
        self.check_response(response, "GET")
        try:
            login = response.json()["login"]
            token = TokenPair.model_validate({**token.model_dump(), "login": login})
        except (ValueError, KeyError, TypeError, ValidationError):
            raise ServiceError(
                "auth_unavailable",
                "GitHub returned an invalid account response.",
                "Run the auth command again later.",
                retryable=True,
            ) from None
        save_cache(self.settings.token_path, token)
        return token.login


async def authorize(settings: Settings, timeout: float = 180) -> None:
    """Only this standalone command may open a browser; callbacks never log secrets."""
    settings.credentials()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    loop = asyncio.get_running_loop()
    result = loop.create_future()
    callback_lock = asyncio.Lock()
    handlers: set[asyncio.Task] = set()
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as http:
        client = GitHubClient(settings, http)

        async def callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            task = asyncio.current_task()
            handlers.add(task)
            status, message = "400 Bad Request", "Authentication failed. Return to the terminal."
            try:
                # A stalled browser connection must not hold authentication open forever.
                line = await asyncio.wait_for(reader.readline(), 5)
                parts = line.decode("ascii").strip().split(" ")
                target = urlsplit(parts[1]) if len(parts) == 3 else None
                if target and parts[0] == "GET" and target.path == "/oauth/callback":
                    async with callback_lock:
                        if not result.done():
                            try:
                                login = await client.complete_auth(
                                    target.query, state, verifier, redirect_uri
                                )
                            except ServiceError as error:
                                result.set_exception(error)
                            else:
                                result.set_result(login)
                                status, message = (
                                    "200 OK",
                                    "Authentication complete. Return to the terminal.",
                                )
                else:
                    status = "404 Not Found"
            except (ValueError, UnicodeDecodeError, asyncio.TimeoutError, ConnectionError):
                pass
            finally:
                content = message.encode()
                writer.write(
                    f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\nContent-Length: {len(content)}\r\nConnection: close\r\n\r\n".encode()
                    + content
                )
                try:
                    await writer.drain()
                except ConnectionError:
                    pass
                finally:
                    writer.close()
                    handlers.discard(task)

        try:
            server = await asyncio.start_server(callback, "127.0.0.1", 0, limit=8192)
        except OSError:
            raise ServiceError(
                "configuration_error",
                "Could not start the loopback OAuth listener.",
                "Allow local loopback connections and run the auth command again.",
            ) from None
        redirect_uri = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/oauth/callback"
        url = "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": settings.client_id,
                "redirect_uri": redirect_uri,
                "scope": "public_repo",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        try:
            try:
                opened = webbrowser.open(url)
            except webbrowser.Error:
                opened = False
            if not opened:
                print(
                    "Open this one-time authorization URL in your browser:\n" + url,
                    file=sys.stderr,
                )
            try:
                login = await asyncio.wait_for(result, timeout)
            except asyncio.TimeoutError:
                raise ServiceError(
                    "reauth_required", "OAuth approval timed out; no token was saved."
                ) from None
        finally:
            # Closing the listener alone does not cancel an exchange already in flight.
            server.close()
            active = list(handlers)
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)
            await server.wait_closed()
        print(f"Authenticated as {login}; repository: {settings.repository}", file=sys.stderr)
