"""No live GitHub calls or real credentials: OAuth and API failures are simulated."""

import asyncio
import base64
import hashlib
import json
import os
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from week2.github_client import (
    GitHubClient,
    ServiceError,
    Settings,
    TokenPair,
    authorize,
    read_cache,
    save_cache,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        "owner/mcp-oauth-sandbox", tmp_path / "private" / "token.json", "test-client", "test-secret"
    )


def cached_token(settings, *, expires_in=3600, refresh_expires_in=86400):
    token = TokenPair(
        access_token="test-access",
        refresh_token="test-refresh",
        access_token_expires_at=time.time() + expires_in,
        refresh_token_expires_at=time.time() + refresh_expires_in,
        scope=["public_repo"],
        login="octocat",
    )
    save_cache(settings.token_path, token)
    return token


def token_response(**overrides):
    return {
        "access_token": "test-new-access",
        "refresh_token": "test-new-refresh",
        "expires_in": 28800,
        "refresh_token_expires_in": 15897600,
        "scope": "public_repo",
        "token_type": "bearer",
        **overrides,
    }


def issue(**overrides):
    return {
        "number": 12,
        "title": "Document retries",
        "state": "open",
        "state_reason": None,
        "user": {"login": "octocat", "avatar_url": "unused"},
        "labels": [{"name": "docs", "color": "unused"}],
        "assignees": [{"login": "hubot"}],
        "body": "Add an example.",
        "comments": 2,
        "locked": False,
        "created_at": "2026-09-28T10:00:00Z",
        "updated_at": "2026-09-29T12:00:00Z",
        "html_url": "https://github.com/owner/mcp-oauth-sandbox/issues/12",
        "node_id": "unused",
        **overrides,
    }


@pytest.mark.asyncio
async def test_normalization_and_pr_filter(settings):
    cached_token(settings)
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[issue(pull_request={}), issue(user=None, body=None)])
        return httpx.Response(200, json=issue(user=None, body="x" * 8001))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GitHubClient(settings, http)
        listing = await client.list_issues("open", "updated", "desc", 5)
        assert listing["count"] == 1
        summary = listing["issues"][0]
        assert summary["issue_number"] == 12
        assert summary["author"] is None
        assert summary["labels"] == ["docs"]
        assert "body" not in summary and "node_id" not in summary
        detail = (await client.get_issue(12))["issue"]
        assert detail["body"] == "x" * 8000
        assert detail["body_truncated"] is True
        assert detail["assignees"] == ["hubot"]
        assert requests[0].url.params["per_page"] == "100"
        assert requests[0].headers["X-GitHub-Api-Version"] == "2026-03-10"


@pytest.mark.asyncio
async def test_null_body_and_preview_without_auth(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preview accessed authentication or the network")

    monkeypatch.setattr("week2.github_client.read_cache", forbidden)
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        preview = await GitHubClient(
            replace(settings, client_id="", client_secret=""), http
        ).add_issue_comment(12, "Preview")
        assert preview["status"] == "preview" and preview["body"] == "Preview"
        assert not settings.token_path.exists()
    monkeypatch.undo()
    cached_token(settings)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=issue(body=None)))
    ) as http:
        result = await GitHubClient(settings, http).get_issue(12)
        assert result["issue"]["body"] == ""
        assert result["issue"]["body_truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,headers,code,retryable",
    [
        (404, {}, "not_found", False),
        (403, {}, "forbidden", False),
        (422, {}, "github_rejected", False),
        (410, {}, "github_rejected", False),
        (503, {}, "github_unavailable", True),
        (429, {"Retry-After": "42"}, "rate_limited", True),
        (
            403,
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(time.time() + 120)},
            "rate_limited",
            True,
        ),
    ],
)
async def test_api_errors(settings, status, headers, code, retryable, caplog):
    cached_token(settings)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status, headers=headers, json={"message": "test-secret test-access test-refresh"}
            )
        )
    ) as http:
        with pytest.raises(ServiceError) as raised:
            await GitHubClient(settings, http).get_issue(999999)
    error = raised.value.error
    assert error["code"] == code and error["retryable"] is retryable
    assert error["http_status"] == status and error["action"]
    if status == 429:
        assert error["retry_after_seconds"] == 42
    for secret in ("test-secret", "test-access", "test-refresh"):
        assert secret not in str(raised.value) + json.dumps(error) + caplog.text


