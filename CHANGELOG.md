# Changelog

## 0.3.3

- Declare HTTP cookie-origin access for the same two Google/Fi hosts. Chromium checks non-Secure cookies against HTTP origins even when retrieving cookies for an HTTPS URL, so HTTPS-only permissions silently omitted them.
- Check all required cookie permissions before capture and show an actionable error when access is missing. The helper still opens/queries HTTPS only, makes no network requests of its own, and exports cookies as HTTPS-only for HA.

## 0.3.2

- Include allowlisted login cookies even when the browser cookie lacks the Secure flag, and include SAPISID. Copied cookies remain HTTPS-only in HA.
- Validate imported browser sessions with Fi account reads only. Do not renew Google cookies during the initial check; defer routine renewal for a full interval after import.
- Show specific safe errors for rejected sessions, missing sign-in/member identity, and Google rate limiting.

## 0.3.1

- Give the browser helper an explicit 400px popup width and minimum width. Avoid viewport-relative maximum width collapsing the actual Chrome extension popup.
- No changes to Fi data-control behavior, entity identities, or account options.

## 0.3.0

- Derive fresh ModifyUser request context from the signed-in Fi page; no data pause is needed for authentication.
- Add local Chrome/Edge and temporary Firefox setup helpers: normal Google sign-in, then copy one setup code into HA.
- Capture from the active Fi tab’s cookie store, with account-change checks, fixed cookie filtering, no background storage, and no network transport.
- Retain offline HAR import as an advanced fallback; a normal account-page reload is sufficient.
- Accept cookie-only imports and older Session JSON; preserve existing sessions, entity IDs, selected lines, and account options.
- Add context/bootstrap and helper isolation tests, and helper checks/packaging to automatic CI.

No live data-control tests are performed by the helper or setup. A second real Google account and long-term cookie portability remain unverified.

## 0.2.0

First public, experimental friends-and-family release for manual HACS custom repositories.

- Standalone repository with HACS metadata and validation workflows.
- Local, offline HAR-to-session helper and masked native HA import flow.
- Multiple named Fi accounts with isolated credentials, health state and alerts.
- Configure flow to add/remove line controls and change per-account notifications.
- Removing a control leaves its Fi data state unchanged and cleans up only that HA entity.
- Neutral initial line selection; health-only accounts can have zero selected lines.
- Candidate validation before replacing credentials; reauthentication rejects a different account.
- Existing integration domain, entity identities, and session-file path retained.
- No household dashboards, UniFi policies, schedules, session data, or private history included.

The public import flow has synthetic coverage; setup against a second live account remains unverified.
