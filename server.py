#!/usr/bin/env python3
"""vOidnet local server - serves the site and logs every search to the console."""

import html as htmllib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 4173
ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 64 * 1024

if os.name == "nt":
    os.system("")  # switch the windows console into ANSI mode

PINK = "\033[95m"
HOTPINK = "\033[38;5;206m"
LILAC = "\033[38;5;183m"
MINT = "\033[38;5;121m"
AMBER = "\033[38;5;222m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print_lock = threading.Lock()


def log_search(payload):
    login = str(payload.get("login") or "?").strip()[:64] or "?"

    raw_emails = payload.get("emails")
    emails = []
    if isinstance(raw_emails, list):
        for item in raw_emails:
            if isinstance(item, str) and item.strip():
                emails.append(item.strip()[:160])
    emails = emails[:25]

    repos = payload.get("repos")
    repos = int(repos) if isinstance(repos, (int, float)) else 0
    mode = payload.get("mode")
    if mode not in ("live", "cache", "fallback"):
        mode = "cache" if payload.get("cached") else "live"
    styles = {
        "live": (MINT, "live"),
        "cache": (LILAC, "cached"),
        "fallback": (AMBER, "public pages"),
    }
    colour, label = styles[mode]

    # One line per search: time, handle, how it was answered, then the addresses.
    with print_lock:
        when = datetime.now().strftime("%H:%M:%S")
        tally = "{} emails".format(len(emails)) if emails else "no emails"
        line = "".join([
            HOTPINK, "\u2665 ", RESET,
            DIM, when, RESET,
            "  ", BOLD, PINK, "@", login, RESET, " " * max(2, 22 - len(login)),
            colour, label, RESET, " " * max(2, 14 - len(label)),
            DIM, "{} repos".format(repos), RESET, "   ",
            DIM, tally, RESET,
        ])
        if emails:
            line += "   " + LILAC + ", ".join(emails) + RESET
        print(line, flush=True)


# ---------------------------------------------------------------------------
# Public-page fallback
#
# The REST API allows 60 requests an hour per address, and nothing in a browser
# can lift that without a token. So when it runs out, read github.com's public
# pages instead: profile and repositories from the HTML, and addresses from the
# commit search endpoint, which has its own separate allowance.
# ---------------------------------------------------------------------------

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 vOidnet/1.0"
)
SCAN_TTL = 10 * 60
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

scan_cache = {}
scan_lock = threading.Lock()


def http_text(url, accept="text/html"):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def grab(patterns, text):
    for pattern in patterns:
        found = re.search(pattern, text, re.S)
        if found:
            value = found.group(1).strip()
            if value:
                return value
    return ""


def strip_tags(value):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def grab_text(patterns, text):
    return strip_tags(grab(patterns, text))


def parse_count(value):
    match = re.match(r"^([\d.,]+)\s*([kmb]?)$", (value or "").strip().lower())
    if not match:
        return 0
    number = float(match.group(1).replace(",", ""))
    return int(number * {"": 1, "k": 1000, "m": 1000000, "b": 1000000000}[match.group(2)])


def scrape_profile(login):
    page = http_text("https://github.com/{}".format(login))
    if 'class="p-nickname' not in page and "vcard-fullname" not in page:
        raise LookupError("no such profile")

    avatar = grab([
        r'src="(https://avatars\.githubusercontent\.com/u/\d+\?v=4)"',
        r'class="avatar-user"[^>]*src="([^"]+)"',
    ], page)
    if avatar.startswith("/"):
        avatar = "https://github.com" + avatar

    counters = [
        parse_count(strip_tags(value))
        for value in re.findall(r'class="text-bold color-fg-default">([^<]+)</span>', page)
    ]

    twitter = grab([r'<li[^>]*itemprop="twitter"[^>]*>[\s\S]*?href="([^"]+)"'], page)
    handle = ""
    if twitter:
        handle = twitter.rstrip("/").rsplit("/", 1)[-1]

    return {
        "login": login,
        "name": grab_text([r'<span[^>]*class="p-name[^"]*"[^>]*>(.*?)</span>'], page) or login,
        "bio": grab_text([r'<div[^>]*class="[^"]*user-profile-bio[^"]*"[^>]*>(.*?)</div>'], page),
        "avatar_url": avatar,
        "html_url": "https://github.com/{}".format(login),
        "company": grab_text([
            r'aria-label="Organization:\s*([^"]*)"',
            r'<span class="p-org"><div>(.*?)</div>',
        ], page),
        "location": grab([r'aria-label="Home location:\s*([^"]*)"'], page),
        "blog": grab([r'<li[^>]*itemprop="url"[^>]*>[\s\S]*?href="([^"]+)"'], page),
        "twitter_username": handle,
        "followers": counters[0] if len(counters) > 0 else 0,
        "following": counters[1] if len(counters) > 1 else 0,
        "public_repos": parse_count(grab([
            r'href="[^"]*tab=repositories"[^>]*>[\s\S]{0,300}?class="Counter[^"]*">([^<]+)<',
        ], page)),
        "created_at": grab([r'Joined[\s\S]{0,120}?datetime="([^"]+)"'], page),
        "updated_at": "",
        "email": grab_text([r'itemprop="email"[^>]*>([^<]+)<'], page),
        "type": "User",
    }


