#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REQUIRED_ENV_VARS = (
    "ATLASSIAN_BASE_URL",
    "ATLASSIAN_EMAIL",
    "ATLASSIAN_API_TOKEN",
)


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    # Keep server logs off stdout so MCP JSON-RPC frames parse cleanly.
    env.setdefault("NODE_ENV", "production")
    env.setdefault("LOG_LEVEL", "error")
    return env


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _missing_env_vars() -> list[str]:
    return [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]


def _print_missing_env_error(command: str, args: list[str]) -> None:
    missing = _missing_env_vars()
    print(
        json.dumps(
            {
                "transport": "stdio",
                "command": command,
                "args": args,
                "error": "Missing required environment variables.",
                "missing_env_vars": missing,
                "hint": "Set ATLASSIAN_BASE_URL, ATLASSIAN_EMAIL, and ATLASSIAN_API_TOKEN.",
            },
            indent=2,
        ),
        file=sys.stderr,
    )


async def _inspect_server(
    command: str, args: list[str], timeout_seconds: float
):
    env = build_env()
    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await asyncio.wait_for(
                session.initialize(), timeout=timeout_seconds
            )
            tools_result = await asyncio.wait_for(
                session.list_tools(), timeout=timeout_seconds
            )
            return init_result, tools_result


async def run(command: str, args: list[str], timeout_seconds: float) -> int:
    try:
        init_result, tools_result = await _inspect_server(
            command, args, timeout_seconds
        )
        response = {
            "transport": "stdio",
            "command": command,
            "args": args,
            "protocol_version": init_result.protocolVersion,
            "server_name": init_result.serverInfo.name,
            "server_version": init_result.serverInfo.version,
            "tool_count": len(tools_result.tools),
            "tool_names": [tool.name for tool in tools_result.tools],
        }
        print(json.dumps(response, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "command": command,
                    "args": args,
                    "error": str(exc),
                    "hint": "Set ATLASSIAN_BASE_URL, ATLASSIAN_EMAIL, and ATLASSIAN_API_TOKEN.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_doctor(command: str, args: list[str], timeout_seconds: float) -> int:
    missing = _missing_env_vars()
    diagnosis = {
        "mode": "doctor",
        "env": {name: ("set" if name not in missing else "missing") for name in REQUIRED_ENV_VARS},
        "ok": False,
    }
    if missing:
        diagnosis["error"] = "Missing required environment variables."
        print(json.dumps(diagnosis, indent=2))
        return 2

    try:
        init_result, tools_result = await _inspect_server(
            command, args, timeout_seconds
        )
        tool_names = {tool.name for tool in tools_result.tools}
        diagnosis.update(
            {
                "ok": True,
                "server_name": init_result.serverInfo.name,
                "server_version": init_result.serverInfo.version,
                "protocol_version": init_result.protocolVersion,
                "tool_count": len(tools_result.tools),
                "recommended_tools": {
                    "get_my_unresolved_issues": "present"
                    if "get_my_unresolved_issues" in tool_names
                    else "missing",
                    "read_jira_issue": "present"
                    if "read_jira_issue" in tool_names
                    else "missing",
                    "search_jira_issues": "present"
                    if "search_jira_issues" in tool_names
                    else "missing",
                },
            }
        )
        print(json.dumps(diagnosis, indent=2))
        return 0
    except Exception as exc:
        diagnosis["error"] = str(exc)
        print(json.dumps(diagnosis, indent=2))
        return 1


async def run_jira_my_tickets(
    command: str, args: list[str], timeout_seconds: float, allow_fallback: bool
) -> int:
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                primary_tool = "get_my_unresolved_issues"
                fallback = None
                tool_used = primary_tool
                attempts = 1
                all_failed = False

                if primary_tool in available_tools:
                    call_result = await asyncio.wait_for(
                        session.call_tool(primary_tool, {}), timeout=timeout_seconds
                    )
                    call_result_dict = _jsonable(call_result)
                    all_failed = bool(call_result_dict.get("isError"))
                else:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Required tool not available: {primary_tool}",
                            }
                        ],
                    }
                    all_failed = True

                if (
                    all_failed
                    and allow_fallback
                    and primary_tool not in available_tools
                    and "search_jira_issues" in available_tools
                ):
                    attempts += 1
                    tool_used = "search_jira_issues"
                    fallback_jql = "assignee = currentUser() ORDER BY priority DESC, updated DESC"
                    fallback_result = await asyncio.wait_for(
                        session.call_tool(
                            "search_jira_issues",
                            {"jql": fallback_jql, "maxResults": 100},
                        ),
                        timeout=timeout_seconds,
                    )
                    fallback_result_dict = _jsonable(fallback_result)
                    fallback = {
                        "applied": True,
                        "tool_used": "search_jira_issues",
                        "jql": fallback_jql,
                        "result": fallback_result_dict,
                    }
                    all_failed = bool(fallback_result_dict.get("isError"))
                elif all_failed:
                    fallback = {
                        "applied": False,
                        "reason": (
                            "disabled by default to avoid slow retry loops; "
                            "rerun with --allow-fallback to enable one fallback call "
                            "when primary tool is missing"
                        ),
                    }

                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-my-tickets",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "tool_used": tool_used,
                            "attempts": attempts,
                            "result": call_result_dict,
                            "fallback": fallback,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-my-tickets",
                    "command": command,
                    "args": args,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_jira_all_issues(
    command: str, args: list[str], timeout_seconds: float, max_results: int = 100
) -> int:
    """Get all Jira issues without filters (fast mode)."""
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                # Try primary tool first, then fallback to search
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                
                call_result_dict = None
                tool_used = None
                
                if "list_all_issues" in available_tools:
                    tool_used = "list_all_issues"
                    call_result = await asyncio.wait_for(
                        session.call_tool(
                            "list_all_issues",
                            {"maxResults": max_results}
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(call_result)
                elif "search_jira_issues" in available_tools:
                    tool_used = "search_jira_issues"
                    call_result = await asyncio.wait_for(
                        session.call_tool(
                            "search_jira_issues",
                            {"jql": "project = MDP ORDER BY created DESC", "maxResults": max_results}
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(call_result)
                else:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "No tool available: list_all_issues or search_jira_issues required",
                            }
                        ],
                    }
                    tool_used = "none"
                
                all_failed = bool(call_result_dict.get("isError"))
                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-all-issues",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "tool_used": tool_used,
                            "max_results": max_results,
                            "result": call_result_dict,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-all-issues",
                    "command": command,
                    "args": args,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_jira_search(
    command: str, args: list[str], timeout_seconds: float, jql: str, max_results: int = 100
) -> int:
    """Search Jira issues with JQL query (fast mode)."""
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                
                if "search_jira_issues" not in available_tools:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Required tool not available: search_jira_issues",
                            }
                        ],
                    }
                else:
                    call_result = await asyncio.wait_for(
                        session.call_tool(
                            "search_jira_issues",
                            {"jql": jql, "maxResults": max_results}
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(call_result)
                
                all_failed = bool(call_result_dict.get("isError"))
                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-search",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "jql": jql,
                            "max_results": max_results,
                            "result": call_result_dict,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-search",
                    "command": command,
                    "args": args,
                    "jql": jql,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_jira_read_issue(
    command: str, args: list[str], timeout_seconds: float, issue_key: str
) -> int:
    """Read full details of a specific Jira issue (fast mode)."""
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                
                if "read_jira_issue" not in available_tools:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Required tool not available: read_jira_issue",
                            }
                        ],
                    }
                else:
                    call_result = await asyncio.wait_for(
                        session.call_tool(
                            "read_jira_issue",
                            {"issueKey": issue_key}
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(call_result)
                
                all_failed = bool(call_result_dict.get("isError"))
                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-read-issue",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "issue_key": issue_key,
                            "result": call_result_dict,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-read-issue",
                    "command": command,
                    "args": args,
                    "issue_key": issue_key,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_jira_related_tickets(
    command: str, args: list[str], timeout_seconds: float, issue_key: str, max_results: int = 50
) -> int:
    """Find all related tickets (linked issues, subtasks, shared epic/labels/components)."""
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                
                # First, get the issue details using read_jira_issue
                if "read_jira_issue" not in available_tools:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Required tool not available: read_jira_issue",
                            }
                        ],
                    }
                    print(
                        json.dumps(
                            {
                                "transport": "stdio",
                                "mode": "jira-related-tickets",
                                "issue_key": issue_key,
                                "result": call_result_dict,
                            },
                            indent=2,
                        )
                    )
                    return 1
                
                # Get issue details using read_jira_issue
                issue_result = await asyncio.wait_for(
                    session.call_tool(
                        "read_jira_issue",
                        {"issueKey": issue_key}
                    ),
                    timeout=timeout_seconds,
                )
                issue_dict = _jsonable(issue_result)
                
                if issue_dict.get("isError"):
                    print(
                        json.dumps(
                            {
                                "transport": "stdio",
                                "mode": "jira-related-tickets",
                                "issue_key": issue_key,
                                "result": issue_dict,
                            },
                            indent=2,
                        )
                    )
                    return 1
                
                # Extract useful metadata from read_jira_issue response
                issue_data = issue_dict.get("content", [{}])[0] if issue_dict.get("content") else {}
                if isinstance(issue_data, dict) and "text" in issue_data:
                    try:
                        issue_data = json.loads(issue_data["text"])
                    except (json.JSONDecodeError, TypeError):
                        issue_data = {}
                
                fields = issue_data.get("fields", {})
                project_key = issue_data.get("key", issue_key).split("-")[0] if issue_data.get("key") else issue_key.split("-")[0]
                
                # Build JQL queries to find related tickets
                related_queries = [
                    f'project = {project_key} AND key != {issue_key} ORDER BY updated DESC'  # All in project
                ]
                
                # Add epic-based query if present
                epic = fields.get("epic")
                if epic:
                    epic_key = epic.get("key") if isinstance(epic, dict) else epic
                    if epic_key:
                        related_queries.append(f'epic = {epic_key} AND key != {issue_key}')
                
                # Add label-based query if present
                labels = fields.get("labels", [])
                if labels:
                    label_query = " OR ".join([f'labels = {label}' for label in labels if label])
                    if label_query:
                        related_queries.append(f'({label_query}) AND key != {issue_key}')
                
                # Add component-based query if present
                components = fields.get("components", [])
                if components:
                    component_names = [
                        c.get("name") for c in components if isinstance(c, dict) and c.get("name")
                    ]
                    if component_names:
                        comp_query = " OR ".join([f'component = "{c}"' for c in component_names])
                        if comp_query:
                            related_queries.append(f'({comp_query}) AND key != {issue_key}')
                
                # Execute the primary query (all in project) to find related tickets
                primary_jql = related_queries[0]
                
                if "search_jira_issues" not in available_tools:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Required tool not available: search_jira_issues",
                            }
                        ],
                    }
                else:
                    search_result = await asyncio.wait_for(
                        session.call_tool(
                            "search_jira_issues",
                            {"jql": primary_jql, "maxResults": max_results}
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(search_result)
                
                # Extract linked issues and subtasks from the original issue
                linked_issues = fields.get("issuelinks", [])
                subtasks = fields.get("subtasks", [])
                
                all_failed = bool(call_result_dict.get("isError"))
                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-related-tickets",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "issue_key": issue_key,
                            "project_key": project_key,
                            "linked_issues_count": len(linked_issues),
                            "subtasks_count": len(subtasks),
                            "related_queries": len(related_queries),
                            "result": call_result_dict,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-related-tickets",
                    "command": command,
                    "args": args,
                    "issue_key": issue_key,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


async def run_jira_create_issue(
    command: str, args: list[str], timeout_seconds: float, 
    project_key: str, issue_type: str, summary: str,
    description: str = "", priority: str = "", assignee: str = "",
    labels: list = None, components: list = None
) -> int:
    """Create a new Jira issue."""
    try:
        env = build_env()
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await asyncio.wait_for(
                    session.initialize(), timeout=timeout_seconds
                )
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout_seconds
                )
                available_tools = {tool.name for tool in tools_result.tools}
                
                if "create_jira_issue" not in available_tools:
                    call_result_dict = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Required tool not available: create_jira_issue",
                            }
                        ],
                    }
                else:
                    # Build tool arguments
                    tool_args = {
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
                    
                    create_result = await asyncio.wait_for(
                        session.call_tool(
                            "create_jira_issue",
                            tool_args
                        ),
                        timeout=timeout_seconds,
                    )
                    call_result_dict = _jsonable(create_result)
                
                all_failed = bool(call_result_dict.get("isError"))
                print(
                    json.dumps(
                        {
                            "transport": "stdio",
                            "mode": "jira-create-issue",
                            "server_name": init_result.serverInfo.name,
                            "server_version": init_result.serverInfo.version,
                            "project_key": project_key,
                            "issue_type": issue_type,
                            "summary": summary,
                            "result": call_result_dict,
                        },
                        indent=2,
                    )
                )
                return 1 if all_failed else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "transport": "stdio",
                    "mode": "jira-create-issue",
                    "command": command,
                    "args": args,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


def run_agent_mode(command: str, args: list[str]) -> int:
    if _missing_env_vars():
        _print_missing_env_error(command, args)
        return 2
    env = build_env()
    os.execvpe(command, [command, *args], env)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or launch mcp-atlassian via this Python wrapper."
    )
    parser.add_argument(
        "--mode",
        choices=["list-tools", "doctor", "jira-my-tickets", "jira-all-issues", "jira-search", "jira-read-issue", "jira-related-tickets", "jira-create-issue", "agent"],
        default="list-tools",
        help=(
            "'list-tools' inspects toolset. "
            "'doctor' validates env + server health. "
            "'jira-my-tickets' calls get_my_unresolved_issues directly. "
            "'jira-all-issues' fetches all Jira issues. "
            "'jira-search' searches issues with JQL query. "
            "'jira-read-issue' reads full details of a specific issue. "
            "'jira-related-tickets' finds related tickets (linked, epic, labels, components). "
            "'jira-create-issue' creates a new Jira issue. "
            "'agent' execs mcp-atlassian for Copilot."
        ),
    )
    parser.add_argument(
        "--command",
        default="node",
        help="Command to launch MCP server.",
    )
    parser.add_argument(
        "--args",
        nargs="*",
        default=["third_party/mcp-atlassian/dist/index.js"],
        help="Command args to launch MCP server.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Timeout in seconds for MCP initialize/list/call operations.",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help=(
            "Allow one fallback from get_my_unresolved_issues to search_jira_issues "
            "when the primary tool is unavailable."
        ),
    )
    parser.add_argument(
        "--jql",
        type=str,
        default="",
        help="JQL query string for jira-search mode.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of results to return (default: 100).",
    )
    parser.add_argument(
        "--issue-key",
        type=str,
        default="",
        help="Jira issue key (e.g. MDP-7) for jira-read-issue mode.",
    )
    parser.add_argument(
        "--project-key",
        type=str,
        default="",
        help="Project key (e.g., MDP) for jira-create-issue mode.",
    )
    parser.add_argument(
        "--issue-type",
        type=str,
        default="",
        help="Issue type (e.g., Idea, Bug, Task) for jira-create-issue mode.",
    )
    parser.add_argument(
        "--summary",
        type=str,
        default="",
        help="Issue summary/title for jira-create-issue mode.",
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Issue description for jira-create-issue mode.",
    )
    parser.add_argument(
        "--priority",
        type=str,
        default="",
        help="Priority (e.g., High, Medium, Low) for jira-create-issue mode.",
    )
    parser.add_argument(
        "--assignee",
        type=str,
        default="",
        help="Assignee account ID for jira-create-issue mode.",
    )
    parser.add_argument(
        "--labels",
        type=str,
        default="",
        help="Comma-separated labels for jira-create-issue mode.",
    )
    parser.add_argument(
        "--components",
        type=str,
        default="",
        help="Comma-separated components for jira-create-issue mode.",
    )
    args = parser.parse_args()
    if args.mode == "agent":
        return run_agent_mode(args.command, args.args)
    if _missing_env_vars():
        _print_missing_env_error(args.command, args.args)
        return 2
    if args.mode == "doctor":
        return asyncio.run(run_doctor(args.command, args.args, args.timeout))
    if args.mode == "jira-my-tickets":
        return asyncio.run(
            run_jira_my_tickets(
                args.command, args.args, args.timeout, args.allow_fallback
            )
        )
    if args.mode == "jira-all-issues":
        return asyncio.run(
            run_jira_all_issues(
                args.command, args.args, args.timeout, args.max_results
            )
        )
    if args.mode == "jira-search":
        if not args.jql:
            print(
                json.dumps(
                    {
                        "error": "--jql query required for jira-search mode",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        return asyncio.run(
            run_jira_search(
                args.command, args.args, args.timeout, args.jql, args.max_results
            )
        )
    if args.mode == "jira-read-issue":
        if not args.issue_key:
            print(
                json.dumps(
                    {
                        "error": "--issue-key required for jira-read-issue mode (e.g., MDP-7)",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        return asyncio.run(
            run_jira_read_issue(
                args.command, args.args, args.timeout, args.issue_key
            )
        )
    if args.mode == "jira-related-tickets":
        if not args.issue_key:
            print(
                json.dumps(
                    {
                        "error": "--issue-key required for jira-related-tickets mode (e.g., MDP-8)",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        return asyncio.run(
            run_jira_related_tickets(
                args.command, args.args, args.timeout, args.issue_key, args.max_results
            )
        )
    if args.mode == "jira-create-issue":
        if not args.project_key or not args.issue_type or not args.summary:
            print(
                json.dumps(
                    {
                        "error": "--project-key, --issue-type, and --summary required for jira-create-issue mode",
                        "example": "python atlassian_mcp_client.py --mode jira-create-issue --project-key MDP --issue-type Idea --summary 'New feature'",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        
        # Parse comma-separated labels and components
        labels = [l.strip() for l in args.labels.split(",") if l.strip()] if args.labels else None
        components = [c.strip() for c in args.components.split(",") if c.strip()] if args.components else None
        
        return asyncio.run(
            run_jira_create_issue(
                args.command,
                args.args,
                args.timeout,
                args.project_key,
                args.issue_type,
                args.summary,
                args.description,
                args.priority,
                args.assignee,
                labels,
                components,
            )
        )
    return asyncio.run(run(args.command, args.args, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
