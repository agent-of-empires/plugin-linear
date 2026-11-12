from __future__ import annotations

import json

import pytest

from aoe_linear_plugin.uistate import PANE_SLOT, ROW_BADGE_SLOT, session_payloads


def test_session_payloads_publish_only_a_row_badge_and_pane() -> None:
    """The row has no identifier or status column, and no sort key or filter facet follows one."""
    snapshot = {
        "sessions": [
            {"session_id": "s1", "issues": [{"identifier": "ENG-1", "state": {"type": "started"}}], "repos": []},
            {"session_id": "s2", "issues": [], "repos": []},
        ]
    }
    payloads = session_payloads(snapshot, {"s1": "ENG-1"})

    assert [item["slot"] for item in payloads] == [ROW_BADGE_SLOT[0], PANE_SLOT[0], ROW_BADGE_SLOT[0], PANE_SLOT[0]]
    assert [item["session_id"] for item in payloads] == ["s1", "s1", "s2", "s2"]


def test_session_ui_shows_linear_status_and_selectable_linked_issues(recorded_linear_responses) -> None:
    issues = [
        {
            "id": "2",
            "identifier": "ENG-2",
            "title": "Normal",
            "url": "https://linear.app/acme/issue/ENG-2",
            "priority": 3,
            "state": {"name": "Todo", "type": "unstarted", "color": "#aaaaaa"},
        },
        {
            "id": "1",
            "identifier": "ENG-1",
            "title": "Urgent",
            "url": "https://linear.app/acme/issue/ENG-1",
            "priority": 1,
            "state": {"name": "In Progress", "type": "started", "color": "#5e6ad2"},
            "assignee": {"displayName": "A User"},
            "labels": {"nodes": [{"name": "Bug"}, {"name": "Backend"}]},
            "attachments": recorded_linear_responses["branch_match"]["body"]["data"]["issueVcsBranchSearch"][
                "attachments"
            ],
            "comments": {"nodes": [{"id": "comment-1", "body": "The fix is ready.", "user": {"name": "A User"}}]},
        },
    ]
    snapshot = {"sessions": [{"session_id": "s1", "issues": issues, "repos": []}]}
    payloads = session_payloads(snapshot, {"s1": "ENG-1"})
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}

    assert set(by_slot) == {ROW_BADGE_SLOT[0], PANE_SLOT[0]}
    assert by_slot[ROW_BADGE_SLOT[0]]["items"] == [
        {
            "text": "◐",
            "tone": "info",
            "href": "https://linear.app/acme/issue/ENG-1",
            "tooltip": "In Progress · Urgent",
        }
    ]
    assert by_slot[ROW_BADGE_SLOT[0]]["href"] == "https://linear.app/acme/issue/ENG-1"

    pane = by_slot[PANE_SLOT[0]]
    callout = next(block for block in pane["blocks"] if block.get("kind") == "callout")
    assert callout["title"] == "ENG-1 · In Progress"
    assert callout["detail"] == "Urgent"
    assert callout["icon"] == "circle-dot"
    assert callout["color"] == "#5e6ad2"

    selector = next(block for block in pane["blocks"] if block.get("title") == "Other linked issues")
    assert [row["prefix"] for row in selector["children"]] == ["ENG-2"]
    assert selector["children"][0]["method"] == "linear.select_issue"
    assert selector["children"][0]["href"] == "https://linear.app/acme/issue/ENG-2"
    details = next(block for block in pane["blocks"] if block.get("title") == "Details")
    assert {"kind": "row", "label": "Labels", "value": "Bug, Backend"} in details["children"]
    resources = next(block for block in pane["blocks"] if block.get("title") == "Linked resources")
    assert resources["children"][0]["href"] == "https://example.invalid/recorded-resource"
    comments = next(block for block in pane["blocks"] if block.get("title") == "Comments")
    assert comments["children"] == [{"kind": "comment", "author": "A User", "body": "The fix is ready."}]


