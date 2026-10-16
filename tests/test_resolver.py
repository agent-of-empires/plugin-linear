from __future__ import annotations

from aoe_linear_plugin.resolver import identifiers_in_branch, resolve_branch, selected_issue


class Client:
    def __init__(self) -> None:
        self.identifier_requests: list[str] = []

    def issue_for_branch(self, branch: str) -> dict[str, str] | None:
        assert branch == "feature/ENG-2-add-OPS-7"
        return {"id": "1", "identifier": "ENG-2"}

    def issue_by_identifier(self, identifier: str) -> dict[str, str] | None:
        self.identifier_requests.append(identifier)
        return {"id": identifier, "identifier": identifier} if identifier == "OPS-7" else None


def test_branch_identifiers_are_normalized_deduplicated_and_bounded() -> None:
    assert identifiers_in_branch("feature/eng-12-add-eng-12-and-OPS-4x") == ["ENG-12"]
    assert identifiers_in_branch("fix/OPS-4-more") == ["OPS-4"]
    assert identifiers_in_branch("fix/ENG-0") == []


def test_resolve_branch_combines_branch_metadata_and_identifiers() -> None:
    client = Client()
    issues = resolve_branch(client, "feature/ENG-2-add-OPS-7")
    assert [issue["identifier"] for issue in issues] == ["ENG-2", "OPS-7"]
    assert client.identifier_requests == ["OPS-7"]


def test_selection_prefers_explicit_identifier_and_falls_back_deterministically() -> None:
    issues = [{"identifier": "ENG-4"}, {"identifier": "ENG-5"}]
    assert selected_issue(issues, "eng-5") == issues[1]
    assert selected_issue(issues, "ENG-404") == issues[0]
    assert selected_issue([], None) is None
