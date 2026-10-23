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

The offline helper extracts only Fi credentials and the request context, never
replays a captured action, and never contacts Google. Setup validates a private
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
has not been verified on a second real Google account. A browser rendering/keyboard
acceptance pass of the new flow is not claimed. Home Assistant owns rendering;
there are no custom frontend assets. Live household installation is not upgraded
as part of publishing this standalone package.

## Account options and migration

Each new account uses its own session path, state store, notification ID, entity IDs,
and device. Existing entries without account_key keep legacy IDs and paths. The
Configure flow reads current account lines, saves selected controls and notifier
options, and reloads the entry; stale switches are removed only from that entry’s
entity registry. It never calls a data-control operation. Empty selection is allowed.
A new account cannot overlap known line identities with another configured account.
Reauthentication requires a surviving known line, allowing members to be removed.
