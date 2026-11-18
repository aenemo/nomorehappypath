# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Each agent's CLI window opens in its role's Settings colour (owner 2026-11-17: "if i have multiple agents cli open
i know by the color who is who"). Task 2026-11-16_agent-terminal-role-colors: the resolver, every start path's default,
the colour a window really opened in (recorded for its row and for View agent), and a terminal that refuses the colour.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from harness import board_viewer, control, global_settings, platform_support, project_worker
from harness.platform_support import defaults, linux
from tests import test_board_viewer as _viewer_tests

TEAL, CORAL, PURPLE, PINK = (0x0F, 0x3F, 0x3B), (0x5A, 0x25, 0x22), (0x42, 0x27, 0x5A), (0x5A, 0x1F, 0x3D)


class _Host:
    """A terminal host that records the colour each window was asked for and answers with a chosen `colored`."""

    def __init__(self, colored=True):
        self.colored, self.asked = colored, []

    def open_session(self, session_id, argv, *, color_rgb):
        self.asked.append(tuple(color_rgb))
        return defaults.SessionSurface(session_id=session_id, colored=self.colored)


class ResolverTests(unittest.TestCase):
    def test_no_pick_takes_each_roles_default_settings_colour(self):
        for kind, rgb in (("codex_delivery", TEAL), ("claude_reviewer", CORAL), ("claude_cto", PURPLE)):
            self.assertEqual(control.terminal_color({"kind": kind, "color": "settings"}, None)["rgb"], rgb, kind)
            self.assertEqual(control.terminal_color({"kind": kind}, None)["rgb"], rgb, "a session with no colour at all")

    def test_a_changed_settings_colour_is_used(self):
        color = control.terminal_color({"kind": "codex_delivery", "color": "settings"}, {"role_colors": {"delivery": "pink"}})
        self.assertEqual((color["rgb"], color["label"]), (PINK, "Settings colour (Pink)"))

    def test_a_colour_picked_for_one_start_wins_black_included(self):
        self.assertEqual(control.terminal_color({"kind": "codex_delivery", "color": "blue"}, None)["rgb"], (0x12, 0x3B, 0x5D))
        picked_black = {"kind": "codex_delivery", "color": "black", "color_chosen": True}
        self.assertEqual(control.terminal_color(picked_black, None)["rgb"], (0, 0, 0))

    def test_an_older_black_session_takes_the_settings_colour_and_an_older_blue_one_keeps_blue(self):
        self.assertEqual(control.terminal_color({"kind": "claude_reviewer", "color": "black"}, None)["rgb"], CORAL)
        self.assertEqual(control.terminal_color({"kind": "claude_reviewer", "color": "blue"}, None)["rgb"], (0x12, 0x3B, 0x5D))

    def test_damaged_settings_fall_back_to_the_default_colours_and_an_unknown_kind_is_black(self):
        for damaged in ({"role_colors": ["pink"]}, {"role_colors": {"delivery": 7}}, {"error": "unreadable"}, "junk"):
            self.assertEqual(control.terminal_color({"kind": "codex_delivery"}, damaged)["rgb"], TEAL, repr(damaged))
        self.assertEqual(control.terminal_color({"kind": "nothing", "color": "settings"}, None)["rgb"], (0, 0, 0))

    def test_every_terminal_shade_is_dark_enough_for_the_white_text(self):
        for color_id, color in control.ROLE_COLOR_CHOICES.items():
            red, green, blue = (int(color["terminal"][index:index + 2], 16) / 255 for index in (1, 3, 5))
            linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in (red, green, blue)]
            luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
            self.assertGreaterEqual(1.05 / (luminance + 0.05), 7.0, color_id)