@pytest.mark.asyncio
async def test_pr_rejected_before_write(settings):
    cached_token(settings)
    methods = []

    def handle(request):
        methods.append(request.method)
        return httpx.Response(200, json=issue(pull_request={}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GitHubClient(settings, http)
        for operation in (client.get_issue(12), client.add_issue_comment(12, "Do not post", False)):
            with pytest.raises(ServiceError, match="Pull Request") as raised:
                await operation
            assert raised.value.error["code"] == "unsupported_target"
    assert methods == ["GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["created", "timeout", "5xx", "invalid_json", "missing_receipt"]
)
async def test_write_once_and_unknown_outcomes(settings, outcome):
    cached_token(settings)
    methods = []

    def handle(request):
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=issue())
        assert json.loads(request.content) == {"body": "An approved comment."}
        if outcome == "timeout":
            raise httpx.ReadTimeout("test-secret", request=request)
        if outcome == "5xx":
            return httpx.Response(503)
        if outcome == "invalid_json":
            return httpx.Response(201, text="invalid")
        if outcome == "missing_receipt":
            return httpx.Response(201, json={})
        return httpx.Response(
            201,
            json={
                "id": 123,
                "user": {"login": "octocat"},
                "created_at": "2026-09-29T12:05:00Z",
                "html_url": "https://github.com/owner/mcp-oauth-sandbox/issues/12#issuecomment-123",
                "body": "unused",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GitHubClient(settings, http)
        if outcome == "created":
            receipt = await client.add_issue_comment(12, "An approved comment.", False)
            assert receipt["status"] == "created" and receipt["comment_id"] == 123
            assert "body" not in receipt
        else:
            with pytest.raises(ServiceError) as raised:
                await client.add_issue_comment(12, "An approved comment.", False)
            assert raised.value.error["code"] == "comment_outcome_unknown"
            assert raised.value.error["retryable"] is False
    assert methods == ["GET", "POST"]


@pytest.mark.asyncio
async def test_refresh_before_expiry_and_concurrent_rotation(settings):
    cached_token(settings, expires_in=59)
    requests = []

    async def handle(request):
        requests.append(request)
        if request.url.host == "github.com":
            await asyncio.sleep(0)  # Let the other coroutine wait on the refresh lock.
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["refresh_token"]
            assert form["refresh_token"] == ["test-refresh"]
            return httpx.Response(200, json=token_response())
        assert request.headers["Authorization"] == "Bearer test-new-access"
        return httpx.Response(200, json=issue())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GitHubClient(settings, http)
        await asyncio.gather(client.get_issue(12), client.get_issue(12))
    assert len([request for request in requests if request.url.host == "github.com"]) == 1
    saved = read_cache(settings.token_path)
    assert saved.access_token == "test-new-access" and saved.refresh_token == "test-new-refresh"


@pytest.mark.asyncio
@pytest.mark.parametrize("second_status", [200, 401])
async def test_401_refresh_retry_bound(settings, second_status):
    cached_token(settings)
    api_tokens, refreshes = [], []

    def handle(request):
        if request.url.host == "github.com":
            refreshes.append(request)
            return httpx.Response(200, json=token_response())
        api_tokens.append(request.headers["Authorization"])
        return httpx.Response(401 if len(api_tokens) == 1 else second_status, json=issue())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        if second_status == 200:
            assert (await GitHubClient(settings, http).get_issue(12))["status"] == "ok"
        else:
            with pytest.raises(ServiceError) as raised:
                await GitHubClient(settings, http).get_issue(12)
            assert raised.value.error["code"] == "reauth_required"
    assert api_tokens == ["Bearer test-access", "Bearer test-new-access"]
    assert len(refreshes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,code",
    [
        ("invalid", "reauth_required"),
        ("expired", "reauth_required"),
        ("timeout", "auth_unavailable"),
        ("5xx", "auth_unavailable"),
        ("missing_secret", "configuration_error"),
    ],
)
async def test_refresh_failures_preserve_cache(settings, outcome, code):
    cached_token(settings, expires_in=1, refresh_expires_in=-1 if outcome == "expired" else 86400)
    original = settings.token_path.read_bytes()

    def handle(request):
        if outcome == "timeout":
            raise httpx.ReadTimeout("test-secret", request=request)
        if outcome == "5xx":
            return httpx.Response(503)
        return httpx.Response(
            200, json={"error": "bad_refresh_token", "error_description": "test-refresh"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        if outcome == "missing_secret":
            settings = replace(settings, client_secret="")
        with pytest.raises(ServiceError) as raised:
            await GitHubClient(settings, http).get_issue(12)
        assert raised.value.error["code"] == code
        assert settings.token_path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["state", "duplicate_state", "denied", "scope", "refresh", "lifetime", "identity"]
)
async def test_failed_auth_never_writes_cache(settings, problem):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/user":
            return httpx.Response(200, json={})
        payload = token_response()
        if problem == "scope":
            payload["scope"] = "user"
        if problem == "refresh":
            del payload["refresh_token"]
        if problem == "lifetime":
            payload["expires_in"] = -1
        return httpx.Response(200, json=payload)

    query = "code=test-code&state=expected"
    if problem == "state":
        query = "code=test-code&state=wrong"
    if problem == "duplicate_state":
        query += "&state=expected"
    if problem == "denied":
        query = "state=expected&error=access_denied"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ServiceError) as raised:
            await GitHubClient(settings, http).complete_auth(
                query, "expected", "test-verifier", "http://127.0.0.1:1234/oauth/callback"
            )
    assert not settings.token_path.exists()
    if problem in {"state", "duplicate_state", "denied"}:
        assert requests == []
    for secret in ("test-code", "test-verifier", "test-secret", "test-new-access"):
        assert secret not in str(raised.value)


@pytest.mark.asyncio
async def test_successful_code_exchange_and_private_atomic_cache(settings, monkeypatch):
    requests, replacements = [], []
    real_replace = os.replace

    def atomic(source, destination):
        assert os.stat(source).st_mode & 0o777 == 0o600
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr("week2.github_client.os.replace", atomic)

    def handle(request):
        requests.append(request)
        if request.url.path == "/user":
            assert request.headers["Authorization"] == "Bearer test-new-access"
            return httpx.Response(200, json={"login": "octocat"})
        form = parse_qs(request.content.decode())
        assert form["code"] == ["test-code"]
        assert form["code_verifier"] == ["test-verifier"]
        assert form["redirect_uri"] == ["http://127.0.0.1:1234/oauth/callback"]
        assert form["client_secret"] == ["test-secret"]
        return httpx.Response(200, json=token_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        login = await GitHubClient(settings, http).complete_auth(
            "code=test-code&state=expected",
            "expected",
            "test-verifier",
            "http://127.0.0.1:1234/oauth/callback",
        )
    assert login == "octocat" and len(requests) == 2
    assert len(replacements) == 1
    assert settings.token_path.stat().st_mode & 0o777 == 0o600
    assert settings.token_path.parent.stat().st_mode & 0o777 == 0o700
    assert read_cache(settings.token_path).login == "octocat"
    contents = settings.token_path.read_text()
    for secret in ("test-code", "test-verifier", "test-secret", "expected"):
        assert secret not in contents


@pytest.mark.parametrize(
    "problem", ["bad_json", "missing_field", "unsafe_file", "unsafe_directory", "symlink"]
)
def test_invalid_cache_rejected(settings, problem):
    cached_token(settings)
    if problem == "bad_json":
        settings.token_path.write_text("not json")
    elif problem == "missing_field":
        settings.token_path.write_text("{}")
    elif problem == "unsafe_file":
        settings.token_path.chmod(0o644)
    elif problem == "unsafe_directory":
        settings.token_path.parent.chmod(0o755)
    else:
        original = settings.token_path.with_suffix(".original")
        settings.token_path.rename(original)
        settings.token_path.symlink_to(original)
    with pytest.raises(ServiceError) as raised:
        read_cache(settings.token_path)
    assert raised.value.error["code"] == "reauth_required"


@pytest.mark.parametrize(
    "repository", ["", "owner/repo/extra", "https://github.com/owner/repo", "owner/..", "../repo"]
)
def test_repository_validation(monkeypatch, repository):
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    with pytest.raises(ServiceError) as raised:
        Settings.from_env()
    assert raised.value.error["code"] == "configuration_error"


@pytest.mark.asyncio
async def test_read_network_error_is_retryable(settings):
    cached_token(settings)

    def handle(request):
        raise httpx.ConnectError("test-secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ServiceError) as raised:
            await GitHubClient(settings, http).get_issue(12)
    assert raised.value.error["code"] == "network_error"
    assert raised.value.error["retryable"] is True
    assert "test-secret" not in str(raised.value)


@pytest.mark.asyncio
async def test_post_401_is_the_only_write_retry(settings):
    cached_token(settings)
    posts, refreshes = [], []

    def handle(request):
        if request.url.host == "github.com":
            refreshes.append(request)
            return httpx.Response(200, json=token_response())
        if request.method == "GET":
            return httpx.Response(200, json=issue())
        posts.append(request)
        if len(posts) == 1:
            return httpx.Response(401)
        return httpx.Response(
            201,
            json={
                "id": 123,
                "user": None,
                "created_at": "2026-09-29T12:05:00Z",
                "html_url": "https://github.com/owner/mcp-oauth-sandbox/issues/12#issuecomment-123",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await GitHubClient(settings, http).add_issue_comment(12, "Approved", False)
    assert result["status"] == "created" and result["author"] is None
    assert len(posts) == 2 and len(refreshes) == 1
    assert posts[0].headers["Authorization"] == "Bearer test-access"
    assert posts[1].headers["Authorization"] == "Bearer test-new-access"
    assert posts[0].content == posts[1].content


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "bad_state", "timeout"])
async def test_loopback_auth_and_timeout_cancellation(settings, monkeypatch, capsys, outcome):
    real_client = httpx.AsyncClient
    browser_tasks, api_requests, browser_replies = [], [], []
    authorize_query = None
    exchange_started = asyncio.Event()

    async def handle(request):
        api_requests.append(request)
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octocat"})
        form = parse_qs(request.content.decode())
        verifier = form["code_verifier"][0]
        actual_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert authorize_query["code_challenge"] == [actual_challenge]
        assert form["redirect_uri"] == authorize_query["redirect_uri"]
        exchange_started.set()
        if outcome == "timeout":
            await asyncio.Event().wait()  # Cancelled when auth's overall deadline expires.
        return httpx.Response(200, json=token_response())

    monkeypatch.setattr(
        "week2.github_client.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )

    async def simulated_browser(url):
        nonlocal authorize_query
        authorize_query = parse_qs(urlsplit(url).query)
        assert authorize_query["scope"] == ["public_repo"]
        assert authorize_query["code_challenge_method"] == ["S256"]
        redirect = urlsplit(authorize_query["redirect_uri"][0])
        assert redirect.hostname == "127.0.0.1"
        reader, writer = await asyncio.open_connection(redirect.hostname, redirect.port)
        state = "wrong" if outcome == "bad_state" else authorize_query["state"][0]
        query = urlencode({"code": "test-code", "state": state})
        writer.write(f"GET {redirect.path}?{query} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode())
        await writer.drain()
        browser_replies.append((await asyncio.wait_for(reader.read(), 2)).decode())
        writer.close()
        await writer.wait_closed()

    def open_browser(url):
        browser_tasks.append(asyncio.create_task(simulated_browser(url)))
        return True

    monkeypatch.setattr("week2.github_client.webbrowser.open", open_browser)
    if outcome == "success":
        await authorize(settings, timeout=1)
        assert read_cache(settings.token_path).login == "octocat"
    else:
        with pytest.raises(ServiceError) as raised:
            await authorize(settings, timeout=0.3)
        assert raised.value.error["code"] == "reauth_required"
        assert not settings.token_path.exists()
    await asyncio.wait_for(asyncio.gather(*browser_tasks), 2)
    if outcome == "bad_state":
        assert api_requests == []
    if outcome == "timeout":
        assert exchange_started.is_set()
        assert len(api_requests) == 1
    combined = "".join(browser_replies) + capsys.readouterr().err
    for secret in ("test-code", "test-secret", "test-new-access", authorize_query["state"][0]):
        assert secret not in combined