def test_row_badge_is_one_glyph_per_linear_workflow_type() -> None:
    states = [
        ("backlog", "◌"),
        ("unstarted", "○"),
        ("started", "◐"),
        ("completed", "●"),
        ("canceled", "✕"),
    ]
    snapshot = {
        "sessions": [
            {
                "session_id": f"s{index}",
                "issues": [{"identifier": "ENG-1", "title": "Task", "state": {"name": state_type, "type": state_type}}],
                "repos": [],
            }
            for index, (state_type, _) in enumerate(states)
        ]
    }

    glyphs = [
        item["payload"]["items"][0]["text"] for item in session_payloads(snapshot) if item["slot"] == ROW_BADGE_SLOT[0]
    ]
    assert glyphs == [glyph for _, glyph in states]


def test_no_issue_shows_api_error_without_fabricating_issue_state() -> None:
    snapshot = {
        "sessions": [
            {"session_id": "s1", "issues": [], "linked": True, "repos": [{"error": {"hint": "API unavailable"}}]}
        ]
    }
    payloads = session_payloads(snapshot)
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}
    assert by_slot[ROW_BADGE_SLOT[0]]["items"] == [{"text": "!", "tone": "danger", "tooltip": "API unavailable"}]
    assert any(block.get("title") == "Linear unavailable" for block in by_slot[PANE_SLOT[0]]["blocks"])


def test_show_priority_setting_hides_priority_badges_only() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [
                    {"identifier": "ENG-1", "title": "Urgent", "priority": 1, "state": {"name": "Todo"}},
                    {"identifier": "ENG-2", "title": "Normal", "priority": 2, "state": {"name": "Todo"}},
                ],
                "repos": [],
            }
        ]
    }
    pane = session_payloads(snapshot, show_priority=False)[-1]["payload"]
    selector = next(block for block in pane["blocks"] if block.get("title") == "Other linked issues")
    assert "badges" not in selector["children"][0]
    assert pane["blocks"][0]["title"].startswith("ENG-1")


def test_stale_cache_is_visible_in_row_and_pane() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [{"identifier": "ENG-1", "title": "Task", "state": {"name": "Todo"}}],
                "repos": [],
                "stale": True,
            }
        ]
    }
    payloads = session_payloads(snapshot)
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}
    assert by_slot[ROW_BADGE_SLOT[0]]["items"][-1]["text"] == "stale"
    # The labelled chip carries staleness; the status glyph keeps its workflow tone.
    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["tone"] == "neutral"
    assert by_slot[PANE_SLOT[0]]["blocks"][0]["tone"] == "warn"


def test_row_status_color_follows_the_workflow_state_not_priority() -> None:
    states = [
        ("In Progress", "started", "info"),
        ("Done", "completed", "success"),
        ("Canceled", "canceled", "neutral"),
        ("Todo", "unstarted", "neutral"),
    ]
    snapshot = {
        "sessions": [
            {
                "session_id": f"s{index}",
                "issues": [{"identifier": "ENG-1", "priority": 1, "state": {"name": name, "type": state_type}}],
                "repos": [],
            }
            for index, (name, state_type, _) in enumerate(states)
        ]
    }
    payloads = session_payloads(snapshot)

    badges = {item["session_id"]: item["payload"]["items"][0] for item in payloads if item["slot"] == ROW_BADGE_SLOT[0]}
    assert {sid: badge["tone"] for sid, badge in badges.items()} == {
        f"s{index}": tone for index, (_, _, tone) in enumerate(states)
    }


def test_empty_stale_error_does_not_claim_cached_data() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [],
                "linked": True,
                "repos": [{"error": {"hint": "Linear GraphQL error"}}],
                "stale": True,
            }
        ]
    }
    payloads = session_payloads(snapshot)
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}

    assert [item["text"] for item in by_slot[ROW_BADGE_SLOT[0]]["items"]] == ["!"]
    assert [block.get("title") for block in by_slot[PANE_SLOT[0]]["blocks"]] == ["Linear unavailable"]