class StartPathTests(unittest.TestCase):
    def test_create_with_no_colour_stores_the_settings_marker_and_a_pick_is_marked_chosen(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = control.create(root, "codex_delivery")
            self.assertEqual((plain["color"], plain["color_chosen"], plain["color_label"]), ("settings", False, "Settings colour"))
            black = control.create(root, "claude_reviewer", color="black")
            self.assertEqual((black["color"], black["color_chosen"]), ("black", True))
            with self.assertRaisesRegex(ValueError, "unknown terminal color"):
                control.create(root, "claude_cto", color="neon")

    def test_the_session_request_with_an_omitted_or_null_colour_uses_settings(self):
        for body in ({"kind": "codex_delivery"}, {"kind": "codex_delivery", "color": None}, {"kind": "codex_delivery", "color": ""}):
            with TemporaryDirectory() as tmp:
                session = board_viewer.create_session_request(Path(tmp), body, None)
                self.assertEqual(session["color"], "settings", body)


class LaunchTests(unittest.TestCase):
    def _launch(self, launcher, settings_colors=None, colored=True):
        with TemporaryDirectory() as tmp:
            root, home = Path(tmp) / "project", Path(tmp) / "home"
            root.mkdir(); home.mkdir()
            global_settings.initialize(home)
            if settings_colors:
                global_settings.update_agent_settings(home, global_settings.load(home)["agent_settings"], None, None, settings_colors)
            session = control.create(root, "codex_delivery")
            host = _Host(colored)
            with mock.patch.object(platform_support, "terminal_host", return_value=host), \
                 mock.patch("harness.claude_auth.prepare_launch", return_value=None):
                if launcher == "worker":
                    project_worker.launch_terminal(root, session, "/tmp/fixture-bootstrap.sock", manager_home=home)
                else:
                    board_viewer.launch_terminal(root, session, manager_home=home)
            recorded = next(item for item in control.snapshot(root)["sessions"] if item["id"] == session["id"])
            return host.asked, recorded

    def test_both_launchers_open_the_window_in_the_roles_settings_colour_and_record_it(self):
        for launcher in ("viewer", "worker"):
            asked, recorded = self._launch(launcher)
            self.assertEqual(asked, [TEAL], launcher)
            self.assertEqual(recorded["window_color"], {"label": "Settings colour (Teal)", "hex": "#0F3F3B"}, launcher)

    def test_a_settings_change_reaches_the_next_window(self):
        asked, recorded = self._launch("viewer", {"delivery": "pink"})
        self.assertEqual((asked, recorded["window_color"]["hex"]), ([PINK], "#5A1F3D"))

    def test_a_refused_colour_still_opens_and_is_recorded_as_not_coloured(self):
        asked, recorded = self._launch("worker", colored=False)
        self.assertEqual(asked, [TEAL])
        self.assertEqual(recorded["window_color"], {"label": "Not coloured (the terminal refused the colour)", "hex": ""})


class TerminalHostTests(unittest.TestCase):
    def test_macos_script_keeps_the_colour_in_its_own_try_and_reports_a_refusal(self):
        script = defaults.MacOSTerminalHost()._open_script(TEAL) if hasattr(defaults, "MacOSTerminalHost") else None
        if script is None:
            with mock.patch.object(defaults.sys, "platform", "darwin"):
                script = platform_support.terminal_host()._open_script(TEAL)
        colour_block = script.split("set background color", 1)[0].rsplit("try", 1)[1]
        self.assertNotIn("end try", colour_block, "the colour lines open their own try")
        self.assertIn('set colourResult to "uncolored"', script)
        self.assertIn("return colourResult", script)
        self.assertIn("set newTab to do script", script.split("try", 1)[0], "opening the window is outside any try")

    def test_macos_direct_launch_reports_uncolored_and_a_failed_open_still_raises(self):
        darwin = mock.patch.object(defaults.sys, "platform", "darwin")
        darwin.start(); self.addCleanup(darwin.stop)   # the Mac host refuses off macOS, so the claim lasts the whole test
        host = platform_support.terminal_host()
        refused = subprocess.CompletedProcess([], 0, stdout="uncolored\n", stderr="")
        with mock.patch.object(defaults.subprocess, "run", return_value=refused):
            self.assertIs(host.open_session("codex_delivery-abc", ["/bin/true"], color_rgb=TEAL).colored, False)
        fine = subprocess.CompletedProcess([], 0, stdout="colored\n", stderr="")
        with mock.patch.object(defaults.subprocess, "run", return_value=fine):
            self.assertIs(host.open_session("codex_delivery-abc", ["/bin/true"], color_rgb=TEAL).colored, True)
        with mock.patch.object(defaults.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "osascript")):
            with self.assertRaises(subprocess.CalledProcessError):
                host.open_session("codex_delivery-abc", ["/bin/true"], color_rgb=TEAL)

    def test_linux_reports_a_failed_colour_command_and_still_opens(self):
        host = linux._TmuxTerminalHost()

        def run(command, *args, **kwargs):
            return subprocess.CompletedProcess(command, 1 if "select-pane" in command else 0, stdout="", stderr="")
        with mock.patch.object(linux, "launch_problem", return_value=""), mock.patch.object(linux.subprocess, "run", side_effect=run):
            self.assertIs(host.open_session("claude_reviewer-abc", ["/bin/true"], color_rgb=CORAL).colored, False)

        def run_ok(command, *args, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        with mock.patch.object(linux, "launch_problem", return_value=""), mock.patch.object(linux.subprocess, "run", side_effect=run_ok) as calls:
            self.assertIs(host.open_session("claude_reviewer-abc", ["/bin/true"], color_rgb=CORAL).colored, True)
            self.assertIn("bg=#5a2522", calls.call_args_list[-1].args[0])

    def test_view_agent_reopens_in_the_recorded_window_colour(self):
        with mock.patch.object(defaults.sys, "platform", "darwin"):
            host = platform_support.terminal_host()
        context = mock.Mock(); context.storage_path.return_value = Path("/tmp/fixture-sockets")
        not_found = subprocess.CompletedProcess([], 0, stdout="not found\n", stderr="")
        for session, rgb in (
            ({"id": "codex_delivery-abc", "kind": "codex_delivery", "color": "settings", "window_color": {"label": "x", "hex": "#5A1F3D"}}, PINK),
            ({"id": "codex_delivery-abc", "kind": "codex_delivery", "color": "settings"}, TEAL),
            ({"id": "claude_reviewer-abc", "kind": "claude_reviewer", "color": "black"}, CORAL),
            ({"id": "claude_reviewer-abc", "kind": "claude_reviewer", "color": "settings", "window_color": {"label": "Not coloured", "hex": ""}}, CORAL),
        ):
            with mock.patch("harness.project_context.project_context", return_value=context), \
                 mock.patch.object(host, "_live_screen_name", return_value="nmhp-x"), \
                 mock.patch.object(defaults.subprocess, "run", return_value=not_found), \
                 mock.patch.object(host, "_open_screen_view") as opened:
                host.view_session(session, root=Path("/tmp/fixture-root"))
            self.assertEqual(tuple(opened.call_args.args[2]), rgb, session)


class ViewAgentRecordsTheReopenedColourTests(unittest.TestCase):
    """A window reopened by View agent records the colour it really took, in both directions."""

    def _reopen(self, recorded_before, colored):
        from harness import agent_view
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = control.create(root, "codex_delivery")
            with control.locked_state(root) as state:
                stored = state["sessions"][session["id"]]
                stored["status"] = "running"
                if recorded_before:
                    stored["window_color"] = recorded_before
            with mock.patch.object(defaults.sys, "platform", "darwin"):
                host = platform_support.terminal_host()
            context = mock.Mock(); context.storage_path.return_value = Path("/tmp/fixture-sockets")
            not_found = subprocess.CompletedProcess([], 0, stdout="not found\n", stderr="")
            with mock.patch.object(platform_support, "terminal_host", return_value=host), \
                 mock.patch.object(host, "uses_browser_view", return_value=False, create=True), \
                 mock.patch("harness.project_context.project_context", return_value=context), \
                 mock.patch.object(host, "_live_screen_name", return_value="nmhp-x"), \
                 mock.patch.object(defaults.subprocess, "run", return_value=not_found), \
                 mock.patch.object(host, "_open_screen_view", return_value=colored):
                agent_view.open_view(root, session["id"])
            return next(item for item in control.snapshot(root)["sessions"] if item["id"] == session["id"])["window_color"]

    def test_a_teal_window_reopened_without_colour_is_recorded_as_not_coloured(self):
        recorded = self._reopen({"label": "Settings colour (Teal)", "hex": "#0F3F3B"}, False)
        self.assertEqual(recorded, {"label": "Not coloured (the terminal refused the colour)", "hex": ""})
        row = AgentRowSwatchTests()._swatch({"kind": "codex_delivery", "color": "settings", "window_color": recorded})
        self.assertIn("Not coloured", row)

    def test_a_refused_window_reopened_in_colour_is_recorded_in_colour(self):
        recorded = self._reopen({"label": "Not coloured (the terminal refused the colour)", "hex": ""}, True)
        self.assertEqual(recorded, {"label": "Settings colour (Teal)", "hex": "#0F3F3B"})
        row = AgentRowSwatchTests()._swatch({"kind": "codex_delivery", "color": "settings", "window_color": recorded})
        self.assertIn("#0F3F3B", row)


class AgentRowSwatchTests(unittest.TestCase):
    """The row's "Terminal color" note, executed (node) with the viewer suite's own runner."""

    script = _viewer_tests.BoardViewerTests.script
    declarations_only = _viewer_tests.BoardViewerTests.declarations_only
    run_node = _viewer_tests.BoardViewerTests.run_node

    def _swatch(self, session, view=None):
        return self.run_node("roleColorView=%s;process.stdout.write(JSON.stringify(sessionColorHtml(%s)));"
                             % (json.dumps(view), json.dumps(session)))

    def test_the_row_shows_the_window_colour_and_not_todays_settings(self):
        view = {"builder": {"hex": "#22c55e", "ink": "#15803d", "terminal": "#164A35", "label": "Green"}}
        opened = self._swatch({"kind": "codex_delivery", "color": "settings", "window_color": {"label": "Settings colour (Teal)", "hex": "#0F3F3B"}}, view)
        self.assertIn("#0F3F3B", opened); self.assertIn("Settings colour (Teal)", opened)
        launching = self._swatch({"kind": "codex_delivery", "color": "settings"}, view)
        self.assertIn("#164A35", launching); self.assertIn("Settings colour (Green)", launching)

    def test_a_refused_colour_shows_not_coloured_and_an_older_black_session_shows_black(self):
        refused = self._swatch({"kind": "codex_delivery", "color": "settings", "window_color": {"label": "Not coloured (the terminal refused the colour)", "hex": ""}})
        self.assertIn("background:transparent", refused); self.assertIn("Not coloured", refused)
        older = self._swatch({"kind": "codex_delivery", "color": "black", "color_hex": "#000000", "color_label": "Standard black"})
        self.assertIn("Standard black", older)

    def test_the_start_dialog_preselects_the_settings_colour(self):
        page = board_viewer.rendered_page()
        self.assertIn("{id:'settings',label:\"This agent's colour from Settings\"", page)
        self.assertIn("async function start(kind,color='settings'", page)
        self.assertNotIn("start(kind,'black')", page)


if __name__ == "__main__":
    unittest.main()
