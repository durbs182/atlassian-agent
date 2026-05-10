#!/usr/bin/env python3
"""
MCP client for the Atlassian remote server at https://mcp.atlassian.com/v1/mcp.

Uses Streamable HTTP transport with the MCP SDK's built-in OAuth 2.0 PKCE flow,
exactly as Claude Code does. On first run it opens a browser for Atlassian login
and caches the token in ~/.atlassian_mcp_token.json for subsequent runs.

No environment variables are required for OAuth auth. Optionally set:
  MCP_SERVER_URL       — Override server URL (default: https://mcp.atlassian.com/v1/mcp)
  ATLASSIAN_TOKEN      — Skip OAuth and use this Bearer token directly (for CI/testing)
  ATLASSIAN_TOKEN_FILE — Override token cache path
                         (default: ~/.atlassian_mcp_token.json)

For confluence-rename-space mode (direct REST API), additionally set:
  ATLASSIAN_BASE_URL   — e.g. https://yourorg.atlassian.net
  ATLASSIAN_EMAIL      — your Atlassian account email
  ATLASSIAN_API_TOKEN  — Atlassian API token (from id.atlassian.com/manage-profile/security/api-tokens)
"""

import argparse
import asyncio
import base64
import http.server
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

DEFAULT_SERVER_URL = "https://mcp.atlassian.com/v1/mcp"
DEFAULT_TOKEN_FILE = Path.home() / ".atlassian_mcp_token.json"
OAUTH_CALLBACK_PORT = 8484
OAUTH_CALLBACK_PATH = "/oauth/callback"
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_CALLBACK_PORT}{OAUTH_CALLBACK_PATH}"

TOOL_TEAMWORK_CONTEXT = "getTeamworkGraphContext"
TOOL_TEAMWORK_OBJECT = "getTeamworkGraphObject"
TOOL_SEARCH_JIRA = "searchJiraIssuesUsingJql"
TOOL_GET_JIRA_ISSUE = "getJiraIssue"
TOOL_CREATE_JIRA_ISSUE = "createJiraIssue"


# ── Token storage ─────────────────────────────────────────────────────────────

def _token_file() -> Path:
    return Path(os.getenv("ATLASSIAN_TOKEN_FILE", str(DEFAULT_TOKEN_FILE)))


class FileTokenStorage:
    """Persist OAuth tokens and client registration to a local JSON file."""

    def __init__(self, path: Path):
        self._path = path
        self._data: dict = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2))

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._data.get("tokens")
        if raw:
            return OAuthToken.model_validate(raw)
        return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._data.get("client_info")
        if raw:
            return OAuthClientInformationFull.model_validate(raw)
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        self._save()


# ── OAuth browser + callback ──────────────────────────────────────────────────

