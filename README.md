# Linear plugin for Agent of Empires

Refresh failures keep previously loaded issue data visible and mark it stale.
A failure before any issue data is cached is shown as unavailable, not stale.

The Linear plugin resolves issue state for session branches and displays it in the session list and a Linear pane. It uses Linear's GraphQL API directly; it does not shell out to `linear` or `gh`.

## Install and authenticate

AoE 1.20.0 or newer with plugin SDK API 19 and Python 3.10+ are required. Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/`; `pip` access to package dependencies is required. Local source trees must not contain symlinks such as `.venv`.

Set `LINEAR_API_KEY` in the environment inherited by the AoE daemon, then restart the daemon. `LINEAR_TOKEN` is an alternate name for a personal API key, not an OAuth access token; OAuth authentication is not supported. Use a personal API key with read access. The plugin never stores credentials in its manifest, config, logs, or issue cache.

The manifest uses the unverified community ID `community.linear`. There is no published release or tag yet, so `gh:agent-of-empires/plugin-linear` requires explicit consent (`--yes` or interactive confirmation) to fall back to the default branch. Linear is not in AoE's featured index; a featured entry is only needed for a reserved verified namespace or featured listing.

The manifest prompts for `net`, `runtime.worker`, `session.read`, `process.spawn`, `fs.read`, and `browser_open` capabilities. Build creates an isolated venv under `.aoe-build/`; the host launches `.aoe-build/venv/bin/aoe-linear-worker`.

## Features

- `Linear: status` returns the branch and its linked issues, with actionable auth/network/GraphQL errors.
- `Linear: refresh` schedules an update of all active session panes in the worker's outer loop; the plugin polls at the configurable interval (default 120 seconds, `0` disables polling). Each refresh reuses one HTTP client. A rate limit stops remaining requests, retains completed results, and uses last-good state until the advertised reset time.
- `Linear: open issue` opens the issue currently shown on the session row.
- Branch resolution combines Linear's issue `branchName` metadata with up to five distinct issue identifiers embedded in branch names (for example `feature/ENG-123-add-cache`). A failed speculative GraphQL lookup (such as `UTF-8` in a branch name) does not discard other matches. Authentication, transport, and rate-limit failures remain visible. Multiple matches are shown in the pane; the selected issue can be changed there.
- Session refresh considers the session checkout and host-provided `workspace_repos`, deduplicates repeated issue records, and keeps prior UI state while sessions are unavailable.
- The row badge links to the selected issue and shows its Linear workflow-state glyph; the status column shows only its workflow state; sorting ranks urgent/high/started issues ahead of completed issues.
- Pane details include issue status, priority, team, assignee, project, cycle, description, up to 10 recent comments, and attached resources. The selected issue appears in the pane header; the selector lists only alternate issues. Attachments may include linked pull requests when Linear has attached them.
- Keeps previously loaded issue data visible and marks it stale when refresh fails.
- Shows an unavailable state when a refresh fails before any issue data is cached.
- Session panes stay under the host's 64 KiB payload limit by dropping older comments, then truncating long descriptions when needed.

The session row exposes Linear workflow and priority as filter facets for the dashboard and Kanban Board. Facet values include every linked issue in that session, not only the selected issue; refreshes with cached issue data keep those values. The filter contract:

| Facet id | Label | Column | Values |
|---|---|---|---|
| `linear_workflow` | Linear workflow | `linear_issue_status` | `state:triage`, `state:backlog`, `state:unstarted`, `state:started`, `state:completed`, `state:canceled` |
| `linear_priority` | Linear priority | `linear_issue_status` | `priority:0` (No priority) through `priority:4` (Low) |

## Install from source

AoE 1.20.0 or newer is required. Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/` during installation. Python 3.10+ and `pip` access to the package dependencies are required. For a local install, use a clean source tree (no `.venv` or other symlinks); the AoE installer rejects symlinks in local plugin sources.

The manifest uses the unverified community ID `community.linear`. There is no published GitHub release or tag yet. `gh:agent-of-empires/plugin-linear` therefore cannot resolve to a release; AoE can fall back to the unverified default branch only with explicit consent (`--yes` or an interactive confirmation). That branch must contain this manifest before it can install this plugin. Linear is not in AoE's featured index; a featured-index entry is only needed to claim a reserved verified namespace or featured listing.

