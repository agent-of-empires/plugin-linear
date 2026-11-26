# Changelog

## [0.2.0](https://github.com/agent-of-empires/plugin-linear/compare/v0.1.1...v0.2.0) (2026-11-26)


### Features

* **api:** add authenticated Linear GraphQL lookup ([#8](https://github.com/agent-of-empires/plugin-linear/issues/8)) ([4dd6642](https://github.com/agent-of-empires/plugin-linear/commit/4dd6642fd2c8b08c6a80779cf09696446073c81e))
* **commands:** add Linear status and open handlers ([#10](https://github.com/agent-of-empires/plugin-linear/issues/10)) ([a5bb0eb](https://github.com/agent-of-empires/plugin-linear/commit/a5bb0eb53f8651419d0f3d814c6ea9cf227f2494))
* **kanban:** publish Linear workflow and priority facets ([#20](https://github.com/agent-of-empires/plugin-linear/issues/20)) ([9805bcc](https://github.com/agent-of-empires/plugin-linear/commit/9805bccc9fc2cde89a7a7d26391bb0f74243f423))
* **linear:** make snoozed session row status opt-in ([#29](https://github.com/agent-of-empires/plugin-linear/issues/29)) ([3971503](https://github.com/agent-of-empires/plugin-linear/commit/39715033481877e24a5268b5a2ba4a713e9eca58))
* **linear:** resolve issues from commit and pull request text ([#32](https://github.com/agent-of-empires/plugin-linear/issues/32)) ([4248a98](https://github.com/agent-of-empires/plugin-linear/commit/4248a9863969a3a6c72ff61073a52e5ea5b0375b))
* **refresh:** cache Linear issues and honor rate limits ([#11](https://github.com/agent-of-empires/plugin-linear/issues/11)) ([c665621](https://github.com/agent-of-empires/plugin-linear/commit/c665621cc7353d3180198daa5719b9739411d0da))
* **resolution:** discover issues across checkouts ([#9](https://github.com/agent-of-empires/plugin-linear/issues/9)) ([30a5b69](https://github.com/agent-of-empires/plugin-linear/commit/30a5b69174e4e299236762e24398aac7ddee920a))
* **row:** show one status glyph instead of the issue identifier ([#30](https://github.com/agent-of-empires/plugin-linear/issues/30)) ([f2d27a2](https://github.com/agent-of-empires/plugin-linear/commit/f2d27a27cbbbc9c8e09686e082e19fe816490886))
* **ui:** show Linear issues in sessions ([#12](https://github.com/agent-of-empires/plugin-linear/issues/12)) ([ca79aff](https://github.com/agent-of-empires/plugin-linear/commit/ca79affc257b09e9c384e8614605f5ac030c3109))
* **worker:** connect Linear plugin to AoE host ([#13](https://github.com/agent-of-empires/plugin-linear/issues/13)) ([9f1eff2](https://github.com/agent-of-empires/plugin-linear/commit/9f1eff279991cd741756e0d5cc4ad71a2935d328))


### Bug Fixes

* **auth:** read the token from a file when the environment has none ([#42](https://github.com/agent-of-empires/plugin-linear/issues/42)) ([acab384](https://github.com/agent-of-empires/plugin-linear/commit/acab38473a251a06665d0dd7b970143511c5accd))
* **linear:** keep checkouts that do not use linear quiet ([#27](https://github.com/agent-of-empires/plugin-linear/issues/27)) ([e15503a](https://github.com/agent-of-empires/plugin-linear/commit/e15503a7813aa80af364312378202af6044936c9))
* **linear:** report outages and stop misreading branch text ([#37](https://github.com/agent-of-empires/plugin-linear/issues/37)) ([98e4623](https://github.com/agent-of-empires/plugin-linear/commit/98e46230560d9bbfb2b9628bf4ff24efb7c3523b))
* **plugin:** add supported AoE manifest and worker ([a058d71](https://github.com/agent-of-empires/plugin-linear/commit/a058d7190fc7a96630885e7bff95703a603ee3f5))
* **ui:** render row status by workflow state, not priority ([#28](https://github.com/agent-of-empires/plugin-linear/issues/28)) ([2c480c0](https://github.com/agent-of-empires/plugin-linear/commit/2c480c065c088d10b8f908f4d4e821e776ef2ced))
* **worker:** contain unexpected dispatch errors ([713cca1](https://github.com/agent-of-empires/plugin-linear/commit/713cca13625ac72663a254aa5f01f787fbfefb8d))
* **worker:** ignore malformed notifications ([8134039](https://github.com/agent-of-empires/plugin-linear/commit/8134039fae3b627ad2dfcbbff0b7971b4f87337d))
* **worker:** validate JSON-RPC requests ([eca0705](https://github.com/agent-of-empires/plugin-linear/commit/eca0705e745580ba8775ebf4aaa3837dd54f9d4f))

## 0.1.1

- Resolve the token from `~/.config/linear/api_key` (or `LINEAR_API_KEY_FILE`) when the environment has none, so a worker authenticates even when its daemon was started from an SSH session that could not read the Keychain; the key is re-read on every refresh, so replacing it needs no restart.
- Read a bounded head of the key file and end its first line at a carriage return as well as a newline, drop a byte-order mark, and treat an unresolvable `~user` in `LINEAR_API_KEY_FILE` as no token, so a malformed or mistyped file reports an auth state instead of failing the status request and stopping refresh publication.
- Read commit-subject hints only from commits authored on the branch, so a checkout sitting on `main` no longer attributes an inherited `ENG-12` commit to the current session.
- Treat pull request number slugs such as `athal/pr-85-work` as branch text that is not a Linear issue, so the pull request lookup still discovers the real link.
- Keep a branch known to be linked when a later poll's Linear request fails, reporting the outage instead of calling the checkout unlinked.
- Skip the `gh` pull request lookup when no Linear token is configured, since the text cannot change the auth snapshot and each cold checkout costs up to `GH_TIMEOUT`.

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