def _run_callback_server() -> tuple[str, str | None]:
    """
    Start a one-shot local HTTP server, wait for the OAuth redirect,
    and return (code, state). Blocks until the callback arrives.
    """
    result: dict = {}
    ready = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silence access log

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != OAUTH_CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = dict(urllib.parse.parse_qsl(parsed.query))
            result["code"] = params.get("code", "")
            result["state"] = params.get("state")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication complete.</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
            ready.set()

    server = http.server.HTTPServer(("localhost", OAUTH_CALLBACK_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ready.wait(timeout=300)
    server.shutdown()
    return result.get("code", ""), result.get("state")


async def _open_browser(url: str) -> None:
    print(f"\nOpening browser for Atlassian login...\n  {url}\n", file=sys.stderr)
    webbrowser.open(url)


async def _wait_for_callback() -> tuple[str, str | None]:
    print(
        f"Waiting for OAuth callback on http://localhost:{OAUTH_CALLBACK_PORT}{OAUTH_CALLBACK_PATH} ...",
        file=sys.stderr,
    )
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_callback_server)


# ── Session factory ───────────────────────────────────────────────────────────

def _server_url() -> str:
    return os.getenv("MCP_SERVER_URL", DEFAULT_SERVER_URL)


def _build_auth() -> OAuthClientProvider | None:
    """Return an OAuthClientProvider using cached tokens, or None if a static token is set."""
    if os.getenv("ATLASSIAN_TOKEN"):
        return None  # caller will set Authorization header directly

    storage = FileTokenStorage(_token_file())
    client_metadata = OAuthClientMetadata(
        redirect_uris=[OAUTH_REDIRECT_URI],  # type: ignore[arg-type]
        client_name="atlassian-remote-mcp-client",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    return OAuthClientProvider(
        server_url=_server_url(),
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_open_browser,
        callback_handler=_wait_for_callback,
        timeout=300.0,
    )


@asynccontextmanager
async def _session(timeout_seconds: float):
    url = _server_url()
    static_token = os.getenv("ATLASSIAN_TOKEN")

    if static_token:
        headers = {"Authorization": f"Bearer {static_token}"}
        auth = None
    else:
        headers = None
        auth = _build_auth()

    async with streamablehttp_client(url, headers=headers, auth=auth) as (read, write, _):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout_seconds)
            yield session


# ── Direct Confluence REST API ────────────────────────────────────────────────

def _confluence_request(
    method: str, path: str, timeout_seconds: float, body: dict | None = None
) -> dict:
    base_url = os.getenv("ATLASSIAN_BASE_URL", "").rstrip("/")
    email = os.getenv("ATLASSIAN_EMAIL", "")
    api_token = os.getenv("ATLASSIAN_API_TOKEN", "")
    auth = base64.b64encode(f"{email}:{api_token}".encode()).decode("ascii")
    headers = {"Accept": "application/json", "Authorization": f"Basic {auth}"}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode()
    request = urllib.request.Request(
        url=f"{base_url}{path}", data=payload, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(
            f"Confluence API {method} {path} failed with status {exc.code}: {detail}"
        ) from exc


def run_confluence_rename_space(
    space_key: str, space_name: str, timeout_seconds: float
) -> int:
    try:
        encoded_key = urllib.parse.quote(space_key, safe="")
        spaces = _confluence_request(
            "GET", f"/wiki/api/v2/spaces?keys={encoded_key}", timeout_seconds
        )
        results = spaces.get("results", [])
        if not results:
            print(
                json.dumps(
                    {"mode": "confluence-rename-space", "space_key": space_key,
                     "error": f"Space not found for key: {space_key}"},
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1

        current = results[0]
        current_name = current.get("name", "")
        space_type = current.get("type", "global")
        space_id = str(current.get("id", ""))

        if current_name == space_name:
            print(json.dumps(
                {"mode": "confluence-rename-space", "space_key": space_key,
                 "space_id": space_id, "old_name": current_name,
                 "new_name": space_name, "unchanged": True,
                 "message": "Space already has the requested name."},
                indent=2,
            ))
            return 0

        _confluence_request(
            "PUT",
            f"/wiki/rest/api/space/{encoded_key}",
            timeout_seconds,
            body={"key": space_key, "name": space_name, "type": space_type},
        )
        verified = _confluence_request(
            "GET", f"/wiki/api/v2/spaces/{space_id}", timeout_seconds
        )
        verified_name = verified.get("name", "")
        ok = verified_name == space_name
        print(json.dumps(
            {"mode": "confluence-rename-space", "space_key": space_key,
             "space_id": space_id, "old_name": current_name,
             "new_name": verified_name, "requested_name": space_name,
             "updated": ok},
            indent=2,
        ))
        return 0 if ok else 1
    except Exception as exc:
        print(json.dumps(
            {"mode": "confluence-rename-space", "space_key": space_key,
             "requested_name": space_name, "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# ── MCP modes ─────────────────────────────────────────────────────────────────

async def run_list_tools(timeout_seconds: float) -> int:
    try:
        async with _session(timeout_seconds) as session:
            tools_result = await asyncio.wait_for(
                session.list_tools(), timeout=timeout_seconds
            )
            print(json.dumps(
                {"transport": "http", "server_url": _server_url(),
                 "tool_count": len(tools_result.tools),
                 "tool_names": [t.name for t in tools_result.tools]},
                indent=2,
            ))
            return 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "server_url": _server_url(), "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


async def run_doctor(timeout_seconds: float) -> int:
    token_cache = _token_file()
    diagnosis: dict = {
        "mode": "doctor",
        "server_url": _server_url(),
        "auth": (
            "static-token (ATLASSIAN_TOKEN)"
            if os.getenv("ATLASSIAN_TOKEN")
            else f"oauth (cache: {token_cache})"
        ),
        "token_cache_exists": token_cache.exists(),
        "ok": False,
    }
    try:
        async with _session(timeout_seconds) as session:
            tools_result = await asyncio.wait_for(
                session.list_tools(), timeout=timeout_seconds
            )
            tool_names = {t.name for t in tools_result.tools}
            has_jira = TOOL_SEARCH_JIRA in tool_names
            diagnosis.update({
                "ok": True,
                "tool_count": len(tools_result.tools),
                "auth_scope": "oauth-full" if has_jira else "api-token-limited",
                "available_tools": {
                    TOOL_TEAMWORK_CONTEXT: "present" if TOOL_TEAMWORK_CONTEXT in tool_names else "missing",
                    TOOL_TEAMWORK_OBJECT: "present" if TOOL_TEAMWORK_OBJECT in tool_names else "missing",
                    TOOL_SEARCH_JIRA: "present" if has_jira else "missing (needs OAuth token)",
                    TOOL_GET_JIRA_ISSUE: "present" if TOOL_GET_JIRA_ISSUE in tool_names else "missing (needs OAuth token)",
                    TOOL_CREATE_JIRA_ISSUE: "present" if TOOL_CREATE_JIRA_ISSUE in tool_names else "missing (needs OAuth token)",
                },
            })
    except Exception as exc:
        diagnosis["error"] = str(exc)
    print(json.dumps(diagnosis, indent=2))
    return 0 if diagnosis["ok"] else 1


async def run_jira_my_tickets(timeout_seconds: float) -> int:
    jql = "assignee = currentUser() AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
    try:
        async with _session(timeout_seconds) as session:
            result = await asyncio.wait_for(
                session.call_tool(TOOL_SEARCH_JIRA, {"jql": jql, "maxResults": 100}),
                timeout=timeout_seconds,
            )
            result_dict = _jsonable(result)
            print(json.dumps(
                {"transport": "http", "mode": "jira-my-tickets",
                 "server_url": _server_url(), "jql": jql, "result": result_dict},
                indent=2,
            ))
            return 1 if result_dict.get("isError") else 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "mode": "jira-my-tickets",
             "server_url": _server_url(), "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


async def run_jira_all_issues(timeout_seconds: float, max_results: int) -> int:
    jql = "ORDER BY created DESC"
    try:
        async with _session(timeout_seconds) as session:
            result = await asyncio.wait_for(
                session.call_tool(TOOL_SEARCH_JIRA, {"jql": jql, "maxResults": max_results}),
                timeout=timeout_seconds,
            )
            result_dict = _jsonable(result)
            print(json.dumps(
                {"transport": "http", "mode": "jira-all-issues",
                 "server_url": _server_url(), "max_results": max_results,
                 "result": result_dict},
                indent=2,
            ))
            return 1 if result_dict.get("isError") else 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "mode": "jira-all-issues",
             "server_url": _server_url(), "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


async def run_jira_search(timeout_seconds: float, jql: str, max_results: int) -> int:
    try:
        async with _session(timeout_seconds) as session:
            result = await asyncio.wait_for(
                session.call_tool(TOOL_SEARCH_JIRA, {"jql": jql, "maxResults": max_results}),
                timeout=timeout_seconds,
            )
            result_dict = _jsonable(result)
            print(json.dumps(
                {"transport": "http", "mode": "jira-search",
                 "server_url": _server_url(), "jql": jql,
                 "max_results": max_results, "result": result_dict},
                indent=2,
            ))
            return 1 if result_dict.get("isError") else 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "mode": "jira-search",
             "server_url": _server_url(), "jql": jql, "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


async def run_jira_read_issue(timeout_seconds: float, issue_key: str) -> int:
    try:
        async with _session(timeout_seconds) as session:
            result = await asyncio.wait_for(
                session.call_tool(TOOL_GET_JIRA_ISSUE, {"issueKey": issue_key}),
                timeout=timeout_seconds,
            )
            result_dict = _jsonable(result)
            print(json.dumps(
                {"transport": "http", "mode": "jira-read-issue",
                 "server_url": _server_url(), "issue_key": issue_key,
                 "result": result_dict},
                indent=2,
            ))
            return 1 if result_dict.get("isError") else 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "mode": "jira-read-issue",
             "server_url": _server_url(), "issue_key": issue_key, "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


async def run_jira_create_issue(
    timeout_seconds: float, project_key: str, issue_type: str, summary: str,
    description: str, priority: str, assignee: str,
    labels: list | None, components: list | None,
) -> int:
    try:
        async with _session(timeout_seconds) as session:
            tool_args: dict = {
                "projectKey": project_key,
                "issueType": issue_type,
                "summary": summary,
            }
            if description:
                tool_args["description"] = description
            if priority:
                tool_args["priority"] = priority
            if assignee:
                tool_args["assignee"] = assignee
            if labels:
                tool_args["labels"] = labels
            if components:
                tool_args["components"] = components

            result = await asyncio.wait_for(
                session.call_tool(TOOL_CREATE_JIRA_ISSUE, tool_args),
                timeout=timeout_seconds,
            )
            result_dict = _jsonable(result)
            print(json.dumps(
                {"transport": "http", "mode": "jira-create-issue",
                 "server_url": _server_url(), "project_key": project_key,
                 "issue_type": issue_type, "summary": summary,
                 "result": result_dict},
                indent=2,
            ))
            return 1 if result_dict.get("isError") else 0
    except Exception as exc:
        print(json.dumps(
            {"transport": "http", "mode": "jira-create-issue",
             "server_url": _server_url(), "error": str(exc)},
            indent=2,
        ), file=sys.stderr)
        return 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"MCP client for {DEFAULT_SERVER_URL}.\n"
            "On first run, opens a browser for Atlassian OAuth login.\n"
            "Token is cached in ~/.atlassian_mcp_token.json for future runs.\n"
            "Set ATLASSIAN_TOKEN to bypass OAuth with a static Bearer token."
        )
    )
    parser.add_argument(
        "--mode",
        choices=[
            "list-tools", "doctor",
            "jira-my-tickets", "jira-all-issues", "jira-search",
            "jira-read-issue", "jira-create-issue",
            "confluence-rename-space",
        ],
        default="list-tools",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--jql", type=str, default="")
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--issue-key", type=str, default="")
    parser.add_argument("--project-key", type=str, default="")
    parser.add_argument("--issue-type", type=str, default="")
    parser.add_argument("--summary", type=str, default="")
    parser.add_argument("--description", type=str, default="")
    parser.add_argument("--priority", type=str, default="")
    parser.add_argument("--assignee", type=str, default="")
    parser.add_argument("--labels", type=str, default="")
    parser.add_argument("--components", type=str, default="")
    parser.add_argument("--space-key", type=str, default="")
    parser.add_argument("--space-name", type=str, default="")
    args = parser.parse_args()

    if args.mode == "list-tools":
        return asyncio.run(run_list_tools(args.timeout))
    if args.mode == "doctor":
        return asyncio.run(run_doctor(args.timeout))
    if args.mode == "jira-my-tickets":
        return asyncio.run(run_jira_my_tickets(args.timeout))
    if args.mode == "jira-all-issues":
        return asyncio.run(run_jira_all_issues(args.timeout, args.max_results))
    if args.mode == "jira-search":
        if not args.jql:
            print(json.dumps({"error": "--jql required for jira-search mode"}, indent=2), file=sys.stderr)
            return 1
        return asyncio.run(run_jira_search(args.timeout, args.jql, args.max_results))
    if args.mode == "jira-read-issue":
        if not args.issue_key:
            print(json.dumps({"error": "--issue-key required (e.g. PROJ-7)"}, indent=2), file=sys.stderr)
            return 1
        return asyncio.run(run_jira_read_issue(args.timeout, args.issue_key))
    if args.mode == "jira-create-issue":
        if not args.project_key or not args.issue_type or not args.summary:
            print(json.dumps(
                {"error": "--project-key, --issue-type, and --summary required",
                 "example": "python atlassian_remote_mcp_client.py --mode jira-create-issue "
                            "--project-key PROJ --issue-type Task --summary 'New task'"},
                indent=2,
            ), file=sys.stderr)
            return 1
        labels = [lbl.strip() for lbl in args.labels.split(",") if lbl.strip()] if args.labels else None
        components = [c.strip() for c in args.components.split(",") if c.strip()] if args.components else None
        return asyncio.run(run_jira_create_issue(
            args.timeout, args.project_key, args.issue_type, args.summary,
            args.description, args.priority, args.assignee, labels, components,
        ))
    if args.mode == "confluence-rename-space":
        if not args.space_key or not args.space_name:
            print(json.dumps(
                {"error": "--space-key and --space-name required",
                 "example": "python atlassian_remote_mcp_client.py --mode confluence-rename-space "
                            "--space-key MFS --space-name 'Team Documents'"},
                indent=2,
            ), file=sys.stderr)
            return 1
        return run_confluence_rename_space(args.space_key, args.space_name, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
