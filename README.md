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
- Atlassian Jira account with API token
- MCP Atlassian Server (see below)

### Install MCP Server

The MCP Atlassian Server is required to communicate with Jira. Clone and install it:

```bash
# Clone the MCP server repository
cd /Users/pauldurbin/github
git clone https://github.com/pauldurbin/mcp-server.git
cd mcp-server

# Install dependencies
npm install

# Build the project
npm run build

# The server will be started automatically by atlassian_mcp_client.py
# To run manually for testing:
node build/index.js http &
```

**Server location:** `/Users/pauldurbin/github/mcp-server`

The wrapper will automatically start the MCP server on first use. You can verify it's running:

```bash
ps aux | grep "mcp-atlassian\|index.js"
```

### Configure Environment Variables

```bash
export ATLASSIAN_BASE_URL="https://your-instance.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"
```

Get your API token: https://id.atlassian.com/manage-profile/security/api-tokens

### Verify Setup

```bash
./scripts/jira-query.sh --mode doctor
```

Expected output shows:
- ✅ Environment variables set
- ✅ MCP server reachable
- ✅ Required tools available

## Architecture

```
User Command
    ↓
jira-query.sh (bash wrapper)
    ↓
atlassian_mcp_client.py (Python MCP client)
    ↓
MCP Atlassian Server (Node.js)
    ↓
Jira REST API
```

### Direct Call Benefits

- **No task agent overhead** - Direct stdio communication with MCP server
- **Fast initialization** - MCP server keeps state across calls
- **Output formatting local** - Summary format doesn't affect query performance
- **Scalable** - Handles large descriptions efficiently

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
