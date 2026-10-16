from __future__ import annotations

from aoe_linear_plugin.uistate import PANE_SLOT, ROW_BADGE_SLOT, ROW_COLUMN_SLOT, session_payloads


def test_session_ui_shows_priority_state_selectable_issue_and_links() -> None:
    issues = [
        {
            "id": "2",
            "identifier": "ENG-2",
            "title": "Normal",
            "url": "https://linear.app/acme/issue/ENG-2",
            "priority": 3,
            "state": {"name": "Todo", "type": "unstarted"},
        },
        {
            "id": "1",
            "identifier": "ENG-1",
            "title": "Urgent",
            "url": "https://linear.app/acme/issue/ENG-1",
            "priority": 1,
            "state": {"name": "In Progress", "type": "started"},
            "assignee": {"displayName": "A User"},
            "labels": {"nodes": [{"name": "Bug"}, {"name": "Backend"}]},
            "attachments": [{"title": "Pull request", "url": "https://github.com/acme/repo/pull/1"}],
        },
    ]
    snapshot = {"sessions": [{"session_id": "s1", "issues": issues, "repos": []}]}
    payloads = session_payloads(snapshot, {"s1": "ENG-1"})
    by_slot = {item["slot"]: item["payload"] for item in payloads if item.get("session_id") == "s1"}

    assert by_slot[ROW_BADGE_SLOT[0]]["items"][0]["text"] == "ENG-1"
    assert by_slot[ROW_COLUMN_SLOT[0]]["text"] == "In Progress · ENG-1"
    assert by_slot[ROW_BADGE_SLOT[0]]["href"] == "https://linear.app/acme/issue/ENG-1"
    assert payloads[0]["payload"] == {
        "label": "Linear issue attention",
        "column": ROW_COLUMN_SLOT[1],
        "direction": "asc",
    }
    pane = by_slot[PANE_SLOT[0]]
    selector = next(block for block in pane["blocks"] if block.get("title") == "Linked issues")
    assert selector["children"][0]["prefix"] == "ENG-1"
    assert selector["children"][0]["method"] == "linear.select_issue"
    assert selector["children"][0]["selected"] is True
    assert selector["children"][0]["href"] == "https://linear.app/acme/issue/ENG-1"
    details = next(block for block in pane["blocks"] if block.get("title") == "Details")
    assert {"kind": "row", "label": "Labels", "value": "Bug, Backend"} in details["children"]
    resources = next(block for block in pane["blocks"] if block.get("title") == "Linked resources")
    assert resources["children"][0]["href"].startswith("https://github.com/")


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
                "issues": [{"identifier": "ENG-1", "title": "Urgent", "priority": 1, "state": {"name": "Todo"}}],
                "repos": [],
            }
        ]
    }
    pane = session_payloads(snapshot, show_priority=False)[-1]["payload"]
    selector = next(block for block in pane["blocks"] if block.get("title") == "Linked issues")
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
