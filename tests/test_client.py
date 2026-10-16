from __future__ import annotations

import json

import httpx
import pytest

from aoe_linear_plugin.client import API_URL, LinearClient
from aoe_linear_plugin.errors import LinearAuthError, LinearGraphQLError, LinearRateLimitError


def test_graphql_query_sends_token_and_variables() -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"issue": {"id": "issue-id"}}})

    with LinearClient("secret-token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_by_identifier("ENG-12")

    assert seen["url"] == API_URL
    assert seen["authorization"] == "secret-token"
    assert seen["body"]["variables"] == {"id": "ENG-12"}
    assert "IssueByIdentifier" in seen["body"]["query"]
    assert issue == {"id": "issue-id"}


def test_branch_lookup_uses_linear_vcs_branch_search() -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        return httpx.Response(
            200,
            json={"data": {"issueVcsBranchSearch": {"id": "1", "identifier": "ENG-12"}}},
        )

    with LinearClient("token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_for_branch("feature/ENG-12-change")

    assert seen["variables"] == {"branchName": "feature/ENG-12-change"}
    assert "issueVcsBranchSearch" in seen["query"]
    assert issue == {"id": "1", "identifier": "ENG-12"}


def test_http_auth_rate_limit_and_graphql_errors_are_typed() -> None:
    auth_transport = httpx.MockTransport(lambda _: httpx.Response(401))
    with LinearClient("secret-token", transport=auth_transport) as client, pytest.raises(LinearAuthError) as auth:
        client.execute("query { viewer { id } }")
    assert "secret-token" not in str(auth.value)

    limited_transport = httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "17"}))
    with LinearClient("token", transport=limited_transport) as client, pytest.raises(LinearRateLimitError) as limited:
        client.execute("query { viewer { id } }")
    assert limited.value.retry_after == 17

    errors_transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"errors": [{"message": "bad query"}]}))
    with (
        LinearClient("token", transport=errors_transport) as client,
        pytest.raises(LinearGraphQLError, match="bad query"),
    ):
        client.execute("query { viewer { id } }")


def test_retry_after_is_bounded_and_malformed_header_is_ignored() -> None:
    def response(value: str) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": value})

    for value, expected in (("5000", 3600.0), ("-4", 0.0), ("later", None)):
        transport = httpx.MockTransport(lambda _, value=value: response(value))
        with LinearClient("token", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
            client.execute("query { viewer { id } }")
        assert error.value.retry_after == expected
