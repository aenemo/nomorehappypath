# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""The owner's separate backup confirmation on Accept (SAVED_DATA_UPGRADE_SAFETY.md section 3.5),
proven directly against record_release_decision: refused without it, refused with the wrong value,
accepted with the frozen snapshot's own sha256, kept on a retried Accept, and a fresh release needs
a fresh one. Also: the rendered Accept card always carries the box and confirm checkbox markup
(section 12.7 - the Reviewer's own contract check for this is tests/test_saved_data.py's sibling
fixture; this file is the permanent, delivered proof).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness import board, board_viewer


class AcceptConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _release(self, task: str, saved_data: dict) -> None:
        with board.locked_state(self.root) as state:
            state.setdefault("releases", {})[task] = {
                "task": task, "status": "VISUAL_TEST_REQUIRED",
                "head_commit": "abc123", "cto_id": "cto-test", "recorded_at": board.now(),
                "saved_data": saved_data,
            }

    def test_unchanged_release_needs_no_confirmation(self):
        self._release("T-UNCHANGED", {"status": "unchanged"})
        response = board.record_release_decision(self.root, "T-UNCHANGED", "accepted")
        self.assertEqual(response["decision"], "accepted")

    def test_changed_release_refuses_accept_without_confirmation(self):
        self._release("T-CHANGED", {"status": "changed", "what": "a due date", "sha256": "deadbeef"})
        with self.assertRaisesRegex(ValueError, "backup"):
            board.record_release_decision(self.root, "T-CHANGED", "accepted")

    def test_changed_release_refuses_accept_with_the_wrong_confirmation(self):
        self._release("T-WRONG", {"status": "changed", "what": "a due date", "sha256": "deadbeef"})
        with self.assertRaisesRegex(ValueError, "backup"):
            board.record_release_decision(self.root, "T-WRONG", "accepted", saved_data_confirmed="not-the-right-hash")

    def test_changed_release_accepts_with_the_frozen_sha256(self):
        self._release("T-RIGHT", {"status": "changed", "what": "a due date", "sha256": "deadbeef"})
        response = board.record_release_decision(self.root, "T-RIGHT", "accepted", saved_data_confirmed="deadbeef")
        self.assertEqual(response["decision"], "accepted")
        self.assertEqual(response["saved_data_confirmed"], "deadbeef")

    def test_a_different_release_needs_a_fresh_confirmation(self):
        # First release of this task is confirmed and accepted.
        self._release("T-REPLACED", {"status": "changed", "what": "a due date", "sha256": "first-hash"})
        board.record_release_decision(self.root, "T-REPLACED", "accepted", saved_data_confirmed="first-hash")
        # A repaired release of the SAME task gets a new snapshot (record_release_ready supersedes the
        # old decision, per the existing "new candidate supersedes an earlier response" rule) and needs
        # its own confirmation; the old hash from the earlier release must not still work.
        with board.locked_state(self.root) as state:
            state["release_decisions"].pop("T-REPLACED", None)
        self._release("T-REPLACED", {"status": "changed", "what": "a due date, take two", "sha256": "second-hash"})
        with self.assertRaisesRegex(ValueError, "backup"):
            board.record_release_decision(self.root, "T-REPLACED", "accepted", saved_data_confirmed="first-hash")
        response = board.record_release_decision(self.root, "T-REPLACED", "accepted", saved_data_confirmed="second-hash")
        self.assertEqual(response["decision"], "accepted")

    def test_accept_refuses_when_main_moved_since_the_upgrade_check_ran(self):
        # spec 3.1: the upgrade check proved the move from `previous_commit`; if the release's own
        # acceptance_base_commit (main as it stands now) has since moved past that, the check no
        # longer proves anything about what this release would actually upgrade from.
        self._release("T-STALE", {
            "status": "changed", "what": "a due date", "sha256": "deadbeef", "previous_commit": "original-main",
        })
        with board.locked_state(self.root) as state:
            state["releases"]["T-STALE"]["acceptance_base_commit"] = "main-moved-since"
        with self.assertRaisesRegex(ValueError, "different version"):
            board.record_release_decision(self.root, "T-STALE", "accepted", saved_data_confirmed="deadbeef")

    def test_accept_succeeds_when_acceptance_base_still_matches_previous_commit(self):
        self._release("T-FRESH", {
            "status": "changed", "what": "a due date", "sha256": "deadbeef", "previous_commit": "original-main",
        })
        with board.locked_state(self.root) as state:
            state["releases"]["T-FRESH"]["acceptance_base_commit"] = "original-main"
        response = board.record_release_decision(self.root, "T-FRESH", "accepted", saved_data_confirmed="deadbeef")
        self.assertEqual(response["decision"], "accepted")

    def test_not_accepted_needs_no_confirmation_even_for_a_changed_release(self):
        self._release("T-REJECT", {"status": "changed", "what": "a due date", "sha256": "deadbeef"})
        response = board.record_release_decision(self.root, "T-REJECT", "not_accepted", reason="I want to review it more first")
        self.assertEqual(response["decision"], "not_accepted")


class ReleaseSnapshotReadsTheReviewerVerdictTests(unittest.TestCase):
    """Regression for certified finding S-002 (review round 1): the frozen release must read the
    Reviewer's own verdict (result_summary), never Delivery's hand-in summary - the two can freely
    disagree (Delivery declares WHAT changed; only the Reviewer's line carries the outcome)."""

    def test_snapshot_uses_result_summary_not_delivery_summary(self):
        request = {
            "reviewed_commit": "", "reviewed_tree_hash": "", "id": "R1",
            "saved_data": {
                "rules": True, "declared_changed": True, "description": "each to-do gains a due date",
                "previous_commit": "", "previous_state": "first", "hint_paths": [],
            },
            "summary": "Saved data: unchanged",  # Delivery's hand-in text; must be ignored here
            "result_summary": (
                "TASK DONE: YES\nSecurity check: fine.\n"
                "Saved data: changed — each to-do gains a due date — first version, nothing to upgrade"
            ),
        }
        snapshot = board._saved_data_release_snapshot(Path("/tmp"), {"task_workspaces": {}}, "T", request)
        self.assertEqual(snapshot["status"], "changed")
        self.assertEqual(snapshot["result"], "first_version")


class AcceptCardMarkupTests(unittest.TestCase):
    def test_rendered_page_always_carries_the_box_and_confirm_markup(self):
        html = board_viewer.rendered_page(project_name="Sample")
        self.assertIn("Saved data", html)
        self.assertIn("I have made the backup", html)
        self.assertIn("saved-data-confirm-checkbox", html)
        self.assertIn("savedDataConfirmChanged", html)
