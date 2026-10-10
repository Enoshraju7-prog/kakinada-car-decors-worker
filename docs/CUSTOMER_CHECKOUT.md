# Customer details at checkout

9 October 2026 — planned and implemented locally. Live deployment is pending review.

## Partner flow

1. Select products and quantities in **Make sale**.
2. Choose **Walk-in · no details**, or **Save customer details**.
3. For a returning customer, enter their Indian mobile number and click **Find customer**. Review the saved name/address and previous purchase dates. For a new customer, enter their name; address is optional.
4. Review and confirm the sale. Customer creation/update, purchase link and stock deduction commit together. Failed sales create no customer or purchase link.
5. In **Activity**, expand a sale and select **View customer**. This shows the current customer profile and latest 20 purchases with dates, purchased product names, quantities, units, totals and payment methods. Older purchases are available through the paginated API; full customer-history navigation is a later UI improvement.

## Decisions

- Enosh confirmed Walk-in is allowed; no contact details are required in this mode.
- Phone is the customer identity for this pilot. `+91`, spaces, punctuation and leading zero normalize to the same Indian mobile number. Names alone are never merged. Other countries/landlines are not supported yet.
- One phone corresponds to one profile; shared family phone numbers need a future explicit identity workflow. No silent name/address replacement on collision: first find and review the saved profile. Editing a found name/address updates the profile only when a sale commits. Changing the phone requires another lookup.
- Existing sales remain walk-in; there is no guessed customer backfill.
- Purchase time is the existing server-generated sale timestamp, displayed in IST. Customer profiles are current contact records. New sales additionally save an encrypted name/phone snapshot for printable receipts; addresses are not printed or duplicated in those snapshots. See [Sales receipts](SALES_RECEIPTS.md).
- Customer details are only available to signed-in partners. Staff retain walk-in checkout. There is no customer tool exposed to the LLM, and transaction/agent results contain no decrypted contact fields.

## Security and operation

- `customers.encrypted_details` holds authenticated Fernet ciphertext for name, phone and address. `phone_key` is an independently keyed HMAC-SHA256 lookup token with a database unique constraint. Customer-to-sale links are foreign keys and have immutable-history protection.
- Customer details are not duplicated in transaction JSON, audit payloads, notification outbox or retry response records. Customer sale retry fingerprints use a keyed digest. Browser session storage contains only the retry digest and request ID, never customer field values.
- Customer lookup is a POST body, not a phone number in a URL. All customer routes require partner authentication; writes/lookups require the existing CSRF token and same-origin checks. Responses use `Cache-Control: no-store`. Deployment must keep existing HTTPS enabled.
- Local setup generates keys privately in ignored `backend/.env` with permissions 0600. Deployment needs separately generated `KCD_CUSTOMER_ENCRYPTION_KEYS` (Fernet key, or comma-separated keys newest first) and `KCD_CUSTOMER_LOOKUP_KEY` (independent random 32-byte hex secret). Never commit keys or copy them into frontend configuration. No live secrets changed in this slice.
- Back up encryption and lookup keys separately from database dumps in private restricted storage. Losing them makes profiles unreadable or unmatchable. A database-only dump contains encrypted details, but an attacker who compromises the running server or its keys can read them. Encryption is not protection against a compromised partner account or server.
- Multiple Fernet keys allow old ciphertext to remain readable during rotation. Re-encrypt all profiles before removing an old key. The lookup key must remain stable; replacing it needs an explicit reindex migration, not an environment edit.
- No plaintext fallback: missing/invalid keys reject customer-detail sales and lookup; Walk-in sales continue to work.
- Retention/deletion policy and dedicated access auditing are follow-up business decisions before large-scale customer collection. Do not use contacts for marketing without a separate approved workflow.

Encryption reference: [cryptography Fernet documentation](https://cryptography.io/en/latest/fernet/).

## Verification

- Full backend regression suite: 62 tests passed on isolated `kcd_test`.
- New checks: phone normalization, authenticated encryption/tamper rejection/key rotation, replay safety, concurrent first purchases reuse one profile, profile conflict handling, saved history/timestamps, failed-sale rollback, absent secrets, anonymous/staff denial, non-cacheable responses, and no contact fields in transaction/retry/audit/outbox records.
- Frontend TypeScript and production build passed. Checkout verifies the committed customer link and details through a separate API read before reporting success.
- Applied migration 0007 only to local project demo/submission/test databases. Existing shop transactions and local inventory preserved. Production is unchanged.

The assistant can now report historical sales using customer references. Partner-only customer lookup stays in the browser, outside model requests and saved AI reports. See [Sales history](SALES_HISTORY.md).
