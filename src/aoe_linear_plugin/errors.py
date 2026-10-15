"""Actionable errors returned by the Linear API client."""

from __future__ import annotations


class LinearError(Exception):
    """A safe-to-display Linear integration error."""

    kind = "linear"

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LinearAuthError(LinearError):
    """Missing or rejected Linear credentials."""

    kind = "auth"


class LinearRateLimitError(LinearError):
    """Linear requested that the client slow down."""

    kind = "rate_limited"


class LinearNetworkError(LinearError):
    """Transport or HTTP failure without exposing request credentials."""

    kind = "network"


class LinearGraphQLError(LinearError):
    """GraphQL operation or partial-data failure."""

    kind = "graphql"
