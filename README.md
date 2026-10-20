# Linear plugin for Agent of Empires

Links Linear issues to Agent of Empires sessions, showing workflow status, issue details, comments, and related resources.

## Features

- Keeps previously loaded issue data visible and marks it stale when refresh fails.
- Shows an unavailable state when a refresh fails before any issue data is cached.
- Keeps session panes under the host's 64 KiB payload limit by dropping older comments, then truncating long descriptions when needed.
