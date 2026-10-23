#!/usr/bin/env python3
"""Extract a minimal Fi session from a locally exported HAR. Never makes requests."""
from __future__ import annotations

import argparse
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

AUTH_COOKIES = re.compile(r"SID|HSID|SSID|APISID|OSID")


def from_har(raw):
    """Only Fi request headers and the ModifyUser request context are retained."""
    cookies, agent, context = {}, None, None
    for entry in raw["log"]["entries"]:
        request = entry.get("request", {})
        url = urlsplit(request.get("url", ""))
        if url.scheme != "https" or url.hostname != "fi.google.com":
            continue
        headers = {h["name"].lower(): h["value"] for h in request.get("headers", [])}
        agent = headers.get("user-agent", agent)
        parsed = SimpleCookie()
        parsed.load(headers.get("cookie", ""))
        request_cookies = list(request.get("cookies", []))
        request_cookies += [{"name": k, "value": v.value} for k, v in parsed.items()]
        for cookie in request_cookies:
            name = cookie["name"]
            if AUTH_COOKIES.search(name) and cookie.get("value"):
                domain = cookie.get("domain", ".google.com")
                if domain in ("google.com", ".google.com", "fi.google.com", ".fi.google.com"):
                    cookies[(domain, name)] = {"name": name, "value": cookie["value"],
                        "domain": domain, "secure": True, "path": "/", "expires": None}
        if url.path != "/_/data/batchexecute":
            continue
        post = request.get("postData", {})
        form = parse_qs(post.get("text", ""))
        for param in post.get("params", []):
            if param.get("name") == "f.req":
                form["f.req"] = [param["value"]]
        for text in form.get("f.req", []):
            for batch in json.loads(text):
                for call in batch:
                    if call[0] == "aU43Ic":
                        payload = json.loads(call[1])
                        if isinstance(payload[0], list) and payload[0]:
                            context = payload[0]
    if not cookies or not agent:
        raise ValueError("HAR is missing Fi cookies or User-Agent; export with sensitive headers included.")
    if context is None:
        raise ValueError("HAR has no Fi data-pause request context. Follow the manual capture steps in README.")
    return {"user_agent": agent, "control_context": context, "cookies": list(cookies.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.har.stat().st_size > 64_000_000:
            raise ValueError("HAR exceeds the 64 MB limit; capture only the documented Fi steps.")
        seed = from_har(json.loads(args.har.read_text()))
        # O_EXCL prevents accidental replacement of an existing session or HAR.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(seed, stream, separators=(",", ":"))
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        parser.exit(1, "Import failed. Check the capture instructions, input format, and that the output file does not already exist. No credentials were printed.\n")
    print("Session written privately. Paste its contents into the integration's Session JSON field; do not share either file.")


if __name__ == "__main__":
    main()
