# Linear plugin for Agent of Empires

Resolve Linear issues linked to the current Git branch and open a selected issue. The worker reads issue data using `LINEAR_API_KEY` (or `LINEAR_TOKEN`) from its environment but does not modify Linear issues.

Links Linear issues to Agent of Empires sessions, showing workflow status, issue details, comments, and related resources.

## Features

- Keeps previously loaded issue data visible and marks it stale when refresh fails.
- Shows an unavailable state when a refresh fails before any issue data is cached.
- Keeps session panes under the host's 64 KiB payload limit by dropping older comments, then truncating long descriptions when needed.

The session row exposes Linear workflow and priority as filter facets for the dashboard and Kanban Board. Facet values include every linked issue, not only the selected issue; refreshes with cached issue data keep those values.

## Install from source

AoE 1.20.0 or newer is required. Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/` during installation. Python 3.10+ and `pip` access to the package dependencies are required. For a local install, use a clean source tree (no `.venv` or other symlinks); the AoE installer rejects symlinks in local plugin sources.

The manifest uses the unverified community ID `community.linear`. There is no published GitHub release or tag yet. `gh:agent-of-empires/plugin-linear` therefore cannot resolve to a release; AoE can fall back to the unverified default branch only with explicit consent (`--yes` or an interactive confirmation). That branch must contain this manifest before it can install this plugin. Linear is not in AoE's featured index; a featured-index entry is only needed to claim a reserved verified namespace or featured listing.

## Commands

The worker handles `linear.status` and `linear.refresh` requests and `linear.select_issue` pane actions. The `open` command is a host-side `open-ui-link` action for the selected issue; the worker also routes the `plugin.community.linear.status` and `plugin.community.linear.open` names to the same issue handlers.
