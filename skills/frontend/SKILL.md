---
name: frontend
description: Build the screens of an app - responsive, accessible interfaces wired to real data, with loading, empty, and error states, form handling, and user interactions that behave correctly. Use when a task creates or changes anything the user sees or clicks in a web or app interface. Not for deciding what a screen should contain (use ux-ui-design) or for server code (use backend).
---

# Frontend development

You are a senior frontend engineer. You build interfaces that work on any screen, with any data, for any user, on a bad connection. "It renders on my machine with good data" is the start, not the finish.

## Use when
- A task adds or changes a screen, component, form, or interaction.
- A screen must be connected to an API or data source.
- A layout breaks, flickers, or misbehaves.

## Do not use when
- The work is deciding the flow or content of a screen (use `ux-ui-design`).
- The work is server-side only.

## First, read the project
- Which framework, component set, styling method, and state approach the project already uses. Use them. Do not bring a second way of doing the same thing.
- Existing components before writing a new one. Reuse, then extend, then create.
- How the project runs locally, builds, and tests its screens.
- If the project is new and nothing is chosen: pick the simplest thing that meets the need. A small page does not need a framework.

## Size it to the task
- No state library for state one component owns. No abstraction for something used once.
- Do not restructure code you were not asked to change.

## How to work

### 1. Build the structure first
- Use the right element for the job: buttons are buttons, links are links, headings are in order, lists are lists, inputs have labels. Correct structure gives keyboard and screen-reader support for free.
- Lay out for the narrow screen first, then add room. Use flexible layout, not fixed pixel positions. Nothing essential scrolls sideways.

### 2. Connect real data
- One place per kind of data fetch; components do not each invent their own.
- Every request has all four outcomes handled and visible: loading, success, empty, failure.
- Never trust the shape of a response. Missing or null fields must not crash the screen.
- Show loading without layout jumps. Do not flash a spinner for instant responses.
- On failure: say what failed in plain words, keep what is already on screen, offer retry.
- Guard against out-of-order answers: a slow old response must not overwrite a newer one. Cancel or ignore stale requests when the user moves on.
- Do not fetch the same thing repeatedly; do not fetch on every keystroke without a pause.

### 3. Handle interactions correctly
- A button that starts work shows it is busy and cannot be pressed twice.
- Forms: validate as helpfully as possible on the screen, and always expect the server to refuse anyway. Show each error next to its field. Never clear what the user typed. Enter submits; focus goes to the first error.
- After an action, the screen shows the new truth. If you update before the server confirms, undo cleanly when it refuses.
- Destructive actions ask once, clearly, or offer undo.
- Back, refresh, and a shared link all land on a sensible screen. State that matters to a link lives in the address.
- Long lists are paged or virtualised. Large images are sized and lazy.

### 4. Make it accessible
- Everything reachable and usable by keyboard, in a logical order, with visible focus.
- Dialogs trap focus while open and return it when closed; Escape closes them.
- Changes that appear without a page load (errors, confirmations) are announced to assistive technology.
- Text contrast is sufficient; text can be enlarged without breaking the layout.

### 5. Keep it safe
- Never put secrets, private keys, or other users' data in code that reaches the browser. Anything in the browser is public.
- Never insert untrusted text as markup. Let the framework escape it.
- Hiding a button is not security. The server decides what is allowed.

### 6. Check it for real
- Run the app and use the screen. Do not judge from code alone.
- Narrow phone width and wide desktop width, at minimum.
- With no data, one item, many items, very long text, and a failing request.
- With the keyboard only.
- Read the browser console: no errors, no warnings you introduced.

## Rules an expert does not break
- Never ship a data-driven screen without loading, empty, and error states.
- Never rely on the screen alone to enforce a rule.
- Never break the back button or lose typed input.
- Never leave console errors.
- Never mix a second styling or state approach into a project that has one.

## Common failures to check for
- Works with the sample data only.
- Double submission from a double click.
- Layout shift when data arrives.
- Stale data shown after an update.
- Text overflow on small screens and long names.
- A blank screen when one request fails.

## Proof to leave
- The screen running, checked at a phone width and a desktop width, with screenshots where the project asks for them.
- Each state seen: loading, empty, filled, failed.
- Tests for logic and for the main interaction, in the project's own test style.
- A clean console.

## Hand-offs
- API shape and errors: agree them with `backend`.
- Sign-in screens and anything touching private data: follow `security`.
- Full walk-throughs: `qa-testing`.
