"""Small authenticated Linear GraphQL client."""

from __future__ import annotations

import json
from typing import Any

import httpx

from aoe_linear_plugin.errors import LinearAuthError, LinearGraphQLError, LinearNetworkError, LinearRateLimitError

API_URL = "https://api.linear.app/graphql"
ISSUE_FIELDS = """
  id identifier title url description priority branchName
  state { id name type color }
  assignee { id name displayName }
  team { id key name }
  project { id name url }
  cycle { id name number startsAt endsAt }
  labels { nodes { id name color } }
  attachments { nodes { id title subtitle url } }
  comments(last: 10) { nodes { id body user { name } } }
"""


class LinearClient:
    """Linear GraphQL transport with bearer auth and bounded request timeouts."""

    def __init__(
        self,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            headers={"Authorization": token, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LinearClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one GraphQL query; partial GraphQL errors are not ignored."""
        try:
            response = self._client.post(API_URL, json={"query": query, "variables": variables or {}})
        except httpx.HTTPError as exc:
            raise LinearNetworkError("Could not reach Linear. Check network connectivity.") from exc
        if response.status_code in (401, 403):
            raise LinearAuthError(
                "Linear rejected the API key. Check LINEAR_API_KEY in plugin settings or environment."
            )
        if response.status_code == 429:
            retry_after = _retry_after(response.headers.get("Retry-After"))
            raise LinearRateLimitError(
                "Linear rate limit reached; cached issue data is being shown.",
                retry_after=retry_after,
            )
        if response.status_code >= 500:
            raise LinearNetworkError(f"Linear returned HTTP {response.status_code}; retry later.")
        if response.status_code >= 400:
            raise LinearNetworkError(f"Linear returned HTTP {response.status_code}; check the API request.")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LinearNetworkError("Linear returned an invalid JSON response.") from exc
        if not isinstance(payload, dict):
            raise LinearNetworkError("Linear returned an invalid GraphQL response.")
        errors = payload.get("errors")
        if errors:
            messages = [error.get("message", "GraphQL error") for error in errors if isinstance(error, dict)]
            safe_message = "; ".join(str(message)[:200] for message in messages[:3]) or "GraphQL operation failed"
            raise LinearGraphQLError(f"Linear GraphQL error: {safe_message}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise LinearGraphQLError("Linear returned no GraphQL data.")
        return data

    def issue_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        query = f"query IssueByIdentifier($id: String!) {{ issue(id: $id) {{{ISSUE_FIELDS}}} }}"
        issue = self.execute(query, {"id": identifier}).get("issue")
        return issue if isinstance(issue, dict) else None

    def issue_for_branch(self, branch: str) -> dict[str, Any] | None:
        """Look up one issue by its exact Linear VCS branch metadata."""
        query = f"""query IssueVcsBranchSearch($branchName: String!) {{
          issueVcsBranchSearch(branchName: $branchName) {{{ISSUE_FIELDS}}}
        }}"""
        issue = self.execute(query, {"branchName": branch}).get("issueVcsBranchSearch")
        return issue if isinstance(issue, dict) else None


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return min(max(float(value), 0.0), 3600.0)
    except ValueError:
        return None
