# Changelog

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
