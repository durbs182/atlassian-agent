# atlassian-expert (fast-path workflow)

**TL;DR for fast reads:** Use direct bash calls to scripts, NOT the task tool agent.

## 📊 Performance Comparison

| Method | Time | Overhead |
|--------|------|----------|
| Direct bash call | 0.8-1.1s | None |
| Task tool (agent) | 4-6s | 3-5s agent overhead |

**Recommendation:** Use direct bash for all Jira reads. Task tool adds 4-5x overhead!

---

## Confluence Coverage Runbook

Use the Confluence coverage plan when validating Confluence functionality end-to-end:

- `docs/CONFLUENCE-TEST-PLAN.md`
- MCP source used by this project: `https://github.com/durbs182/mcp-atlassian` (pinned via git submodule in `third_party/mcp-atlassian`)

---

## ⚡ Output Format Optimization

For tickets with large descriptions (like MDP-8 at 22.5 KB), use `--format summary` to get only essential fields:

```bash
# Large output (25 KB with full description)
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format json

# Compact output (~300 bytes, same speed)
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
```

**Summary format includes:**
- key, id, summary, status, type, priority, reporter, created, updated, labels, components
- **Excludes:** Full description, transitions (can still be queried separately if needed)

---

## Fast Path 1: Get My Jira Tickets (No Agent)

**Use this for speed:**
```bash
cd /Users/pauldurbin/github/atlassian-agent
./scripts/jira-query.sh --mode my-tickets

# Compact format for large results
./scripts/jira-query.sh --mode my-tickets --format summary
```

Expected time: ~0.8s (vs 4-5s with task agent)

**With fallback (if primary tool unavailable):**
```bash
./scripts/jira-query.sh --mode my-tickets --allow-fallback
```

---

## Fast Path 2: Get All Jira Issues

```bash
./scripts/jira-query.sh --mode all-issues --max-results 50 --format summary
```

---

## Fast Path 3: Search Jira with JQL

```bash
./scripts/jira-query.sh --mode search --jql "assignee = currentUser()" --format summary
```

---

## Fast Path 4: Get Full Issue Details

```bash
# Full details (use for analysis that needs complete info)
./scripts/jira-query.sh --mode read-issue --issue-key MDP-7

# Summary only (recommended for large tickets to avoid output bloat)
./scripts/jira-query.sh --mode read-issue --issue-key MDP-7 --format summary
```

---

## Fast Path 5: Find Related Tickets (NEW - 1.9x speedup)

**Why this matters:** Finding related tickets used to require 3 sequential API calls (~2.9s). Now it's optimized into 1 fast call (~1.5s).

```bash
# Find all tickets related to MDP-8 (same project, epic, labels, components)
./scripts/jira-query.sh --mode related-tickets --issue-key MDP-8

# Compact format (recommended)
./scripts/jira-query.sh --mode related-tickets --issue-key MDP-8 --format summary

# Limit results
./scripts/jira-query.sh --mode related-tickets --issue-key MDP-8 --max-results 25
```

**What it does:**
- Fetches issue metadata once (project, epic, labels, components, linked issues, subtasks)
- Builds smart JQL query: `project = MDP AND key != MDP-8`
- Returns all related tickets in same project
- Extracts linked issues and subtasks metadata

**Performance:** ~1.5s vs ~2.9s (manual workflow)

---

## Fast Path 6: Create a Jira Issue

**Create a simple ticket (required fields only):**
```bash
./scripts/jira-query.sh --mode create-issue \
  --project-key MDP \
  --issue-type Bug \
  --summary "Login button not responding"
```

**Create a ticket with full details:**
```bash
./scripts/jira-query.sh --mode create-issue \
  --project-key MDP \
  --issue-type Task \
  --summary "Add dark mode support" \
  --description "Implement dark mode toggle for improved UX" \
  --priority High \
  --labels "feature,ui"
```

**Parameters:**
- `--project-key` (required): Jira project key (e.g., MDP)
- `--issue-type` (required): Issue type (e.g., Bug, Task, Idea, Feature)
- `--summary` (required): Issue title/summary
- `--description` (optional): Detailed description
- `--priority` (optional): High, Medium, Low
- `--labels` (optional): Comma-separated labels

**Performance:** ~1.1s (direct MCP call, no agent overhead)

**Note:** Created issues are returned with their web URL for verification.

---

## Fast Path 7: Verify Setup (No Queries)

```bash
./scripts/jira-query.sh --mode doctor
```

This checks:
- ✅ Environment variables set
- ✅ MCP server reachable
- ✅ Required tools available
- ✅ No query executed

