#!/usr/bin/env python3
# Copyright (c) 2026 KpiMinds LLC. Licensed under the Apache License, Version 2.0; see LICENSE. SPDX-License-Identifier: Apache-2.0
"""Run the saved-data upgrade-safety test shard on the owner's named Linux test machine
(SAVED_DATA_UPGRADE_SAFETY.md spec 12.10: "macOS and Linux: the fixture row runs under the
platform confinement on both"). Reuses this project's established test-machine convention
(the `harness-next-selfcheck-test-lock-v2` exclusive lock, one fresh timestamped run folder,
cleaned up after) instead of inventing a new one.

Declared as a machine-dependent command per `directives/AGENT.md`'s test-machine chapter:
`TEST_MACHINE_GEN=1 python3 scripts/saved_data_linux_proof.py` - the `TEST_MACHINE_GEN=`
prefix is what `harness.test_machine.machine_dependent` checks to stamp the result with the
machine's revision; this script itself does not read that prefix.

Prints the remote `python3 -m unittest` output (its own `Ran <n> tests` line included) and
exits with its return code; exits 2 with a plain reason if the machine is not usable.
`tests/test_saved_data_linux_machine.py` wraps `main()` as a unittest, so a Scenario Ledger row
can cite it with a recognized test runner.

Usage: TEST_MACHINE_GEN=1 python3 scripts/saved_data_linux_proof.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.project_context import ProjectContext, project_context  # noqa: E402
from harness import test_machine  # noqa: E402

MODULES = [
    "tests.test_saved_data",
    "tests.test_saved_data_previous_version_export",
    "tests.test_saved_data_todo_fixture",
    "tests.test_saved_data_accept_confirmation",
    "tests.test_saved_data_request_info",
    "tests.test_saved_data_verdict_problem",
    "tests.test_review_brief",
]

_RUNNER_SCRIPT = '''#!/usr/bin/env python3
import fcntl, os, subprocess, sys, tempfile, time
LOCK_DIR = os.path.expanduser("~/harness-next-selfcheck-test-lock-v2")
RUN_DIR = sys.argv[1]
MODULES = sys.argv[2:]
def write_holder():
    holder = f"v2 engineering-0033-3ebb94 delivery pid={os.getpid()} start={time.ctime()} since={time.ctime()}\\n"
    fd, tmp_path = tempfile.mkstemp(dir=LOCK_DIR)
    with os.fdopen(fd, "w") as fh:
        fh.write(holder)
    os.rename(tmp_path, os.path.join(LOCK_DIR, "holder.txt"))
def main():
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_fd = os.open(os.path.join(LOCK_DIR, "lock"), os.O_CREAT | os.O_RDWR)
    deadline = time.monotonic() + 240
    acquired = False
    while time.monotonic() < deadline:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            break
        except BlockingIOError:
            time.sleep(1)
    if not acquired:
        holder = ""
        try:
            with open(os.path.join(LOCK_DIR, "holder.txt")) as fh:
                holder = fh.read().strip()
        except OSError:
            pass
        print(f"LOCK CONTENTION: held by {holder or chr(39)+chr(39)}", file=sys.stderr)
        sys.exit(2)
    try:
        write_holder()
        env = dict(os.environ)
        env["PYTHONPATH"] = RUN_DIR
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-m", "unittest", *MODULES], cwd=RUN_DIR, env=env,
                                 capture_output=True, text=True, timeout=240)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
if __name__ == "__main__":
    main()
'''


def _options(known_hosts: str, port: int, *, scp: bool) -> list[str]:
    """Shared non-interactive connection flags; scp's port flag is `-P`, ssh's is `-p`."""
    return [
        "-F", "/dev/null", "-i", "KEYPATH", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", f"UserKnownHostsFile={known_hosts}", "-o", "StrictHostKeyChecking=yes",
        "-o", "ControlMaster=no", "-o", "ControlPath=none", "-o", "ForwardAgent=no",
        "-P" if scp else "-p", str(port),
    ]


def _project_context() -> ProjectContext:
    """The context this run's test-machine connection is stored under.

    A compatibility context (this project's own `.harness` folder) is tried
    first. This installation's project is managed by an outer harness that
    keeps data under `~/.harness-home/projects/<id>/`, outside the project
    folder entirely, so this also tries every such project whose `data`
    folder holds a `test_machine` record for the same machine address this
    project's `.harness`-local record (if any) would otherwise be missing -
    there is normally exactly one on a developer's machine. Returns the
    compatibility context if none of those has a usable record either, so
    the caller's own "not connected" message names the real cause.
    """
    compat = project_context(str(ROOT))
    if test_machine.read(compat):
        return compat
    home = Path.home() / ".harness-home" / "projects"
    candidates = []
    for data_root in sorted(home.glob("*/data")):
        candidate = ProjectContext(ROOT, data_root, data_root.parent / "workspaces")
        if test_machine.read(candidate):
            candidates.append(candidate)
    # Several harness-home projects can each hold a test-machine record on a
    # shared developer machine; only one is THIS project's. Prefer one that is
    # immediately usable (connected, not asking to re-authenticate) over the
    # first one found, since a stale/foreign record would otherwise win by
    # alphabetical luck.
    for candidate in candidates:
        if test_machine.usability(candidate)[0]:
            return candidate
    return candidates[0] if candidates else compat


def main() -> int:
    """Run the saved-data test shard on the connected Linux machine; return its exit code (see module note for 2's two meanings)."""
    context = _project_context()
    connection = test_machine.read(context)
    if not connection or not connection.get("key_path"):
        print("not run: no test machine is connected for this project", file=sys.stderr)
        return 2
    ok, _code, message = test_machine.usability(context)
    if not ok:
        print(f"not run: {message}", file=sys.stderr)
        return 2
    key_path = connection["key_path"]
    known_hosts = connection["known_hosts_path"]
    address, user, port = connection["address"], connection["user"], int(connection.get("port", 22))
    ssh_options = [opt.replace("KEYPATH", key_path) for opt in _options(known_hosts, port, scp=False)]
    scp_options = [opt.replace("KEYPATH", key_path) for opt in _options(known_hosts, port, scp=True)]
    target = f"{user}@{address}"
    run_id = f"harness-next-selfcheck-run-{time.strftime('%Y%m%d%H%M%S')}-saved-data"
    run_path = f"~/{run_id}"

    with tempfile.TemporaryDirectory() as scratch:
        archive_path = Path(scratch) / "candidate.tar"
        subprocess.run(["git", "archive", "--format=tar", "HEAD", "-o", str(archive_path)], cwd=ROOT, check=True)
        runner_path = Path(scratch) / "locked_run.py"
        runner_path.write_text(_RUNNER_SCRIPT)

        # Everything from the first remote mkdir onward creates state on the machine, so cleanup
        # (the one line this run is allowed to remove) must run whichever of these steps fails.
        try:
            subprocess.run(["ssh", *ssh_options, target, f"mkdir -p {run_path}/src"], check=True)
            subprocess.run(["scp", *scp_options, str(archive_path), str(runner_path), f"{target}:{run_path}/"], check=True)
            subprocess.run(["ssh", *ssh_options, target, f"tar -xf {run_path}/candidate.tar -C {run_path}/src && rm {run_path}/candidate.tar"], check=True)
            result = subprocess.run(
                ["ssh", *ssh_options, target, f"python3 {run_path}/locked_run.py {run_path}/src " + " ".join(MODULES)],
                capture_output=True, text=True, timeout=300,
            )
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            return result.returncode
        finally:
            subprocess.run(["ssh", *ssh_options, target, f"rm -rf {run_path}"], check=False)


if __name__ == "__main__":
    sys.exit(main())
