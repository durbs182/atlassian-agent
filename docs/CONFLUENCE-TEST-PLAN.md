# Confluence Coverage Test Plan for `atlassian-expert`

This plan defines how to validate Confluence functionality coverage for the `atlassian-expert` workflow using the local MCP wrapper:

```bash
cd /Users/pauldurbin/github/atlassian-agent
source .venv/bin/activate
python atlassian_mcp_client.py --mode list-tools
python atlassian_mcp_client.py --mode agent
```

## 1. Objectives

1. Validate end-to-end Confluence coverage across read and write flows exposed by MCP tools.
2. Align test coverage to Atlassian Confluence Cloud REST documentation groups.
3. Provide a repeatable smoke/full/negative test runbook with clear pass/fail gates.
4. Standardize evidence capture for regressions and release readiness.

## 2. Atlassian Documentation Baseline

Use these as authoritative references when defining expected behavior:

- REST API intro: https://developer.atlassian.com/cloud/confluence/rest/v1/intro/
- Content: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content/
- Search (CQL): https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-search/
- Spaces: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-space/
- Users: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-users/
- Attachments: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content---attachments/
- Comments: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content-comments/
- Labels: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content-labels/

## 3. Current Confluence Surface in This Repo

### Wrapper-level Confluence mode
- `confluence-rename-space` in `atlassian_mcp_client.py`

### MCP Confluence tools (24)
- `get_confluence_current_user`
- `get_confluence_user`
- `search_pages_by_user_involvement`
- `list_pages_created_by_user`
- `list_attachments_uploaded_by_user`
- `read_confluence_page`
- `search_confluence_pages`
- `list_confluence_spaces`
- `get_confluence_space`
- `list_attachments_on_page`
- `download_confluence_attachment`
- `upload_confluence_attachment`
- `get_page_with_attachments`
- `create_confluence_page`
- `update_confluence_page`
- `list_confluence_page_children`
- `list_confluence_page_ancestors`
- `add_confluence_comment`
- `find_confluence_users`
- `list_confluence_page_labels`
- `add_confluence_page_label`
- `export_confluence_page`
- `get_my_recent_confluence_pages`
- `get_confluence_pages_mentioning_me`

## 4. Test Fixtures

Create and reuse fixtures per run:

- **Run tag:** `cf-test-YYYYMMDD-HHMM`
- **Space key:** Existing non-production space with edit rights (recommended dedicated test space).
- **Parent page title:** `CF TEST ROOT <run-tag>`
- **Child page title:** `CF TEST CHILD <run-tag>`
- **Comment text:** `CF test comment <run-tag>`
- **Labels:** `cf-test`, `cf-coverage`
- **Attachment file:** small text file `cf-test-<run-tag>.txt`
- **Mention target:** your own account (minimum) + optional secondary user

Cleanup policy:
- Keep all generated pages under the run-tagged parent page.
- Add `cf-test` label to all test-created pages.
- If hard delete is unavailable through current tools, archive/clean manually in Confluence UI at end of test cycle.

## 5. Execution Phases

## Phase A — Smoke (must pass every run)

1. Environment and tool availability
2. Space read/access
3. Create page
4. Read page
5. Update page
6. Add/list label
7. Add comment
8. Upload/list/download attachment
9. Export page (markdown and html)

## Phase B — Full functional coverage

1. CQL search paths
2. Page hierarchy (children + ancestors)
3. User lookup and user-involvement queries
4. Recent pages + mentioning-me views
5. Composite page+attachments retrieval
6. Space rename wrapper mode (where permitted)

## Phase C — Negative and robustness

1. Missing required arguments
2. Invalid IDs/keys
3. Invalid enum/type values
4. Pagination boundary violations
5. Permission-denied attempts in restricted space/page
6. Stale version update conflict scenario for page updates

## 6. Coverage Matrix

