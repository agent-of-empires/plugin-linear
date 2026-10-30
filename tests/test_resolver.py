from __future__ import annotations

import json

import httpx
import pytest

from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.errors import LinearGraphQLError, LinearRateLimitError
from aoe_linear_plugin.resolver import branch_is_linear, identifiers_in_branch, resolve_branch, selected_issue


def test_branch_identifiers_are_normalized_deduplicated_and_bounded() -> None:
    assert identifiers_in_branch("feature/eng-12-add-eng-12-and-OPS-4x") == ["ENG-12"]
    assert identifiers_in_branch("fix/OPS-4-more") == ["OPS-4"]
    assert identifiers_in_branch("fix/ENG-0") == []


def test_dependency_branches_are_not_treated_as_linear_work() -> None:
    assert branch_is_linear("feature/ENG-12-add-work") is True
    assert branch_is_linear("eng-12-fix") is True
    assert branch_is_linear("dependabot/pip/httpx-0.27.0") is False
    assert branch_is_linear("renovate/major-react-monorepo") is False
    assert branch_is_linear("main") is False


def test_resolve_branch_combines_branch_metadata_and_identifiers() -> None:
    requested = []

    def respond(request):
        variables = json.loads(request.content)["variables"]
        if "branchName" in variables:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": {"id": "1", "identifier": "ENG-2"}}})
        requested.append(variables["id"])
        return httpx.Response(200, json={"data": {"issue": {"id": "2", "identifier": "OPS-7"}}})

    with LinearClient("key", transport=httpx.MockTransport(respond)) as client:
        issues = resolve_branch(client, "feature/ENG-2-add-OPS-7")
    assert [issue["identifier"] for issue in issues] == ["ENG-2", "OPS-7"]
    assert requested == ["OPS-7"]


@pytest.mark.parametrize("branch", ["eng-12-fix-utf-8-decoding", "fix/issue-42", "chore/bump-python-3.12"])
def test_speculative_graphql_failure_preserves_branch_match(branch) -> None:
    issue = {"id": "1", "identifier": "ENG-12"}

    def respond(request):
        variables = json.loads(request.content)["variables"]
        if "branchName" in variables:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": issue}})
        return httpx.Response(200, json={"data": None, "errors": [{"message": "Entity not found: Issue"}]})

    with LinearClient("key", transport=httpx.MockTransport(respond)) as client:
        assert resolve_branch(client, branch) == [issue]


def test_identifier_resolution_keeps_valid_issue_before_unknown_identifier() -> None:
    issue = {"id": "1", "identifier": "ENG-12"}

    def respond(request):
        variables = json.loads(request.content)["variables"]
        if "branchName" in variables:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": None}})
        if variables["id"] == "ENG-12":
            return httpx.Response(200, json={"data": {"issue": issue}})
        return httpx.Response(200, json={"data": None, "errors": [{"message": "Entity not found: Issue"}]})

    with LinearClient("key", transport=httpx.MockTransport(respond)) as client:
        assert resolve_branch(client, "eng-12-fix-utf-8-decoding") == [issue]


def test_speculative_lookup_count_is_bounded() -> None:
    requested = []

    def respond(request):
        variables = json.loads(request.content)["variables"]
        if "branchName" in variables:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": None}})
        requested.append(variables["id"])
        return httpx.Response(200, json={"data": None, "errors": [{"message": "Entity not found: Issue"}]})

    with LinearClient("key", transport=httpx.MockTransport(respond)) as client:
        assert resolve_branch(client, "-".join(f"ISSUE-{i}" for i in range(1, 20))) == []
    assert requested == ["ISSUE-1", "ISSUE-2", "ISSUE-3", "ISSUE-4", "ISSUE-5"]


def test_branch_search_errors_and_identifier_rate_limits_are_not_hidden() -> None:
    with (
        LinearClient(
            "key",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"errors": [{"message": "invalid query"}]})
            ),
        ) as client,
        pytest.raises(LinearGraphQLError),
    ):
        resolve_branch(client, "ENG-12")

    def respond(request):
        if "branchName" in json.loads(request.content)["variables"]:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": None}})
        return httpx.Response(429, headers={"Retry-After": "60"})

    with LinearClient("key", transport=httpx.MockTransport(respond)) as client, pytest.raises(LinearRateLimitError):
        resolve_branch(client, "ENG-12")


def test_selection_prefers_explicit_identifier_and_falls_back_deterministically() -> None:
    issues = [{"identifier": "ENG-4"}, {"identifier": "ENG-5"}]
    assert selected_issue(issues, "eng-5") == issues[1]
    assert selected_issue(issues, "ENG-404") == issues[0]
    assert selected_issue([], None) is None
