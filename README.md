# Atlassian Agent - Fast Jira Query Interface

A high-performance Jira query wrapper built on the MCP (Model Context Protocol) Atlassian server. Provides direct-call access to Jira operations without task agent overhead (5.5x faster than traditional task agent approaches).

## Quick Start

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
./scripts/jira-query.sh --mode my-tickets
```

## Performance

| Method | Time | Overhead |
|--------|------|----------|
| Direct bash call | 0.8-1.1s | None |
| Task tool (agent) | 4-6s | 3-5s agent overhead |

**5.5x faster** than task agent for all Jira reads.

## Features

### Query Modes

1. **my-tickets** - Get your unresolved issues
   ```bash
   ./scripts/jira-query.sh --mode my-tickets --format summary
   ```

2. **all-issues** - List all Jira issues (MDP project)
   ```bash
   ./scripts/jira-query.sh --mode all-issues --max-results 10
   ```

3. **read-issue** - Get full details of a specific ticket
   ```bash
   ./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
   ```

4. **search** - Custom JQL queries
   ```bash
   ./scripts/jira-query.sh --mode search --jql "project = MDP AND type = Bug" --max-results 5
   ```

5. **related-tickets** - Find linked, epic, label, and component matches
   ```bash
   ./scripts/jira-query.sh --mode related-tickets --issue-key MDP-8 --format summary
   ```

6. **create-issue** - Create new Jira tickets
   ```bash
   ./scripts/jira-query.sh --mode create-issue \
     --project-key MDP \
     --issue-type Bug \
     --summary "Login button not responding" \
     --priority High \
     --labels "urgent,backend"
   ```

### Output Formats

- **json** (default): Full JSON response
- **summary**: Key fields only (compact, ~300 bytes vs 25 KB for full output)
- **table**: Formatted table view

```bash
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 16+
- npm package manager
- Atlassian Jira account with API token
- MCP Atlassian Server (included, see below)

### Step 1: Clone This Repository

```bash
git clone https://github.com/durbs182/atlassian-agent.git
cd atlassian-agent
```

### Step 2: Set Up Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install mcp
```

### Step 3: Install MCP Server

The MCP Atlassian Server is required to communicate with Jira. It's available at https://github.com/pauldurbin/mcp-server.

**Option A: Use existing MCP server (if already installed)**

If you already have the MCP server at `/Users/pauldurbin/github/mcp-server` or another location, ensure it's built:

```bash
cd /path/to/mcp-server
npm install
npm run build
```

**Option B: Clone and install MCP server**

```bash
# Clone MCP server (parallel to this repo)
cd ..
git clone https://github.com/pauldurbin/mcp-server.git
cd mcp-server

# Install and build
npm install
npm run build

# Verify the build
ls -la build/index.js
```

**Server location:** The script expects the MCP server at `../mcp-server` relative to this repo, or uses the environment variable `MCP_ATLASSIAN_PATH` if set:

```bash
export MCP_ATLASSIAN_PATH="/your/path/to/mcp-server"
```

### Step 4: Configure Environment Variables

```bash
# Jira Cloud credentials
export ATLASSIAN_BASE_URL="https://your-domain.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"

# Optional: MCP server path (if not in ../mcp-server)
export MCP_ATLASSIAN_PATH="/your/path/to/mcp-server"
```

**Get your API token:** https://id.atlassian.com/manage-profile/security/api-tokens

### Step 5: Verify Setup

```bash
./scripts/jira-query.sh --mode doctor
```

Expected output shows:
- ✅ Environment variables set
- ✅ MCP server reachable
- ✅ 40+ Jira tools available
- ✅ Required tools (get_my_unresolved_issues, read_jira_issue, search_jira_issues) present

### Step 6: Test a Query

```bash
./scripts/jira-query.sh --mode my-tickets --format summary
```

If you see your Jira tickets, you're all set!

## Architecture

### How It Works

```
User Command
    ↓
jira-query.sh (bash wrapper)
    ↓
