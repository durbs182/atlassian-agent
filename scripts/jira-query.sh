#!/usr/bin/env bash
set -euo pipefail

cd /Users/pauldurbin/github/atlassian-agent

# Help text
show_help() {
    cat <<EOF
Usage: jira-query.sh [OPTIONS]

Fast direct-call interface for Jira queries (no task agent overhead).

OPTIONS:
  --mode MODE              Query mode: my-tickets, all-issues, search, read-issue, related-tickets, create-issue, doctor
                          (default: my-tickets)
  --issue-key KEY         Jira issue key (required for read-issue and related-tickets modes, e.g. MDP-7)
  --project-key KEY       Project key (required for create-issue mode, e.g. MDP)
  --issue-type TYPE       Issue type (required for create-issue mode, e.g. Idea, Bug, Task)
  --summary TEXT          Issue summary (required for create-issue mode)
  --description TEXT      Issue description (optional for create-issue mode)
  --priority LEVEL        Priority level (optional for create-issue mode: High, Medium, Low)
  --labels LABELS         Comma-separated labels (optional for create-issue mode)
  --jql QUERY             JQL query string (required for search mode)
  --max-results N         Maximum results to return (default: 100)
  --format FORMAT         Output format: json, summary, table (default: json)
                          - json: Full JSON response
                          - summary: Key fields only (compact, no descriptions)
  --allow-fallback        Allow fallback to search_jira_issues if primary fails
  --help                  Show this help message

EXAMPLES:
  # Get your unresolved tickets (fast)
  jira-query.sh --mode my-tickets

  # Get all Jira issues (compact format)
  jira-query.sh --mode all-issues --max-results 50 --format summary

  # Search with JQL (summary only)
  jira-query.sh --mode search --jql "assignee = currentUser()" --format summary

  # Get full details of a specific issue (summary format for large tickets)
  jira-query.sh --mode read-issue --issue-key MDP-7 --format summary

  # Get full details with all fields
  jira-query.sh --mode read-issue --issue-key MDP-7 --format json

  # Find related tickets (linked, epic, labels, components)
  jira-query.sh --mode related-tickets --issue-key MDP-8 --format summary

  # Create a new ticket (minimum fields)
  jira-query.sh --mode create-issue --project-key MDP --issue-type Bug --summary "Login button not responding"

  # Create a ticket with full details
  jira-query.sh --mode create-issue --project-key MDP --issue-type Task --summary "Add dark mode support" \
    --description "Implement dark mode toggle for improved UX" --priority High --labels "feature,ui"

  # Verify setup
  jira-query.sh --mode doctor

PERFORMANCE:
  - Direct calls: ~0.8-1.1s
  - 4x faster than task agent (which adds 3-5s overhead)
  - Use --format summary to avoid large output for tickets with big descriptions
EOF
}

# Format JSON output for summary display
format_summary() {
    local mode="$1"
    local json_output="$2"
    
    case "$mode" in
        read-issue)
            # Extract key fields from single issue
            echo "$json_output" | jq '.result.content[0].text | fromjson | {
                key,
                id,
                summary: .fields.summary,
                status: .fields.status,
                type: .fields.issueType,
                priority: .fields.priority,
                reporter: .fields.reporter,
                created: .fields.created,
                updated: .fields.updated,
                labels: .fields.labels,
                components: .fields.components
            }' 2>/dev/null
            ;;
        search|all-issues|my-tickets)
            # Extract key fields from search results
            echo "$json_output" | jq '.result.content[0].text | fromjson | {
                totalResults,
                issues: [.issues[] | {
                    key,
                    summary: .fields.summary,
                    status: .fields.status,
                    type: .fields.issueType,
                    priority: .fields.priority,
                    reporter: .fields.reporter,
                    created: .fields.created
                }]
            }' 2>/dev/null
            ;;
        *)
            # For other modes, just return as-is
            echo "$json_output"
            ;;
    esac
}

