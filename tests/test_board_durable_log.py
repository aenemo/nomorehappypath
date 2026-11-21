# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""The board's durable event log is the authority on what was already exported.

A crash between the events.jsonl append and the state.json replace used to bring
the board back with an older `last_event_exported` and `next_event`, so the next
persist re-appended lines already on disk and reused sequence numbers the module
promises are never reused. A backup taken before the crash made it worse: the
newest backup was preferred without consulting the surviving log at all.

These tests reproduce both crash shapes, prove the durable tail is read without
loading the whole log, and pin the owner-only file modes the board stores its
directions and findings under.

Run:  PYTHONPATH=. python3 -m unittest tests.test_board_durable_log -v
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import board


def _record(sequence: int, message: str = "board event") -> dict:
    """Return one event shaped like the board's own durable lines."""
    return {
        "sequence": sequence,
        "at": "2026-11-21T00:00:00+00:00",
        "kind": "status_update",
        "agent_id": "system",
        "role": "system",
        "task": "",
        "message": message,
    }


def _write_log(path: Path, records: list[dict]) -> None:
    """Write records as the durable log's own one-object-per-line format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _log_sequences(path: Path) -> list[int]:
    """Return every sequence in the durable log, in file order."""
    return [
        int(json.loads(line)["sequence"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class BoardDurableLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        # Board backups live beside the project by design; remove this test's.
        self.addCleanup(shutil.rmtree, board._board_backup_root(self.root), True)

    def board_dir(self) -> Path:
        """Return this project's board storage directory."""
        return board.board_dir(self.root)

    def test_a_state_missing_after_a_crash_never_replays_events_the_log_holds(self):
        directory = self.board_dir()
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / "events.jsonl"
        earlier = [_record(1), _record(2)]
        newest = _record(3)
        _write_log(log, earlier + [newest])

        # The crash: a real state was written (next_event 4, export marker 3),
        # then lost, while an OLDER backup still exists beside the project.
        current = board._initial_state()
        current.update({"next_event": 4, "last_event_exported": 3, "events": earlier + [newest]})
        board._write_state_file(board._state_path(self.root), current)
        board._state_path(self.root).unlink()

        older = board._initial_state()
        older.update({"next_event": 3, "last_event_exported": 0, "events": earlier})
        snapshot = board._board_backup_root(self.root) / "e000000003"
        snapshot.mkdir(parents=True)
        (snapshot / "state.json").write_text(json.dumps(older, sort_keys=True), encoding="utf-8")

        loaded = board._load_or_recover_state(self.root, allow_restore=True)

        last_logged = 3
        self.assertGreater(loaded["next_event"], last_logged)
        self.assertGreaterEqual(loaded["last_event_exported"], last_logged)
        self.assertGreaterEqual(loaded["event_window_start"], last_logged)

        before = _log_sequences(log)
        board._persist_visible_board(self.root, loaded)
        after = _log_sequences(log)
        self.assertEqual(after, before, "a recovered state re-appended lines already in the log")
        self.assertEqual(len(after), len(set(after)), "a sequence number was reused")

    def test_a_stale_export_marker_cannot_duplicate_lines_already_in_the_log(self):
        log = self.board_dir() / "events.jsonl"
        records = [_record(1), _record(2), _record(3)]
        _write_log(log, records)

        state = board._initial_state()
        state.update({"next_event": 4, "last_event_exported": 1, "events": records})

        board._persist_visible_board(self.root, state)

        self.assertEqual(_log_sequences(log), [1, 2, 3])

    def test_log_last_sequence_reads_the_tail_and_ignores_a_partial_line(self):
        log = self.board_dir() / "events.jsonl"
        self.assertEqual(board._log_last_sequence(log), 0, "a missing log reports 0")

        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")
        self.assertEqual(board._log_last_sequence(log), 0, "an empty log reports 0")

        _write_log(log, [_record(1), _record(2), _record(3)])
        self.assertEqual(board._log_last_sequence(log), 3)

        # A crash can leave a half-written final line with no newline.
        log.write_text(log.read_text(encoding="utf-8") + '{"sequence": 99, "kind": "half', encoding="utf-8")
        self.assertEqual(board._log_last_sequence(log), 3, "a partial trailing line was trusted")

        # The last sequence must be found without reading a whole large log.
        many = [_record(sequence, "x" * 60) for sequence in range(1, 2501)]
        _write_log(log, many)
        self.assertGreater(log.stat().st_size, board.LOG_TAIL_CHUNK_BYTES * 2)
        self.assertEqual(board._log_last_sequence(log), 2500)

    def test_state_and_event_writes_flush_their_bytes_to_disk(self):
        calls: list[int] = []
        real_fsync = os.fsync

        def record_fsync(descriptor: int) -> None:
            calls.append(descriptor)
            return real_fsync(descriptor)

        with patch("os.fsync", side_effect=record_fsync):
            with board.locked_state(self.root) as state:
                board._event(state, "status_update", None, {"task": "", "message": "flush me"})

        self.assertGreaterEqual(len(calls), 2, "a durable board write skipped flush and fsync")

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX file modes are only checked on Linux")
    def test_board_storage_and_its_durable_files_are_owner_only(self):
        # A permissive umask is what the board used to inherit; with it, files
        # are 0666 and the directory 0777 unless the board sets its own modes.
        previous_umask = os.umask(0)
        try:
            with board.locked_state(self.root) as state:
                board._event(state, "status_update", None, {"task": "", "message": "owner only"})
        finally:
            os.umask(previous_umask)

        directory = self.board_dir()
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for name in ("state.json", "events.jsonl", "BOARD.md", ".lock"):
            mode = stat.S_IMODE((directory / name).stat().st_mode)
            self.assertEqual(mode, 0o600, f"{name} is readable by other local users")

        board._append_cold(self.root, "agents", [{"id": "agent-1", "active": False}])
        archive = board._cold_dir(self.root)
        self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((archive / "agents.jsonl").stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
