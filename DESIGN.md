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

A quiet utility for trusted friends and family, with no custom frontend. Home
Assistant owns theme, visual tokens, responsive layout, keyboard handling, native
form labels, and feedback. English strings are provided. No Japan-market scope.
The signature is explicit verified state and a visible recovery path, with no
optimistic data toggle. No CSS, custom overlays, animations, or additional shell.

## Colors

Inherit Home Assistant's semantic colors.

## Typography

Inherit Home Assistant typography.

## Layout

Use the native Add integration and Reauthentication flows. Session import precedes
line selection; the same masked input and validation are reused for reauthentication.
No credential appears in a label, error, URL, selected-line screen, or saved config entry.

## Elevation & Depth

Home Assistant owns dialogs and elevation.

## Shapes

Home Assistant owns control and dialog shapes.

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
