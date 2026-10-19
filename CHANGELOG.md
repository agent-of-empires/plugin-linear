# Changelog

## 0.1.0

- Initial Linear GraphQL plugin with branch-linked issue lookup, multi-checkout discovery, worker commands, session UI, and configurable polling.
- Use Linear workflow icons and colors, render comments and attached resources, and avoid duplicating the selected issue in its selector.
- Preserve valid branch matches when speculative identifiers fail, and bound speculative lookups to five.
- Reuse the refresh HTTP client and retain completed results when a rate limit interrupts a refresh.
- Keep the worker alive after malformed requests or repaint failures, and defer refresh requests until the outer event loop.
- Include pre-commit tooling and clarify personal API key configuration in the daemon environment.
- Verify four status scenarios against the live Linear API and worker; use sanitized recorded replies in regression tests.
- Add an API 19 Linear suggestions provider for Agent of Empires 1.20.0+, covering assigned issues in configured Up Next workflow states, with optional team/project filters and explicit AoE project mappings.
- Discover suggestions independently of AoE sessions; publish complete snapshots and preserve the last-good host snapshot when refresh fails.
- Keep session creation, issue-text trust handling, and permission decisions in the AoE host.
- Rank unprioritized suggestions after Urgent through Low, and restrict assigned-issue queries to eligible workflow states before pagination while retaining local eligibility checks.
