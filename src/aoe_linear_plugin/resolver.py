"""Branch-name issue identifiers and explicit Linear issue resolution."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.errors import LinearGraphQLError

_IDENTIFIER = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]{0,19}-[1-9][0-9]*)(?![A-Z0-9.])", re.IGNORECASE)


def branch_is_linear(branch: str) -> bool:
    """Whether a branch names a Linear issue, the only local signal that a checkout uses Linear.

    The trailing lookahead rejects dotted version suffixes, so dependency branches like
    ``dependabot/pip/httpx-0.27.0`` are not mistaken for Linear work.
    """
    return bool(identifiers_in_branch(branch))


def identifiers_in_branch(branch: str) -> list[str]:
    """Return distinct Linear-style identifiers in branch order."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _IDENTIFIER.finditer(branch):
        identifier = match.group(1).upper()
        if identifier not in seen:
            seen.add(identifier)
            found.append(identifier)
    return found


def resolve_branch(client: LinearClient, branch: str) -> list[dict[str, Any]]:
    """Resolve exact branch metadata plus any issue identifiers in the name."""
    candidates: dict[str, dict[str, Any]] = {}
    branch_issue = client.issue_for_branch(branch)
    if branch_issue and isinstance(branch_issue.get("id"), str):
        candidates[branch_issue["id"]] = branch_issue
    known_identifiers = {
        issue.get("identifier", "").casefold()
        for issue in candidates.values()
        if isinstance(issue.get("identifier"), str)
    }
    for identifier in identifiers_in_branch(branch)[:5]:
        if identifier.casefold() in known_identifiers:
            continue
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