## Commands

The worker handles `linear.status`, `linear.open`, and `linear.refresh` requests and `linear.select_issue` pane actions, and routes the `plugin.community.linear.status`, `plugin.community.linear.open`, and `plugin.community.linear.refresh` names to the same handlers. The `open` command is a host-side `open-ui-link` action for the selected issue; reader failures always signal worker shutdown, and poll failures log only the exception class, never potentially sensitive exception text.

- Suggestions independently discover your assigned issues in the configured Linear workflow states (default: exact state name `Up Next`), without depending on existing AoE sessions. Every successful complete refresh replaces the current snapshot; API failures report an error and do not replace the last-good snapshot.
- Each suggestion links to its canonical Linear issue URL and includes a preview and an actionable prompt that identifies issue text as untrusted input. The worker only publishes issue data to the host; session creation, prompting, trust defaults, and permission checks remain host-owned.

### GitHub plugin feature mapping

Linear is an issue tracker, not a source-control or CI provider. This plugin reports Linear issue/workflow state and attached issue resources only. Linear does not provide GitHub's pull-request mergeability/conflicts, review decisions or reviewer roster, CI check runs, unresolved review threads, PR diff statistics, merge verdict, or PR timeline. The plugin does not infer or synthesize those states. A linked pull request is shown only when it exists as a Linear issue attachment; it is a link, not a PR status integration.

## Settings

- **Refresh interval**: 0–86400 seconds (default 120); zero disables background polling.
- **Show priority**: controls priority badges in the issue selector.
- **Ignore Git submodules**: excludes initialized nested child submodules during checkout discovery; the session's primary checkout is retained.
- **Suggestion workflow states**: comma-separated exact Linear state names; defaults to `Up Next`.
- **Suggestion teams/projects**: optional comma-separated exact Linear team keys/IDs and project names/IDs; empty means no additional scope restriction.
- **Suggestion AoE project mappings**: optional JSON object mapping Linear project IDs or names to an exact registered AoE project name or canonical local path. Unmapped issues have no project assignment; the provider never guesses a scratch project.

## Development

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pre-commit install
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

Worker-host smoke test, including an interleaved refresh during startup, a malformed request, and a subsequent status request:

```sh
uv run pytest tests/test_main.py::test_worker_host_smoke_answers_startup_rpcs_and_status
```

Issue lookups use Linear GraphQL at `https://api.linear.app/graphql`. Linear reports rate limits as HTTP 400 with `extensions.code == "RATELIMITED"` and no `Retry-After` header; the client then serves last-good data until the advertised reset time in the `X-RateLimit-*` headers. Missing credentials are reported as an actionable auth state; there is no fabricated data fallback.

### Live verification and remaining release gates

On 2026-10-18, the status handler and real NDJSON worker both passed four authenticated scenarios: an API-provided VCS branch, an identifier-bearing branch containing an unrelated `UTF-8` identifier, a `fix/issue-42`-style unknown identifier, and an issue with an attachment. The attachment also produced a linked-resource pane payload. This is API/protocol verification, not browser-render verification; dashboard QA still stops at the passphrase sign-in screen.

Anonymized real GraphQL replies are recorded in [`tests/fixtures/linear_live.json`](tests/fixtures/linear_live.json) and used by the offline client, resolver, refresh, and attachment-rendering regressions. String content and identities are redacted, and cycle numbers are replaced with a synthetic value; response envelopes, nulls, and workflow types are retained. Boundary tests still use synthetic inputs. No live-network test or credential is needed to run the suite.

Release automation and the featured-index pin flow remain separate follow-up work: mirror plugin-github's maintainer-gated release PR, matching package/manifest versions, tag-on-merge, checked source release, and canonical `aoe plugin hash` pin proposal. Do not publish a release or change AoE's trust root as part of a code-review update. A host secret-setting type, aliased multi-branch GraphQL batching, and authenticated dashboard screenshots also remain follow-ups.

## License

MIT. See [LICENSE](LICENSE).
