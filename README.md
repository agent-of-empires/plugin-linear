# Linear plugin for Agent of Empires

Refresh failures keep previously loaded issue data visible and mark it stale.
A failure before any issue data is cached is shown as unavailable, not stale.

The Linear plugin resolves issue state for session branches and displays it in the session list and a Linear pane. It uses Linear's GraphQL API directly; it does not shell out to `linear` or `gh`.

## Install and authenticate

Install from **Settings → Plugins → Discover** or:

```sh
aoe plugin install agent-of-empires/plugin-linear
```

Set `LINEAR_API_KEY` in the environment inherited by the AoE daemon, then restart the daemon. `LINEAR_TOKEN` is an alternate name for a personal API key, not an OAuth access token; OAuth authentication is not supported. Use a personal API key with read access. The plugin never stores credentials in its manifest, config, logs, or issue cache. Authenticated live API verification has not been performed.

`agent-of-empires.linear` is in AoE's reserved namespace. The host requires an official featured-index pin before users can install it; that pin can only be generated for a released source tree. This implementation does not publish a release or modify AoE's featured index, so installation remains unavailable until that follow-up is approved and completed.

The manifest prompts for `net`, `runtime.worker`, `session.read`, and `browser_open` capabilities. Build creates an isolated venv under `.aoe-build/`; the host launches `.aoe-build/venv/bin/aoe-linear-worker`.

## Features

- `Linear: status` returns the branch and its linked issues, with actionable auth/network/GraphQL errors.
- `Linear: refresh` schedules an update of all active session panes in the worker's outer loop; the plugin polls at the configurable interval (default 120 seconds, `0` disables polling). Each refresh reuses one HTTP client. A rate limit stops remaining requests, retains completed results, and uses last-good state during the `Retry-After` cooldown.
- `Linear: open issue` opens the issue currently shown on the session row.
- Branch resolution combines Linear's issue `branchName` metadata with up to five distinct issue identifiers embedded in branch names (for example `feature/ENG-123-add-cache`). A failed speculative GraphQL lookup (such as `UTF-8` in a branch name) does not discard other matches. Authentication, transport, and rate-limit failures remain visible. Multiple matches are shown in the pane; the selected issue can be changed there.
- Session refresh considers the session checkout and host-provided `workspace_repos`, deduplicates repeated issue records, and keeps prior UI state while sessions are unavailable.
- The row badge links to the selected issue and shows its Linear workflow-state glyph; the status column shows only its workflow state; sorting ranks urgent/high/started issues ahead of completed issues.
- Pane details include issue status, priority, team, assignee, project, cycle, description, up to 10 recent comments, and attached resources. The selected issue appears in the pane header; the selector lists only alternate issues. Attachments may include linked pull requests when Linear has attached them.

### GitHub plugin feature mapping

Linear is an issue tracker, not a source-control or CI provider. This plugin reports Linear issue/workflow state and attached issue resources only. Linear does not provide GitHub's pull-request mergeability/conflicts, review decisions or reviewer roster, CI check runs, unresolved review threads, PR diff statistics, merge verdict, or PR timeline. The plugin does not infer or synthesize those states. A linked pull request is shown only when it exists as a Linear issue attachment; it is a link, not a PR status integration.

## Settings

- **Refresh interval**: 0–86400 seconds (default 120); zero disables background polling.
- **Show priority**: controls priority badges in the issue selector.
- **Ignore Git submodules**: excludes initialized nested child submodules during checkout discovery; the session's primary checkout is retained.

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

Issue lookups use Linear GraphQL at `https://api.linear.app/graphql`. HTTP 429 responses honor `Retry-After` and background polling serves last-good data during the backoff. Missing credentials are reported as an actionable auth state; there is no fabricated data fallback.

### Remaining release and verification gates

Before merge, run against a real Linear workspace using a VCS-linked branch, an identifier-bearing branch, a `fix/issue-42`-style branch, and an issue with an attachment. Record the real status output and sanitized GraphQL responses; the current transport fixtures are hand-written, not recorded API evidence. No API key was available during the feedback update, and dashboard verification stopped at the passphrase sign-in screen.

Release automation and the featured-index pin flow remain separate follow-up work: mirror plugin-github's maintainer-gated release PR, matching package/manifest versions, tag-on-merge, checked source release, and canonical `aoe plugin hash` pin proposal. Do not publish a release or change AoE's trust root as part of a code-review update. A host secret-setting type, aliased multi-branch GraphQL batching, and authenticated dashboard screenshots also remain follow-ups.

## License

MIT. See [LICENSE](LICENSE).
