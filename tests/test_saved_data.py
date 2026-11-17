# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Tests for harness.saved_data: the hint, previous-version state, UPGRADING.md
section parsing and the Reviewer's "Saved data: ..." verdict-line parsing, per
SAVED_DATA_UPGRADE_SAFETY.md section 3.1-3.4 and the acceptance tests of
section 12 items 1, 2 and 6 that are pure-function, not board-state, checks.
"""
from __future__ import annotations

import unittest

from harness import saved_data


class HintTests(unittest.TestCase):
    """Section 12.1: the hint spots likely paths; it decides nothing."""

    def test_migration_folder_path_is_hinted(self):
        self.assertEqual(saved_data.hint(["migrations/0002_due.py"]), ["migrations/0002_due.py"])

    def test_schema_sql_and_prisma_and_schema_rb_are_hinted(self):
        paths = ["db/schema.sql", "prisma/schema.prisma", "app/db/schema.rb"]
        self.assertEqual(saved_data.hint(paths), sorted(paths))

    def test_same_migration_path_under_tests_is_ignored(self):
        self.assertEqual(saved_data.hint(["tests/migrations/0002_due.py", "test_migrate_helper.py"]), [])

    def test_json_settings_shape_change_is_not_hinted(self):
        self.assertEqual(saved_data.hint(["app/settings.json"]), [])

    def test_added_destructive_sql_line_is_hinted(self):
        found = saved_data.hint(["app/queries.py"], {"app/queries.py": ["cur.execute('DROP TABLE legacy')"]})
        self.assertEqual(found, ["app/queries.py"])

    def test_destructive_sql_in_a_test_file_is_ignored(self):
        found = saved_data.hint(["tests/test_queries.py"], {"tests/test_queries.py": ["DELETE FROM widgets"]})
        self.assertEqual(found, [])

    def test_harmless_added_line_is_not_hinted(self):
        found = saved_data.hint(["app/queries.py"], {"app/queries.py": ["def new_helper(): return 1"]})
        self.assertEqual(found, [])

    def test_removed_destructive_line_without_an_added_one_is_not_hinted(self):
        # hint() only ever receives ADDED lines from its caller; a removal is
        # never passed in, so this just proves an empty added-line list hints nothing.
        found = saved_data.hint(["app/queries.py"], {"app/queries.py": []})
        self.assertEqual(found, [])

    def test_result_is_sorted_and_deduplicated(self):
        found = saved_data.hint(["migrations/b.py", "migrations/a.py", "migrations/a.py"])
        self.assertEqual(found, ["migrations/a.py", "migrations/b.py"])


class PreviousStateTests(unittest.TestCase):
    """Section 12.2: first/known/unknown classification."""

    def test_no_repository_is_unknown(self):
        self.assertEqual(saved_data.previous_state(False, "", None), "unknown")

    def test_unresolved_main_is_unknown(self):
        self.assertEqual(saved_data.previous_state(True, "", None), "unknown")

    def test_empty_main_tree_is_first(self):
        self.assertEqual(saved_data.previous_state(True, "abc123", 0), "first")

    def test_main_with_files_is_known(self):
        self.assertEqual(saved_data.previous_state(True, "abc123", 4), "known")


class UpgradingSectionsTests(unittest.TestCase):
    """Section 12.3: the four required UPGRADING.md headings."""

    COMPLETE = (
        "## What changes in your saved data\n"
        "Each to-do gains an empty due date.\n\n"
        "## Where your data is\n"
        "todo.db in the project folder; set TODO_DB to point at a test copy.\n\n"
        "## Before you update\n"
        "Stop the app, copy todo.db, keep v1.2.\n\n"
        "## If something goes wrong\n"
        "Stop the new app, put the copy back, start v1.2. Anything saved after the update is lost.\n"
    )

    def test_complete_document_has_no_missing_sections(self):
        self.assertEqual(saved_data.missing_upgrading_sections(self.COMPLETE), [])
        sections = saved_data.upgrading_sections(self.COMPLETE)
        self.assertEqual(sections["## Where your data is"], "todo.db in the project folder; set TODO_DB to point at a test copy.")

    def test_missing_heading_is_reported(self):
        text = self.COMPLETE.replace("## If something goes wrong\n", "").split("Stop the new app")[0]
        missing = saved_data.missing_upgrading_sections(text)
        self.assertIn("## If something goes wrong", missing)

    def test_empty_heading_counts_as_missing(self):
        text = self.COMPLETE.replace(
            "## Before you update\nStop the app, copy todo.db, keep v1.2.\n\n",
            "## Before you update\n\n",
        )
        self.assertIn("## Before you update", saved_data.missing_upgrading_sections(text))

    def test_heading_text_used_as_prose_is_not_mistaken_for_a_real_section(self):
        text = "Some notes mention ## Where your data is in passing.\n" + self.COMPLETE
        # the prose line does not match exactly (has a trailing period/words after),
        # so the real section after it is still the one picked up whole.
        self.assertEqual(saved_data.missing_upgrading_sections(text), [])


class DeliveryDeclarationTests(unittest.TestCase):
    """Delivery's loose hand-in declaration (spec 3.2.1), distinct from the Reviewer's strict verdict line."""

    def test_no_phrase_anywhere_returns_none(self):
        self.assertIsNone(saved_data.delivery_declaration("The app looks good. Security check: fine."))

    def test_unchanged_with_trailing_prose(self):
        result = saved_data.delivery_declaration("Saved data: unchanged. The app looks good.")
        self.assertEqual(result, {"status": "unchanged"})

    def test_changed_with_what_on_its_own_line(self):
        result = saved_data.delivery_declaration("Saved data: changed — each to-do gains a due date\nSecurity check: fine.")
        self.assertEqual(result, {"status": "changed", "what": "each to-do gains a due date"})

    def test_changed_with_leading_prose_on_same_line(self):
        result = saved_data.delivery_declaration("All done. Saved data: changed: a new column for due dates\nSecurity check: fine.")
        self.assertEqual(result, {"status": "changed", "what": "a new column for due dates"})


class ParseVerdictLineTests(unittest.TestCase):
    """Section 12.6: the Reviewer's six accepted "Saved data: ..." forms."""

    def test_no_line_at_all_returns_none(self):
        self.assertIsNone(saved_data.parse_verdict_line("TASK DONE: YES — it works.\nSecurity check: fine."))

    def test_bare_unchanged(self):
        self.assertEqual(saved_data.parse_verdict_line("Saved data: unchanged"), {"status": "unchanged", "reason": ""})

    def test_unchanged_with_reason(self):
        result = saved_data.parse_verdict_line("Saved data: unchanged — the hinted file only renames a function")
        self.assertEqual(result, {"status": "unchanged", "reason": "the hinted file only renames a function"})

    def test_changed_passed(self):
        result = saved_data.parse_verdict_line("Saved data: changed — each to-do gains a due date — upgrade check S-UPG: passed")
        self.assertEqual(result, {"status": "changed", "outcome": "passed", "what": "each to-do gains a due date", "row_id": "S-UPG"})

    def test_changed_failed(self):
        result = saved_data.parse_verdict_line("Saved data: changed — a column is dropped — upgrade check S-7: failed")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["row_id"], "S-7")

    def test_changed_not_run(self):
        result = saved_data.parse_verdict_line("Saved data: changed — a new index — upgrade check: not run (the old version needs Postgres this machine lacks)")
        self.assertEqual(result["outcome"], "not_run")
        self.assertEqual(result["why"], "the old version needs Postgres this machine lacks")

    def test_changed_first_version(self):
        result = saved_data.parse_verdict_line("Saved data: changed — the first saved record — first version, nothing to upgrade")
        self.assertEqual(result["outcome"], "first_version")

    def test_changed_missing_parts(self):
        result = saved_data.parse_verdict_line('Saved data: changed — a renamed column — upgrade check: missing UPGRADING.md "Before you update"')
        self.assertEqual(result["outcome"], "missing")
        self.assertEqual(result["missing"], 'UPGRADING.md "Before you update"')

    def test_malformed_line_is_reported_as_malformed_not_silently_dropped(self):
        result = saved_data.parse_verdict_line("Saved data: changed, I think, not sure")
        self.assertEqual(result["status"], "malformed")

    def test_only_the_first_matching_line_is_used(self):
        summary = "TASK DONE: YES\nSaved data: unchanged\nSecurity check: fine.\nSaved data: changed — ignored second line — upgrade check S-1: passed"
        self.assertEqual(saved_data.parse_verdict_line(summary), {"status": "unchanged", "reason": ""})
