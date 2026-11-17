# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""The board's own `.previous-version/` export inside the Reviewer's disposable checkout
(SAVED_DATA_UPGRADE_SAFETY.md spec 3.4.1), and the request-time refusal of a candidate that
already tracks that reserved name (spec 3.4.1's other half, _saved_data_request_info).
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import board


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_head(cwd: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class PreviousVersionExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "repo"
        self.workspace.mkdir()
        _git(["init", "-q", "-b", "main"], self.workspace)
        _git(["config", "user.email", "harness@example.invalid"], self.workspace)
        _git(["config", "user.name", "Harness"], self.workspace)
        (self.workspace / "app.py").write_text("VERSION = 1\n")
        _git(["add", "."], self.workspace)
        _git(["commit", "-qm", "v1"], self.workspace)
        self.previous_commit = _git_head(self.workspace)
        (self.workspace / "app.py").write_text("VERSION = 2\n")
        (self.workspace / "ledger.md").write_text(
            "| ID | What was tested | Simulation command | Expected system response | Observed system response | QA result |\n"
            "|---|---|---|---|---|---|\n| S-1 | ok | true | ok | ok | PASS |\n"
        )
        _git(["add", "."], self.workspace)
        _git(["commit", "-qm", "v2"], self.workspace)
        self.candidate_commit = _git_head(self.workspace)
        self.state = {"task_workspaces": {"T": str(self.workspace)}, "subtask_workspaces": {}}

    def _request(self, saved_data_info: dict) -> dict:
        return {"task": "T", "subtask": "", "reviewed_commit": self.candidate_commit, "saved_data": saved_data_info}

    def test_declared_changed_known_previous_exports_the_real_old_files(self):
        request = self._request({"rules": True, "declared_changed": True, "previous_state": "known", "previous_commit": self.previous_commit})
        with board._review_candidate_checkout(self.root, self.state, request, self.workspace / "ledger.md") as (checkout, _ledger):
            self.assertEqual((checkout / ".previous-version" / "app.py").read_text(), "VERSION = 1\n")
            self.assertEqual((checkout / "app.py").read_text(), "VERSION = 2\n")   # the candidate itself is untouched

    def test_unchanged_task_gets_no_previous_version_folder(self):
        request = self._request({"rules": False, "declared_changed": False, "previous_state": "known", "previous_commit": self.previous_commit})
        with board._review_candidate_checkout(self.root, self.state, request, self.workspace / "ledger.md") as (checkout, _ledger):
            self.assertFalse((checkout / ".previous-version").exists())

    def test_declared_changed_but_first_version_gets_no_previous_version_folder(self):
        request = self._request({"rules": True, "declared_changed": True, "previous_state": "first", "previous_commit": ""})
        with board._review_candidate_checkout(self.root, self.state, request, self.workspace / "ledger.md") as (checkout, _ledger):
            self.assertFalse((checkout / ".previous-version").exists())

    def test_request_review_refuses_a_candidate_that_already_tracks_dot_previous_version(self):
        (self.workspace / ".previous-version").mkdir()
        (self.workspace / ".previous-version" / "x.txt").write_text("x\n")
        _git(["add", "."], self.workspace)
        _git(["commit", "-qm", "tracked .previous-version"], self.workspace)
        review_artifact = {"files": [".previous-version/x.txt", "app.py"], "available": True}
        with self.assertRaisesRegex(ValueError, "\\.previous-version"):
            board._saved_data_request_info(self.root, self.workspace, review_artifact, "", "Saved data: changed — a thing")