def scrape_repos(login, pages=3):
    repos = []
    seen = set()

    for page_no in range(1, pages + 1):
        url = "https://github.com/{}?tab=repositories&page={}".format(login, page_no)
        page = http_text(url)
        blocks = re.split(r'<li[^>]*itemprop="owns"', page)[1:]
        if not blocks:
            break

        fresh = 0
        for block in blocks:
            link = re.search(
                r'href="/([^"/]+)/([^"/?]+)"\s+itemprop="name codeRepository"', block, re.S
            )
            if not link:
                continue
            full_name = "{}/{}".format(link.group(1), link.group(2))
            if full_name.lower() in seen:
                continue
            seen.add(full_name.lower())
            fresh += 1

            repos.append({
                "name": link.group(2),
                "full_name": full_name,
                "description": grab_text([r'itemprop="description">([\s\S]*?)</p>'], block),
                "language": grab_text([r'itemprop="programmingLanguage">([^<]+)<'], block),
                "topics": [],
                "stargazers_count": parse_count(grab([
                    r'/stargazers"[^>]*>[\s\S]*?</svg>([\s\S]{0,80}?)</a>',
                ], block)),
                "forks_count": parse_count(grab([
                    r'/forks"[^>]*>[\s\S]*?</svg>([\s\S]{0,80}?)</a>',
                ], block)),
                "pushed_at": grab([r'<relative-time[^>]*datetime="([^"]+)"'], block),
                "created_at": "",
                "html_url": "https://github.com/{}".format(full_name),
                "private": False,
                "fork": "Forked from" in block,
                "archived": "Archived" in block,
                "is_template": False,
            })

        if fresh == 0:
            break

    return repos


def search_emails(login):
    """Commit search has its own 10/minute allowance, separate from core."""
    if not LOGIN_RE.match(login):
        return []

    query = urllib.parse.quote("author:{}".format(login))
    url = "https://api.github.com/search/commits?q={}&per_page=100&sort=author-date&order=desc".format(query)

    try:
        payload = json.loads(http_text(url, "application/vnd.github+json"))
    except (urllib.error.HTTPError, ValueError, OSError):
        return []

    found = {}
    for item in payload.get("items") or []:
        commit = item.get("commit") or {}
        repo = (item.get("repository") or {}).get("full_name") or ""
        short = repo.rsplit("/", 1)[-1] if repo else ""

        # One commit counts once even when author and committer share an address.
        seen = set()
        for role in ("author", "committer"):
            address = ((commit.get(role) or {}).get("email") or "").strip()
            if not address:
                continue
            low = address.lower()
            if low in seen:
                continue
            seen.add(low)
            if low.endswith("noreply.github.com") or low == "noreply@github.com":
                continue
            entry = found.setdefault(low, {
                "address": address,
                "count": 0,
                "repos": {},
                "source": "commit",
                "tags": ["search"],
            })
            entry["count"] += 1
            if short:
                entry["repos"][short] = entry["repos"].get(short, 0) + 1

    out = []
    for entry in sorted(found.values(), key=lambda item: -item["count"]):
        ranked = sorted(entry["repos"].items(), key=lambda pair: (-pair[1], pair[0]))
        out.append({
            "address": entry["address"],
            "count": entry["count"],
            "repos": [name for name, _ in ranked[:6]],
            "source": entry["source"],
            "tags": entry["tags"],
        })
    return out[:50]


def build_scan(login):
    profile = scrape_profile(login)
    repos = scrape_repos(login)
    emails = search_emails(login)

    if not profile.get("public_repos"):
        profile["public_repos"] = len(repos)
    if not profile.get("avatar_url"):
        profile["avatar_url"] = "https://github.com/{}.png".format(login)

    return {
        "source": "public-pages",
        "user": profile,
        "orgs": [],
        "repos": repos,
        "emails": emails,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def scan(login):
    key = login.lower()
    with scan_lock:
        entry = scan_cache.get(key)
        if entry and time.time() - entry[0] < SCAN_TTL:
            return entry[1]

    payload = build_scan(login)

    with scan_lock:
        scan_cache[key] = (time.time(), payload)
    return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # Never let the browser hold onto index.html — edits would be invisible
        # until the file's mtime moved. The /api/* endpoints already send no-store.
        if self.path.split("?")[0] in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/scan":
            login = (urllib.parse.parse_qs(parsed.query).get("login") or [""])[0].strip()
            if not LOGIN_RE.match(login):
                self.send_json(400, {"error": "invalid login"})
                return
            try:
                payload = scan(login)
            except LookupError:
                self.send_json(404, {"error": "not found"})
                return
            except urllib.error.HTTPError as exc:
                self.send_json(404 if exc.code == 404 else 502, {"error": "github replied {}".format(exc.code)})
                return
            except Exception as exc:
                self.send_json(502, {"error": str(exc)})
                return
            self.send_json(200, payload)
            return

        super().do_GET()

    def log_request(self, code="-", size="-"):
        # Keep the console for searches; only complain about real errors.
        try:
            status = int(code)
        except (TypeError, ValueError):
            status = 0
        if status >= 400:
            super().log_request(code, size)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/log":
            self.send_error(404, "not found")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            self.send_error(400, "bad content length")
            return

        if length <= 0:
            self.send_error(411, "content length required")
            return
        if length > MAX_BODY:
            self.send_error(413, "payload too large")
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "invalid json")
            return

        if not isinstance(payload, dict):
            self.send_error(400, "invalid payload")
            return

        log_search(payload)
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def main():
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print("vOidnet could not start on {}:{} - {}".format(HOST, PORT, exc))
        print("something else may hold the port; stop.bat frees it.")
        return 1

    print("{}{}vOidnet{}  serving {}".format(HOTPINK, BOLD, RESET, ROOT))
    print("  {}http://{}:{}/{}".format(PINK, HOST, PORT, RESET))
    print("  {}searches are printed below as they happen - close this window to stop{}\n".format(DIM, RESET), flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nvOidnet stopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())