#!/usr/bin/env python3
"""Build deterministic Chrome and temporary Firefox helper ZIPs; no secrets."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ("core.js", "popup.html", "popup.css", "popup.js")


def package(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for browser in ("chrome", "firefox"):
        manifest = json.loads((ROOT / "browser_helper/manifest.json").read_text())
        if browser == "firefox":
            manifest.pop("incognito")
            manifest["browser_specific_settings"] = {"gecko": {
                "id": "google-fi-data-setup@sneedster.github.io", "strict_min_version": "115.0",
                "data_collection_permissions": {"required": ["none"]}}}
        path = output / f"google-fi-data-helper-{browser}.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            contents = {name: (ROOT / "browser_helper" / name).read_bytes() for name in FILES}
            contents["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
            contents["LICENSE"] = (ROOT / "LICENSE").read_bytes()
            for name, content in sorted(contents.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        print(path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    package(parser.parse_args().output)
