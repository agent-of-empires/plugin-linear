# Linear plugin for Agent of Empires

Resolve Linear issues linked to the current Git branch and open a selected issue. The worker reads `LINEAR_API_KEY` (or `LINEAR_TOKEN`) from its environment; it does not read or write Linear issues.

## Install from source

AoE 1.20.0 or newer is required. Install a clean checkout or source archive with `aoe plugin install <source>`. The host builds the Python worker into `.aoe-build/` during installation. Python 3.10+ and `pip` access to the package dependencies are required. For a local install, use a clean source tree (no `.venv` or other symlinks); the AoE installer rejects symlinks in local plugin sources.

The manifest uses the unverified community ID `community.linear`. There is no published GitHub release or tag yet. `gh:agent-of-empires/plugin-linear` therefore cannot resolve to a release; AoE can fall back to the unverified default branch only with explicit consent (`--yes` or an interactive confirmation). That branch must contain this manifest before it can install this plugin. Linear is not in AoE's featured index; a featured-index entry is only needed to claim a reserved verified namespace or featured listing.

## Commands

The worker protocol exposes `status` and `open` commands with optional `path` (default `.`) and `selected` issue identifier parameters. `status` returns branch-linked issue state; `open` resolves and opens the issue URL in the browser. These are worker commands only: AoE 1.20.0 does not yet dispatch manifest command contributions to workers from its CLI or palette.
