"""A local `board.py --root <project>` uses the folders NMHP registered for that project (2026-11-20).

Lease and contract analysis: a command run with only --root bound the task to a worktree in the legacy
<parent>/.harness-task-workspaces folder, where the project's agents may not write. These tests drive board.main
exactly that way against a private registry."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import board, board_client, control, project_registry
from harness.project_context import ProjectContext
from tests.requirements_support import agreed_requirements


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class BoardCliRegisteredFoldersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.home = base / "manager-home"
        self.code = base / "projects" / "lease"
        self.code.mkdir(parents=True)
        # Both registered folders differ from the legacy layout, as for any project NMHP registers with its own folders.
        self.data = self.home / "projects" / "lease-id" / "data"
        self.workspace = self.home / "workspaces" / "lease-id"
        self.workspace.mkdir(parents=True)
        self.context = ProjectContext(self.code, self.data, self.workspace)
        self.legacy = ProjectContext.compatibility(self.code)
        clean = {key: value for key, value in os.environ.items() if not key.startswith("HARNESS_BOARD_")}
        clean.pop("HARNESS_CERTIFIED_BOARD", None)
        self.environment = patch.dict(os.environ, clean, clear=True)
        self.environment.start()
        self.home_patch = patch.object(project_registry, "default_home", return_value=self.home)
        self.home_patch.start()

    def tearDown(self):
        self.home_patch.stop()
        self.environment.stop()
        self.tmp.cleanup()

    def _register(self, *entries):
        project_registry.save(self.home, {"version": project_registry.REGISTRY_VERSION, "projects": list(entries)})

    def _entry(self, code=None, workspace=None, project_id="lease-id"):
        return {"id": project_id, "name": "Lease", "kind": "scaffold", "code_root": str(code or self.code),
                "data_root": str(self.data), "workspace_root": str(workspace or self.workspace)}

    def _args(self, root=None):
        return board.build_parser().parse_args(["--root", str(root or self.code), "poll", "--agent", "x"])

    def _quiet(self, function, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            value = function(*args)
        return value, err.getvalue()

    def _repository(self):
        repository = self.code.parent / "lease-product"
        repository.mkdir()
        _git("init", "-q", "-b", "main", cwd=repository)
        _git("config", "user.email", "harness@example.invalid", cwd=repository)
        _git("config", "user.name", "Harness", cwd=repository)
        (repository / "product.txt").write_text("baseline\n")
        _git("add", "product.txt", cwd=repository)
        _git("commit", "-qm", "baseline", cwd=repository)
        return repository

    def _delivery(self, task):
        session = control.create(self.context, "codex_delivery")
        agent = board.register(self.context, "development", board.AWAITING_OWNER_DIRECTION, vendor="OpenAI", session_id=session["id"])
        board.record_owner_direction(self.context, session["id"], "Build the lease analyzer.")
        board.begin_task(self.context, agent["id"], task)
        agreed_requirements(self.context, agent["id"], f"Final agreed requirements for {task}: build and verify it end to end.")
        return agent

    def _main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = board.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_a_root_only_command_binds_the_task_inside_the_registered_folders(self):
        self._register(self._entry())
        repository = self._repository()
        agent = self._delivery("LEASE-BIND")
        code, _out, err = self._main("--root", str(self.code), "bind-repository", "--agent", agent["id"], "--repo", str(repository))
        self.assertEqual(code, 0, err)
        state = board.snapshot(self.context)
        workspace = Path(state["task_workspaces"]["LEASE-BIND"])
        self.assertIn(self.workspace, workspace.parents)
        self.assertEqual(Path(state["task_branches"]["LEASE-BIND"]["workspace"]), workspace)
        self.assertTrue((workspace / "product.txt").is_file())
        # nothing legacy appeared: no second board, no worktree where the agents may not write
        self.assertFalse(self.legacy.workspace_root.exists())
        self.assertFalse(self.legacy.data_root.exists())

    def test_one_registered_match_is_used_and_anything_else_keeps_todays_folders(self):
        self._register(self._entry())
        self.assertEqual(self._quiet(board._registered_context, self._args())[0], self.context)
        other = self.code.parent / "other"
        other.mkdir()
        self._register(self._entry(code=other))
        self.assertEqual(self._quiet(board._registered_context, self._args()), (None, ""))   # not registered: silent, legacy
        self._register(self._entry(), self._entry(workspace=self.code.parent / "elsewhere", project_id="twin"))
        context, note = self._quiet(board._registered_context, self._args())
        self.assertIsNone(context)                                                         # two matches: no guessing
        self.assertIn("2 NMHP projects use this folder", note)
        self.assertIn(str(self.legacy.workspace_root), note)
        self._register(self._entry() | {"code_root": ""})
        self.assertEqual(self._quiet(board._registered_context, self._args()), (None, ""))   # an entry without a folder never matches

    def test_a_symlinked_or_differently_cased_project_folder_still_matches(self):
        self._register(self._entry())
        alias = self.code.parent / "lease-link"
        alias.symlink_to(self.code, target_is_directory=True)
        self.assertEqual(self._quiet(board._registered_context, self._args(alias))[0], self.context)
        cased = self.code.parent / "LEASE"
        if sys.platform == "darwin" and cased.exists():   # macOS's default volume ignores letter case
            self.assertEqual(self._quiet(board._registered_context, self._args(cased))[0], self.context)

    def test_explicit_folders_win_one_alone_is_refused_and_a_damaged_or_missing_registry_keeps_todays_folders(self):
        self._register(self._entry())
        explicit = board.build_parser().parse_args(
            ["--root", str(self.code), "--data-root", str(self.code / ".harness"), "--workspace-root", str(self.code.parent / "x"), "poll", "--agent", "x"])
        self.assertIsNone(board._registered_context(explicit))
        with self.assertRaises(ValueError):
            self._main("--root", str(self.code), "--workspace-root", str(self.workspace), "poll", "--agent", "x")
        (self.home / project_registry.REGISTRY_FILENAME).write_text("{not json")
        context, note = self._quiet(board._registered_context, self._args())
        self.assertIsNone(context)
        self.assertIn("could not be read", note)
        (self.home / project_registry.REGISTRY_FILENAME).unlink()
        self.assertEqual(self._quiet(board._registered_context, self._args()), (None, ""))

    def test_a_managed_agent_command_still_goes_to_its_board_and_never_reads_the_registry(self):
        self._register(self._entry())
        with patch.object(board_client, "environment_state", return_value="managed"), \
                patch.object(board_client, "invoke", return_value=0) as invoke, \
                patch.object(project_registry, "entries", side_effect=AssertionError("registry read")):
            code, _out, _err = self._main("--root", str(self.code), "poll", "--agent", "x")
        self.assertEqual(code, 0)
        invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
