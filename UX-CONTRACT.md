# Public integration contract

The README defines experimental scope and authentication instructions. This is a
manually added HACS repository for friends and family, not a catalog submission.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Form | HA config flow / TextSelector | config_flow.py, strings.json | masked session import and same-account reauth | Real HA config flow tests; no second live Google account acceptance claim |
| Select/Listbox | HA schema renderer | config_flow.py | native multi-select for lines and notifier choice | Schema/default/selection validation tests |
| Toast | HA persistent notification | coordinator.py | one alert per incident, quiet recovery | Synthetic failure/restart/recovery tests |

## Authentication boundary

The offline HAR fallback extracts only Fi auth cookies and User-Agent, discards
actions/responses, and never contacts Google. The browser helper reads the active
Fi tab’s bootstrap and corresponding cookie store on explicit copy; it makes no
requests, writes no cookies, has no page message API or background/storage, and
places the setup code only on the user’s clipboard. It does not render the code.
HA derives fresh context from its own authenticated account-page read. It never
needs a captured pause action or context. Setup validates a private
candidate using account reads before line choice; cancellation does not replace
the active jar. Same-account reauthentication checks all configured line IDs before
committing. No credentials in config-entry data, error strings, logs, diagnostics,
fixtures, or published history. Use a trusted HA connection for submission.

## Data controls

On enables mobile data; off pauses indefinitely. Reads precede writes and follow
writes. Unknown outcomes are reconciled by reads, never repeated automatically.
Unavailability preserves last-known state and recovery guidance. The component
never pauses phone service or automatically resumes data after authentication loss.

## Verification boundary

Tests use synthetic credentials, captures and account snapshots. Public onboarding
has not been verified on a second real Google account. Home Assistant owns its native rendering. The separate helper is verified with
synthetic browser APIs and popup success/error/busy/keyboard rendering; do not
confuse that with a real extension installation or another-account acceptance.
Household upgrades are a separately verified deployment with a private backup.

## Account options and migration

Each new account uses its own session path, state store, notification ID, entity IDs,
and device. Existing entries without account_key keep legacy IDs and paths. The
Configure flow reads current account lines, saves selected controls and notifier
options, and reloads the entry; stale switches are removed only from that entry’s
entity registry. It never calls a data-control operation. Empty selection is allowed.
A new account cannot overlap known line identities with another configured account.
Reauthentication requires a surviving known line, allowing members to be removed.

## Browser setup helper

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Button | Native extension buttons | browser_helper/popup.html, popup.css | Open Fi; copy setup code | Keyboard, busy and failure recovery |
| Feedback | Extension-local inline status | browser_helper/popup.js | Fixed safe errors, busy, copied | Synthetic browser UI + helper tests |
| Clipboard | Explicit copy action | browser_helper/core.js, popup.js | Local copy only; no automatic HA connection | Store/account race tests; no raw exception output |

The helper supports one signed-in Google account per browser profile. Another Fi
account uses another profile; non-default authuser/session indices are rejected.
Cookie store identity must match the active Fi tab; never fall back to another
store. Capture rechecks the member identifier and document URL before copy. Cookie
values are filtered to fixed authentication names, exact Google/Fi domains and
unpartitioned storage. Exported cookies are HTTPS-only. HTTP cookie-origin access
is declared solely because Chromium checks non-Secure cookies against HTTP hosts;
opening Fi and cookie retrieval still use HTTPS. Missing permissions stop capture
before any page or cookie read. No external services receive capture contents.
