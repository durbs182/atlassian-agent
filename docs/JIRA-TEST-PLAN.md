# Jira Coverage Test Plan for `atlassian-expert`

This plan defines how to validate Jira functionality coverage for the `atlassian-expert` workflow using the local MCP wrapper:

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python atlassian_mcp_client.py --mode list-tools
python atlassian_mcp_client.py --mode agent
```

## 1. Objectives

1. Validate end-to-end Jira coverage across read and write flows exposed by wrapper + MCP tools.
2. Align coverage to Atlassian Jira Cloud REST documentation groups.
3. Provide a repeatable smoke/full/negative runbook with explicit pass/fail gates.
4. Standardize evidence capture for regressions and release readiness.

## 2. Atlassian Documentation Baseline

Use these references as the behavioral baseline:

- Jira REST API v3 intro: https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
- Issue search (JQL): https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
- Issues: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/
- Issue comments: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/
- Issue transitions: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-post
- Projects: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/
- Boards/Sprints (Agile): https://developer.atlassian.com/cloud/jira/software/rest/
- Users: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-users/
- Worklogs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-worklogs/

## 3. Current Jira Surface in This Repo

### Wrapper-level Jira modes
- `jira-my-tickets`
- `jira-all-issues`
- `jira-search`
- `jira-read-issue`
- `jira-related-tickets`
- `jira-create-issue`

### MCP Jira tool families (coverage domains)
- Issue lifecycle: create/read/update/search/list
- Comments and transitions
- Projects, boards, sprints
- User-centric issue activity
- Worklogs and user work reporting

## 4. Test Fixtures

Use run-scoped fixtures per execution:

- **Run tag:** `jr-test-YYYYMMDD-HHMM`
- **Project key:** dedicated non-production test project (recommended)
- **Issue types:** `Task`, `Bug`
- **Labels:** `jr-test`, `jr-coverage`, `<run-tag>`
- **Seed issue summary:** `JR TEST ROOT <run-tag>`
- **Comment text:** `JR test comment <run-tag>`
- **Transition target:** one valid workflow transition (e.g., To Do → In Progress)
- **User fixtures:** current user + optional secondary test user

Cleanup policy:
- Mark all generated issues with run-tag label.
- Transition generated issues to a terminal state (`Done`/`Closed`) at run end.
- Never modify or transition non-run-tagged issues.

## 5. Execution Phases

## Phase A — Smoke (must pass every run)

1. Environment + tool availability
2. Project access/read
3. Create issue
4. Read issue
5. Search/list issue by JQL
6. Add comment
7. Perform transition and verify status

## Phase B — Full functional coverage

1. Related-ticket workflow (project + epic/labels/components)
2. My tickets/all issues/search variants
3. Issue update variants (fields, labels/components)
4. User-centric issue/activity views
5. Board and sprint read paths
6. Worklog retrieval and aggregation

## Phase C — Negative and robustness

1. Missing required arguments
2. Invalid issue keys and IDs
3. Invalid transition IDs / transition not allowed
4. Invalid JQL / unbounded JQL handling
5. Pagination boundary violations
6. Permission-denied operations

## 6. Coverage Matrix

| Domain | Wrapper / MCP tools | Atlassian docs group | Core assertions |
|---|---|---|---|
| Environment/tooling | `doctor`, `list-tools` | REST intro | Required env/toolset is present and callable |
| Issue lifecycle | `jira-create-issue`, `jira-read-issue`, search/list tools | Issues + Search | Created issue is retrievable; key fields round-trip; version/status coherent |
| Search + listing | `jira-search`, `jira-all-issues`, `jira-my-tickets` | Issue search | Correct JQL filtering, pagination behavior, and bounded query handling |
| Related tickets | `jira-related-tickets` | Search + Issues | Related set includes linked/epic/label/component-driven matches |
| Comments | MCP add/read comment tools | Issue comments | Added comment is persisted and queryable on target issue |
| Transitions | MCP transition tools | Transitions | Valid transitions succeed; invalid transitions fail explicitly without false success |
| Projects/Agile | project/board/sprint listing tools | Projects + Jira Software API | Returned entities match permissions/scope and contain expected metadata |
| User activity | user-centric issue/worklog tools | Users + Worklogs + Search | User filters return expected issues/work entries and totals |

## 7. Detailed Test Cases (minimum)

### A. Smoke cases

1. `doctor` returns `ok=true` with all required env vars set.
2. `list-tools` includes required Jira read and write tools.
3. Create run-tagged Task issue.
4. Read created issue and verify summary/labels.
5. Search by run-tag label returns created issue.
6. Add run-tagged comment and verify persistence.
7. Transition issue to next workflow state; verify resulting status.

### B. Full cases

1. Create second issue and validate related-ticket discovery behavior.
2. Validate `jira-my-tickets` and `jira-all-issues` response consistency for fixture issues.
3. Validate board/sprint listing calls where project is board-enabled.
4. Validate user worklog path returns expected structure and totals.
5. Validate filtering by assignee/reporter via search and user-centric flows.

### C. Negative cases

1. Empty/invalid `issueKey` returns validation error.
2. Invalid `transitionId` returns explicit API error (no false success).
3. Invalid or unsafe JQL returns clear error response.
4. Out-of-range pagination values return validation error.
5. Permission-limited operations fail with explicit auth/permission messaging.

## 8. Pass/Fail Gates

- **Smoke gate:** 100% pass required.
- **Full gate:** no critical failures; medium failures require triage entry.
- **Negative gate:** invalid-input tests must fail safely with explicit error responses.
- **Release readiness:** all gates pass across two consecutive runs in same environment.

## 9. Evidence Capture Format

For every test case capture:

- `test_id`
- `tool_name` or wrapper mode
- `arguments` (redacted as needed)
- `expected_result`
- `actual_result_excerpt`
- `duration_ms`
- `status` (`PASS`/`FAIL`)
- `artifact_links` (issue URL, logs, run outputs)
- `defect_reference` (if failed)

Recommended output location: `logs/jira-tests/<run-tag>/`.

## 10. Suggested Run Cadence

- **Per Jira code-path change:** run Phase A (Smoke)
- **Before merging Jira behavior changes:** run Phases A + B
- **Before release or dependency upgrade:** run Phases A + B + C

## 11. Implementation Backlog (automation)

1. Add `scripts/jira-test-runner.py` to execute matrix cases via MCP session calls.
2. Add `--profile` switch (`smoke`, `full`, `negative`).
3. Emit machine-readable evidence to `logs/jira-tests`.
4. Add CI smoke profile against dedicated Jira test project.
