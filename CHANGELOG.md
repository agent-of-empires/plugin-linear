# Changelog

## 0.2.0

- Add an API 22 Linear suggestions provider for the AoE release that ships the suggestions contract, covering assigned issues in configured Up Next workflow states with optional team/project filters and host-managed project mappings.
- Discover suggestions independently of AoE sessions; publish complete snapshots and preserve the last-good host snapshot when refresh fails.
- Keep session creation, issue-text trust handling, and permission decisions in the AoE host.
- Rank unprioritized suggestions after Urgent through Low, and restrict assigned-issue queries to eligible workflow states before pagination while retaining local eligibility checks.
- Keep session badges and panes refreshing after unexpected suggestion failures, report a safe suggestion error without replacing the queue, and retain the Up Next default when workflow settings are cleared.
- Honor host source switches and suggestion refresh intervals, publish bounded template variables, and keep issue descriptions separate from draft prompts.
- Skip history inherited from the base branch when reading commit subjects for identifiers, so a checkout on `main` no longer claims an older issue as its work.
- Do not read a pull request number such as `pr-85` as a team key, so the pull request lookup that finds the real issue still runs; issue no speculative lookups for dependency-update branches.
- Report a Linear failure on a branch already linked through Linear's VCS metadata instead of calling the checkout unlinked, and skip `gh` pull request lookups during a refresh that has no API token.

## 0.1.0

- Match Linear identifiers whose team key starts with a digit (`0DIN-2360`), which worktree branches such as `athal/0din-2360-...` previously never resolved.
- Fall back to AoE session titles and recent commit subjects when a worktree branch is a slug with no Linear identifier in it.
- Read the branch's pull request title, body, and comments with `gh` when local hints name no issue, cached per commit and opt-out with the `use_pull_requests` setting.
- Initial Linear GraphQL plugin with branch-linked issue lookup, multi-checkout discovery, worker commands, session UI, and configurable polling.
- Use Linear workflow icons and colors, render comments and attached resources, and avoid duplicating the selected issue in its selector.
- Preserve valid branch matches when speculative identifiers fail, and bound speculative lookups to five.
- Reuse the refresh HTTP client and retain completed results when a rate limit interrupts a refresh.
- Keep the worker alive after malformed requests or repaint failures, and defer refresh requests until the outer event loop.
- Include pre-commit tooling and clarify personal API key configuration in the daemon environment.
- Verify four status scenarios against the live Linear API and worker; use sanitized recorded replies in regression tests.
- Keep checkouts whose branch names no Linear issue quiet instead of reporting auth, transport, or rate-limit errors, and clear the Linear badge, status column, and sort key when a session has no Linear work.
- Color the session row badge and status text by the Linear workflow state alone, so an urgent or cached issue no longer renders a status it does not have (staleness stays on its own labelled chip).
- Print Linear's short workflow category ("Started", not "In Progress") in the row status text, keeping the exact state name in its tooltip, so the row still fits when a second plugin owns a status column on the same session.
