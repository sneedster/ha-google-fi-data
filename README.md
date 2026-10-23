# Google Fi Data for Home Assistant

An unofficial, experimental Google Fi mobile-data switch for each phone line you select.
**On enables mobile data; off pauses data indefinitely.** It never pauses phone service.

This is a personal project shared with friends and family. It uses undocumented
Google Fi web requests, can break whenever Google changes its website, and comes
with **no promise of support, compatibility, or ongoing maintenance**. It is not
associated with Google or Home Assistant. There is no plan to submit it to the
HACS default catalog. Keep the official [Google Fi website](https://fi.google.com/account)
available for manual control, especially if a line is paused.

## Install through a HACS custom repository

Requires Home Assistant 2026.10 or later and HACS 2 or later.

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/sneedster/ha-google-fi-data`, category **Integration**.
3. Find **Google Fi Data** in HACS and download it.
4. Restart Home Assistant.
5. Follow Authentication below, then open **Settings → Devices & services → Add integration → Google Fi Data**.
6. Paste the generated Session JSON. Select only the phone lines you want to control,
   and optionally a Companion app phone for failure notifications. No lines are preselected.

To add another Fi account, repeat **Add integration** with its own browser capture
and a distinct account name. Each account has separate credentials, health entities,
notifications, and line controls. The same account cannot be added twice.

Manual installation: copy `custom_components/google_fi_data/` into your Home Assistant
`custom_components/` directory and restart. Each account must be captured from a browser profile signed into only that account.

## Authentication

There is no official consumer OAuth login for this integration. It needs Google
web-session cookies plus a request context obtained from your own browser. **These
cookies are Google account credentials, not a token restricted to Fi.** Use this
only on a Home Assistant installation and computer you trust. Never send a HAR,
session file, cookies, or account request to another person, an issue, or a chat.

The capture is an advanced, manual setup step. Use Chrome/Chromium on a computer,
signed into Google Fi as the account/group owner. Use a profile with only the intended
Google account signed in; multiple simultaneous Google accounts are not supported.

1. Download this repository's source ZIP or clone it to your computer. Python 3.11+
   is required for the local helper; it has no third-party dependencies.
2. Open Chrome Developer Tools → **Network** on `https://fi.google.com/account`.
   Enable recording and **Preserve log**, then clear the existing log and reload Fi.
3. On a line you control and can safely interrupt, **manually pause mobile data**
   using Fi's own UI. This captures the account request context; the helper never
   replays this request. **Immediately resume data in Fi and confirm it is enabled.**
   Do not perform this step on a line that must remain connected.
4. Export the Network log as a HAR **with sensitive data included**. Chrome normally
   sanitizes Cookie headers; its DevTools settings may require enabling sensitive HAR
   export. If cookies or User-Agent are absent, the helper will reject the capture.
   Save it outside the source checkout. HARs also contain private account responses.
5. In a local terminal, from the downloaded repository, run:

   ```sh
   python3 tools/import_session.py /path/to/fi-capture.har --output /path/to/fi-session.json
   ```

   The helper runs entirely offline, extracts only the necessary Fi authentication
   cookies, browser User-Agent, and request context, and creates an owner-only file.
   It refuses to overwrite an existing file. Nothing is uploaded or printed as a credential.
6. Open that JSON file locally, copy its contents, and paste into the integration's
   masked **Session JSON** field. Connect to HA over HTTPS or a trusted private LAN;
   do not submit account credentials over an untrusted HTTP connection.
7. After setup succeeds, remove the HAR and exported session file and clear the
   clipboard. New accounts keep sessions in `.storage/google_fi_data.<account-key>.session.json`;
   upgraded private installations retain `.storage/google_fi_data.session.json`. Each is
   written atomically with mode `0600`. HA backups may include it; keep backups private.

The setup flow validates the account with a read before offering line selection.
Credentials stay out of HA config-entry data and are saved only after you confirm
selected lines. Cancelling or rejecting a candidate keeps the active session intact.
Cookie renewal runs in the background without leaving a browser open. Google can
still revoke access. When HA requests reauthentication, repeat the capture/import
with the same account. Reauthentication must share at least one known line with the configured account;
a different account cannot replace its session. If every line on an account has
been replaced, remove and add that account explicitly after checking data state in Fi.
There is no automatic resume on authentication failure or recovery.

## Entities and behavior

- One **data switch** for each selected phone line; local line names are discovered
  from your account, not fixed to the author's household.
- An authentication health sensor, last successful read timestamp, and access-problem
  binary sensor. Reads run every 60 seconds; cookie renewal attempts every ten minutes.
- A diagnostic test-alert button on each integration device page.
- One persistent HA failure alert and optional Companion app notification per incident.
  Dismissing it sticks across polling and restart; recovery clears it quietly.

Controls read before writing and verify afterward. Uncertain writes are reconciled
with a read, never blindly repeated. Unknown/stale states make switches unavailable;
last verified paused lines and uncertain requests remain visible in failure alerts.
Resume validates a fresh server-issued action against the selected line. Data pause
is indefinite, so a failed morning automation can leave data paused until you restore it
in Fi. Never rely on this as a guaranteed parenting, availability, or emergency control.

A switch controls **cellular mobile data only**. Calls, SMS, Wi-Fi, UniFi firewall rules,
household dashboards, bedtime schedules, and the author's watchdog automation are not
installed or changed. Build your own HA automations around your actual entity IDs.
To add or remove controls, open **Settings → Devices & services → Google Fi Data**,
then **Configure** on the relevant account. New lines are read from Fi each time.
Save your selection and optional phone notifier; the entry reloads and removed switch
entities are cleaned up. This does not pause or resume any line. You may select zero
lines to retain health monitoring without controls.

Existing installations can upgrade through HACS with the same domain,
entity unique IDs, and private session-file location; back up first.

## Checks and limits

```sh
python3 -m unittest discover -s tests
```

Tests use invented accounts, synthetic responses, and temporary directories. They do
not contact Google or change real phone lines. The original private build was verified
on the author's household account, including session renewal and HA restarts. The
public setup/import and multi-account/options paths are tested with synthetic captures
and account snapshots, including native HA flow/schema tests; a fresh setup on another
Google account has **not** been verified. No claim is made that this works with every
Fi plan, account role, or Google account configuration.

HACS validation and Home Assistant hassfest run in GitHub Actions. Their passing does
not prove Google's private endpoints still work. If they change, use Fi directly;
there may not be a fix or a release on any particular timetable.

## Remove

Resume any paused lines in Google Fi first. Remove the integration in HA, then remove
it through HACS and restart. Remove the private session file only if it is no longer
needed. Removing source or an HA integration does not resume data on Google's servers.

MIT licensed. Google Fi is a trademark of Google LLC.
