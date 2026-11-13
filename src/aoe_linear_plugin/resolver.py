"""Branch-name issue identifiers and explicit Linear issue resolution."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.errors import LinearGraphQLError

# Linear team keys may start with a digit (``0DIN``), so the key only has to contain a letter;
# that still rejects bare number ranges such as version specs.
_IDENTIFIER = re.compile(
    r"(?<![A-Z0-9])((?=[A-Z0-9]*[A-Z])[A-Z0-9]{1,20}-[1-9][0-9]*)(?![A-Z0-9]|\.\d)",
    re.IGNORECASE,
)
_DEPENDENCY_BRANCH = re.compile(r"^(?:dependabot|renovate|snyk|pre-commit-ci|greenkeeper)/", re.IGNORECASE)
# ``pr-85`` names a pull request, not a team's issue. A team key spelled ``PR`` would be hidden
# too, which is the cheaper mistake: suppressing pull request discovery is worse than missing it.
_PULL_REQUEST_KEYS = frozenset({"PR", "PULLREQUEST"})
MAX_BRANCH_IDENTIFIERS = 5
MAX_HINT_IDENTIFIERS = 3


def branch_is_linear(branch: str) -> bool:
    """Whether a branch names a Linear issue, the only local signal that a checkout uses Linear.

    A dotted version suffix is not an issue number, so ``dependabot/pip/httpx-0.27.0`` does not
    count, and known dependency-update branches are excluded even when the package name ends in
    a bare integer (``dependabot/npm_and_yarn/react-18``). A pull request number such as
    ``athal/pr-85-work`` is also not an issue, so the pull request text still gets discovered.
    """
    return bool(branch_identifiers(branch))


def identifiers_in_text(text: str) -> list[str]:
    """Return distinct Linear-style identifiers in text order."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _IDENTIFIER.finditer(text):
        identifier = match.group(1).upper()
        if identifier not in seen:
            seen.add(identifier)
            found.append(identifier)
    return found


def identifiers_in_branch(branch: str) -> list[str]:
    """Return distinct Linear-style identifiers in branch order, unfiltered."""
    return identifiers_in_text(branch)


def branch_identifiers(branch: str) -> list[str]:
    """Identifiers a branch name speculatively suggests as Linear issues.

    Empty for dependency-update branches, whose package names end in bare integers, and for
    pull request number slugs. Both are branch text that looks like an identifier but names
    something else, and resolving them would link a checkout to an unrelated issue.
    """
    if _DEPENDENCY_BRANCH.match(branch):
        return []
    return [
        identifier
        for identifier in identifiers_in_branch(branch)
        if identifier.partition("-")[0] not in _PULL_REQUEST_KEYS
    ]


def hint_identifiers(hints: Iterable[str]) -> list[str]:
    """Identifiers named by free text such as commit subjects or session titles, bounded."""
    found: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        for identifier in identifiers_in_text(hint):
            if identifier in seen:
                continue
            seen.add(identifier)
            found.append(identifier)
            if len(found) >= MAX_HINT_IDENTIFIERS:
                return found
    return found


def resolve_branch(
    client: LinearClient,
    branch: str,
    *,
    hints: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Resolve exact branch metadata plus issue identifiers in the name and hints.

    A worktree branch is often a slug of the task title with no identifier in it, so callers
    may pass the session title and recent commit subjects. Branch text still wins: hints are
    consulted only when the branch names no issue, and hint lookups are bounded so speculative
    lookups stay cheap. The exact branch name is always searched as VCS metadata, but the
    identifiers guessed from it go through the same exclusions as ``branch_is_linear`` so a
    dependency or pull request slug cannot resolve an issue on its own.
    """
    candidates: dict[str, dict[str, Any]] = {}
    branch_issue = client.issue_for_branch(branch)
    if branch_issue and isinstance(branch_issue.get("id"), str):
        candidates[branch_issue["id"]] = branch_issue
    known_identifiers = {
        issue.get("identifier", "").casefold()
        for issue in candidates.values()
        if isinstance(issue.get("identifier"), str)
    }

    def speculative() -> Iterator[str]:
        yield from branch_identifiers(branch)[:MAX_BRANCH_IDENTIFIERS]
        # A branch cut from main carries unrelated issues in its commit history, so hints are
        # read only when the branch itself resolved nothing.
        if not candidates:
            yield from hint_identifiers(hints)

    attempted: set[str] = set()
    for identifier in speculative():
        key = identifier.casefold()
        if key in known_identifiers or key in attempted:
            continue
        attempted.add(key)
        try:
            identifier_issue = client.issue_by_identifier(identifier)
        except LinearGraphQLError:
            # Branch text is speculative: e.g. UTF-8 is not necessarily an issue.
            continue
        if identifier_issue and isinstance(identifier_issue.get("id"), str):
            candidates[identifier_issue["id"]] = identifier_issue
    return sorted(candidates.values(), key=lambda issue: (issue.get("identifier", ""), issue.get("title", "")))


def selected_issue(issues: Iterable[dict[str, Any]], identifier: str | None) -> dict[str, Any] | None:
    """Pick an explicit issue when available, otherwise the first stable choice."""
    candidates = list(issues)
    if identifier:
        for issue in candidates:
            if issue.get("identifier", "").casefold() == identifier.casefold():
                return issue
    return candidates[0] if candidates else None