# Parse arguments
MODE="my-tickets"
JQL=""
ISSUE_KEY=""
PROJECT_KEY=""
ISSUE_TYPE=""
SUMMARY=""
DESCRIPTION=""
PRIORITY=""
LABELS=""
MAX_RESULTS=100
FORMAT="json"
ALLOW_FALLBACK=0
TIMEOUT=12

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --jql)
            JQL="$2"
            shift 2
            ;;
        --issue-key)
            ISSUE_KEY="$2"
            shift 2
            ;;
        --max-results)
            MAX_RESULTS="$2"
            shift 2
            ;;
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --project-key)
            PROJECT_KEY="$2"
            shift 2
            ;;
        --issue-type)
            ISSUE_TYPE="$2"
            shift 2
            ;;
        --summary)
            SUMMARY="$2"
            shift 2
            ;;
        --description)
            DESCRIPTION="$2"
            shift 2
            ;;
        --priority)
            PRIORITY="$2"
            shift 2
            ;;
        --labels)
            LABELS="$2"
            shift 2
            ;;
        --allow-fallback)
            ALLOW_FALLBACK=1
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help
            exit 1
            ;;
    esac
done

# Validate format
if [[ "$FORMAT" != "json" && "$FORMAT" != "summary" && "$FORMAT" != "table" ]]; then
    echo "Invalid format: $FORMAT (expected: json, summary, or table)" >&2
    exit 1
fi

# Activate venv and run
source .venv/bin/activate

case "$MODE" in
    doctor)
        python atlassian_mcp_client.py --mode doctor --timeout "$TIMEOUT"
        ;;
    my-tickets)
        FALLBACK_FLAG=""
        if [[ $ALLOW_FALLBACK -eq 1 ]]; then
            FALLBACK_FLAG="--allow-fallback"
        fi
        OUTPUT=$(python atlassian_mcp_client.py --mode jira-my-tickets --timeout "$TIMEOUT" $FALLBACK_FLAG)
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "my-tickets" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    all-issues)
        OUTPUT=$(python atlassian_mcp_client.py --mode jira-all-issues --timeout "$TIMEOUT" --max-results "$MAX_RESULTS")
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "all-issues" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    search)
        if [[ -z "$JQL" ]]; then
            echo "Error: --jql required for search mode" >&2
            exit 1
        fi
        OUTPUT=$(python atlassian_mcp_client.py --mode jira-search --timeout "$TIMEOUT" --jql "$JQL" --max-results "$MAX_RESULTS")
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "search" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    read-issue)
        if [[ -z "$ISSUE_KEY" ]]; then
            echo "Error: --issue-key required for read-issue mode (e.g., MDP-7)" >&2
            exit 1
        fi
        OUTPUT=$(python atlassian_mcp_client.py --mode jira-read-issue --timeout "$TIMEOUT" --issue-key "$ISSUE_KEY")
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "read-issue" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    related-tickets)
        if [[ -z "$ISSUE_KEY" ]]; then
            echo "Error: --issue-key required for related-tickets mode (e.g., MDP-8)" >&2
            exit 1
        fi
        OUTPUT=$(python atlassian_mcp_client.py --mode jira-related-tickets --timeout "$TIMEOUT" --issue-key "$ISSUE_KEY" --max-results "$MAX_RESULTS")
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "search" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    create-issue)
        if [[ -z "$PROJECT_KEY" ]]; then
            echo "Error: --project-key required for create-issue mode (e.g., MDP)" >&2
            exit 1
        fi
        if [[ -z "$ISSUE_TYPE" ]]; then
            echo "Error: --issue-type required for create-issue mode (e.g., Bug, Task, Idea)" >&2
            exit 1
        fi
        if [[ -z "$SUMMARY" ]]; then
            echo "Error: --summary required for create-issue mode" >&2
            exit 1
        fi
        CMD="python atlassian_mcp_client.py --mode jira-create-issue --timeout \"$TIMEOUT\" --project-key \"$PROJECT_KEY\" --issue-type \"$ISSUE_TYPE\" --summary \"$SUMMARY\""
        [[ -n "$DESCRIPTION" ]] && CMD="$CMD --description \"$DESCRIPTION\""
        [[ -n "$PRIORITY" ]] && CMD="$CMD --priority \"$PRIORITY\""
        [[ -n "$LABELS" ]] && CMD="$CMD --labels \"$LABELS\""
        OUTPUT=$(eval "$CMD")
        if [[ "$FORMAT" == "summary" ]]; then
            format_summary "create-issue" "$OUTPUT"
        else
            echo "$OUTPUT"
        fi
        ;;
    *)
        echo "Unknown mode: $MODE" >&2
        echo "Valid modes: my-tickets, all-issues, search, read-issue, related-tickets, create-issue, doctor" >&2
        exit 1
        ;;
esac
