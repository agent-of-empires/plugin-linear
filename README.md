# Linear plugin for Agent of Empires

A refresh failure for a checkout with cached issues keeps that data visible and marks the affected session stale.
A failure for a checkout with no cached issues is shown as unavailable, not stale; cached issues from other checkouts alone do not mark the session stale.
A rate limit is session-wide rather than per checkout: it comes from one request, then every request on that key stops until the advertised reset. Sessions with cached issues are marked stale, and checkouts with no cached issues show the rate-limit state, including sessions whose own request was never sent.

The Linear plugin resolves issue state for session branches and displays it in the session list and a Linear pane. It uses Linear's GraphQL API directly and does not shell out to `linear`. When a branch, its recent commits, and the session title name no issue, it can ask the GitHub CLI (`gh`) for the branch's pull request title, body, and comments and read a Linear link from that text; this lookup is optional, cached per commit, and controlled by the `use_pull_requests` setting.

## Install and authenticate

AoE 1.27.0 or later (plugin SDK API 27) and Python 3.10+ are required. The manifest nests `status`, `refresh` and `open` under a `linear` command group, and the host rejects command groups below API 27, so an older release refuses the manifest rather than loading it without the nesting. v1.26.0 reports API 25. v1.27.0 is the first release that reports API 27 and it also carries the host-side suggestion handlers; it is not tagged yet. Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/`; `pip` access to package dependencies is required. Local source trees must not contain symlinks such as `.venv`.

The token is resolved on every refresh, in a fixed order: `LINEAR_API_KEY`, then `LINEAR_TOKEN` (`LINEAR_TOKEN` is an alternate name for a personal API key, not an OAuth access token; OAuth authentication is not supported), then a token file: the one named by `LINEAR_API_KEY_FILE` when it is set, which is an override and suppresses the default, otherwise `~/.config/linear/api_key`. The file holds one line, mode `0600`. Use a personal API key with read access. A file is read per refresh, so replacing a rejected file-backed key needs no daemon restart; a key taken from the environment changes only when the daemon is restarted with the new value.

The file is not a convenience. AoE fixes the daemon's environment when the daemon starts and hands that copy to every plugin worker, so a daemon started from a session that cannot read the platform credential store never sees an exported key: on macOS an SSH session cannot authorize a Keychain item, and `security find-generic-password -w` then fails with `errSecInteractionNotAllowed` and prints nothing. A file the user owns is the same answer `gh auth token` gives from `~/.config/gh/hosts.yml`. The plugin never writes credentials to its manifest, config, logs, or issue cache, and the file is read rather than copied anywhere.

The manifest claims the reserved `agent-of-empires.*` namespace, which AoE refuses to install unless the fetched source tree is featured-verified. agent-of-empires/agent-of-empires#5664 merged that pin, but it attests `plugin-linear` 0.1.0 at tag `v0.1.0` (`69383b7`, an API 7 tree that predates this work), so it does not cover this manifest. Until 0.2.0 is tagged from the tree carrying this manifest and a pin for that tag is published, `gh:` installs of this branch fail with a reserved-namespace error. Local development is unaffected: `aoe plugin install --dev <dir>` bypasses the gate. Because the publishable tag is 0.1.0 and it does not contain this manifest, `gh:agent-of-empires/plugin-linear` resolves only with explicit consent (`--yes` or interactive confirmation) to fall back to the default branch, which must contain this manifest before it can install this plugin.

The manifest prompts for `net`, `runtime.worker`, `session.read`, `process.spawn`, `fs.read`, and `browser_open` capabilities. Build creates an isolated venv under `.aoe-build/`; the host launches `.aoe-build/venv/bin/aoe-linear-worker`.

## Features

- `Linear: status` returns the branch and its linked issues, with actionable auth/network/GraphQL errors.
- `Linear: refresh` schedules an update of all active session panes in the worker's outer loop; the plugin polls at the configurable interval (default 120 seconds, `0` disables polling). Each refresh reuses one HTTP client. A rate limit stops remaining requests, retains completed results, and uses last-good state until the advertised reset time.
- `Linear: open issue` opens the issue currently shown on the session row.
- Branch resolution combines Linear's issue `branchName` metadata with up to five distinct issue identifiers embedded in branch names (for example `feature/ENG-123-add-cache`), including team keys that start with a digit (`athal/0din-2360-...`); dependency-update branches and pull request slugs such as `athal/pr-85-work` name no issue. When a worktree branch is a slug of the task title instead (for example `litellm`), up to three identifiers from commits authored on the branch and the AoE session title are tried as well. If those name no issue, the branch's pull request title, body, and comments are read with `gh pr list` and tried as the last resort; the lookup is skipped when `gh` is missing or unauthenticated and cached per commit for 10 minutes so polling does not repeat it. A failed speculative GraphQL lookup (such as `UTF-8` in a branch name) does not discard other matches. Authentication, transport, and rate-limit failures remain visible. Multiple matches are shown in the pane; the selected issue can be changed there.
- Session refresh considers the session checkout and host-provided `workspace_repos`, deduplicates repeated issue records, and keeps prior UI state while sessions are unavailable.
- The session row carries one Linear badge and nothing else: a single workflow-state glyph (`◌` backlog, `○` todo, `◐` in progress, `●` done, `×` canceled) tinted by that state and linked to the selected issue. It shows no issue identifier and no status column, so the row stays quiet; the pane carries identifiers, titles, and details.
- Pane details include issue status, priority, team, assignee, project, cycle, description, up to 10 recent comments, and attached resources. The selected issue appears in the pane header; the selector lists only alternate issues. Attachments may include linked pull requests when Linear has attached them.
- Keeps previously loaded issue data visible and marks it stale when refresh fails.
- Shows an unavailable state when a refresh fails before any issue data is cached.
- Treats a checkout as not using Linear when neither its branch, its recent commit subjects, nor the session title names a Linear issue, so a missing key or a failed request shows a neutral state instead of an error badge or callout.
- Coexists with the GitHub plugin: sessions without Linear work get a cleared Linear badge, so the row is left to whatever else claims it.
- Suggestions independently discover your assigned issues in the configured Linear workflow states (default: exact state name `Up Next`), without depending on existing AoE sessions. The host can disable the source and controls its refresh interval. Successful refreshes publish the highest-priority 500 issues; failures preserve the last-good snapshot.
- Each suggestion links to its Linear issue and exposes its description as untrusted preview text, separate from its draft prompt. The host owns session creation, prompting, trust defaults, and permission checks.
- Session panes stay under the host's 64 KiB payload limit by dropping older comments, then truncating long descriptions when needed.

The plugin declares only a `row-badge` and a `pane`. It publishes no status column, sort key, or filter facet, so Linear adds no column, sort option, or filter to the dashboard's toolbar; workflow and priority are readable in the pane.

## Install from source

AoE 1.27.0 or later (plugin SDK API 27) is required, and that release is not tagged yet; see [Install and authenticate](#install-and-authenticate). Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/` during installation. Python 3.10+ and `pip` access to the package dependencies are required. For a local install, use a clean source tree (no `.venv` or other symlinks); the AoE installer rejects symlinks in local plugin sources.

