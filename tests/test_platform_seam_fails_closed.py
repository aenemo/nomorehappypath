# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""The platform seam must fail CLOSED when it does not know the platform.

Review finding (2026-11-21): `platform_support.launch_problem()` is the one
predicate the installer, the settings page and the board read as "agents can
start here". A platform with no implementation was handed the macOS defaults
module, which declares no check of its own, so the seam answered "ready" on a
machine it had never been ported to (measured on Windows 11, v0.28.0) and the
launcher then refused every agent. The folder picker had the same class of
defect one layer down: it probed `os.uname()`, which does not exist on Windows,
so a refusal that was supposed to be named arrived as an AttributeError.
"""
from __future__ import annotations

import types
import unittest
from unittest import mock

from harness import platform_support
from harness.platform_support import defaults, linux


class UnknownPlatformIsRefusedTests(unittest.TestCase):
    def test_a_platform_with_no_implementation_is_not_reported_ready(self):
        for name in ("win32", "cygwin", "msys", "freebsd13"):
            with self.subTest(platform=name), mock.patch("sys.platform", name):
                problem = platform_support.launch_problem()
                self.assertNotEqual(problem, "", f"{name} must not claim agents can launch")
                self.assertIn(name, problem)
                self.assertIn("macOS and Linux", problem)

    def test_macos_keeps_its_own_answer(self):
        with mock.patch("sys.platform", "darwin"):
            self.assertEqual(platform_support.launch_problem(), "")

    def test_a_selected_modules_own_check_still_decides(self):
        with mock.patch("sys.platform", "linux"), \
                mock.patch.object(linux, "launch_problem", return_value="tmux is missing"):
            self.assertEqual(platform_support.launch_problem(), "tmux is missing")


class FolderPickerRefusesByNameTests(unittest.TestCase):
    def test_no_uname_still_raises_the_named_refusal(self):
        # A host without os.uname (Windows) must reach the refusal, not AttributeError.
        with mock.patch.object(defaults, "os", types.SimpleNamespace()):
            with self.assertRaises(defaults.UnsupportedPlatformOperation):
                defaults.FOLDER_CHOOSER.choose("Choose a project folder")


if __name__ == "__main__":
    unittest.main()
