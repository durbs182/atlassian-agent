# Setup Guide - Atlassian Agent

## Prerequisites

- Python 3.10+
- Node.js 16+
- Atlassian Jira account with API token

## Step 1: Environment Variables

Set your Atlassian credentials:

```bash
export ATLASSIAN_BASE_URL="https://your-instance.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"
```

Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens

## Step 2: Virtual Environment

```bash
cd /Users/pauldurbin/github/atlassian-agent
python3 -m venv .venv
source .venv/bin/activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt 2>/dev/null || pip install mcp
npm install
```

## Step 4: Verify Setup

```bash
./scripts/jira-query.sh --mode doctor
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
  "server_version": "3.0.0",
  "protocol_version": "2025-06-18",
  "tool_count": 41,
  "recommended_tools": {
    "get_my_unresolved_issues": "present",
    "read_jira_issue": "present",
    "search_jira_issues": "present"
  }
}
```

## Step 5: Test Basic Query

```bash
./scripts/jira-query.sh --mode my-tickets --format summary
```

Should show your unresolved Jira tickets.

## Troubleshooting

### "Command not found: jira-query.sh"
```bash
# Make sure you're in the repo directory
cd /Users/pauldurbin/github/atlassian-agent
chmod +x scripts/jira-query.sh
./scripts/jira-query.sh --help
```

### "env: python: No such file or directory"
```bash
# Use python3 instead
python3 atlassian_mcp_client.py --mode doctor
```

### "ATLASSIAN_BASE_URL not set"
```bash
# Check environment variables
echo $ATLASSIAN_BASE_URL
# If empty, set them:
export ATLASSIAN_BASE_URL="https://your-instance.atlassian.net"
export ATLASSIAN_EMAIL="your-email@example.com"
export ATLASSIAN_API_TOKEN="your-api-token"
```

### "MCP server not reachable"
```bash
# Verify Node.js is installed
node --version

# Check if MCP server is running
ps aux | grep mcp-atlassian

# The wrapper will start it automatically on first use
```

### "Unbounded JQL queries are not allowed"
This is a Jira API requirement. Always add a project filter:
```bash
# ✅ Correct
./scripts/jira-query.sh --mode search --jql "project = MDP AND type = Bug"

# ❌ Wrong - missing project filter
./scripts/jira-query.sh --mode search --jql "type = Bug"
```

## Development

### Project Structure
```
.
├── README.md                         # User documentation
├── SETUP.md                          # This file
├── atlassian-expert.instructions.md  # Agent guidance
├── atlassian_mcp_client.py          # Python MCP wrapper
├── scripts/
│   ├── jira-query.sh               # Main CLI interface
│   ├── get-my-jira-tickets.sh      # Deprecated - use jira-query.sh
│   └── atlassian-doctor.sh         # Deprecated - use jira-query.sh --mode doctor
├── third_party/
│   └── mcp-atlassian/              # MCP Atlassian server (external)
└── package.json                     # Node dependencies
```

### Adding New Query Modes

1. Add async function in `atlassian_mcp_client.py`:
```python
async def run_jira_my_new_mode(command, args, timeout_seconds):
    # Implementation here
    pass
```

2. Register in argparser:
```python
parser.add_argument(
    "--mode",
    choices=["list-tools", "doctor", "jira-my-new-mode"],
)
```

3. Add handler in main():
```python
if args.mode == "jira-my-new-mode":
    return asyncio.run(run_jira_my_new_mode(...))
```

4. Add to bash wrapper in `scripts/jira-query.sh`:
```bash
my-new-mode)
    OUTPUT=$(python atlassian_mcp_client.py --mode jira-my-new-mode ...)
    ...
    ;;
```

### Performance Testing

Time a query:
```bash
time ./scripts/jira-query.sh --mode my-tickets
```

Expected: 0.8-1.1 seconds

Compare with task agent (should be 4-6 seconds):
```bash
time task atlassian-expert "Get all my Jira tickets"
```

## Integration with Copilot Agent

The agent uses the `atlassian-expert.instructions.md` file for guidance. Key features:

- **Fast Paths**: Direct bash calls for specific query patterns
- **Optimization Patterns**: Multi-step query workflows
- **Performance Comparison**: When to use direct vs task agent

See `atlassian-expert.instructions.md` for full agent integration guide.

## API Limits

Jira Cloud has rate limits:
- 600 requests per minute per user
- 2,000 requests per minute per IP for service accounts

The wrapper is fast enough to stay within limits for normal usage.

## Security

- Never commit `.env` files with credentials
- API tokens are sensitive - treat like passwords
- Use environment variables, not command-line args
- Consider using `.env` files locally (add to .gitignore)

## Support

See README.md for more information and examples.