@pytest.mark.parametrize("character", ["日", "🙂", "\x01"])
def test_pane_budget_keeps_newest_comments_with_multibyte_and_escaped_text(character: str) -> None:
    issue = {
        "identifier": "ENG-1",
        "title": "Task",
        "description": character * 4000,
        "comments": {"nodes": [{"body": character * 2000, "user": {"name": f"Author {index}"}} for index in range(10)]},
    }
    pane = session_payloads({"sessions": [{"session_id": "s1", "issues": [issue]}]})[-1]["payload"]

    assert len(json.dumps(pane, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 64 * 1024
    comments = next(block for block in pane["blocks"] if block.get("title") == "Comments")
    authors = [comment["author"] for comment in comments["children"]]
    assert authors == [f"Author {index}" for index in range(10 - len(authors), 10)]
    assert "Author 0" not in authors
    assert authors[-1] == "Author 9"
    assert comments["value"] == str(len(authors))
    description = next(block for block in pane["blocks"] if block.get("title") == "Description")
    assert description["children"][0]["text"] == issue["description"]
    assert len(issue["comments"]["nodes"]) == 10


def test_pane_budget_trims_description_after_removing_comments() -> None:
    issue = {
        "identifier": "ENG-1",
        "title": "Task",
        "description": "🙂" * 4000,
        "attachments": {"nodes": [{"title": "x" * 3000, "url": "https://example.com"} for _ in range(15)]},
        "comments": {"nodes": [{"body": "Newest comment", "user": {"name": "A User"}}]},
    }
    pane = session_payloads({"sessions": [{"session_id": "s1", "issues": [issue]}]})[-1]["payload"]

    assert len(json.dumps(pane, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 64 * 1024
    assert not any(block.get("title") == "Comments" for block in pane["blocks"])
    description = next(block for block in pane["blocks"] if block.get("title") == "Description")
    text = description["children"][0]["text"]
    assert text.endswith("…")
    assert issue["description"].startswith(text[:-1])
    assert text != issue["description"]
    resources = next(block for block in pane["blocks"] if block.get("title") == "Linked resources")
    assert len(resources["children"]) == 15


def test_pane_budget_also_bounds_oversized_issue_metadata() -> None:
    issue = {"identifier": "ENG-1", "title": "🙂" * (64 * 1024)}
    pane = session_payloads({"sessions": [{"session_id": "s1", "issues": [issue]}]})[-1]["payload"]

    assert len(json.dumps(pane, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 64 * 1024
    assert any("omitted" in block.get("text", "") for block in pane["blocks"])


def test_partial_repo_failure_is_visible_without_claiming_cached_data() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [{"identifier": "ENG-1", "title": "Task"}],
                "repos": [{"error": None}, {"error": {"hint": "Authentication failed"}}],
                "stale": False,
            }
        ]
    }
    pane = session_payloads(snapshot)[-1]["payload"]

    assert any(block.get("detail") == "Authentication failed" for block in pane["blocks"])
    assert any(block.get("title", "").startswith("ENG-1") for block in pane["blocks"])
    assert not any("cached" in block.get("text", "") for block in pane["blocks"])


def test_session_without_linear_work_publishes_no_linear_state() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [],
                "linked": False,
                "repos": [
                    {"path": "/repo", "branch": "main", "issues": [], "linked": False, "error": None},
                    # Defensive: a leftover error on an unlinked checkout must still stay quiet.
                    {"path": "/repo2", "branch": "develop", "issues": [], "linked": False, "error": {"hint": "x"}},
                ],
            }
        ]
    }
    payloads = session_payloads(snapshot)

    session_payloads_by_slot = [item["slot"] for item in payloads if item.get("session_id") == "s1"]
    assert session_payloads_by_slot == [ROW_BADGE_SLOT[0], PANE_SLOT[0]]
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}
    assert by_slot[ROW_BADGE_SLOT[0]] == {"items": []}
    assert not any(block.get("tone") in {"warn", "danger"} for block in by_slot[PANE_SLOT[0]]["blocks"])


def test_attachment_with_null_subtitle_renders_without_a_null_label() -> None:
    issue = {
        "identifier": "ENG-1",
        "attachments": {"nodes": [{"title": "PR", "url": "https://github.com/acme/repo/pull/1", "subtitle": None}]},
    }
    pane = session_payloads({"sessions": [{"session_id": "s1", "issues": [issue]}]})[-1]["payload"]
    resources = next(block for block in pane["blocks"] if block.get("title") == "Linked resources")

    assert resources["children"][0]["sublabel"] == ""
    assert resources["children"][0]["href"] == "https://github.com/acme/repo/pull/1"
