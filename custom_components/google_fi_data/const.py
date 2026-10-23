DOMAIN = "google_fi_data"
SESSION_FILE = ".storage/google_fi_data.session.json"
STATE_KEY = "google_fi_data_last_known"
NOTIFICATION_ID = "google_fi_data_access"


def selected_lines(entry):
    return entry.options.get("lines", entry.data["lines"])


def session_file(entry):
    # Existing household entries keep their original path and entity IDs.
    return entry.data.get("session_file", SESSION_FILE)


def scoped_key(entry, legacy):
    return f"{legacy}_{entry.entry_id}" if entry.data.get("account_key") else legacy


def entity_uid(entry, suffix):
    return f"{scoped_key(entry, DOMAIN)}_{suffix}"


def known_line_ids(entry):
    return entry.options.get("account_line_ids", entry.data.get("account_line_ids", list(entry.data["lines"])))