---

## Fast Path 8: Rename Confluence Space (First-Try Path)

Use the wrapper's dedicated rename mode so we hit the correct Confluence API path immediately.

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python atlassian_mcp_client.py \
  --mode confluence-rename-space \
  --space-key MFS \
  --space-name "team documents"
```

This mode intentionally uses the supported `/wiki/rest/api/space/{key}` update endpoint
and verifies the result via `/wiki/api/v2/spaces/{id}`.

---

## Old Method (Task Tool) - Avoid for Reads

**Do NOT use this for simple Jira reads:**
```bash
# ❌ SLOW (4-6s overhead from task tool)
task atlassian-expert "Get all Jira tickets"
```

**When to use task tool:**
- Complex multi-step operations requiring reasoning
- Need to correlate multiple Jira queries with other analysis
- Writing operations (create/update/comment)

For **reads only**, use direct bash.

---

## Preflight Setup (One-Time)

At session start, verify setup is working:
```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python atlassian_mcp_client.py --mode doctor --timeout 8
```

Expected output:
```json
{
  "mode": "doctor",
  "env": {
    "ATLASSIAN_BASE_URL": "set",
    "ATLASSIAN_EMAIL": "set",
    "ATLASSIAN_API_TOKEN": "set"
  },
  "ok": true,
  "server_name": "mcp-atlassian",
  "server_version": "x.y.z",
  "tool_count": 41,
  "recommended_tools": {
    "get_my_unresolved_issues": "present",
    "search_jira_issues": "present",
    "list_all_issues": "present",
    "read_jira_issue": "present"
  }
}
```

If `ok=false`, check:
- Missing env vars? Set `ATLASSIAN_BASE_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`
- MCP server not running? Error message will indicate why

---

## Direct Python MCP Client (Advanced)

For custom modes or debugging, call the Python client directly:

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate

# List all available tools
python atlassian_mcp_client.py --mode list-tools

# Get all issues (up to 100 by default)
python atlassian_mcp_client.py --mode jira-all-issues --max-results 50

# Search with JQL
python atlassian_mcp_client.py --mode jira-search --jql "assignee = currentUser()" --max-results 100

# Get my unresolved tickets
python atlassian_mcp_client.py --mode jira-my-tickets --timeout 15 --allow-fallback

# Read specific issue
python atlassian_mcp_client.py --mode jira-read-issue --issue-key MDP-7
```

