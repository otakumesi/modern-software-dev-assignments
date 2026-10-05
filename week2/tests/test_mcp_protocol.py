"""Exercise initialize, tools/list and tools/call through an actual stdio process."""

import json
import sys
from pathlib import Path

import jsonschema
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_stdio_contract_and_offline_preview(tmp_path):
    cache = tmp_path / "unused-cache" / "token.json"
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "week2.github_mcp", "serve"],
        cwd=str(ROOT),
        env={
            "GITHUB_REPOSITORY": "owner/mcp-oauth-sandbox",
            "GITHUB_MCP_TOKEN_PATH": str(cache),
            "GITHUB_CLIENT_ID": "",
            "GITHUB_CLIENT_SECRET": "",
        },
        keep_alive=False,
    )
    async with Client(transport, mode="legacy") as client:
        initialized = await client.initialize()
        assert "explicit user approval" in initialized.instructions
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert set(tools) == {
            "list_issues",
            "get_issue",
            "preview_issue_comment",
            "add_issue_comment",
        }
        for tool in tools.values():
            assert tool.description and "issue_number" in tool.description
            assert tool.output_schema
            assert "ctx" not in tool.input_schema["properties"]
        for name in ("list_issues", "get_issue", "add_issue_comment"):
            assert tools[name].annotations.open_world_hint is True
        assert tools["preview_issue_comment"].annotations.open_world_hint is False
        listing = tools["list_issues"].input_schema["properties"]
        assert listing["state"]["enum"] == ["open", "closed", "all"]
        assert listing["state"]["default"] == "open"
        assert listing["sort"]["enum"] == ["created", "updated", "comments"]
        assert listing["sort"]["default"] == "updated"
        assert listing["direction"]["enum"] == ["asc", "desc"]
        assert listing["direction"]["default"] == "desc"
        assert listing["limit"]["minimum"] == 1
        assert listing["limit"]["maximum"] == 30
        assert listing["limit"]["default"] == 10
        for name in ("get_issue", "preview_issue_comment", "add_issue_comment"):
            assert tools[name].input_schema["properties"]["issue_number"]["minimum"] == 1
        for name in ("preview_issue_comment", "add_issue_comment"):
            fields = tools[name].input_schema["properties"]
            assert set(fields) == {"issue_number", "body"}  # No dry_run switch on either tool.
            assert fields["body"]["minLength"] == 1
            assert fields["body"]["maxLength"] == 5000
        comment = tools["add_issue_comment"]
        assert comment.annotations.read_only_hint is False
        assert comment.annotations.destructive_hint is False
        assert comment.annotations.idempotent_hint is False
        for name in ("list_issues", "get_issue", "preview_issue_comment"):
            assert tools[name].annotations.read_only_hint is True

        async def post(issue_number, body):
            result = await client.call_tool(
                "add_issue_comment", {"issue_number": issue_number, "body": body}
            )
            jsonschema.validate(result.structured_content, comment.output_schema)
            return result.structured_content

        unpreviewed = await post(3, "On it.")
        assert unpreviewed["status"] == "error"
        assert unpreviewed["error"]["code"] == "preview_required"
        assert unpreviewed["error"]["retryable"] is False
        assert "preview_issue_comment" in unpreviewed["error"]["action"]

        result = await client.call_tool(
            "preview_issue_comment", {"issue_number": 12, "body": "A safe preview."}
        )
        assert result.is_error is False
        jsonschema.validate(result.structured_content, tools["preview_issue_comment"].output_schema)
        assert result.structured_content == {
            "status": "preview",
            "repository": "owner/mcp-oauth-sandbox",
            "issue_number": 12,
            "body": "A safe preview.",
            "target_url": "https://github.com/owner/mcp-oauth-sandbox/issues/12",
            "next_step": (
                "Nothing was posted. Show this exact body to the user and stop. "
                "Call add_issue_comment with the same issue_number and body only after the "
                "user explicitly approves this preview."
            ),
        }
        assert not cache.parent.exists()
        for issue_number, body in ((12, "A different body."), (13, "A safe preview.")):
            mismatch = await post(issue_number, body)
            assert mismatch["error"]["code"] == "preview_required"
        assert not cache.parent.exists()  # Rejected posts never reach auth or HTTP.

        # A matching preview passes the gate (then fails on missing credentials) and is consumed.
        approved = await post(12, "A safe preview.")
        assert approved["error"]["code"] == "configuration_error"
        assert (await post(12, "A safe preview."))["error"]["code"] == "preview_required"

        for name, arguments in (
            ("list_issues", {"limit": 31}),
            ("list_issues", {"sort": "stars"}),
            ("get_issue", {"issue_number": 0}),
            ("preview_issue_comment", {"issue_number": 12, "body": ""}),
            ("add_issue_comment", {"issue_number": 12, "body": "x" * 5001}),
            ("add_issue_comment", {"issue_number": 12, "body": "A", "dry_run": False}),
        ):
            invalid = await client.call_tool(name, arguments, raise_on_error=False)
            assert invalid.is_error is True
        missing = await client.call_tool("get_issue", {"issue_number": 12})
        assert missing.is_error is False  # Known operational failures are data.
        assert missing.structured_content["status"] == "error"
        assert missing.structured_content["error"]["code"] == "configuration_error"
        jsonschema.validate(missing.structured_content, tools["get_issue"].output_schema)
        assert "auth" in json.dumps(missing.structured_content).lower()


@pytest.mark.asyncio
async def test_missing_cache_returns_auth_command(tmp_path):
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "week2.github_mcp", "serve"],
        cwd=str(ROOT),
        env={
            "GITHUB_REPOSITORY": "owner/mcp-oauth-sandbox",
            "GITHUB_MCP_TOKEN_PATH": str(tmp_path / "absent" / "token.json"),
            "GITHUB_CLIENT_ID": "test-client-id",
            "GITHUB_CLIENT_SECRET": "",
        },
        keep_alive=False,
    )
    async with Client(transport, mode="legacy") as client:
        result = await client.call_tool("list_issues", {})
        error = result.structured_content["error"]
        assert error["code"] == "auth_required"
        assert error["retryable"] is False
        assert "uv run python -m week2.github_mcp auth" in error["action"]
