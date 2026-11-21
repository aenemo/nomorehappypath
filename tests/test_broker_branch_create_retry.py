# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""branch_create must be bounded, retryable, and leave nothing behind on failure."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from harness.git_broker import (
    BrokerError,
    GitBroker,
    GitIdentity,
    RecoveryHoldError,
    git_timeout_seconds,
)
from harness.project_context import ProjectContext


class BranchCreateRetryTests(unittest.TestCase):
    """Fixtures mirror tests/test_git_broker.py so both suites exercise one broker setup."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "code"
        self.data = self.base / "data"
        self.workspaces = self.base / "workspaces"
        self.repository.mkdir()
        self._git(self.repository, "init", "-b", "main")
        (self.repository / "product.txt").write_text("base\n", encoding="utf-8")
        self._git(self.repository, "add", "product.txt")
        self._git(
            self.repository, "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-m", "base",
        )
        self.base_commit = self._git(self.repository, "rev-parse", "HEAD").strip()
        self.base_tree = self._git(self.repository, "rev-parse", "HEAD^{tree}").strip()
        self.state = {
            "agents": {
                "delivery": {
                    "id": "delivery", "role": "engineering", "task": "TASK",
                    "active": True, "session_id": "session-delivery",
                    "write_authority": True,
                },
                "cto": {
                    "id": "cto", "role": "cto", "task": "GLOBAL_MONITOR",
                    "active": True, "session_id": "session-cto",
                },
            },
            "delivery_plans": {
                "TASK": {
                    "mode": "application",
                    "subtasks": {"alpha": {"status": "open"}, "beta": {"status": "open"}},
                },
            },
            "task_repositories": {"TASK": str(self.repository)},
            "task_workspaces": {},
            "subtask_workspaces": {},
            "task_baselines": {"TASK": {"head": self.base_commit, "tree": self.base_tree}},
            "qa_requests": {},
            "release_decisions": {},
            "git_acceptances": {},
            "remote_push_instructions": {},
            "approved_remotes": {},
        }
        self.context = ProjectContext(self.repository, self.data, self.workspaces)
        self.broker = GitBroker(self.context, state_loader=lambda: self.state)

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, cwd: Path, *arguments: str, check: bool = True) -> str:
        result = subprocess.run(
            ["/usr/bin/git", *arguments], cwd=cwd, capture_output=True, text=True,
        )
        if check and result.returncode:
            self.fail(result.stderr or result.stdout)
        return result.stdout

    def task_workspace(self) -> Path:
        repository = self.repository.resolve()
        key = hashlib.sha256(str(repository).encode("utf-8")).hexdigest()[:12]
        return self.broker.context.workspace_root / f"{repository.name}-{key}" / "TASK"

    def journal_rows(self) -> list[dict]:
        path = self.broker.transactions_path
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def advance_main(self) -> None:
        (self.repository / "external.txt").write_text("external\n", encoding="utf-8")
        self._git(self.repository, "add", "external.txt")
        self._git(
            self.repository, "-c", "user.name=External", "-c",
            "user.email=external@example.invalid", "commit", "-m", "external",
        )

    def test_every_git_command_is_bounded_and_a_timeout_surfaces_as_broker_error(self):
        observed: list[object] = []
        real_run = subprocess.run

        def wedged(command, **kwargs):
            if "timeout" in kwargs:
                observed.append(kwargs["timeout"])
            if isinstance(command, (list, tuple)) and "worktree" in command and "add" in command:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return real_run(command, **kwargs)

        with mock.patch.dict(os.environ, {"HARNESS_GIT_TIMEOUT": "7"}), \
                mock.patch("harness.git_broker.subprocess.run", side_effect=wedged):
            with self.assertRaisesRegex(
                BrokerError, r"git worktree add was killed after 7 seconds",
            ):
                self.broker.branch_create("delivery", 1)
        self.assertTrue(observed)
        self.assertEqual(set(observed), {7})

    def test_timeout_environment_value_falls_back_to_the_default(self):
        for value in ("", "0", "-5", "not-a-number"):
            with self.subTest(value=value), \
                    mock.patch.dict(os.environ, {"HARNESS_GIT_TIMEOUT": value}):
                self.assertEqual(git_timeout_seconds(), 300)
        with mock.patch.dict(os.environ, {"HARNESS_GIT_TIMEOUT": "45"}):
            self.assertEqual(git_timeout_seconds(), 45)

        with mock.patch.dict(os.environ, {"HARNESS_GIT_TIMEOUT": "soon"}), \
                mock.patch(
                    "harness.git_broker.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(["git", "rev-parse"], 300),
                ):
            with self.assertRaisesRegex(
                BrokerError, r"git rev-parse --show-toplevel was killed after 300 seconds",
            ):
                self.broker.branch_create("delivery", 1)

    def test_retry_after_a_successful_create_adopts_the_same_start(self):
        first = self.broker.branch_create("delivery", 1)
        self.assertFalse(first["adopted"])
        second = self.broker.branch_create("delivery", 2)
        self.assertTrue(second["adopted"])
        for key in (
            "task", "subtask", "repository", "workspace", "branch",
            "base_commit", "base_tree", "inherited_tracked_paths",
        ):
            self.assertEqual(first[key], second[key], key)
        self.assertTrue(Path(second["workspace"]).is_dir())
        self.assertEqual(self._git(self.repository, "rev-parse", second["branch"]).strip(), self.base_commit)
        self.assertEqual(len(list((self.repository / ".git" / "worktrees").iterdir())), 1)
        self.assertTrue(any(
            row.get("step") == "adopted" and row.get("branch") == first["branch"]
            for row in self.journal_rows()
        ))
        nonces = json.loads(self.broker.nonces_path.read_text(encoding="utf-8"))
        self.assertEqual(nonces["session-delivery"], 2)

    def test_a_missing_worktree_is_rebuilt_from_the_existing_branch(self):
        first = self.broker.branch_create("delivery", 1)
        self._git(self.repository, "worktree", "remove", "--force", first["workspace"])
        self.assertFalse(Path(first["workspace"]).exists())
        rebuilt = self.broker.branch_create("delivery", 2)
        self.assertFalse(rebuilt["adopted"])
        self.assertEqual(rebuilt["branch"], first["branch"])
        self.assertTrue(Path(rebuilt["workspace"]).is_dir())
        self.assertEqual(self._git(self.repository, "rev-parse", rebuilt["branch"]).strip(), self.base_commit)
        self.assertEqual(self._git(Path(rebuilt["workspace"]), "status", "--porcelain"), "")

    def test_a_branch_repointed_at_another_commit_is_still_refused(self):
        first = self.broker.branch_create("delivery", 1)
        self.advance_main()
        moved = self._git(self.repository, "rev-parse", "HEAD").strip()
        self._git(self.repository, "update-ref", first["branch"], moved)
        self._git(self.repository, "reset", "--hard", self.base_commit)
        with self.assertRaisesRegex(BrokerError, "already exists"):
            self.broker.branch_create("delivery", 2)
        self.assertFalse(any(row.get("step") == "adopted" for row in self.journal_rows()))

    def test_a_moved_head_is_not_adopted_as_the_same_start(self):
        self.broker.branch_create("delivery", 1)
        self.advance_main()
        with self.assertRaisesRegex(BrokerError, "already exists"):
            self.broker.branch_create("delivery", 2)

    def test_a_failure_after_creation_removes_the_worktree_and_branch_and_stays_retryable(self):
        workspace = self.task_workspace()
        real_identity = GitBroker._identity
        calls = {"count": 0}

        def mismatched(broker, repository, revision="HEAD"):
            calls["count"] += 1
            identity = real_identity(broker, repository, revision)
            if calls["count"] == 2:
                return GitIdentity("0" * 40, identity.tree)
            return identity

        with mock.patch.object(GitBroker, "_identity", mismatched):
            with self.assertRaises(RecoveryHoldError):
                self.broker.branch_create("delivery", 1)

        self.assertEqual(calls["count"], 2)
        self.assertFalse(workspace.exists())
        self.assertEqual(
            self._git(self.repository, "rev-parse", "--verify", "refs/heads/harness/tasks/TASK/task", check=False),
            "",
        )
        cleanup = [row for row in self.journal_rows() if row.get("step") == "cleanup"]
        self.assertTrue(cleanup)
        self.assertTrue(cleanup[-1]["removed_worktree"])
        self.assertTrue(cleanup[-1]["removed_branch"])
        self.assertTrue(any(
            row.get("step") == "done" and row.get("status") == "aborted"
            for row in self.journal_rows()
        ))

        retried = self.broker.branch_create("delivery", 2)
        self.assertFalse(retried["adopted"])
        self.assertTrue(Path(retried["workspace"]).is_dir())
        self.assertEqual(retried["base_commit"], self.base_commit)


if __name__ == "__main__":
    unittest.main()
