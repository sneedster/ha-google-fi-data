---
version: alpha
name: Google Fi Data
omitted:
  - section: colors
    reason: Native Home Assistant theme owns all colors.
  - section: typography
    reason: Native Home Assistant owns typography.
  - section: rounded
    reason: Native Home Assistant owns shapes.
  - section: spacing
    reason: Native Home Assistant owns form geometry.
components:
  form: {}
  switch: {}
  notification: {}
---

# Google Fi Data

## Overview

A quiet utility for trusted friends and family. Home
Assistant owns theme, visual tokens, responsive layout, keyboard handling, native
form labels, and feedback. English strings are provided. No Japan-market scope.
The signature is explicit verified state and a visible recovery path, with no
optimistic data toggle. HA has no custom CSS, overlays, animations, or additional shell. The separate browser helper has one small, local popup; it does not theme or alter Fi or HA.

## Colors

Inherit Home Assistant's semantic colors in HA. For the standalone helper, `browser_helper/popup.css` is the canonical runtime token source (Model B); its CSS variables define light/dark surface, ink, muted, accent, error and success roles. The cool teal accent identifies setup actions without imitating Google branding. No duplicate theme adapter.

## Typography

Inherit Home Assistant typography in HA. The helper uses the system UI font at 14px, a restrained 23px heading, and 12px utility/privacy copy; no remote fonts.

## Layout

Use the native Add integration and Reauthentication flows. Session import precedes
line selection; the same masked input and validation are reused for reauthentication.
No credential appears in a label, error, URL, selected-line screen, or saved config entry. The helper has an explicit 400px root width and 360px minimum, avoiding viewport-width feedback during browser-popup sizing: account check, copy action, reserved feedback region, privacy guidance. Its two numbered steps represent the actual ordered workflow. No overlay or nested navigation.

## Elevation & Depth

Home Assistant owns dialogs and elevation.

## Shapes

Home Assistant owns control and dialog shapes. The helper’s canonical CSS uses an 8px control/feedback radius and 42px minimum button height.

## Components

Native TextSelector password input supports paste and accessible labels. Native
multi-select has no preselected account lines. Notification choice uses native HA
schema rendering. No changes to the switch/health/notification runtime UI from the
private build. Invalid input gives a fixed safe error and remains on the same step.
Account mismatch retains existing credentials. Candidate credentials are committed
only on final line confirmation, or successful same-account reauthentication.

## Motion

Inherit Home Assistant feedback and reduced-motion preferences.

## Do's and Don'ts

Use native controls, plain labels and safe actionable errors. Keep the private session
outside source. Never display or log session contents or imply that unavailable means
data is enabled. Do not add a branded portal, independent theme, or custom select popup.

## Browser helper boundary

Native buttons retain keyboard and focus behavior. `popup.js` owns busy/disabled,
inline polite live status, fixed safe errors, and copy confirmation. A reserved
feedback area reduces jumps; long errors can expand and scroll. `popup.css` owns
all helper tokens, dark/high-contrast treatment and responsive geometry. No motion
is used beyond the native pressed state. The comparable HA setup flow retains the
same plain language and masked Setup code field; their rendering remains separate
because extension privileges must never be exposed to page scripts.
