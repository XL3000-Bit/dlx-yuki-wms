# PHASE 10 Manual Smoke Checklist

Run this checklist on a disposable environment migrated to the release head. Record tester, build/commit, browser, database, warehouse fixtures, and date. This checklist is currently **not run** because migration `0019` blocks environment provisioning.

## Core flow

- [ ] Login as Admin, Manager, Operator, and Viewer; confirm logout and token refresh do not expose raw errors.
- [ ] Global Search: exact, prefix, and contains queries; open an Outbound result; refresh and confirm selected/filter state is restored.
- [ ] Create a Load, add an OB, reject a duplicate Load/OB relation with a readable conflict message, and reopen by deep link.
- [ ] Create a Work Order, assign, start, complete, and inspect immutable history; reject an invalid transition without an event.
- [ ] Create an Exception, investigate, create/link a Work Order, resolve, and inspect immutable exception history.
- [ ] Upload a document, download it, upload a new version, archive it, and verify a missing file produces a safe error.
- [ ] Open Dashboard, apply warehouse/date filters, click Attention Queue, and refresh the target page.
- [ ] Refresh notifications twice, confirm dedupe, mark one/all read, and follow the deep link after refresh.

## Security and failure flow

- [ ] Viewer can read permitted records but cannot mutate Load, Work Order, Exception, Document, or Notification-owned data.
- [ ] Warehouse A user cannot list, count, search, look up, deep-link, download, view events for, or mutate Warehouse B data.
- [ ] Direct ID requests use the intended 403/404 non-disclosure policy and do not leak record existence.
- [ ] Upload rejection, 409 conflicts, 422 validation, and simulated 500 errors show understandable UI messages without traceback, token, cookie, or file contents.
- [ ] Unknown/stale deep-link targets degrade safely; no link points to a missing route.

## Completion

- [ ] Attach screenshots/log references and list deviations.
- [ ] Re-run automated regression after any smoke fix.
- [ ] Obtain release owner sign-off.
