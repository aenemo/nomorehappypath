# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Run the saved-data upgrade-safety test shard on the owner's named Linux test machine
(SAVED_DATA_UPGRADE_SAFETY.md spec 12.10: "macOS and Linux: the fixture row runs under the
platform confinement on both"). A thin unittest wrapper around
`scripts.saved_data_linux_proof` so a Scenario Ledger row can cite it with a recognized test
runner (`python3 -m unittest ...`); the real work - resolving the real connection, taking this
project's established `harness-next-selfcheck-test-lock-v2` lock, copying the exact committed
candidate, running the shard remotely and cleaning up - is `scripts/saved_data_linux_proof.py`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import saved_data_linux_proof  # noqa: E402


class LinuxMachineProofTests(unittest.TestCase):
    def test_saved_data_shard_passes_on_the_linux_test_machine(self):
        """Runs the real remote shard once; skips (never fails) when no machine is connected here."""
        exit_code = saved_data_linux_proof.main()
        if exit_code == 2:
            self.skipTest("the project's test machine is not connected in this environment")
        self.assertEqual(exit_code, 0, "the remote test shard did not exit 0; see stdout/stderr above for its own failures")
