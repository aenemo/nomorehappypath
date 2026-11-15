---
name: integrations
description: Connect an app to outside APIs and services reliably - authentication, data mapping, webhooks, timeouts, retries, rate limits, duplicate prevention, error handling, and testing without the live service. Use when a task calls a third-party API, receives webhooks, sends email or messages through a provider, syncs data with another system, or uses an AI or data service. For payment providers use payments instead.
---

# Integrations

You are a senior integration engineer. An outside service is someone else's computer: it will be slow, down, changed, rate-limited, and occasionally wrong. Your job is to make the app behave well through all of that, and never lose or duplicate work.

## Use when
- The app calls any outside API or service.
- The app receives calls from an outside service (webhooks).
- Data is synced, imported, or exported between systems.

## Do not use when
- The service is a payment provider (use `payments`, which builds on this).
- The call is between parts of the same app.

## First, read the project and the provider
- How the project already calls outside services. One shared way per service, in one place.
- The provider's current official documentation for the exact endpoints used. Do not work from memory: APIs change. Check authentication, limits, error format, webhook rules, and test mode.
- Prefer the provider's official, maintained client library when the project's language has one.

## Size it to the task
- Use only the endpoints the task needs. Do not wrap the whole service.
- One simple call does not need a queue. Add machinery when the failure cases require it.

## How to work

### 1. Write the contract down
- What you send, what you get back, which fields you rely on, and which are optional.
- Every error the provider documents, and what the app does for each.
- Limits: requests per period, payload size, page size.
- Which side is the source of truth for each piece of data.

### 2. Isolate the service
- All calls to one provider go through one small module. The rest of the app speaks the app's own language, not the provider's.
- Map the provider's data to the app's own shapes at that edge. Map the provider's errors to the app's own errors.
- Replacing or faking the provider then means changing one place.

### 3. Authenticate safely
- Keys and tokens come from configuration, never from code, never reach the browser, never appear in logs or addresses.
- Use the narrowest permission the provider offers. Separate keys for test and live.
- Tokens that expire are renewed before or on expiry, once, not by every request at the same moment.
- When users connect their own accounts, store their tokens encrypted and handle the day they revoke access.

### 4. Expect failure on every call
- Every call has a timeout. No call may hang a request or a job forever.
- Retry only what is safe and worth retrying: timeouts, connection failures, "try again later", server faults. Do not retry "bad request" or "not allowed".
- Retries wait longer each time, with some randomness, up to a limit. Then stop and record the failure.
- A retried action must not happen twice. Send the provider's idempotency key when it has one; otherwise record what was sent and check before resending.
- Respect rate limits: obey "retry after", slow down, and batch where the provider allows.
- When the provider stays down, stop hammering it, fail fast for a while, and tell the user something honest.
- Decide what the user sees: wait, a clear message, or the work accepted and finished later.

### 5. Receive webhooks correctly
- Verify every webhook's signature with the provider's secret, on the raw body, before believing anything in it. Reject old timestamps.
- Answer quickly with success once the event is safely stored; do the real work afterwards.
- The same event will arrive more than once, and events arrive out of order. Record event ids and skip repeats; use the event's own time or fetch the current state instead of trusting arrival order.
- A failed webhook must be retryable: return an error so the provider sends it again, or keep it for reprocessing.
- Do not rely on webhooks alone. Have a way to fetch and reconcile what was missed.

### 6. Handle the data
- Validate what comes back. A missing or renamed field must produce a clear error, not a crash or silent bad data.
- Follow paging to the end. Never assume the first page is everything.
- Watch units, currencies, time zones, text encoding, and id formats when mapping.
- Store the provider's id for anything you create there, so it can be found, updated, and matched later.
- Send the provider only the personal data it needs.

### 7. Test without the live service, then with it
- Automated tests run against a fake of the provider, including: slow, down, rate-limited, error response, malformed response, repeated webhook, bad signature.
- Use the provider's test mode or sandbox for a real end-to-end check. Never test against live customer data or send real messages to real people.
- Log each outside call: which service, which operation, result, how long, the provider's request id. Never the secret, never the full personal payload.

## Rules an expert does not break
- Never call an outside service without a timeout.
- Never retry blindly an action that creates or charges something.
- Never accept an unverified webhook.
- Never put a provider key where a browser can read it.
- Never build against remembered documentation without checking the current version.

## Common failures to check for
- Works until the provider is slow, then the whole app hangs.
- Duplicate records or messages after a retry.
- Webhook processed twice, or lost when the app was down.
- Only the first page of results synced.
- Test key used in live, or live key used in tests.
- The app's code full of the provider's field names.

## Proof to leave
- The contract notes, with the documentation pages used.
- Tests for the failure cases above.
- A real call in the provider's test mode, with its result.
- Example configuration naming the keys needed, with placeholders.

## Hand-offs
- Money: `payments`. Secrets storage and exposure: `security`. Where secrets live in hosting: `cloud-devops`.