atlassian_mcp_client.py (Python MCP client)
    ↓
MCP Atlassian Server (Node.js/stdio)
    ↓
Jira REST API (Cloud)
```

### MCP Server

The **Model Context Protocol (MCP)** Atlassian Server is the bridge between this wrapper and Jira.

- **Repository:** https://github.com/pauldurbin/mcp-server
- **Transport:** stdio (subprocess communication)
- **Tools:** 40+ Jira tools including issue CRUD, search, transitions, comments
- **Auto-started:** Launched automatically by `atlassian_mcp_client.py` on first use
- **State management:** Maintains MCP session across calls for performance

The wrapper uses direct stdio communication instead of going through a task agent, which eliminates 3-5 seconds of overhead per query.

### Direct Call Benefits

- **No task agent overhead** - Direct stdio communication with MCP server
- **Fast initialization** - MCP server keeps state across calls
- **Output formatting local** - Summary format doesn't affect query performance
- **Scalable** - Handles large descriptions efficiently
- **Reliable** - Standard MCP protocol ensures compatibility

## Files

- `atlassian_mcp_client.py` - Python wrapper for MCP server communication
- `scripts/jira-query.sh` - User-facing CLI interface
- `atlassian-expert.instructions.md` - Agent guidance documentation

## Usage Examples

### Get Unresolved Tickets
```bash
./scripts/jira-query.sh --mode my-tickets --format summary
```

### Find All Bugs in Project
```bash
./scripts/jira-query.sh --mode search \
  --jql "project = MDP AND type = Bug" \
  --max-results 20 \
  --format summary
```

### Create Issue with Full Details
```bash
./scripts/jira-query.sh --mode create-issue \
  --project-key MDP \
  --issue-type Task \
  --summary "Add dark mode support" \
  --description "Implement dark mode toggle for improved UX" \
  --priority High \
  --labels "feature,ui"
```

### Get Related Tickets (Linked Issues)
```bash
./scripts/jira-query.sh --mode related-tickets \
  --issue-key MDP-8 \
  --format summary
```

## Performance Tips

1. **Use summary format for large tickets**
   ```bash
   # Compact: ~300 bytes, same speed
   ./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
   
   # Full: ~25 KB
   ./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format json
   ```

2. **Limit results for searches**
   ```bash
   # Fast: returns first 10
   ./scripts/jira-query.sh --mode search --jql "project = MDP" --max-results 10
   ```

3. **Use direct bash, not task agent**
   ```bash
   # ✅ FAST (0.8-1.1s)
   ./scripts/jira-query.sh --mode my-tickets
   
   # ❌ SLOW (4-6s)
   task atlassian-expert "Get all Jira tickets"
   ```

## Troubleshooting

### "Unbounded JQL queries are not allowed"
Make sure to add a restrictive clause to your JQL:
```bash
# ❌ Wrong
./scripts/jira-query.sh --mode search --jql "type = Bug"

# ✅ Correct
./scripts/jira-query.sh --mode search --jql "project = MDP AND type = Bug"
```

### Large Output Issues
Use summary format to reduce output:
```bash
./scripts/jira-query.sh --mode read-issue --issue-key MDP-8 --format summary
```

### Connection Issues
Verify setup:
```bash
./scripts/jira-query.sh --mode doctor
```

Check environment variables are set:
```bash
echo $ATLASSIAN_BASE_URL
echo $ATLASSIAN_EMAIL
echo $ATLASSIAN_API_TOKEN
```

## Help

```bash
./scripts/jira-query.sh --help
```

## Agent Integration

For Copilot Agent use, see `atlassian-expert.instructions.md` for:
- Fast Path guides
- Optimization patterns
- Multi-step query workflows
- When to use task agent vs direct bash

## License

Internal tool for Atlassian API integration.

## Support

For issues or questions, check:
1. Help text: `./scripts/jira-query.sh --help`
2. Doctor mode: `./scripts/jira-query.sh --mode doctor`
3. Instructions: `cat atlassian-expert.instructions.md`