Available modes:
- `doctor` — Validate env + server health
- `jira-my-tickets` — Get unresolved tickets assigned to current user
- `jira-all-issues` — Get all Jira issues (no filters)
- `jira-search` — Search with JQL query
- `jira-read-issue` — Read full details of specific issue
- `list-tools` — Inspect available MCP tools
- `agent` — Launch full MCP server for Copilot (don't use directly)

---

## Output Format Guide

### JSON Format (default)
- Full response with all fields
- Includes full descriptions, transitions, custom fields
- Best for: Analysis, integration with other tools, archiving

```bash
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format json
# Output: 25+ KB for large tickets
```

### Summary Format (recommended for large results)
- Essential fields only: key, summary, status, type, priority, reporter, dates, labels
- Compact output (~300 bytes per issue)
- Best for: Quick viewing, bulk results, avoiding output bloat
- **Same query speed** as full format

```bash
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
# Output: ~300 bytes (readable, clean)
```

---

## Retry Policy (Strict)

- **Tool not found:** 0 retries (check `doctor` output)
- **MCP execution error:** 0 automatic retries (check error message)
- **Transport timeout:** 1 retry max (increase `--timeout` if needed)

Default policy prevents slow retry loops.

---

## Scope Policy

- **"My tickets"** → Returns unresolved tickets by default
- **"All tickets"** → Returns ALL issues, any status
- **"Search"** → Custom JQL query

Only broaden scope if user explicitly asks.

---

## Write Policy

Read-only requests execute immediately.

Write operations require explicit confirmation before executing:
- Create issue
- Update issue
- Add comment
- Change status

Summarize exact action before executing.

---

## Environment Variables

Required for all queries:
```bash
export ATLASSIAN_BASE_URL="https://your-domain.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"  # From atlassian.com/manage/api-tokens
```

Check `.env.example` in the repo for template.

---

## Troubleshooting

### "MCP server not found" or connection errors
```bash
# Check if MCP server is running
ps aux | grep mcp-atlassian

# If not running, it should auto-start on first query
# If still fails, check Python venv:
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python -c "from mcp import ClientSession; print('MCP SDK OK')"
```

### "Tool not available" error
```bash
# Check which tools are available
./scripts/jira-query.sh --mode doctor

# Look at "recommended_tools" section in output
```

### Query timeout
```bash
# Increase timeout (default 12s for queries, 8s for doctor)
./scripts/jira-query.sh --mode all-issues --max-results 1000 --timeout 30

# Or via Python client:
python atlassian_mcp_client.py --mode jira-all-issues --timeout 30
```

### Large output causing display issues
```bash
# Use summary format instead of json
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary

# Or pipe to less/more for pagination
./scripts/jira-query.sh --mode all-issues --format json | less
```

---

## Performance Tips

1. **Use `--format summary`** — Reduces output bloat for tickets with large descriptions
2. **Use `--max-results` to limit data** — 100 results ~800ms, 1000 results ~2s
3. **Use search filters** — Specific JQL is faster than fetching all issues
4. **Avoid repeated queries** — Cache results if possible
5. **Use direct bash** — Never use task tool for reads (4-5x slower)

---

## Example Session

```bash
# 1. Verify setup (8-second timeout, includes MCP init)
./scripts/jira-query.sh --mode doctor

# 2. Get my tickets with summary format (reuses warm MCP session, ~1s)
./scripts/jira-query.sh --mode my-tickets --format summary

# 3. Search for critical issues (compact format)
./scripts/jira-query.sh --mode search --jql "priority = Highest" --format summary

# 4. Get first 50 all issues (summary only)
./scripts/jira-query.sh --mode all-issues --max-results 50 --format summary

# 5. Read specific issue (summary if it's large)
./scripts/jira-query.sh --mode read-issue --issue-key MDP-7 --format summary
```

Total time: ~6 seconds (vs ~25 seconds if using task tool 5x)


**Use this for speed:**
```bash
cd /Users/pauldurbin/github/atlassian-agent
./scripts/jira-query.sh --mode my-tickets
```

Expected time: ~0.8s (vs 4-5s with task agent)

**With fallback (if primary tool unavailable):**
```bash
./scripts/jira-query.sh --mode my-tickets --allow-fallback
```

---

## Fast Path 2: Get All Jira Issues

```bash
./scripts/jira-query.sh --mode all-issues --max-results 50
```

---

## Fast Path 3: Search Jira with JQL

```bash
./scripts/jira-query.sh --mode search --jql "assignee = currentUser()" --max-results 100
```

---

## Fast Path 4: Verify Setup (No Queries)

```bash
./scripts/jira-query.sh --mode doctor
```

This checks:
- ✅ Environment variables set
- ✅ MCP server reachable
- ✅ Required tools available
- ✅ No query executed

---

## Old Method (Task Tool) - Avoid for Reads

**Do NOT use this for simple Jira reads:**
```bash
# ❌ SLOW (4-6s overhead from task tool)
task atlassian-expert "Get all Jira tickets"
```

**When to use task tool:**
- Complex multi-step operations requiring reasoning
- Need to correlate multiple Jira queries with other analysis
- Writing operations (create/update/comment)

For **reads only**, use direct bash.

---

## Preflight Setup (One-Time)

At session start, verify setup is working:
```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python atlassian_mcp_client.py --mode doctor --timeout 8
```

Expected output:
```json
{
  "mode": "doctor",
  "env": {
    "ATLASSIAN_BASE_URL": "set",
    "ATLASSIAN_EMAIL": "set",
    "ATLASSIAN_API_TOKEN": "set"
  },
  "ok": true,
  "server_name": "mcp-atlassian",
  "server_version": "x.y.z",
  "tool_count": 15,
  "recommended_tools": {
    "get_my_unresolved_issues": "present",
    "search_jira_issues": "present",
    "list_all_issues": "present"
  }
}
```

If `ok=false`, check:
- Missing env vars? Set `ATLASSIAN_BASE_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`
- MCP server not running? Error message will indicate why

---

## Direct Python MCP Client (Advanced)

For custom modes or debugging, call the Python client directly:

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate

# List all available tools
python atlassian_mcp_client.py --mode list-tools

# Get all issues (up to 100 by default)
python atlassian_mcp_client.py --mode jira-all-issues --max-results 50

# Search with JQL
python atlassian_mcp_client.py --mode jira-search --jql "assignee = currentUser()" --max-results 100

# Get my unresolved tickets
python atlassian_mcp_client.py --mode jira-my-tickets --timeout 15 --allow-fallback
```

Available modes:
- `doctor` — Validate env + server health
- `jira-my-tickets` — Get unresolved tickets assigned to current user
- `jira-all-issues` — Get all Jira issues (no filters)
- `jira-search` — Search with JQL query
- `list-tools` — Inspect available MCP tools
- `agent` — Launch full MCP server for Copilot (don't use directly)

---

## Retry Policy (Strict)

- **Tool not found:** 0 retries (check `doctor` output)
- **MCP execution error:** 0 automatic retries (check error message)
- **Transport timeout:** 1 retry max (increase `--timeout` if needed)

Default policy prevents slow retry loops.

---

## Scope Policy

- **"My tickets"** → Returns unresolved tickets by default
- **"All tickets"** → Returns ALL issues, any status
- **"Search"** → Custom JQL query

Only broaden scope if user explicitly asks.

---

## Write Policy

Read-only requests execute immediately.

Write operations require explicit confirmation before executing:
- Create issue
- Update issue
- Add comment
- Change status

Summarize exact action before executing.

---

## Environment Variables

Required for all queries:
```bash
export ATLASSIAN_BASE_URL="https://your-domain.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"  # From atlassian.com/manage/api-tokens
```

Check `.env.example` in the repo for template.

---

## Troubleshooting

### "MCP server not found" or connection errors
```bash
# Check if MCP server is running
ps aux | grep mcp-atlassian

# If not running, it should auto-start on first query
# If still fails, check Python venv:
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python -c "from mcp import ClientSession; print('MCP SDK OK')"
```

### "Tool not available" error
```bash
# Check which tools are available
./scripts/jira-query.sh --mode doctor

# Look at "recommended_tools" section in output
```

### Query timeout
```bash
# Increase timeout (default 12s for queries, 8s for doctor)
./scripts/jira-query.sh --mode all-issues --max-results 1000 --timeout 30

# Or via Python client:
python atlassian_mcp_client.py --mode jira-all-issues --timeout 30
```

---

## Performance Tips

1. **Use `--max-results` to limit data** — 100 results ~800ms, 1000 results ~2s
2. **Use search filters** — Specific JQL is faster than fetching all issues
3. **Avoid repeated queries** — Cache results if possible
4. **Use direct bash** — Never use task tool for reads (4-5x slower)

---

## Example Session

```bash
# 1. Verify setup (8-second timeout, includes MCP init)
./scripts/jira-query.sh --mode doctor

# 2. Get my tickets (reuses warm MCP session, ~1s)
./scripts/jira-query.sh --mode my-tickets

# 3. Search for critical issues (JQL can be complex)
./scripts/jira-query.sh --mode search --jql "priority = Highest AND status != Done"

# 4. Get first 50 all issues
./scripts/jira-query.sh --mode all-issues --max-results 50

# 5. Find related tickets (~1.5s instead of manual ~2.9s)
./scripts/jira-query.sh --mode related-tickets --issue-key MDP-8 --format summary
```

Total time: ~5.5 seconds (vs ~20 seconds if using task tool 4x)

---

## Optimization Pattern: Multi-Step Queries

The `related-tickets` mode demonstrates a reusable pattern for optimizing multi-step Jira queries:

### Pattern: Metadata-Driven Search

**Problem:** Multi-step workflows cause N+1 API calls:
```
Step 1: Fetch primary resource        ~0.9s
Step 2: Extract metadata
Step 3: Fetch related resources       ~0.9s
Step 4: Fetch more related resources  ~0.9s
─────────────────────────────────
Total:                                ~2.9s ❌
```

**Solution:** Single optimized call with smart JQL:
```
Step 1: Fetch primary + extract metadata       ~0.9s
Step 2: Build JQL from metadata
Step 3: Single related search (smart JQL)      ~0.6s
─────────────────────────────────
Total:                                         ~1.5s ✅
```

**Key Insight:** Extract metadata in Python (no extra round trip), build smart JQL, execute once.

### Future Optimization Candidates

Apply this pattern to:
- `--mode issue-hierarchy` — Find issues in same epic/parent
- `--mode team-board` — Find all issues assigned to team members
- `--mode sprint-velocity` — Analyze all tickets in sprint with velocity data
- `--mode component-health` — Find all issues in component with status breakdown

### Why This Works

1. **Metadata stays local** — Extract in Python, don't round-trip to server
2. **Smart JQL** — Build queries based on actual data (epic, labels, components)
3. **Avoid N+1** — One primary fetch + one related search instead of three separate calls
4. **Format locally** — Use bash wrapper's format_summary() (no server formatting)
5. **Cache-friendly** — Metadata extracted once, reused for multiple queries if needed