The manifest claims the reserved `agent-of-empires.*` namespace, which install and load both refuse unless the fetched source tree hashes to a featured-index pin. agent-of-empires/agent-of-empires#5664 merged that pin for 0.1.0 at tag `v0.1.0`; it is a maintainer attestation of one specific tree, so every source change needs a newly tagged release and a new pin. Tag `v0.1.0` exists but predates this manifest (API 7, `69383b7`), and a tag cannot be moved once it has been published, so this work needs its own release before any pin can cover it. `gh:agent-of-empires/plugin-linear` therefore cannot resolve to a tag containing this manifest yet; AoE can fall back to the default branch only with explicit consent (`--yes` or an interactive confirmation). That branch must contain this manifest before it can install this plugin.

## Commands

The CLI exposes them as `aoe linear status`, `aoe linear refresh`, and `aoe linear open`; that nesting comes from the manifest's `[[command_groups]]` entry, which needs SDK API 27. The worker handles `linear.status`, `linear.open`, and `linear.refresh` requests and `linear.select_issue` pane actions, and routes the `plugin.agent-of-empires.linear.status`, `plugin.agent-of-empires.linear.open`, and `plugin.agent-of-empires.linear.refresh` names to the same handlers. The `open` command is a host-side `open-ui-link` action for the selected issue; reader failures always signal worker shutdown, and poll failures log only the exception class, never potentially sensitive exception text.

