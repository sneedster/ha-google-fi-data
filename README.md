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
6. Paste the helper’s setup code. Select only the phone lines you want to control,
   and optionally a Companion app phone for failure notifications. No lines are preselected.

To add another Fi account, repeat **Add integration** with its own browser capture
and a distinct account name. Each account has separate credentials, health entities,
notifications, and line controls. The same account cannot be added twice.

Manual installation: copy `custom_components/google_fi_data/` into your Home Assistant
`custom_components/` directory and restart. Use a browser profile signed into only the intended Google account for each capture.

## Authentication

The **browser setup helper** replaces HAR exports and manual data pauses.
Sign in normally on Google’s own Fi page (including your usual verification),
then copy one setup code into HA. Neither capture nor setup pauses or resumes data.
HA builds its request context from the signed-in account page on every bootstrap.

There is no official consumer OAuth login for this integration. The setup code
contains Google session cookies: **Google account credentials, not a token restricted
to Fi**. Use only a computer and Home Assistant you trust. Never share the code,
HARs, cookies, or session files in an issue or chat.

### Install the helper once

Download the helper ZIP for your browser from the
[release assets](https://github.com/sneedster/ha-google-fi-data/releases/latest).
These are local, unpacked/temporary extensions; they are not extension-store listings.

- **Chrome / Chromium / Edge:** Unzip `google-fi-data-helper-chrome.zip`.
  Open `chrome://extensions` (Edge: `edge://extensions`), enable **Developer mode**,
  choose **Load unpacked**, and select the unzipped directory containing `manifest.json`.
- **Firefox:** Unzip `google-fi-data-helper-firefox.zip`. Open `about:debugging`,
  choose **This Firefox → Load Temporary Add-on**, and select `manifest.json`.
  This temporary installation lasts until Firefox exits. If using a private window,
  allow the helper to run in private windows in its add-on settings.

The helper needs access to Fi’s page and Google’s parent-domain session cookies,
plus permission to copy to your clipboard. It has no background service, storage,
analytics, request interception, or network transport. It reads cookies only after
**Copy setup code** is clicked, from the cookie store of the active Fi tab. Remove
or disable it after setup if you prefer.

The manifest includes HTTP and HTTPS access for these same two hosts because
Chromium checks a cookie without the Secure flag against an HTTP cookie origin,
even when retrieving cookies for the HTTPS Fi URL. This is a cookie-access
requirement: the helper opens and queries HTTPS only, and copied cookies are
restricted to HTTPS in HA. Updates may ask you to approve the additional host
access. Capture stops with an error if required permissions are missing.

### Connect an account

1. Use a browser profile signed into **only the intended Google account**, as the
   Fi group owner. To connect another account, use a separate profile. Multiple
   simultaneous Google sign-ins in one profile are not supported.
2. Open the helper and choose **Open Google Fi**. Sign in normally on Google’s site.
3. Check that Fi shows the intended account. From that Fi tab, reopen the helper
   and choose **Copy setup code**. It does not display or save the code.
4. In HA, add **Google Fi Data**, paste into **Setup code**, and choose your lines.
   Use HTTPS or a trusted private LAN; do not send credentials over untrusted HTTP.
5. Clear your clipboard after setup. Clipboard managers can keep copied text;
   remove the code from their history too. You can now close the browser.

The code is copied locally; the helper does not send it to Google, HA, or a third
party. Pasting into HA is the explicit transfer. Google may bind sessions to the
original browser/device or revoke them later; an exported cookie is not guaranteed
to remain usable. If a Chrome capture quickly stops working, try a fresh Firefox
capture. The helper does not disable session protections or bypass verification.

HA validates with Fi account reads only, without calling Google’s cookie-renewal endpoint. Routine renewal is deferred for ten minutes after a successful import. Credentials
stay out of config-entry data and are committed only after line confirmation.
Rejected candidates keep the active session intact. Each account has an owner-only,
atomic session file under `.storage/google_fi_data.<account-key>.session.json`;
legacy installations retain `.storage/google_fi_data.session.json`. HA backups can
include these credentials; keep backups private.

Cookie renewal runs in the background. When HA requests reauthentication, repeat
capture using the same account. Reauthentication must share at least one known
line with that configured account; another account cannot replace its session.
If every line has been replaced, check data states in Fi, then remove and add the
account explicitly. There is no automatic resume on authentication loss/recovery.

### Advanced fallback: offline HAR import

If you cannot use the extension, record only a normal reload of
`https://fi.google.com/account` in your browser’s Network panel and export a HAR
with sensitive headers included. **Do not pause any line.** Save outside the checkout,
then run locally with Python 3.11+:

```sh
python3 tools/import_session.py /path/to/fi-capture.har --output /path/to/fi-session.json
```

This offline helper extracts only Fi auth headers/cookies, discards requests and
responses, creates an owner-only file, and refuses overwrite. Paste the resulting
JSON into HA’s **Setup code** field, then delete the HAR/session export and clear
your clipboard. Existing older Session JSON exports remain accepted; captured
control contexts are replaced by context derived from Fi’s current account page.

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
node --test tests_helper/*.test.cjs
```

Tests use invented accounts, synthetic responses, and temporary directories. They do
not contact Google or change real phone lines. The original private build was verified
on the author's household account, including session renewal and HA restarts. A fresh
Chrome-helper capture was also accepted by HA's read-only validation and correctly
identified the existing account without replacing its credentials or changing data.
The
public setup/import and multi-account/options paths are tested with synthetic captures
and account snapshots, including native HA flow/schema tests; a fresh setup on another
Google account has **not** been verified. No claim is made that this works with every
Fi plan, account role, or Google account configuration.

Python tests, native HA flow tests, helper tests/packaging, HACS validation, and
Home Assistant hassfest run automatically on pushes and pull requests in GitHub Actions. Their passing does
not prove Google's private endpoints still work. If they change, use Fi directly;
there may not be a fix or a release on any particular timetable.

## Remove

Resume any paused lines in Google Fi first. Remove the integration in HA, then remove
it through HACS and restart. Remove the private session file only if it is no longer
needed. Removing source or an HA integration does not resume data on Google's servers.

MIT licensed. Google Fi is a trademark of Google LLC.
