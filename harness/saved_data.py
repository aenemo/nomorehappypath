# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Pure helpers for saved-data upgrade safety (SAVED_DATA_UPGRADE_SAFETY.md sections 3.1-3.4).

Deciding whether a release changes the owner's saved data is never mechanical
(spec 3.2.5): Delivery declares it and the Reviewer states the real verdict in
one required line. This module holds only the parts that ARE mechanical and
so can be tested on their own, with no board state and no live Git process:
- `hint`: spots likely data-changing paths for the Reviewer, deciding nothing.
- `previous_state`: classifies the last-accepted version (first/known/unknown).
- `upgrading_sections` / `missing_upgrading_sections`: read UPGRADING.md's
  four required headings.
- `parse_verdict_line`: reads the Reviewer's required "Saved data: ..." line.
`harness/board.py` does the Git work (resolving `main`, diffing commits,
building `UPGRADING.md`'s text) and calls these with plain strings/lists.
"""
from __future__ import annotations

import re

# The four headings UPGRADING.md must carry, each non-empty, in this order
# (spec 3.3.3). Matched as an exact stripped line so a heading used as prose
# elsewhere in the document is never mistaken for the real section start.
REQUIRED_UPGRADING_HEADINGS: tuple[str, ...] = (
    "## What changes in your saved data",
    "## Where your data is",
    "## Before you update",
    "## If something goes wrong",
)

_TEST_PATH = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[^/]*$|\.test\.[^/]*$|\.spec\.[^/]*$",
    re.IGNORECASE,
)
_MIGRATION_PATH = re.compile(
    r"(^|/)(migrations|migrate|alembic)(/|$)|(^|/)db/migrate(/|$)",
    re.IGNORECASE,
)
_SCHEMA_NAME = re.compile(r"(^|/)schema\.(sql|rb)$|\.prisma$", re.IGNORECASE)
_DESTRUCTIVE_SQL = re.compile(
    r"\b(ALTER TABLE|DROP TABLE|DROP COLUMN|RENAME COLUMN|TRUNCATE|DELETE FROM)\b",
    re.IGNORECASE,
)


def is_test_path(path: str) -> bool:
    """True when `path` is a test file/folder, exempt from the hint (spec 3.2.2)."""
    return bool(_TEST_PATH.search(path))


def hint(changed_paths: list[str], added_lines_by_path: dict[str, list[str]] | None = None) -> list[str]:
    """Likely saved-data-changing paths among a candidate's changed, non-test files.

    Args:
        changed_paths: paths that differ between the previous version and the
            candidate (test paths are filtered out here regardless of what
            the caller already removed, so this stays safe on its own).
        added_lines_by_path: for each changed path, lines the diff ADDED
            (never removed lines: a destructive statement being taken OUT is
            not itself a reason to hint); a path missing from this dict is
            treated as adding no lines. Defaults to no added-line data.

    Returns: a sorted, de-duplicated list of paths that look like a
        saved-data change by filename/location or an added destructive SQL
        keyword. This is a hint only (spec 3.2.2): it never decides the
        verdict, and it misses JSON/settings-shape or ORM-model changes.
    """
    added_lines_by_path = added_lines_by_path or {}
    found: set[str] = set()
    for path in changed_paths:
        if is_test_path(path):
            continue
        if _MIGRATION_PATH.search(path) or _SCHEMA_NAME.search(path):
            found.add(path)
            continue
        for line in added_lines_by_path.get(path, []):
            if _DESTRUCTIVE_SQL.search(line):
                found.add(path)
                break
    return sorted(found)


def previous_state(has_repository: bool, main_commit: str, main_tree_entry_count: int | None) -> str:
    """Classify the last-accepted version for the upgrade check (spec 3.1).

    Args:
        has_repository: whether this task's project is a Git repository at all.
        main_commit: the project's `main` tip commit hash, or "" when it
            cannot be resolved.
        main_tree_entry_count: how many entries `main`'s tree holds, or None
            when `main_commit` is falsy (then irrelevant and ignored).

    Returns: "unknown" (no repository, or `main` cannot be resolved —
        the upgrade check cannot run), "first" (`main` has no commit, or its
        tree is empty — nothing to upgrade from; the board's own repository
        initialization commits no files, so an empty tree means exactly
        that), or "known" (`main` has a commit with app files; the upgrade
        check runs against it).
    """
    if not has_repository or not main_commit:
        return "unknown"
    if not main_tree_entry_count:
        return "first"
    return "known"


def upgrading_sections(text: str) -> dict[str, str]:
    """Split UPGRADING.md text into its four required sections (spec 3.3.3).

    Args: text: the full UPGRADING.md content.
    Returns: a dict of heading -> stripped body text, for only the headings
        actually present in `text`; a heading missing from the dict is a
        heading `missing_upgrading_sections` will report.
    """
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        """Commit the heading in `current` and its buffered body lines into `sections`; no-op before the first heading."""
        if current is not None:
            sections[current] = "\n".join(buffer).strip()

    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped in REQUIRED_UPGRADING_HEADINGS:
            flush()
            current = stripped
            buffer = []
        elif current is not None:
            buffer.append(line)
    flush()
    return sections


def missing_upgrading_sections(text: str) -> list[str]:
    """Required UPGRADING.md headings that are absent or empty, in spec order."""
    sections = upgrading_sections(text)
    return [heading for heading in REQUIRED_UPGRADING_HEADINGS if not sections.get(heading, "").strip()]


def delivery_declaration(summary: str) -> dict[str, str] | None:
    """Delivery's saved-data declaration, read loosely from its hand-in summary (spec 3.2.1).

    Unlike the Reviewer's six strict verdict forms (`parse_verdict_line`),
    Delivery only ever states WHETHER saved data changes - there is no
    outcome yet at request time, since the upgrade check has not run - so
    this matches "Saved data: unchanged" or "Saved data: changed" as a
    substring anywhere in the summary (any trailing prose, any leading
    prose), the same loose way the existing "Security:"/"Code quality:"
    hand-in lines are already read.

    Returns: None when neither phrase appears anywhere (the caller's "a
    final request needs a saved-data declaration" refusal). Otherwise
    {"status": "unchanged"}, or {"status": "changed", "what": "<the text
    after the phrase, up to the next line break, stripped of a leading
    separator and a trailing period>"}.
    """
    if "Saved data: changed" in summary:
        tail = summary.split("Saved data: changed", 1)[1].lstrip(" :—-")
        what = tail.split("\n", 1)[0].strip().rstrip(".")
        return {"status": "changed", "what": what}
    if "Saved data: unchanged" in summary:
        return {"status": "unchanged"}
    return None


_UNCHANGED_BARE = re.compile(r"^Saved data:\s*unchanged\s*$")
_UNCHANGED_REASON = re.compile(r"^Saved data:\s*unchanged\s*—\s*(?P<reason>.+)$")
_CHANGED_OUTCOME = re.compile(
    r"^Saved data:\s*changed\s*—\s*(?P<what>.+?)\s*—\s*upgrade check (?P<row_id>\S+):\s*(?P<outcome>passed|failed)\s*$"
)
_CHANGED_NOT_RUN = re.compile(
    r"^Saved data:\s*changed\s*—\s*(?P<what>.+?)\s*—\s*upgrade check:\s*not run \((?P<why>.+)\)\s*$"
)
_CHANGED_FIRST = re.compile(
    r"^Saved data:\s*changed\s*—\s*(?P<what>.+?)\s*—\s*first version, nothing to upgrade\s*$"
)
_CHANGED_MISSING = re.compile(
    r"^Saved data:\s*changed\s*—\s*(?P<what>.+?)\s*—\s*upgrade check:\s*missing (?P<missing>.+)$"
)


def parse_verdict_line(summary: str) -> dict[str, str] | None:
    """Find and parse the Reviewer's one required "Saved data: ..." line (spec 3.2.3).

    Args: summary: the full verdict text (may hold many lines; only the first
        line starting with "Saved data:" is read, matching the board's rule
        that exactly one such line is required).
    Returns: None when no "Saved data:" line is present at all (the caller's
        3.2.3 refusal case). Otherwise a dict with "status" ("unchanged" or
        "changed", or "malformed" when the line starts with "Saved data:"
        but matches none of the six accepted forms):
        - unchanged: {"status": "unchanged", "reason": "<text after the em
          dash, or "" for the bare line>"}
        - changed/passed or failed: {"status": "changed", "outcome": "passed"
          or "failed", "what": "<what changed>", "row_id": "<ledger row id>"}
        - changed/not run: {"status": "changed", "outcome": "not_run",
          "what": "<what changed>", "why": "<reason>"}
        - changed/first version: {"status": "changed", "outcome":
          "first_version", "what": "<what changed>"}
        - changed/missing parts: {"status": "changed", "outcome": "missing",
          "what": "<what changed>", "missing": "<the missing parts>"}
        - malformed: {"status": "malformed", "line": "<the offending line>"}
    """
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line.startswith("Saved data:"):
            continue
        match = _UNCHANGED_BARE.match(line)
        if match:
            return {"status": "unchanged", "reason": ""}
        match = _UNCHANGED_REASON.match(line)
        if match:
            return {"status": "unchanged", "reason": match.group("reason").strip()}
        match = _CHANGED_OUTCOME.match(line)
        if match:
            return {
                "status": "changed", "outcome": match.group("outcome"),
                "what": match.group("what").strip(), "row_id": match.group("row_id"),
            }
        match = _CHANGED_NOT_RUN.match(line)
        if match:
            return {
                "status": "changed", "outcome": "not_run",
                "what": match.group("what").strip(), "why": match.group("why").strip(),
            }
        match = _CHANGED_FIRST.match(line)
        if match:
            return {"status": "changed", "outcome": "first_version", "what": match.group("what").strip()}
        match = _CHANGED_MISSING.match(line)
        if match:
            return {
                "status": "changed", "outcome": "missing",
                "what": match.group("what").strip(), "missing": match.group("missing").strip(),
            }
        return {"status": "malformed", "line": line}
    return None
