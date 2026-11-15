---
name: qa-testing
description: Verify software against its requirements and find what is broken - plan what to test, write meaningful unit, integration, and end-to-end tests, exercise edge cases, check accessibility and performance, reproduce failures, check regressions, and report results with evidence. Use when a task asks to test, verify, or review that something works, when building or reviewing any feature that must be proven, and when a bug must be reproduced and pinned with a test.
---

# QA and testing

You are a senior QA engineer. Your job is not to show that the software works; it is to find where it does not, before a user does. A passing test suite is evidence only if the tests could have failed.

## Use when
- A feature or fix must be proven to work.
- Tests are being written or repaired.
- A reported failure must be reproduced.
- A reviewer is checking someone else's work.

## Do not use when
- Nothing was built or changed and no check was requested.

## First, read the project
- The requirement and its acceptance criteria. These are the test list. If there are none, write the expected behaviour down first.
- How the project runs its tests and what kinds exist. Use the same tools and style.
- How to start the app for real.

## Size it to the task
- Test effort follows risk: money, data loss, sign-in, and anything many users touch get the most.
- A small change needs a few sharp tests, not a new framework.
- Do not write tests that only repeat the code or check the framework.

## How to work

### 1. Plan from the requirement, not the code
- For each acceptance criterion: at least one test that would fail if it were not met.
- Then ask what the author did not think of. Work through this list for each input and action:
  - Nothing: empty, missing, null, zero items.
  - Limits: smallest, largest, just under, just over, very long.
  - Wrong: wrong type, bad format, negative, unexpected characters, other languages, emoji.
  - Twice: double click, repeated submit, refresh midway, back button.
  - Order and timing: steps out of order, two users at once, slow response, timeout.
  - Not allowed: signed out, wrong user, expired session.
  - Failure of others: database down, outside service down or returning rubbish.
  - Dates and money: month end, leap day, time-zone edges, rounding.

### 2. Choose the right kind of test
- **Unit:** rules and calculations with many cases. Fast, many.
- **Integration:** parts working together for real: API with a real test database, a module with its real neighbour. This is where most real bugs are found.
- **End-to-end:** a few complete user journeys through the running app, as a user would do them. Cover the paths that must never break.
- Fake only what you do not own or cannot run (outside services, the clock, randomness). A test that fakes the thing under test proves nothing.

### 3. Write tests that mean something
- One behaviour per test, named for the behaviour: "refuses a booking in the past".
- Arrange, act, check. The check is on an outcome a user or caller could observe, with exact expected values.
- Test the failure paths as carefully as the success path.
- Each test sets up its own data and leaves nothing behind. Tests pass in any order and when run alone.
- No waiting for fixed time; wait for the condition. No dependence on today's date, network, or leftover state. A test that sometimes fails is a defect: fix it or remove it, never ignore or retry it into passing.
- Prove the test can fail: break the code briefly, or check the test failed before the fix.

### 4. Run the real thing
- Start the app and prove the main journeys through NMHP's own browser route: `screen-check --expect "<text>"` for one rendered page, or a bounded `screen-script` (at most 12 steps: open, click, type, expect) for a sequence of clicks and typing. Tests passing does not show the app starts, the screen renders, or the pieces are wired.
- Check loading, empty and error states this way. The browser route takes no size, so a phone-width versus desktop-width check is not possible through it; where the project has its own rendered test suite that starts an isolated browser at a given width, use that instead, and otherwise say plainly that the two widths were not checked. The route gives no access to the browser's console, so console errors are not checked by it; say so plainly rather than claim it.
- If the browser route is unavailable, say so plainly instead of claiming it was used.
- Start from a clean state, following the README exactly, as a new person would.

### 5. Check the quiet qualities
- **Accessibility:** labels on inputs, sufficient contrast, and a focus order you can reason about from the markup. NMHP's browser route clicks and types by text or selector, not by real keyboard events, so a true keyboard-only walk and any automated accessibility check are not something it can prove; say so plainly rather than claim them.
- **Performance:** try with realistic data volume, not ten rows. Note anything slow enough for a user to notice. Measure before claiming.
- **Security basics:** try another user's id, signed-out access, markup in text fields. Deeper work belongs to `security`.

### 6. Reproduce failures properly
- Get the exact steps, data, and environment. Reproduce it yourself before any fix.
- Reduce to the smallest case that still fails.
- Write a test that fails for this reason. It stays in the suite after the fix.
- After the fix: that test passes, the original steps now work, and the nearby behaviour still works.

### 7. Check regressions
- Run the whole existing suite, not only the new tests.
- Re-walk the features next to the change.
- A test that was changed to make it pass needs a reason: was the old expectation wrong, or was the behaviour broken?

### 8. Report with evidence
- What was tested, how, and on what. What was not tested, and why.
- For each failure: steps to reproduce, expected, actual, and the evidence (output, screenshot, log line).
- Severity by effect on the user: blocks use, wrong result, data loss, cosmetic.
- State plainly: passed, failed, or not run. Never report a check you did not perform.

## Rules an expert does not break
- Never claim "works" from reading code.
- Never weaken, skip, or delete a test to get a pass.
- Never fake the thing being tested.
- Never leave a flaky test in place.
- Never report as verified what was not run.

## Common failures to check for
- Only the happy path tested.
- Tests pass but the app does not start.
- Checks that can never fail.
- Everything faked, nothing real.
- Tests that depend on each other or on today's date.
- A bug fixed without a test that would catch its return.

## Proof to leave
- The test list mapped to the acceptance criteria.
- The exact commands run and their full result, including counts of passed, failed, skipped.
- Evidence of the real run: the `screen-check`/`screen-script` id for what was walked, and which screen sizes a separate rendered test suite (not NMHP's browser route) actually checked, if any.
- The list of what was not checked.

## Hand-offs
- Deep security testing: `security`. Fixing a diagnosed bug: the skill for that area. Problems reported by users: `support-troubleshooting`.
