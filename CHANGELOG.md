# Changelog

## 0.1.0

- Initial Linear GraphQL plugin with branch-linked issue lookup, multi-checkout discovery, worker commands, session UI, and configurable polling.
- Use Linear workflow icons and colors, render comments and attached resources, and avoid duplicating the selected issue in its selector.
- Preserve valid branch matches when speculative identifiers fail, and bound speculative lookups to five.
- Reuse the refresh HTTP client and retain completed results when a rate limit interrupts a refresh.
- Keep the worker alive after malformed requests or repaint failures, and defer refresh requests until the outer event loop.
- Include pre-commit tooling and clarify personal API key configuration in the daemon environment.
- Verify four status scenarios against the live Linear API and worker; use sanitized recorded replies in regression tests.
- Keep checkouts whose branch names no Linear issue quiet instead of reporting auth, transport, or rate-limit errors, and clear the Linear badge, status column, and sort key when a session has no Linear work.
