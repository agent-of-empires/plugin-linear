from __future__ import annotations

import json

import httpx
import pytest

from aoe_linear_plugin.client import API_URL, LinearClient
from aoe_linear_plugin.errors import LinearAuthError, LinearGraphQLError, LinearRateLimitError


def test_graphql_query_sends_token_and_variables(recorded_linear_responses) -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        recorded = recorded_linear_responses["identifier_match"]
        return httpx.Response(recorded["http_status"], json=recorded["body"])

    with LinearClient("secret-token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_by_identifier("LIVE-1")

    assert seen["url"] == API_URL
    assert seen["authorization"] == "secret-token"
    assert seen["body"]["variables"] == {"id": "LIVE-1"}
    assert issue["identifier"] == "LIVE-1"
    assert issue["attachments"]["nodes"][0]["subtitle"] is None


def test_branch_lookup_uses_linear_vcs_branch_search(recorded_linear_responses) -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        recorded = recorded_linear_responses["branch_match"]
        return httpx.Response(recorded["http_status"], json=recorded["body"])

    with LinearClient("token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_for_branch("recorded/live-1-branch")

    assert seen["variables"] == {"branchName": "recorded/live-1-branch"}
    assert issue["identifier"] == "LIVE-1"
    assert issue["state"]["type"] == "started"


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Tue, 14 Nov 2023 22:13:35 GMT", 15.0),
        ("Tue, 14 Nov 2023 22:13:00 GMT", None),
        ("Tue, 14 Nov 2023 23:13:21 GMT", None),
        ("not-a-date", None),
    ],
)
def test_retry_after_http_dates_use_bounded_future_delays(monkeypatch, value, expected) -> None:
    monkeypatch.setattr("aoe_linear_plugin.client.time.time", lambda: 1700000000.0)
    transport = httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": value}))
    with LinearClient("token", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.execute("query { viewer { id } }")
    assert error.value.retry_after == expected


def test_rate_limit_delay_uses_exhausted_budget_reset_before_other_resets(monkeypatch) -> None:
    monkeypatch.setattr("aoe_linear_plugin.client.time.time", lambda: 1700000000.0)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            429,
            headers={
                "X-RateLimit-Requests-Remaining": "4",
                "X-RateLimit-Requests-Reset": "1700001000000",
                "X-RateLimit-Endpoint-Requests-Remaining": "0",
                "X-RateLimit-Endpoint-Requests-Reset": "1700000010000",
                "X-RateLimit-Complexity-Remaining": "2",
                "X-RateLimit-Complexity-Reset": "1700000500000",
            },
        )
    )
    with LinearClient("token", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.execute("query { viewer { id } }")
    assert error.value.retry_after == 10.0


def test_rate_limit_delay_falls_back_to_latest_reset_when_budget_unknown(monkeypatch) -> None:
    monkeypatch.setattr("aoe_linear_plugin.client.time.time", lambda: 1700000000.0)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            429,
            headers={
                "X-RateLimit-Requests-Remaining": "3",
                "X-RateLimit-Requests-Reset": "1700000010000",
                "X-RateLimit-Endpoint-Requests-Reset": "1700000020000",
            },
        )
    )
    with LinearClient("token", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.execute("query { viewer { id } }")
    assert error.value.retry_after == 20.0


@pytest.mark.parametrize("status", [200, 400])
def test_linear_graphql_rate_limit_uses_epoch_millisecond_reset(monkeypatch, status) -> None:
    monkeypatch.setattr("aoe_linear_plugin.client.time.time", lambda: 1700000000.0)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            status,
            headers={"X-RateLimit-Requests-Reset": "1700000045000"},
            json={"errors": [{"message": "rate limited", "extensions": {"code": "RATELIMITED"}}]},
        )
    )
    with LinearClient("key", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.issue_for_branch("feature/example")
    assert error.value.kind == "rate_limited"
    assert error.value.retry_after == 45.0


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf"])
def test_nonfinite_retry_after_does_not_disable_backoff(value) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": value}))
    with LinearClient("key", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.issue_for_branch("feature/example")
    assert error.value.retry_after is None


def test_http_400_graphql_error_is_not_a_network_failure() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(400, json={"errors": [{"message": "Entity not found: Issue"}], "data": None})
    )
    with LinearClient("key", transport=transport) as client, pytest.raises(LinearGraphQLError):
        client.issue_by_identifier("EXAMPLE-1")


@pytest.mark.parametrize(("reset", "expected"), [("1700000000000", 0.0), ("1700010000000", 3600.0), ("nan", None)])
def test_rate_limit_reset_is_bounded_and_finite(monkeypatch, reset, expected) -> None:
    monkeypatch.setattr("aoe_linear_plugin.client.time.time", lambda: 1700000000.0)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            400,
            headers={"X-RateLimit-Requests-Reset": reset},
            json={"errors": [{"extensions": {"code": "RATELIMITED"}}]},
        )
    )
    with LinearClient("key", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
        client.issue_for_branch("feature/example")
    assert error.value.retry_after == expected