The worker also answers the suggestion methods, whose shapes are fixed by the AoE API 23 suggestions contract; suggestion settings are read with `config.get` and the source is toggled through the host's `suggestions.sources` RPC rather than local config.

### GitHub plugin feature mapping

Linear is an issue tracker, not a source-control or CI provider. This plugin reports Linear issue/workflow state and attached issue resources only. Linear does not provide GitHub's pull-request mergeability/conflicts, review decisions or reviewer roster, CI check runs, unresolved review threads, PR diff statistics, merge verdict, or PR timeline. The plugin does not infer or synthesize those states. A linked pull request is shown only when it exists as a Linear issue attachment; it is a link, not a PR status integration.

## Settings

- **Refresh interval**: 0–86400 seconds (default 120); zero disables background polling.
- **Show priority**: controls priority badges in the issue selector.
- **Read Linear links from pull request text** (`use_pull_requests`, on by default): allows one cached `gh pr list` lookup per unresolved checkout, used only when the branch, its recent commits, and the session title name no Linear issue. Background refresh and the `status` and `open` commands honor it. Turn it off to keep the plugin entirely on the Linear API.
- **Show Linear status for snoozed sessions** (`include_snoozed`, off by default): the session list keeps a snoozed session as a sunk row, and turning this on keeps its Linear row badge live. It costs Linear requests for parked work, since every poll re-queries those branches.
- **Ignore Git submodules**: excludes initialized nested child submodules during checkout discovery; the session's primary checkout is retained.
- **Suggestion workflow states**: comma-separated exact Linear state names; defaults to `Up Next`.
- **Suggestion teams/projects**: optional comma-separated exact Linear team keys/IDs and project names/IDs; empty means no additional scope restriction.
- **Suggestion project mapping**: map the Linear project ID (or team ID for an issue without a project) to registered AoE projects in Settings › Suggestions. Existing plugin-specific `suggestion_project_mappings` settings are no longer read and must be recreated in the host.

Settings writes reach the running worker as the host's `plugin.settings.changed` notification, so a change applies on the next poll without restarting the worker.

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

Releases are automated with release-please: a merge to `main` refreshes one release PR that bumps `__version__` and the manifest version and writes `CHANGELOG.md`, and merging it creates the `vX.Y.Z` tag and GitHub Release that `release.yml` attaches a checked source archive to, called as a reusable workflow so publishing needs no personal access token. That PR's checks start in an approval-required state rather than not at all, because a PR opened with the workflow token does not start `pull_request` runs by itself: someone with write access approves the runs in the merge box ("Approve workflows to run") before it can merge. `0.1.1` was cut by hand before adoption, so publish it with `gh workflow run release.yml -f tag=v0.1.1` once this lands: dispatched from `main`, the run checks out the current `main` when the tag does not exist yet and creates the tag there, while a dispatch on any other branch fails rather than tagging unmerged code. The featured-index pin flow remains separate follow-up work: the canonical `aoe plugin hash` pin proposal. Do not publish a release or change AoE's trust root as part of a code-review update. A host secret-setting type, aliased multi-branch GraphQL batching, and authenticated dashboard screenshots also remain follow-ups.

## License

MIT. See [LICENSE](LICENSE).
