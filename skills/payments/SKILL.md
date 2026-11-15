---
name: payments
description: Add payments to an app through a payment provider - checkout, subscriptions, plan changes, cancellations, refunds, invoices, and billing status - with verified webhooks, no duplicate charges, correct access after every payment event, and sandbox testing. Use whenever a task takes money, sells a plan or subscription, gates features by payment, or handles refunds and failed payments.
---

# Payments

You are a senior payments engineer. Mistakes here take real money from real people or give the product away. Two rules sit above the rest: the app never touches card details, and the provider's records, delivered by verified webhooks, are the truth about who has paid.

## Use when
- The app charges once, sells subscriptions, or offers paid plans.
- Access to features depends on payment.
- Refunds, failed payments, cancellations, or invoices must be handled.

## Do not use when
- The app only displays prices with no purchase.

## First, read the project and the provider
- Which provider the project uses or the owner chose. If none is chosen, pick one established provider with hosted checkout; do not combine several.
- The provider's current official documentation and its own published guidance for the chosen flow. Do not work from memory; payment APIs change.
- If the provider publishes its own skill or integration guide for AI coding tools, follow it for provider-specific details. This skill gives the rules any provider must satisfy.
- Everything in `integrations` and `security` applies here.

## Size it to the task
- Use the provider's hosted checkout page and hosted customer billing page wherever they meet the need. They carry the card handling, the legal burden, and most edge cases.
- Build custom payment screens only when a requirement cannot be met otherwise.
- Do not build invoicing, tax, or dunning logic the provider already offers.

## How to work

### 1. Model what is sold
- Products, prices, currency, billing period, trial, and what each plan unlocks, defined once, on the server, matching the provider's records.
- Amounts are whole minor units with a currency. Never floating point.
- The price charged always comes from the server or the provider, never from the browser.

### 2. Keep card data out of the app
- Card details go straight from the customer to the provider through the provider's page or components. They never pass through, or are stored or logged by, the app's server.
- Store only the provider's ids (customer, subscription, payment) and the status.

### 3. Start a payment safely
- Create the checkout on the server for a signed-in, known customer, linked to the app's own user and order ids so the result can be matched.
- Every request that creates a charge, subscription, or refund carries an idempotency key, so a retry or a double click cannot charge twice.
- One provider customer per app user. Look up before creating.

### 4. Trust the webhook, not the return page
- The customer returning to a "success" page proves nothing: they may close the tab, or forge the address. That page only shows "thank you" or "confirming".
- Access is granted, extended, or removed when a verified webhook from the provider says so.
- Verify every webhook signature on the raw body. Record event ids; handle each once. Events repeat and arrive out of order: on doubt, fetch the current state from the provider.
- Answer the webhook quickly; do the work reliably afterwards; let failures be retried.

### 5. Track status in the app
- Keep, per customer, the plan, the status, and the date access runs to, updated only from provider events.
- Handle the whole life of a subscription, not only the first payment: trial start and end, renewal, payment failed and being retried, payment recovered, upgrade, downgrade, cancel now, cancel at period end, resumed, expired, refunded, disputed.
- Decide and state what the customer keeps in each state: for example, access continues until the paid period ends after a cancellation, and during the provider's retry period after a failed renewal.
- The feature check asks one question in one place: "is this customer entitled now?"

### 6. Failures, refunds, and disputes
- A declined payment gives a clear message and a way to try again; nothing is unlocked.
- A failed renewal notifies the customer and offers a way to update the card, usually through the provider's hosted page.
- Refunds are issued through the provider, with an idempotency key, by an authorised person or rule, and are recorded. Decide whether a refund ends access.
- A dispute is recorded and visible to the owner.
- Be able to reconcile: a way to compare the app's records with the provider's and repair differences.

### 7. Secrets and modes
- Secret keys and webhook secrets live only in server configuration. Only the publishable key may reach the browser.
- Test and live keys are separate and never mixed. The app shows clearly, to developers, which mode it is in.
- Restrict key permissions where the provider allows.

### 8. Test in the sandbox
Using the provider's test mode and its test cards and tools, run for real:
- Successful one-time payment and successful subscription.
- Declined card, and a card needing extra bank confirmation.
- Customer closes the tab after paying: access still arrives through the webhook.
- Double click on pay: one charge.
- The same webhook delivered twice: one effect.
- Renewal, failed renewal, recovery.
- Upgrade, downgrade, cancel, refund.
- Webhook with a bad signature: refused.
Never test with real cards or live keys.

### 9. Tell the customer the truth
- Show the price, the period, and what renews, before they pay. Show how to cancel.
- Give a receipt or let the provider send one. Show current plan and next charge in the account screen.

## Rules an expert does not break
- Never let card numbers touch the app's server, database, or logs.
- Never grant access from the browser's return alone.
- Never accept an amount from the client.
- Never create a charge or refund without an idempotency key.
- Never process an unverified webhook.
- Never put a secret key in browser code or the repository.
- Never go live without the sandbox cases above passing.

## Common failures to check for
- Paid customer without access because the webhook failed silently.
- Access never removed after cancellation, refund, or failed renewal.
- Two provider customers for one user.
- Double charge on retry.
- Test webhook secret left in live.
- Plan shown in the app differs from the provider's record.

## Proof to leave
- The sandbox runs listed above, with results.
- The table of subscription states and what access each gives.
- Tests for webhook verification, repeat events, and entitlement checks.
- Example configuration naming each key, with placeholders; no secret in the change.

## Hand-offs
- General outside-service rules: `integrations`. Access control: `security`. Stored amounts and status tables: `data-databases`.
