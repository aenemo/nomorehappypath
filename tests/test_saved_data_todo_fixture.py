# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Section 12.5's worked example, proven for real: a two-version to-do app whose v2 adds a due
date (SAVED_DATA_UPGRADE_SAFETY.md section 5). This is the pattern the board's saved-data upgrade
check (harness/saved_data.py, .previous-version export in board._review_candidate_checkout) exists
to let a real Reviewer run: start the old version, save data, back it up, upgrade, then ALWAYS go
back and compare with the backup - proven here for a good upgrade, one that drops data, and one
that crashes mid-way, each followed by a successful restore.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _seed_v1(db_path: Path) -> list[dict]:
    """The old version's own save path: three to-dos, no due date field at all."""
    todos = [{"id": 1, "text": "Buy milk"}, {"id": 2, "text": "Walk the dog"}, {"id": 3, "text": "Pay rent"}]
    db_path.write_text(json.dumps(todos))
    return todos


def _upgrade_good(db_path: Path) -> None:
    """v2's real migration: every saved to-do gains an empty due date; nothing else changes."""
    todos = json.loads(db_path.read_text())
    for todo in todos:
        todo.setdefault("due", None)
    db_path.write_text(json.dumps(todos))


def _upgrade_drops_text(db_path: Path) -> None:
    """A BROKEN migration: it keeps the ids but drops each to-do's own text (real data loss)."""
    todos = json.loads(db_path.read_text())
    db_path.write_text(json.dumps([{"id": todo["id"], "due": None} for todo in todos]))


def _upgrade_crashes_midway(db_path: Path) -> None:
    """A migration that fails partway through: it truncates the file, then raises."""
    db_path.write_text("")
    raise RuntimeError("simulated crash mid-migration")


class TodoUpgradeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "todo.db"
        self.backup = Path(self.tmp.name) / "todo.db.backup"
        self.saved = _seed_v1(self.db)                 # "the old version saves data" (3.4.3.b)
        self.backup.write_bytes(self.db.read_bytes())  # "makes the backup ... before the update" (3.4.3.c)

    def _go_back(self) -> list[dict]:
        """"## If something goes wrong": stop, put the backup back, start the previous version (3.4.3.e)."""
        self.db.write_bytes(self.backup.read_bytes())
        return json.loads(self.db.read_text())

    def test_good_upgrade_row_passes_and_data_survives(self):
        _upgrade_good(self.db)
        upgraded = json.loads(self.db.read_text())
        self.assertEqual([todo["text"] for todo in upgraded], [todo["text"] for todo in self.saved])
        self.assertTrue(all(todo["due"] is None for todo in upgraded))
        # 3.4.3.e: the go-back still runs and still matches the snapshot, even after a passing upgrade.
        self.assertEqual(self._go_back(), self.saved)

    def test_upgrade_that_drops_data_fails_and_the_go_back_still_restores_it(self):
        _upgrade_drops_text(self.db)
        upgraded = json.loads(self.db.read_text())
        self.assertFalse(all("text" in todo for todo in upgraded), "the broken migration must actually have lost the text field")
        restored = self._go_back()
        self.assertEqual(restored, self.saved, "the go-back must restore the exact pre-upgrade data even though the upgrade itself failed")

    def test_upgrade_that_crashes_midway_fails_and_the_go_back_still_restores_it(self):
        with self.assertRaises(RuntimeError):
            _upgrade_crashes_midway(self.db)
        self.assertEqual(self.db.read_text(), "", "the simulated crash must actually have left the data file truncated")
        restored = self._go_back()
        self.assertEqual(restored, self.saved, "the go-back must restore the exact pre-upgrade data even after a crash mid-upgrade")

    def test_restored_data_is_compared_by_content_not_a_count(self):
        _upgrade_good(self.db)
        restored = self._go_back()
        self.assertEqual(restored, self.saved)
        self.assertEqual([todo["id"] for todo in restored], [1, 2, 3])
        self.assertEqual([todo["text"] for todo in restored], ["Buy milk", "Walk the dog", "Pay rent"])
