# Linear plugin for Agent of Empires

The Linear plugin resolves issue state for session branches and displays it in the session list and a Linear pane. It uses Linear's GraphQL API directly; it does not shell out to `linear` or `gh`.

## Install and authenticate

Install from **Settings → Plugins → Discover** or:

```sh
aoe plugin install agent-of-empires/plugin-linear
```

Set `LINEAR_API_KEY` in the environment inherited by the AoE daemon. `LINEAR_TOKEN` is accepted as an alternate environment variable. Use a Linear API key with read access. The plugin never stores credentials in its manifest, config, logs, or issue cache. Authenticated live API verification was not performed as part of this implementation.

`agent-of-empires.linear` is in AoE's reserved namespace. The host requires an official featured-index pin before users can install it; that pin can only be generated for a released source tree. This implementation does not publish a release or modify AoE's featured index, so installation remains unavailable until that follow-up is approved and completed.

The manifest prompts for `net`, `runtime.worker`, `session.read`, and `browser_open` capabilities. Build creates an isolated venv under `.aoe-build/`; the host launches `.aoe-build/venv/bin/aoe-linear-worker`.

## Features

- `Linear: status` returns the branch and its linked issues, with actionable auth/network/GraphQL errors.
- `Linear: refresh` updates all active session panes; the plugin polls at the configurable interval (default 120 seconds, `0` disables polling). Repeated API calls respect Linear's `Retry-After` cooldown and use last-good state while limited.
- `Linear: open issue` opens the issue currently shown on the session row.
- Branch resolution combines Linear's issue `branchName` metadata with issue identifiers embedded in branch names (for example `feature/ENG-123-add-cache`). Multiple matches are shown in the pane; the selected issue can be changed there.
- Session refresh considers the session checkout and host-provided `workspace_repos`, deduplicates repeated issue records, and keeps prior UI state while sessions are unavailable.
- The row badge links to the selected issue; the status column shows its workflow state and identifier; sorting ranks urgent/high/started issues ahead of completed issues.
- Pane details include issue status, priority, team, assignee, project, cycle, description, and attached resources. Attachments may include linked pull requests when Linear's integration has attached them.

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
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

Worker protocol smoke test (the host answers the startup `config.get` and `sessions.list` RPCs in production):

```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"linear.status","params":{"args":{"path":"."}}}' | uv run aoe-linear-worker
```

Issue lookups use Linear GraphQL at `https://api.linear.app/graphql`. HTTP 429 responses honor `Retry-After` and background polling serves last-good data during the backoff. Missing credentials are reported as an actionable auth state; there is no fabricated data fallback.

## License

MIT. See [LICENSE](LICENSE).
