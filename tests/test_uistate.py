from __future__ import annotations

import json

import pytest

from aoe_linear_plugin.uistate import PANE_SLOT, ROW_BADGE_SLOT, ROW_COLUMN_SLOT, session_payloads


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

    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["text"] == "ENG-1"
    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["icon"] == "circle-dot"
    assert by_slot[ROW_COLUMN_SLOT[0]]["text"] == "In Progress"
    assert by_slot[ROW_BADGE_SLOT[0]]["href"] == "https://linear.app/acme/issue/ENG-1"
    assert payloads[0]["payload"] == {
        "label": "Linear issue attention",
        "column": ROW_COLUMN_SLOT[1],
        "direction": "asc",
    }

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


def test_issue_state_icons_follow_linear_workflow_types() -> None:
    states = [
        ("backlog", "circle-dashed"),
        ("unstarted", "circle"),
        ("started", "circle-dot"),
        ("completed", "circle-check"),
        ("canceled", "circle-x"),
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

    icons = [
        item["payload"]["items"][0]["icon"] for item in session_payloads(snapshot) if item["slot"] == ROW_BADGE_SLOT[0]
    ]
    assert icons == [expected_icon for _, expected_icon in states]


def test_no_issue_shows_api_error_without_fabricating_issue_state() -> None:
    snapshot = {"sessions": [{"session_id": "s1", "issues": [], "repos": [{"error": {"hint": "API unavailable"}}]}]}
    payloads = session_payloads(snapshot)
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}
    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["text"] == "Linear error"
    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["tone"] == "danger"
    assert by_slot[ROW_COLUMN_SLOT[0]]["tone"] == "danger"
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
    assert by_slot[ROW_COLUMN_SLOT[0]]["tone"] == "warn"
    assert by_slot[PANE_SLOT[0]]["blocks"][0]["tone"] == "warn"


def test_empty_stale_error_does_not_claim_cached_data() -> None:
    snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [],
                "repos": [{"error": {"hint": "Linear GraphQL error"}}],
                "stale": True,
            }
        ]
    }
    payloads = session_payloads(snapshot)
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}

    assert [item["text"] for item in by_slot[ROW_BADGE_SLOT[0]]["items"]] == ["Linear error"]
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


def test_attachment_with_null_subtitle_renders_without_a_null_label() -> None:
    issue = {
        "identifier": "ENG-1",
        "attachments": {"nodes": [{"title": "PR", "url": "https://github.com/acme/repo/pull/1", "subtitle": None}]},
    }
    pane = session_payloads({"sessions": [{"session_id": "s1", "issues": [issue]}]})[-1]["payload"]
    resources = next(block for block in pane["blocks"] if block.get("title") == "Linked resources")

    assert resources["children"][0]["sublabel"] == ""
    assert resources["children"][0]["href"] == "https://github.com/acme/repo/pull/1"
