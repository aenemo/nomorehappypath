# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Tests for the record of use: "Skills used" is read from a real Claude or
Codex session record's own tool call/result pairs, never from what an
agent claims about itself — SKILL_LIBRARY_SPEC.md section 3 and S13.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from harness import board, conversation, control, skill_library
from tests.test_requirements_contract import context, delivery_with_direction


def _claude_session_file(control_dir: Path, cli_session_id: str, calls: list[dict]) -> Path:
    """A minimal Claude Code session file: one tool_use/tool_result pair per call.

    Each call: {"id", "input", "output", "ok"} (output may be omitted to
    simulate a call the record never got a result for).
    """
    projects = control_dir / ".claude-store" / "projects" / "proj"
    projects.mkdir(parents=True, exist_ok=True)
    path = projects / f"{cli_session_id}.jsonl"
    lines = []
    for call in calls:
        lines.append(json.dumps({
            "type": "assistant", "timestamp": "2026-11-12T20:00:00Z",
            "message": {"content": [{"type": "tool_use", "id": call["id"], "name": "Read", "input": call["input"]}]},
        }))
        if "output" in call:
            lines.append(json.dumps({
                "type": "user", "timestamp": "2026-11-12T20:00:01Z",
                "message": {"content": [{"type": "tool_result", "tool_use_id": call["id"],
                                          "is_error": not call.get("ok", True),
                                          "content": [{"type": "text", "text": call["output"]}]}]},
            }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class SkillUsageClassificationTests(unittest.TestCase):
    """classify_skill_usage against hand-built event lists: no real CLI needed
    to prove the classification rule itself (the real-record wiring is
    proven separately below, against a real Claude Code session file)."""

    def setUp(self):
        self.skill = skill_library.usable_skills()[3]  # "backend"
        self.agreed = [{"slug": self.skill.slug, "plain_name": self.skill.plain_name, "path": str(self.skill.path)}]
        self.opening = f"name: {self.skill.slug}\ndescription: {self.skill.full_description}\n"

    def test_a_real_read_of_the_skills_own_file_is_opened(self):
        events = [{"path": str(self.skill.path), "command": None, "ok": True, "output": self.opening}]
        result = board.classify_skill_usage(events, self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "opened")

    def test_a_shell_read_of_the_skills_own_file_is_also_opened(self):
        events = [{"path": None, "command": f"cat {self.skill.path}", "ok": True, "output": self.opening}]
        result = board.classify_skill_usage(events, self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "opened")

    def test_a_call_that_only_tests_the_file_exists_is_agreed_not_opened(self):
        events = [{"path": None, "command": f"test -f {self.skill.path}", "ok": True, "output": ""}]
        result = board.classify_skill_usage(events, self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "agreed_not_opened")

    def test_an_agreed_skill_never_touched_is_agreed_not_opened(self):
        result = board.classify_skill_usage([], self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "agreed_not_opened")

    def test_a_failed_read_is_could_not_be_read(self):
        events = [{"path": str(self.skill.path), "command": None, "ok": False, "output": "ENOENT"}]
        result = board.classify_skill_usage(events, self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "could_not_be_read")

    def test_no_usable_record_is_not_known_not_opened_despite_identical_opening_lines(self):
        result = board.classify_skill_usage(None, self.agreed)
        self.assertTrue(result["not_known"])

    def test_reading_a_different_skills_file_is_opened_not_agreed(self):
        other = next(skill for skill in skill_library.usable_skills() if skill.slug != self.skill.slug)
        other_opening = f"name: {other.slug}\ndescription: {other.full_description}\n"
        events = [{"path": str(other.path), "command": None, "ok": True, "output": other_opening}]
        result = board.classify_skill_usage(events, self.agreed)
        self.assertEqual(result["by_slug"][self.skill.slug], "agreed_not_opened")
        self.assertIn(other.plain_name, result["opened_not_agreed"])


class RealSessionRecordTests(unittest.TestCase):
    """The same classification, driven end to end from a real Claude Code
    session file on disk — proving conversation.read_vendor_tool_events
    actually extracts the call/result pair, not just that the classifier
    logic is right in isolation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name)
        self._real_claude_home = conversation.claude_config_dir
        conversation.claude_config_dir = lambda: self.store / ".claude-store"
        self.addCleanup(lambda: setattr(conversation, "claude_config_dir", self._real_claude_home))

    def test_a_real_session_file_showing_the_real_opening_lines_counts_as_opened(self):
        skill = skill_library.usable_skills()[0]
        opening = f"name: {skill.slug}\ndescription: {skill.full_description}\n"
        _claude_session_file(self.store, "cli-abc", [{"id": "t1", "input": {"file_path": str(skill.path)}, "output": opening, "ok": True}])
        events = conversation.read_vendor_tool_events("claude", "cli-abc", wait=True)
        self.assertIsNotNone(events)
        agreed = [{"slug": skill.slug, "plain_name": skill.plain_name, "path": str(skill.path)}]
        result = board.classify_skill_usage(events, agreed)
        self.assertEqual(result["by_slug"][skill.slug], "opened")

    def test_a_call_with_no_result_in_the_record_leaves_the_skill_not_opened(self):
        skill = skill_library.usable_skills()[1]
        _claude_session_file(self.store, "cli-def", [{"id": "t1", "input": {"file_path": str(skill.path)}}])  # no "output": never gets a result
        events = conversation.read_vendor_tool_events("claude", "cli-def", wait=True)
        agreed = [{"slug": skill.slug, "plain_name": skill.plain_name, "path": str(skill.path)}]
        result = board.classify_skill_usage(events, agreed)
        self.assertEqual(result["by_slug"][skill.slug], "agreed_not_opened")


class BoardReadsStayCheapTests(unittest.TestCase):
    """2026-11-16 board freeze (Analyzing NHMP Clone): every board read re-parsed every agent's whole session file,
    including 24 archived agents on the waiting designations (up to ~100 MB each), until the page timed out."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name)
        for name, value in (("claude_config_dir", lambda: self.store / ".claude-store"),
                            ("codex_home", lambda: self.store / ".codex-store")):
            real = getattr(conversation, name)
            setattr(conversation, name, value)
            self.addCleanup(setattr, conversation, name, real)
        self.addCleanup(self._reset)
        self._reset()
        self.now = [1000.0]
        real_clock = conversation._monotonic
        conversation._monotonic = lambda: self.now[0]
        self.addCleanup(setattr, conversation, "_monotonic", real_clock)
        self.parses = []
        self.gate = threading.Event()
        self.gate.set()
        for name in ("read_claude_tool_events", "read_codex_tool_events"):
            real = getattr(conversation, name)
            setattr(conversation, name, lambda path, real=real: (self.parses.append(Path(path).name), self.gate.wait(10), real(path))[2])
            self.addCleanup(setattr, conversation, name, real)

    def _reset(self):
        self.assertTrue(conversation.wait_for_tool_events())
        for store in (conversation._TOOL_EVENTS_CACHE, conversation._LAST_PARSED, conversation._PENDING):
            store.clear()

    def claude(self, calls, name="cli-big"):
        return _claude_session_file(self.store, name, [{"id": f"t{n}", "input": {"file_path": f"/f{n}"}, "output": "o", "ok": True}
                                                       for n in range(calls)])

    def read(self, name="cli-big", provider="claude"):
        return conversation.read_vendor_tool_events(provider, name)

    def settle(self):
        self.assertTrue(conversation.wait_for_tool_events())

    def test_a_board_read_never_waits_for_a_parse(self):
        self.claude(1, "other")
        self.read("other"); self.settle()                      # one file already known
        self.claude(1)
        self.gate.clear()                                     # the next parse hangs until released
        started = time.monotonic()
        self.assertIsNone(self.read(), "not read yet is 'not known'")
        self.assertEqual(len(self.read("other")), 1, "a known file answers while another is being parsed")
        self.assertLess(time.monotonic() - started, 0.5)
        self.gate.set()
        self.settle()
        self.assertEqual([event["path"] for event in self.read()], ["/f0"])

    def test_an_unchanged_file_is_parsed_once_and_callers_never_change_the_next_answer(self):
        self.claude(1)
        self.read(); self.settle()
        first = self.read()
        first[0]["ok"] = False
        first.append({"path": "/planted"})
        self.assertEqual([(event["path"], event["ok"]) for event in self.read()], [("/f0", True)])
        self.settle()
        self.assertEqual(len(self.parses), 1)

    def test_a_growing_file_is_parsed_again_only_after_the_refresh_window(self):
        self.claude(1)
        self.read(); self.settle()
        self.claude(2)
        self.assertEqual(len(self.read()), 1); self.settle()
        self.assertEqual(len(self.parses), 1, "inside the window: no new parse")
        self.now[0] += conversation._TOOL_EVENTS_REFRESH_SECONDS
        self.read(); self.settle()
        self.assertEqual(len(self.read()), 2)
        self.assertEqual(len(self.parses), 2)

    def test_a_file_pushed_out_of_the_cache_is_still_parsed_at_most_once_per_window(self):
        limit = conversation._TOOL_EVENTS_CACHE_FILES
        conversation._TOOL_EVENTS_CACHE_FILES = 2
        self.addCleanup(setattr, conversation, "_TOOL_EVENTS_CACHE_FILES", limit)
        for name in ("a", "b", "c"):
            self.claude(1, name)
        for _ in range(3):                                    # three polls over more files than the cache holds
            for name in ("a", "b", "c"):
                self.read(name)
            self.settle()
        self.assertEqual(sorted(self.parses), ["a.jsonl", "b.jsonl", "c.jsonl"])
        self.assertEqual(len(conversation._TOOL_EVENTS_CACHE), 2)

    def test_a_same_size_replacement_is_noticed_after_the_window(self):
        path = self.claude(1)
        self.read(); self.settle()
        replacement = path.with_suffix(".new")
        replacement.write_text(path.read_text().replace("/f0", "/g0"), encoding="utf-8")
        status = path.stat()
        os.utime(replacement, ns=(status.st_atime_ns, status.st_mtime_ns))
        os.replace(replacement, path)
        self.assertEqual(path.stat().st_size, status.st_size)
        self.now[0] += conversation._TOOL_EVENTS_REFRESH_SECONDS
        self.read(); self.settle()
        self.assertEqual([event["path"] for event in self.read()], ["/g0"])

    def test_an_unreadable_file_is_not_known_and_not_remembered(self):
        path = self.claude(1)
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        if os.access(path, os.R_OK):
            self.skipTest("this account can read any file")
        self.read(); self.settle()
        self.assertIsNone(self.read())
        path.chmod(0o600)
        self.read(); self.settle()
        self.assertEqual(len(self.read()), 1)

    def test_a_codex_rollout_is_read_the_same_way(self):
        folder = self.store / ".codex-store" / "sessions" / "2026" / "11" / "16"
        folder.mkdir(parents=True)
        item = lambda payload: json.dumps({"timestamp": "2026-11-16T17:00:00Z", "type": "response_item", "payload": payload})  # noqa: E731
        (folder / "rollout-2026-11-16T17-00-00-cx1.jsonl").write_text("\n".join([
            item({"type": "function_call", "call_id": "c1", "arguments": json.dumps({"command": ["cat", "/skill/SKILL.md"]})}),
            item({"type": "function_call_output", "call_id": "c1", "output": "name: x"}),
        ]) + "\n", encoding="utf-8")
        self.read("cx1", "codex"); self.settle()
        self.assertEqual(len(self.read("cx1", "codex")), 1)
        self.assertEqual(self.parses, ["rollout-2026-11-16T17-00-00-cx1.jsonl"])

    def test_many_requests_at_once_queue_one_parse_and_none_waits(self):
        self.claude(1)
        self.gate.clear()                                     # the parse is held open the whole time
        waits = []
        def poll():
            started = time.monotonic()
            self.read()
            waits.append(time.monotonic() - started)
        threads = [threading.Thread(target=poll) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(waits), 8)
        self.assertLess(max(waits), 0.5, "no request waits for the parse in progress")
        self.gate.set()
        self.settle()
        self.assertEqual(len(self.parses), 1)

    def test_a_large_growing_session_never_slows_the_board(self):
        # ~18 MB, 8,000 real-shaped tool calls (every tenth reads a library file), the size class of the clone's 74-99 MB files
        skill = skill_library.usable_skills()[0]
        def call(n):
            return {"id": f"t{n}", "input": {"file_path": str(skill.path) if n % 10 == 0 else f"/f{n}"}, "output": "x" * 2000, "ok": True}
        path = _claude_session_file(self.store, "cli-big", [call(n) for n in range(8000)])
        self.assertGreater(path.stat().st_size, 15_000_000)
        root = context(self.store)
        board.register(root, "qa", "REAL-TASK", vendor="Anthropic", session_id="q-session")
        real_session = control.cli_session
        control.cli_session = lambda r, sid: {"cli_session_provider": "claude", "cli_session_id": "cli-big"}
        self.addCleanup(setattr, control, "cli_session", real_session)
        def timed_snapshot():
            started = time.monotonic()
            board.snapshot(root)
            return time.monotonic() - started
        times = [timed_snapshot()]                            # cold: queues the parse, answers "not known"
        self.settle()
        self.assertEqual(len(self.read()), 8000)
        times += [timed_snapshot(), timed_snapshot()]         # warm: classification over the parsed 8,000 events
        extra = _claude_session_file(self.store, "grow", [{"id": "t9000", "input": {"file_path": "/new"}, "output": "y", "ok": True}])
        with path.open("a", encoding="utf-8") as handle:      # the agent keeps working: one more call and its result
            handle.write(extra.read_text(encoding="utf-8"))
        self.now[0] += conversation._TOOL_EVENTS_REFRESH_SECONDS
        polls = []
        threads = [threading.Thread(target=lambda: polls.append(timed_snapshot())) for _ in range(6)]
        for thread in threads:                                # six board reads at once while the refresh runs
            thread.start()
        for thread in threads:
            thread.join(10)
        self.settle()
        times += polls + [timed_snapshot()]
        self.assertEqual(len(times), 10)
        self.assertLess(max(times), 0.5, f"a board read must never wait for a parse: {[round(x, 3) for x in times]}")
        self.assertEqual(len(self.read()), 8001)
        self.assertEqual(self.parses, ["cli-big.jsonl", "cli-big.jsonl"])

    def test_a_large_codex_rollout_is_read_in_the_background_too(self):
        folder = self.store / ".codex-store" / "sessions" / "2026" / "11" / "16"
        folder.mkdir(parents=True)
        lines = []
        for n in range(8000):
            lines.append(json.dumps({"timestamp": "2026-11-16T17:00:00Z", "type": "response_item", "payload": {
                "type": "function_call", "call_id": f"c{n}", "arguments": json.dumps({"command": ["cat", f"/f{n}"]})}}))
            lines.append(json.dumps({"timestamp": "2026-11-16T17:00:01Z", "type": "response_item", "payload": {
                "type": "function_call_output", "call_id": f"c{n}", "output": "z" * 2000}}))
        (folder / "rollout-2026-11-16T17-00-00-cxbig.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        started = time.monotonic()
        self.assertIsNone(self.read("cxbig", "codex"))
        self.assertLess(time.monotonic() - started, 0.5)
        self.settle()
        started = time.monotonic()
        self.assertEqual(len(self.read("cxbig", "codex")), 8000)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_the_production_cache_limit_is_32_files(self):
        self.assertEqual(conversation._TOOL_EVENTS_CACHE_FILES, 32)
        for n in range(33):
            self.claude(1, f"s{n}")
            self.read(f"s{n}")
            self.settle()
        self.assertEqual(len(conversation._TOOL_EVENTS_CACHE), 32)

    def test_only_events_naming_a_library_file_reach_the_classifier_and_the_answer_is_unchanged(self):
        skill = skill_library.usable_skills()[0]
        opening = f"name: {skill.slug}\ndescription: {skill.full_description}\n"
        _claude_session_file(self.store, "cli-big", [
            {"id": "a", "input": {"file_path": "/app/main.py"}, "output": "print()", "ok": True},
            {"id": "b", "input": {"file_path": str(skill.path)}, "output": opening, "ok": True},
            {"id": "c", "input": {"command": "pytest -q"}, "output": "ok", "ok": True}])
        real_session = control.cli_session
        control.cli_session = lambda r, sid: {"cli_session_provider": "claude", "cli_session_id": "cli-big"}
        self.addCleanup(setattr, control, "cli_session", real_session)
        self.read(); self.settle()
        events = board._agent_skill_events(self.store, {"session_id": "s"})
        self.assertEqual([event["path"] for event in events], [str(skill.path)])
        agreed = [{"slug": skill.slug, "plain_name": skill.plain_name, "path": str(skill.path)}]
        self.assertEqual(board.classify_skill_usage(events, agreed), board.classify_skill_usage(self.read(), agreed))
        self.assertEqual(board.classify_skill_usage(events, agreed)["by_slug"][skill.slug], "opened")

    def test_the_waiting_designations_are_never_read_for_skills_used(self):
        root = context(self.store)
        board.register(root, "qa", "REVIEW_QUEUE", vendor="Anthropic", session_id="q-session")
        board.register(root, "engineering", board.AWAITING_OWNER_DIRECTION, vendor="Anthropic", session_id="e-session")
        board.register(root, "cto", "GLOBAL_MONITOR", vendor="Anthropic", session_id="c-session")
        board.register(root, "qa", "REAL-TASK", vendor="Google", session_id="g-session")
        asked = []
        real = board.skill_usage_lines_for_task
        board.skill_usage_lines_for_task = lambda r, task: (asked.append(task), real(r, task))[1]
        self.addCleanup(setattr, board, "skill_usage_lines_for_task", real)
        usage = board.snapshot(root)["task_skill_usage"]
        self.assertEqual(asked, ["REAL-TASK"])
        self.assertEqual(usage, {"REAL-TASK": ["Reviewer: not available for Gemini."]})


class SkillUsageLinesForTaskTests(unittest.TestCase):
    """skill_usage_lines_for_task against a real board + real registered
    agents, proving the per-role composition and the Gemini/not-known cases
    without needing the full card/Go-ahead flow."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = context(Path(self._tmp.name))

    def test_no_agent_on_the_task_yet_shows_nothing(self):
        self.assertEqual(board.skill_usage_lines_for_task(self.root, "NO-SUCH-TASK"), [])

    def test_a_builder_with_no_cli_session_recorded_shows_not_known(self):
        agent = delivery_with_direction(self.root, "USAGE-TASK")
        board.record_requirement_proposal(self.root, agent["id"], "Final agreed requirements: build a small service.",
                                           skills=[{"name": "backend", "reason": "service code"}])
        proposal = board.snapshot(self.root)["requirement_proposals"]["USAGE-TASK"]
        board.record_requirements_decision(self.root, "USAGE-TASK", "go_ahead", version=proposal["version"],
                                            token=(proposal.get("contract_check") or {}).get("token", ""), skills=["backend"])
        lines = board.skill_usage_lines_for_task(self.root, "USAGE-TASK")
        self.assertTrue(any("not known" in line for line in lines))

    def test_a_gemini_agent_shows_not_available_for_gemini(self):
        board.register(self.root, "qa", "USAGE-TASK-2", vendor="Google", session_id="gem-session")
        lines = board.skill_usage_lines_for_task(self.root, "USAGE-TASK-2")
        self.assertIn("Reviewer: not available for Gemini.", lines)

    def test_skills_used_survives_the_agent_being_archived_after_acceptance(self):
        # Final review (B1): once the accepted task's agent is moved from hot state into
        # cold archive storage, Skills used must keep reading it there, not go blank.
        agent = delivery_with_direction(self.root, "ARCHIVED-TASK")
        board.record_requirement_proposal(self.root, agent["id"], "Final agreed requirements: build a small service.",
                                           skills=[{"name": "backend", "reason": "service code"}])
        proposal = board.snapshot(self.root)["requirement_proposals"]["ARCHIVED-TASK"]
        board.record_requirements_decision(self.root, "ARCHIVED-TASK", "go_ahead", version=proposal["version"],
                                            token=(proposal.get("contract_check") or {}).get("token", ""), skills=["backend"])
        before = board.skill_usage_lines_for_task(self.root, "ARCHIVED-TASK")
        with board.locked_state(self.root) as state:
            archived_agent = dict(state["agents"][agent["id"]])
            board._append_cold(self.root, "agents", [archived_agent])
            del state["agents"][agent["id"]]
        self.assertEqual(board.snapshot(self.root)["agents"], {})
        after = board.skill_usage_lines_for_task(self.root, "ARCHIVED-TASK")
        self.assertEqual(before, after)


class LibraryGrowthTests(unittest.TestCase):
    """Final review (B2): a guide folder the owner adds to the library later
    must reach the board's own catalogue (what every next proposal is built
    from) with nothing else edited - spec section 6, "Adding a skill later".
    The board scans the library folder itself, so this holds whatever the
    library module's own fixed table knows about."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        shutil.copytree(skill_library.library_root(), self.root / skill_library.LIBRARY_DIRNAME)

    def _add_guide(self, slug: str, frontmatter: str) -> None:
        folder = self.root / skill_library.LIBRARY_DIRNAME / slug
        folder.mkdir()
        (folder / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n# {slug}\n", encoding="utf-8")

    def test_a_newly_added_guide_reaches_the_next_proposal_catalogue(self):
        self._add_guide("solo-workflow", "name: solo-workflow\ndescription: Guides the new solo workflow.\n"
                                         "plain_name: Solo workflow\nowner_description: Steps for the new workflow.")
        catalogue = board.skill_library_catalogue(self.root)
        slugs = [item["slug"] for item in catalogue]
        self.assertEqual(len(slugs), len(set(slugs)), "no guide may be listed twice")
        self.assertEqual(slugs[:len(skill_library.SKILLS)], [slug for slug, _, _ in skill_library.SKILLS])
        added = next(item for item in catalogue if item["slug"] == "solo-workflow")
        self.assertEqual(added["plain_name"], "Solo workflow")
        self.assertEqual(added["owner_description"], "Steps for the new workflow.")
        self.assertEqual(added["full_description"], "Guides the new solo workflow.")

    def test_a_new_guide_without_plain_lines_still_appears_under_a_readable_name(self):
        self._add_guide("mobile-apps", "name: mobile-apps\ndescription: Builds phone apps that work offline.")
        added = next(item for item in board.skill_library_catalogue(self.root) if item["slug"] == "mobile-apps")
        self.assertEqual(added["plain_name"], "Mobile Apps")
        self.assertEqual(added["owner_description"], "Builds phone apps that work offline.")

    def test_a_damaged_new_guide_is_left_off_the_catalogue(self):
        self._add_guide("half-done", "name: half-done")  # no description line
        self._add_guide("wrong-name", "name: other\ndescription: Its name does not match its folder.")
        slugs = [item["slug"] for item in board.skill_library_catalogue(self.root)]
        self.assertNotIn("half-done", slugs)
        self.assertNotIn("wrong-name", slugs)

    def test_a_builder_can_propose_a_newly_added_guide(self):
        self._add_guide("solo-workflow", "name: solo-workflow\ndescription: Guides the new solo workflow.")
        accepted, dropped = board._validate_proposed_skills(
            [{"name": "solo-workflow", "reason": "the owner works alone"}, {"name": "no-such-guide", "reason": "x"}], self.root)
        self.assertEqual([item["slug"] for item in accepted], ["solo-workflow"])
        self.assertEqual(dropped, ["no-such-guide"])


if __name__ == "__main__":
    unittest.main()