| Domain | Tools | Atlassian docs group | Core assertions |
|---|---|---|---|
| User identity | `get_confluence_current_user`, `get_confluence_user`, `find_confluence_users` | Users | Returns stable account identifiers, expected profile fields, proper not-found behavior |
| Spaces | `list_confluence_spaces`, `get_confluence_space`, wrapper `confluence-rename-space` | Spaces | Space visibility matches permissions; rename verifies old→new in follow-up read |
| Page lifecycle | `create_confluence_page`, `read_confluence_page`, `update_confluence_page` | Content | Created page is readable, version increments on update, content round-trip is correct |
| Search | `search_confluence_pages` | Search + Content | CQL filters return expected page set and pagination metadata |
| Hierarchy | `list_confluence_page_children`, `list_confluence_page_ancestors` | Content | Parent/child relationships are consistent in both directions |
| Comments | `add_confluence_comment` | Comments | Comment appears on target page and contains expected content |
| Labels | `add_confluence_page_label`, `list_confluence_page_labels` | Labels | Added labels are retrievable and deduplicated correctly |
| Attachments | `upload_confluence_attachment`, `list_attachments_on_page`, `download_confluence_attachment`, `get_page_with_attachments`, `list_attachments_uploaded_by_user` | Attachments + Content | Upload creates versioned attachment; list and download metadata/content are consistent |
| User-centric page activity | `search_pages_by_user_involvement`, `list_pages_created_by_user`, `get_my_recent_confluence_pages`, `get_confluence_pages_mentioning_me` | Search + Users + Content | Activity feeds include expected test artifacts and honor scope filters |
| Export | `export_confluence_page` | Content | Export succeeds for markdown/html; exported text contains canonical page content |

## 7. Detailed Test Cases (minimum)

### A. Smoke cases

1. `list_confluence_spaces` returns at least one space.
2. `get_confluence_space` resolves the selected fixture space key.
3. `create_confluence_page` creates parent page with run tag.
4. `create_confluence_page` creates child page under parent.
5. `read_confluence_page` by pageId returns correct title/content.
6. `update_confluence_page` updates content and increments version.
7. `add_confluence_page_label` then `list_confluence_page_labels` contains `cf-test`.
8. `add_confluence_comment` adds run-tagged comment.
9. `upload_confluence_attachment` succeeds for fixture file.
10. `list_attachments_on_page` includes uploaded file.
11. `download_confluence_attachment` returns artifact content/metadata.
12. `export_confluence_page` works for `markdown` and `html`.

### B. Negative cases

1. `read_confluence_page` without `pageId` and without (`title`,`spaceKey`) returns validation error.
2. `update_confluence_page` with invalid version returns conflict/error.
3. `search_confluence_pages` with empty CQL returns validation error.
4. Pagination above limit (e.g., limit > allowed max) returns validation error.
5. `get_confluence_space` with non-existent key returns clear not-found response.
6. Attachment download with invalid attachment ID returns not-found/permission error.

### C. Permission cases

1. Attempt page creation in read-only space should fail with permission error.
2. Attempt label/comment write on restricted page should fail with permission error.

## 8. Pass/Fail Gates

- **Smoke gate:** 100% pass required.
- **Full functional gate:** no critical failures; medium failures require triage entry.
- **Negative gate:** all invalid-input tests must fail safely with explicit error responses.
- **Release readiness:** all gates pass across two consecutive runs in same environment.

## 9. Evidence Capture Format

For each test case capture:

- `test_id`
- `tool_name`
- `arguments` (redacted when needed)
- `expected_result`
- `actual_result_excerpt`
- `duration_ms`
- `status` (`PASS`/`FAIL`)
- `artifact_links` (page URL, attachment ID, logs)
- `defect_reference` (if failed)

Recommended output structure: JSONL or Markdown table per run, stored under `logs/confluence-tests/<run-tag>/`.

## 10. Suggested Run Cadence

- **Per change touching Confluence behavior:** run Phase A (Smoke)
- **Before merging changes to wrapper/tool mappings:** run Phases A + B
- **Before release or after dependency upgrade:** run Phases A + B + C

## 11. Implementation Backlog (automation)

1. Add `scripts/confluence-test-runner.py` to execute matrix cases via MCP session calls.
2. Add a `--profile` switch (`smoke`, `full`, `negative`).
3. Emit machine-readable evidence to `logs/confluence-tests`.
4. Add CI job to run smoke profile against a dedicated test tenant.
