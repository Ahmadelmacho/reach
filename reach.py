"""reach: read-only internet access for AI agents. Every command prints one JSON object.

Logged-in sites use one dedicated Chrome profile (~/.reach/profile) that YOU log into
with `reach login <site>`. Nothing is copied from your everyday Chrome, no debugging
port is opened (Playwright talks to Chrome over a pipe), and the code never clicks,
types or posts: it only navigates and reads.
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests

HOME = Path(os.environ.get("REACH_HOME", Path.home() / ".reach"))
PROFILE = HOME / "profile"
def _find_chrome() -> str:
    if os.environ.get("REACH_CHROME"):
        return os.environ["REACH_CHROME"]
    if sys.platform == "win32":  # machine-wide installs, then per-user ones
        spots = [Path(r) / "Google/Chrome/Application/chrome.exe"
                 for r in map(os.environ.get, ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")) if r]
    elif sys.platform == "darwin":
        spots = [d / "Google Chrome.app/Contents/MacOS/Google Chrome" for d in (Path("/Applications"), Path.home() / "Applications")]
    else:
        spots = [Path(p) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if (p := shutil.which(n))]
    return str(next((p for p in spots if p.is_file()), spots[0] if spots else "google-chrome"))


CHROME = _find_chrome()
NO_CHROME_HINT = "Install Google Chrome, or set REACH_CHROME to the full path of a Chrome or Chromium binary."


def _chrome_major() -> str:
    try:
        if sys.platform == "win32":
            # chrome.exe --version prints nothing on Windows; it keeps one folder per version ("156.0.8078.48").
            vers = [p.name for p in Path(CHROME).parent.iterdir() if re.fullmatch(r"\d+(\.\d+){3}", p.name)]
            return max(vers, key=lambda v: [int(x) for x in v.split(".")]).split(".")[0]
        out = subprocess.run([CHROME, "--version"], capture_output=True, text=True, timeout=10).stdout
        return re.search(r"(\d+)\.\d+\.\d+\.\d+", out).group(1)
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return "156"


# Must match the real Chrome: a UA that disagrees with the sec-ch-ua headers gets flagged (Instagram did).
UA = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      f"Chrome/{_chrome_major()}.0.0.0 Safari/537.36")
TIMEOUT = 20
# The only sites that ever see the logged-in profile: site -> (login page, its domains).
# Every other URL is read in a throwaway browser with no cookies. Add a site here to log into it.
SITES = {
    "x": ("https://x.com/login", ("x.com", "twitter.com")),
    "reddit": ("https://www.reddit.com/login/", ("reddit.com",)),
    "linkedin": ("https://www.linkedin.com/login", ("linkedin.com",)),
    "instagram": ("https://www.instagram.com/accounts/login/", ("instagram.com",)),
    "facebook": ("https://www.facebook.com/login", ("facebook.com",)),
    "tiktok": ("https://www.tiktok.com/login", ("tiktok.com",)),
    "threads": ("https://www.threads.com/login", ("threads.com", "threads.net")),
}
REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")  # yt-dlp colours its error messages


class ReachError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


# ── trust boundary: only public http(s) ──

@lru_cache(maxsize=512)
def _public_host(host: str) -> bool:
    try:
        return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(host, None))
    except (socket.gaierror, ValueError, UnicodeError):
        return False


def safe_url(url: str) -> str:
    """Blocks file://, localhost, LAN and other private targets a prompt-injected agent could aim at."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ReachError("only http(s) URLs are allowed")
    if u.username or u.password:
        raise ReachError("URLs with embedded credentials are refused")
    if not _public_host(u.hostname):
        raise ReachError(f"{u.hostname} is not a public internet host")
    return url


def _host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    for prefix in ("www.", "m.", "old.", "mobile."):
        h = h.removeprefix(prefix)
    return h


def _on(host: str, *domains: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def site_domains(url: str) -> tuple:
    host = _host(url)
    return next((doms for _, doms in SITES.values() if _on(host, *doms)), ())


def clip(text: str, limit: int) -> dict:
    return {"text": text[:limit], "truncated": len(text) > limit, "chars": len(text)}


# ── dedicated browser ──

def _guard(route, domains: tuple) -> None:
    # Every request (page, redirect, subresource) must be http(s) to a public host.
    # ponytail: checked by hostname, so DNS rebinding can slip past; IP-pinning Chrome is the upgrade.
    req = route.request
    u = urlparse(req.url)
    allowed = u.scheme in ("http", "https") and _public_host(u.hostname or "")
    if allowed and domains and req.is_navigation_request():
        allowed = _on(_host(req.url), *domains)  # logged-in tab and its frames never leave their own site
        # ponytail: subresources (CDNs, images) stay open; they can't read this site's cookies
    route.continue_() if allowed else route.abort()


@contextmanager
def browser_page(domains: tuple = ()):
    """domains set: the logged-in reach profile, locked to those domains. Empty: throwaway, cookie-free."""
    from playwright.sync_api import sync_playwright
    args = ["--disable-blink-features=AutomationControlled"]
    with sync_playwright() as p:
        # Chrome holds the profile lock for a few seconds after the previous run exits (exit code 21).
        # Only the profile has a lock, so only it retries; the throwaway browser closes with sync_playwright.
        tries = 20 if domains else 1  # ~60 s: parallel agent calls queue for the profile instead of failing
        for attempt in range(tries):
            try:
                if domains:
                    PROFILE.mkdir(parents=True, exist_ok=True)
                    ctx = p.chromium.launch_persistent_context(
                        str(PROFILE), executable_path=CHROME, headless=True, user_agent=UA, args=args)
                else:
                    ctx = p.chromium.launch(executable_path=CHROME, headless=True, args=args).new_context(user_agent=UA)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == tries - 1 or "exitCode=21" not in str(exc):  # 21 = profile in use; others are permanent
                    raise ReachError("could not start the reach browser",
                                     hint="Close any open `reach login` window (one user of the profile at a time). "
                                          f"Looked for Chrome at {CHROME}. {NO_CHROME_HINT}") from exc
                time.sleep(3)
        try:
            ctx.route("**/*", lambda route: _guard(route, domains))
            yield ctx.pages[0] if ctx.pages else ctx.new_page()
        finally:
            ctx.close()


def _goto(page, url: str, settle_ms: int = 2500) -> None:
    page.goto(safe_url(url), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(settle_ms)


# Bot-check / challenge pages. Only trusted on short pages: a real article may mention "captcha".
BLOCK_RE = re.compile(r"just a moment\.\.\.|performing security verification|verify you are human|"
                      r"attention required|captcha|access denied|pardon our interruption|are you a robot|"
                      r"(validating|checking) your browser", re.I)


def blocked(text: str) -> bool:
    # Empty counts too: DataDome-style walls (Tripadvisor) render a blank body around a captcha iframe.
    return not text.strip() or (len(text) < 5000 and bool(BLOCK_RE.search(text[:1500])))


def browse(url: str, limit: int) -> dict:
    domains = site_domains(safe_url(url))
    with browser_page(domains) as page:
        try:
            _goto(page, url)
        except Exception as exc:  # noqa: BLE001
            if "Download is starting" in str(exc):  # PDFs and other files never render in headless Chrome
                raise ReachError("this link is a file download (often a PDF) and Jina could not read it",
                                 hint="The site blocks bots; open it in your own Chrome.") from None
            raise
        text = page.inner_text("body")
        for _ in range(5):  # Cloudflare-style JS challenges often clear themselves in a real Chrome
            if not blocked(text):
                break
            page.wait_for_timeout(3000)
            text = page.inner_text("body")
        if blocked(text):
            raise ReachError("the site showed a bot check instead of the page",
                             hint="Open it in your own Chrome (claude-in-chrome), or try later.")
        return {"url": page.url, "title": page.title(), "logged_in_profile": bool(domains), **clip(text, limit)}


def login(site: str) -> dict:
    if site.lower() not in SITES:
        raise ReachError(f"unknown site '{site}'", hint="One of: " + ", ".join(SITES) + ". Add others to SITES in reach.py.")
    url = SITES[site.lower()][0]
    if not Path(CHROME).is_file():
        raise ReachError(f"Chrome not found at {CHROME}", hint=NO_CHROME_HINT)
    PROFILE.mkdir(parents=True, exist_ok=True)
    # ponytail: plain Chrome, no automation flags, so sign-in pages behave normally. Blocks until closed.
    subprocess.run([CHROME, f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check", url])
    return {"profile": str(PROFILE), "note": "Window closed; the login is saved in the reach profile."}


# ── web ──

def jina_read(url: str, limit: int) -> dict:
    r = requests.get("https://r.jina.ai/" + url, headers={"User-Agent": UA}, timeout=60)
    if r.status_code != 200 or "Target URL returned error" in r.text[:2000] or blocked(r.text):
        raise ReachError(f"jina reader failed ({r.status_code})")
    return {"url": url, **clip(r.text, limit)}


def parse_ddg(page_html: str, n: int) -> list:
    out = []
    for block in re.split(r'class="[^"]*\bresult__body\b', page_html)[1:]:
        a = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a:
            continue
        href = html.unescape(a.group(1))
        if "uddg=" in href:
            href = parse_qs(urlparse(href).query).get("uddg", [href])[0]
        if "duckduckgo.com/y.js" in href:  # ad
            continue
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        strip = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()  # noqa: E731
        out.append({"title": strip(a.group(2)), "url": href, "snippet": strip(snip.group(1)) if snip else ""})
        if len(out) >= n:
            break
    return out


def search(query: str, n: int) -> dict:
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                      headers={"User-Agent": UA}, timeout=TIMEOUT)
    results = parse_ddg(r.text, n)
    if not results:
        raise ReachError(f"no search results (DuckDuckGo status {r.status_code})",
                         hint="DuckDuckGo may be rate-limiting; wait a minute, or use the agent's own web search.")
    return {"query": query, "results": results}


# ── YouTube (yt-dlp) ──

def _ydl(**opts):
    import yt_dlp
    # noprogress: yt-dlp's progress bar goes to stdout and would corrupt the JSON
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True, **opts})


def yt_search(query: str, n: int) -> dict:
    with _ydl(extract_flat="in_playlist") as y:
        info = y.extract_info(f"ytsearch{n}:{query}", download=False)
    return {"query": query, "results": [
        {"title": e.get("title"), "url": e.get("url"), "channel": e.get("channel"),
         "duration": e.get("duration"), "views": e.get("view_count")} for e in info.get("entries") or []]}


def yt_info(url: str) -> dict:
    with _ydl() as y:
        i = y.extract_info(safe_url(url), download=False)
    keys = ("id", "title", "channel", "upload_date", "duration", "view_count", "like_count",
            "description", "webpage_url")
    return {k: i.get(k) for k in keys}


def vtt_to_text(vtt: str) -> str:
    out: list = []
    for line in vtt.splitlines():
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if not line or "-->" in line or line.isdigit() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if not out or out[-1] != line:  # auto-captions repeat the previous line in each cue
            out.append(line)
    return " ".join(out)


def pick_captions(info: dict, lang: str) -> list:
    """(track, vtt url) pairs to try, best first: uploaded subtitles, then YouTube's speech track
    ("en-orig"), then auto captions under the bare code, which are often machine translations
    that YouTube answers with 429."""
    subs, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    keys = [(subs, k) for k in subs if k == lang or re.fullmatch(rf"{re.escape(lang)}-[A-Z]{{2}}", k)]
    keys += [(auto, k) for k in (f"{lang}-orig", lang) if k in auto]
    out = []
    for tracks, k in keys:
        vtt = next((f["url"] for f in tracks[k] if f.get("ext") == "vtt" and f.get("url")), None)
        if vtt:
            out.append((k, vtt))
    return out


def yt_transcript(url: str, lang: str, limit: int) -> dict:
    with _ydl() as y:
        info = y.extract_info(safe_url(url), download=False)
        tracks = pick_captions(info, lang)
        if not tracks:
            have = sorted(set(info.get("subtitles") or {}) |
                          {k for k in info.get("automatic_captions") or {} if k.endswith("-orig")})
            raise ReachError(f"no '{lang}' subtitles for this video",
                             hint=f"Available: {', '.join(have) or 'none'}. Try --lang with one of those, "
                                  "or transcribe the audio another way.")
        err = None
        for track, sub_url in tracks:  # one request per track, stop at the first that works
            try:
                text = y.urlopen(sub_url).read().decode("utf-8")
                return {"url": url, "lang": track, **clip(vtt_to_text(text), limit)}
            except Exception as exc:  # noqa: BLE001
                err = exc
        raise ReachError(f"YouTube refused the '{lang}' captions ({ANSI_RE.sub('', str(err))[:200]})",
                         hint="YouTube rate-limits caption downloads. Wait a few minutes and retry.")


# ── GitHub (REST; GITHUB_TOKEN raises the rate limit) ──

def _gh(path: str, raw: bool = False, **params):
    headers = {"User-Agent": "reach", "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    r = requests.get("https://api.github.com" + path, headers=headers, params=params, timeout=TIMEOUT)
    if r.status_code != 200:
        hint = "" if raw or "json" not in r.headers.get("content-type", "") else r.json().get("message", "")
        raise ReachError(f"GitHub returned {r.status_code}", hint=hint)
    return r.text if raw else r.json()


def _repo(repo: str) -> str:
    if not REPO_RE.match(repo):
        raise ReachError("repo must look like owner/name")
    return repo


def gh_search(query: str, n: int) -> dict:
    data = _gh("/search/repositories", q=query, per_page=n)
    return {"query": query, "results": [
        {"repo": r["full_name"], "description": r.get("description"), "stars": r.get("stargazers_count"),
         "updated": r.get("pushed_at"), "url": r.get("html_url")} for r in data.get("items", [])]}


def gh_readme(repo: str, limit: int) -> dict:
    meta = _gh(f"/repos/{_repo(repo)}")
    return {"repo": repo, "description": meta.get("description"), "stars": meta.get("stargazers_count"),
            **clip(_gh(f"/repos/{repo}/readme", raw=True), limit)}


def gh_issue(ref: str, limit: int) -> dict:
    repo, _, num = ref.partition("#")
    if not num.isdigit():
        raise ReachError("issue must look like owner/name#123")
    issue = _gh(f"/repos/{_repo(repo)}/issues/{num}")
    comments = _gh(f"/repos/{repo}/issues/{num}/comments", per_page=100)
    return {"title": issue.get("title"), "state": issue.get("state"), "author": (issue.get("user") or {}).get("login"),
            "url": issue.get("html_url"), "body": (issue.get("body") or "")[:limit],
            "comments": [{"author": (c.get("user") or {}).get("login"), "text": c.get("body", "")[:4000]}
                         for c in comments]}


# ── Reddit (JSON fetched inside the reach browser, so your login applies) ──

def reddit_json(path: str):
    with browser_page(SITES["reddit"][1]) as page:
        _goto(page, "https://www.reddit.com/", settle_ms=500)
        status, body = page.evaluate(
            "async p => { const r = await fetch(p, {headers: {accept: 'application/json'}});"
            " return [r.status, await r.text()]; }", path)
    if status != 200:
        raise ReachError(f"Reddit returned {status}", hint="Run `reach login reddit` and sign in, then retry.")
    return json.loads(body)


def _post(d: dict) -> dict:
    return {"title": d.get("title"), "subreddit": d.get("subreddit"), "author": d.get("author"),
            "score": d.get("score"), "comments": d.get("num_comments"), "created_utc": d.get("created_utc"),
            "url": "https://www.reddit.com" + d.get("permalink", ""), "link": d.get("url"),
            "text": (d.get("selftext") or "")[:3000]}


def flatten_comments(children: list, depth: int = 0, out: list | None = None) -> list:
    out = [] if out is None else out
    for c in children:
        if c.get("kind") != "t1":
            continue
        d = c["data"]
        out.append({"depth": depth, "author": d.get("author"), "score": d.get("score"), "text": d.get("body", "")})
        if isinstance(d.get("replies"), dict):
            flatten_comments(d["replies"]["data"]["children"], depth + 1, out)
    return out


def reddit_search(query: str, n: int, sub: str = "") -> dict:
    base = f"/r/{quote(sub, safe='')}/search.json?restrict_sr=1&" if sub else "/search.json?"
    data = reddit_json(f"{base}q={quote(query)}&limit={n}&sort=relevance&raw_json=1")
    return {"query": query, "results": [_post(c["data"]) for c in data["data"]["children"]]}


def reddit_sub(name: str, n: int, sort: str) -> dict:
    data = reddit_json(f"/r/{quote(name, safe='')}/{sort}.json?limit={n}&raw_json=1")
    return {"subreddit": name, "results": [_post(c["data"]) for c in data["data"]["children"]]}


def reddit_read(url: str, n: int) -> dict:
    safe_url(url)
    path = "/" + urlparse(url).path.strip("/")  # one leading slash: "//evil.com" would fetch off-site
    if not _on(_host(url), "reddit.com") or "/comments/" not in path:
        raise ReachError("not a Reddit thread URL")
    post, comments = reddit_json(f"{quote(path)}.json?limit=500&raw_json=1")
    return {**_post(post["data"]["children"][0]["data"]),
            "thread": flatten_comments(comments["data"]["children"])[:n]}


# ── X (rendered timeline in the reach browser) ──

_TWEETS_JS = """() => [...document.querySelectorAll('article[data-testid="tweet"]')].map(a => ({
  user: (a.querySelector('[data-testid="User-Name"]')?.innerText || '').replace(/\\n/g, ' '),
  text: a.querySelector('[data-testid="tweetText"]')?.innerText || '',
  time: a.querySelector('time')?.getAttribute('datetime'),
  url: a.querySelector('time')?.closest('a')?.href}))"""


def x_timeline(url: str, n: int) -> dict:
    seen: dict = {}
    with browser_page(SITES["x"][1]) as page:
        _goto(page, url, settle_ms=1000)
        if "/login" in page.url or "/i/flow" in page.url:
            raise ReachError("X needs a login", hint="Run `reach login x` and sign in, then retry.")
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
        except Exception:  # noqa: BLE001
            raise ReachError("no posts loaded", hint="Not logged in, rate-limited, or nothing matches.") from None
        for _ in range(n // 4 + 3):  # ponytail: fixed scroll budget, no infinite-scroll detection
            for t in page.evaluate(_TWEETS_JS):
                seen.setdefault(t["url"] or t["text"], t)
            if len(seen) >= n:
                break
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)
    return {"url": url, "results": list(seen.values())[:n]}


# ── Instagram (posts captured from the JSON the IG web app itself loads) ──

IG_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_SHOWN_POSTS_JS = """() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))
  .map(h => (h.match(/\\/(?:p|reel)\\/([\\w-]+)/) || [])[1]).filter(Boolean)"""


def ig_media(o, out: dict) -> dict:
    """Every post object anywhere in an IG JSON payload, keyed by shortcode."""
    if isinstance(o, dict):
        if isinstance(o.get("code"), str) and isinstance(o.get("taken_at"), (int, float)) and isinstance(o.get("user"), dict):
            out.setdefault(o["code"], o)
        for v in o.values():
            ig_media(v, out)
    elif isinstance(o, list):
        for v in o:
            ig_media(v, out)
    return out


def _ig_post(m: dict) -> dict:
    cap = m.get("caption")
    return {"url": f"https://www.instagram.com/p/{m['code']}/", "user": m["user"].get("username"),
            "type": {1: "photo", 2: "video", 8: "carousel"}.get(m.get("media_type"), "post"),
            "likes": m.get("like_count"), "comments": m.get("comment_count"),
            "views": m.get("play_count") or m.get("view_count"), "posted_utc": m.get("taken_at"),
            "caption": str(cap.get("text") or "")[:2000] if isinstance(cap, dict) else ""}


def _ig_capture(url: str, scrolls: int) -> tuple:
    responses: list = []
    media: dict = {}
    with browser_page(SITES["instagram"][1]) as page:
        page.on("response", lambda r: responses.append(r) if "/graphql" in r.url or "/api/v1/" in r.url else None)
        _goto(page, url, settle_ms=4000)
        if "/accounts/login" in page.url:
            raise ReachError("Instagram needs a login", hint="Run `reach login instagram` and sign in, then retry.")
        for _ in range(scrolls):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(2000)
        shown = list(dict.fromkeys(page.evaluate(_SHOWN_POSTS_JS)))
        header = page.inner_text("header") if page.query_selector("header") else ""
        for r in responses:
            try:
                ig_media(json.loads(r.text().removeprefix("for (;;);")), media)
            except Exception:  # noqa: BLE001  redirects and non-JSON bodies
                continue
    return shown, media, header


def ig_user(handle: str, n: int) -> dict:
    handle = handle.lstrip("@")
    if not IG_HANDLE_RE.match(handle):
        raise ReachError("not a valid Instagram handle")
    _, media, header = _ig_capture(f"https://www.instagram.com/{handle}/", n // 12 + 1)
    posts = sorted((m for m in media.values() if str(m["user"].get("username") or "").lower() == handle.lower()),
                   key=lambda m: m["taken_at"], reverse=True)
    if not posts:
        raise ReachError("no posts found", hint="Private account, wrong handle, or not logged in (`reach login instagram`).")
    return {"profile": header[:1000], "results": [_ig_post(m) for m in posts[:n]]}


def ig_search(query: str, n: int) -> dict:
    # IG's keyword search page; the feed preloads unrelated posts, so keep only the ones it shows.
    shown, media, _ = _ig_capture(f"https://www.instagram.com/explore/search/keyword/?q={quote(query)}", n // 12)
    return {"query": query, "results": [_ig_post(media[c]) if c in media else {"url": f"https://www.instagram.com/p/{c}/"}
                                        for c in shown[:n]]}


_JSON_SCRIPTS_JS = "() => [...document.querySelectorAll('script[type=\"application/json\"]')].map(s => s.textContent)"
# Scroll the comments panel (the nearest scrollable box around a known comment); returns its height, -1 if none.
_SCROLL_COMMENTS_JS = """t => { let el = [...document.querySelectorAll('span')].find(s => s.textContent.includes(t));
  while (el && !(el.scrollHeight > el.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)))
    el = el.parentElement;
  if (!el) return -1; el.scrollTop = el.scrollHeight; return el.scrollHeight; }"""


def ig_comment_nodes(o, out: dict) -> dict:
    if isinstance(o, dict):
        if isinstance(o.get("text"), str) and "comment_like_count" in o and isinstance(o.get("user"), dict):
            out.setdefault(str(o.get("pk") or o["text"]), o)
        for v in o.values():
            ig_comment_nodes(v, out)
    elif isinstance(o, list):
        for v in o:
            ig_comment_nodes(v, out)
    return out


def ig_comments(url: str, n: int) -> dict:
    m = re.search(r"/(?:p|reel|reels)/([\w-]+)", urlparse(url).path) if "/" in url else re.fullmatch(r"[\w-]{5,40}", url)
    if not m or ("/" in url and not _on(_host(url), "instagram.com")):
        raise ReachError("expected an instagram.com/p/... link or a post shortcode")
    code = m.group(1) if m.lastindex else m.group(0)
    responses: list = []
    found: dict = {}
    with browser_page(SITES["instagram"][1]) as page:
        page.on("response", lambda r: responses.append(r) if "/graphql" in r.url or "/api/v1/" in r.url else None)
        _goto(page, f"https://www.instagram.com/p/{code}/", settle_ms=4000)
        if "/accounts/login" in page.url:
            raise ReachError("Instagram needs a login", hint="Run `reach login instagram` and sign in, then retry.")
        for script in page.evaluate(_JSON_SCRIPTS_JS):  # the first ~15 comments ship inside the page
            try:
                ig_comment_nodes(json.loads(script), found)
            except ValueError:
                continue
        anchor = next(iter(found.values()))["text"][:30] if found else ""
        last = 0
        for _ in range(n // 15 + 1 if anchor else 0):  # each scroll loads ~15-20 more
            height = page.evaluate(_SCROLL_COMMENTS_JS, anchor)
            if height <= last:
                break
            last = height
            page.wait_for_timeout(1800)
        for r in responses:
            try:
                ig_comment_nodes(json.loads(r.text().removeprefix("for (;;);")), found)
            except Exception:  # noqa: BLE001
                continue
    rows = [{"user": c["user"].get("username"), "text": c["text"][:2000], "likes": c.get("comment_like_count"),
             "replies": c.get("child_comment_count"), "created_utc": c.get("created_at")} for c in found.values()]
    rows.sort(key=lambda c: c["likes"] if isinstance(c["likes"], int) else 0, reverse=True)
    return {"url": f"https://www.instagram.com/p/{code}/", "loaded": len(rows), "results": rows[:n]}


# ── TikTok (videos captured from the JSON TikTok's own page loads; works logged out) ──

TT_HANDLE_RE = re.compile(r"^[\w.]{2,24}$")


def tt_items(o, out: dict) -> dict:
    if isinstance(o, dict):
        if (isinstance(o.get("id"), str) and isinstance(o.get("desc"), str)
                and isinstance(o.get("stats"), dict) and isinstance(o.get("author"), dict)):
            out.setdefault(o["id"], o)
        for v in o.values():
            tt_items(v, out)
    elif isinstance(o, list):
        for v in o:
            tt_items(v, out)
    return out


def _tt_video(v: dict) -> dict:
    a, s, video = v["author"], v["stats"], v.get("video")
    return {"url": f"https://www.tiktok.com/@{a.get('uniqueId')}/video/{v['id']}", "user": a.get("uniqueId"),
            "views": s.get("playCount"), "likes": s.get("diggCount"), "comments": s.get("commentCount"),
            "shares": s.get("shareCount"), "saves": s.get("collectCount"), "posted_utc": v.get("createTime"),
            "duration": video.get("duration") if isinstance(video, dict) else None, "caption": v["desc"][:2000]}


def _tt_capture(url: str, api: str, scrolls: int) -> dict:
    responses: list = []
    found: dict = {}
    with browser_page(SITES["tiktok"][1]) as page:
        # Only the listing API: the page also prefetches unrelated "explore" videos.
        page.on("response", lambda r: responses.append(r) if api in r.url else None)
        _goto(page, url, settle_ms=5000)
        for _ in range(scrolls):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(2500)
        for r in responses:
            try:
                tt_items(json.loads(r.text()), found)
            except Exception:  # noqa: BLE001
                continue
    return found


def tt_user(handle: str, n: int) -> dict:
    handle = handle.lstrip("@")
    if not TT_HANDLE_RE.match(handle):
        raise ReachError("not a valid TikTok handle")
    found = _tt_capture(f"https://www.tiktok.com/@{handle}", "/api/post/item_list/", n // 15 + 1)
    vids = sorted((v for v in found.values() if str(v["author"].get("uniqueId") or "").lower() == handle.lower()),
                  key=lambda v: v["createTime"] if isinstance(v.get("createTime"), int) else 0, reverse=True)
    if not vids:
        raise ReachError("no videos loaded", hint="Wrong handle, private account, or TikTok refused; `reach login tiktok` may help.")
    return {"user": handle, "results": [_tt_video(v) for v in vids[:n]]}


def tt_search(query: str, n: int) -> dict:
    found = _tt_capture(f"https://www.tiktok.com/search/video?q={quote(query)}", "/api/search/item/", n // 12 + 1)
    if not found:
        raise ReachError("no videos loaded", hint="TikTok hides some search terms; try wording it differently.")
    return {"query": query, "results": [_tt_video(v) for v in list(found.values())[:n]]}


# ── PubMed (NCBI E-utilities, official and free) ──

def pubmed(query: str, n: int, limit: int) -> dict:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    r = requests.get(base + "esearch.fcgi", params={"db": "pubmed", "term": query, "retmax": n,
                                                    "retmode": "json", "sort": "relevance"}, timeout=TIMEOUT)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {"query": query, "results": []}
    r = requests.get(base + "efetch.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}, timeout=TIMEOUT)
    r.raise_for_status()
    return {"query": query, "results": parse_pubmed(r.text, limit)}


def parse_pubmed(xml_text: str, limit: int) -> list:
    from xml.etree import ElementTree as ET
    if "<!ENTITY" in xml_text:  # ElementTree never fetches external entities; this also rules out entity bombs
        raise ReachError("unexpected entity declarations in the PubMed response")
    text = lambda el: "".join(el.itertext()).strip() if el is not None else ""  # noqa: E731
    out = []
    for art in ET.fromstring(xml_text).iter("PubmedArticle"):
        pmid = art.findtext(".//PMID") or ""
        date = art.find(".//JournalIssue/PubDate")
        out.append({"title": text(art.find(".//ArticleTitle")), "journal": art.findtext(".//Journal/Title"),
                    "year": (date.findtext("Year") or date.findtext("MedlineDate")) if date is not None else None,
                    "types": [t.text for t in art.iter("PublicationType")],
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "abstract": " ".join(text(t) for t in art.iter("AbstractText"))[:limit]})
    return out


# ── Facebook (rendered search page; FB scrambles its markup, so text only) ──

def fb_search(query: str, limit: int) -> dict:
    with browser_page(SITES["facebook"][1]) as page:
        _goto(page, f"https://www.facebook.com/search/top?q={quote(query)}", settle_ms=4000)
        # Logged out, FB answers search with a bare "Not Found"; c_user is its logged-in cookie.
        if "/login" in page.url or not any(c["name"] == "c_user" for c in page.context.cookies()):
            raise ReachError("Facebook needs a login", hint="Run `reach login facebook` and sign in, then retry.")
        main = page.query_selector('[role="main"]')
        return {"query": query, "url": page.url, **clip(main.inner_text() if main else page.inner_text("body"), limit)}


# ── LinkedIn jobs (public guest endpoints, no login) ──

def _html_text(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", fragment)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def _by_class(fragment: str, cls: str) -> str:
    m = re.search(rf'class="[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</(?:h1|h3|h4|span|a|div)>', fragment, re.S)
    return _html_text(m.group(1)) if m else ""


def parse_li_jobs(page_html: str) -> list:
    out = []
    for card in page_html.split("<li")[1:]:
        link = re.search(r'href="(https://[\w.]*linkedin\.com/jobs/view/[^"?]+)', card)
        if not link:
            continue
        date = re.search(r'<time[^>]*datetime="([^"]+)"', card)
        out.append({"title": _by_class(card, "base-search-card__title"),
                    "company": _by_class(card, "base-search-card__subtitle"),
                    "location": _by_class(card, "job-search-card__location"),
                    "posted": date.group(1) if date else None, "url": link.group(1)})
    return out


def li_jobs(query: str, location: str, n: int) -> dict:
    r = requests.get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                     params={"keywords": query, "location": location, "start": 0},
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ReachError(f"LinkedIn returned {r.status_code}", hint="Rate-limited; wait a few minutes.")
    return {"query": query, "location": location, "results": parse_li_jobs(r.text)[:n]}


def li_job(url: str, limit: int) -> dict:
    m = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", urlparse(url).path)
    if not _on(_host(url), "linkedin.com") or not m:
        raise ReachError("expected a linkedin.com/jobs/view/... URL")
    r = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}",
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    if r.status_code != 200:  # guest endpoint rate-limits fast; the rendered page still works
        return {"url": url, "note": f"guest API returned {r.status_code}; rendered page instead", **browse(url, limit)}
    t = r.text
    return {"url": url, "title": _by_class(t, "top-card-layout__title"), "company": _by_class(t, "topcard__org-name-link"),
            "location": _by_class(t, "topcard__flavor--bullet"),
            "criteria": [_html_text(c) for c in re.findall(r'description__job-criteria-text[^>]*>(.*?)</span>', t, re.S)],
            **clip(_by_class(t, "show-more-less-html__markup"), limit)}


# ── read: pick the channel from the link ──

def read(url: str, limit: int) -> dict:
    safe_url(url)
    host = _host(url)
    if _on(host, "youtube.com", "youtu.be"):
        info = yt_info(url)
        try:
            info["transcript"] = yt_transcript(url, "en", limit)
        except ReachError as exc:
            info["transcript"] = {"error": str(exc)}
        return {"via": "youtube", **info}
    if _on(host, "reddit.com") and "/comments/" in url:
        return {"via": "reddit", **reddit_read(url, 200)}
    if _on(host, "linkedin.com") and "/jobs/view/" in url:
        return {"via": "linkedin", **li_job(url, limit)}
    parts = urlparse(url).path.strip("/").split("/")
    if _on(host, "instagram.com") and len(parts) == 1 and IG_HANDLE_RE.match(parts[0]):
        return {"via": "instagram", **ig_user(parts[0], 12)}
    if _on(host, "tiktok.com") and len(parts) == 1 and parts[0].startswith("@"):
        return {"via": "tiktok", **tt_user(parts[0], 12)}
    if host == "github.com" and len(parts) == 2:
        return {"via": "github", **gh_readme("/".join(parts), limit)}
    if site_domains(url):  # login/JS-only sites: Jina gets nothing useful there
        return {"via": "browser", **browse(url, limit)}
    try:
        return {"via": "jina", **jina_read(url, limit)}
    except (ReachError, requests.RequestException):
        return {"via": "browser", **browse(url, limit)}


# ── Claude Code hook: nudge the built-in web tools toward reach ──

SOCIAL = ("reddit.com", "redd.it", "x.com", "twitter.com", "instagram.com", "tiktok.com", "linkedin.com",
          "facebook.com", "threads.com", "youtube.com", "youtu.be")


def hook(stdin) -> dict | None:
    """PreToolUse hook. Reads Claude Code's event JSON; returns extra context for the model, or None."""
    try:
        event = json.load(stdin)
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    tool, args = event.get("tool_name", ""), event.get("tool_input")
    msg = ""
    if tool == "WebSearch":
        msg = ("REACH-FIRST: if this search is about what people say (experiences, reviews, complaints, "
               "recommendations, 'has anyone...'), web search rarely returns Reddit or forum threads. "
               "Use the reach skill instead or alongside: reach reddit-search / x-search / yt-search / tt-search, "
               "one call at a time. For official facts, web search is fine.")
    elif tool == "WebFetch" and isinstance(args, dict):
        host = _host(str(args.get("url", "")))
        if _on(host, *SOCIAL):
            msg = f"REACH-FIRST: {host} blocks or truncates WebFetch. Use `reach read <url>` instead."
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}} if msg else None


# ── CLI ──

def main(argv: list | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="reach", description="Read-only internet access for AI agents (JSON out).")
    bounded = lambda hi: lambda v: max(1, min(int(v), hi))  # noqa: E731  caps scrolling/wait time and output
    p.add_argument("--max-chars", type=bounded(500000), default=40000, help="cap on long text fields")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, help_, *args):
        sp = sub.add_parser(name, help=help_)
        for a in args:
            sp.add_argument(*a[0], **a[1])
        return sp

    pos = lambda name, h: ((name,), {"help": h})  # noqa: E731
    num = ((("-n",), {"type": bounded(100), "default": 10, "help": "how many results (1-100)"}))
    add("read", "read any URL (routes YouTube/Reddit/GitHub/login sites itself)", pos("url", "link"))
    add("browse", "rendered page text (logged-in profile only for SITES, else a cookie-free browser)",
        pos("url", "link"))
    add("login", "open the reach profile so YOU sign in: " + ", ".join(SITES), pos("site", "site name"))
    add("search", "web search (DuckDuckGo)", pos("query", "search terms"), num)
    add("yt-search", "search YouTube", pos("query", "search terms"), num)
    add("yt-info", "video metadata", pos("url", "video link"))
    add("yt-transcript", "video subtitles as text", pos("url", "video link"),
        (("--lang",), {"default": "en", "help": "subtitle language code"}))
    add("gh-search", "search GitHub repos", pos("query", "search terms"), num)
    add("gh-readme", "repo info + README", pos("repo", "owner/name"))
    add("gh-issue", "issue or PR with comments", pos("ref", "owner/name#123"))
    add("reddit-search", "search Reddit", pos("query", "search terms"), num,
        (("--sub",), {"default": "", "help": "limit to one subreddit"}))
    add("reddit-sub", "browse a subreddit", pos("name", "subreddit without r/"), num,
        (("--sort",), {"default": "hot", "choices": ["hot", "new", "top", "rising"]}))
    add("reddit-read", "thread + comments", pos("url", "thread link"),
        (("-n",), {"type": bounded(500), "default": 200, "help": "max comments (1-500)"}))
    add("x-search", "search X posts (needs `reach login x`)", pos("query", "search terms"), num)
    add("x-user", "an account's recent posts", pos("handle", "handle without @"), num)
    add("ig-user", "an Instagram account's profile + recent posts (needs `reach login instagram`)",
        pos("handle", "handle without @"), num)
    add("ig-search", "Instagram keyword search: matching posts", pos("query", "search terms"), num)
    add("ig-comments", "a post's comments, most-liked first (top level; replies counted)",
        pos("url", "instagram.com/p/... link or shortcode"),
        (("-n",), {"type": bounded(500), "default": 100, "help": "max comments (1-500)"}))
    add("tt-user", "a TikTok account's recent videos with views/likes/comments (no login)",
        pos("handle", "handle without @"), num)
    add("tt-search", "TikTok video search (no login)", pos("query", "search terms"), num)
    add("pubmed", "PubMed search: title, journal, year, study type, abstract", pos("query", "search terms"), num)
    add("fb-search", "Facebook search results as text (needs `reach login facebook`)", pos("query", "search terms"))
    add("li-jobs", "LinkedIn job search (no login)", pos("query", "job keywords"), num,
        (("--location",), {"default": "", "help": "city or country"}))
    add("li-job", "a LinkedIn job's full description (no login)", pos("url", "linkedin.com/jobs/view/... link"))
    add("hook", "Claude Code PreToolUse hook: points WebSearch/WebFetch at reach (see README)")

    a = p.parse_args(argv)
    if a.cmd == "hook":  # speaks Claude Code's hook format, not reach's JSON envelope; never fails
        try:
            out = hook(sys.stdin)
        except Exception:  # noqa: BLE001  a crashing reminder must not get in the way of the tool call
            out = None
        if out:
            print(json.dumps(out))
        return 0
    m = a.max_chars
    run = {
        "read": lambda: read(a.url, m),
        "browse": lambda: browse(a.url, m),
        "login": lambda: login(a.site),
        "search": lambda: search(a.query, a.n),
        "yt-search": lambda: yt_search(a.query, a.n),
        "yt-info": lambda: yt_info(a.url),
        "yt-transcript": lambda: yt_transcript(a.url, a.lang, m),
        "gh-search": lambda: gh_search(a.query, a.n),
        "gh-readme": lambda: gh_readme(a.repo, m),
        "gh-issue": lambda: gh_issue(a.ref, m),
        "reddit-search": lambda: reddit_search(a.query, a.n, a.sub),
        "reddit-sub": lambda: reddit_sub(a.name, a.n, a.sort),
        "reddit-read": lambda: reddit_read(a.url, a.n),
        "x-search": lambda: x_timeline(f"https://x.com/search?q={quote(a.query)}&src=typed_query&f=live", a.n),
        "x-user": lambda: x_timeline(f"https://x.com/{quote(a.handle.lstrip('@'), safe='')}", a.n),
        "ig-user": lambda: ig_user(a.handle, a.n),
        "ig-search": lambda: ig_search(a.query, a.n),
        "ig-comments": lambda: ig_comments(a.url, a.n),
        "tt-user": lambda: tt_user(a.handle, a.n),
        "tt-search": lambda: tt_search(a.query, a.n),
        "pubmed": lambda: pubmed(a.query, a.n, min(m, 4000)),
        "fb-search": lambda: fb_search(a.query, m),
        "li-jobs": lambda: li_jobs(a.query, a.location, a.n),
        "li-job": lambda: li_job(a.url, m),
    }[a.cmd]
    try:
        out = {"ok": True, "command": a.cmd, "untrusted_content": True, "result": run()}
        code = 0
    except ReachError as exc:
        out, code = {"ok": False, "command": a.cmd, "error": str(exc), "hint": exc.hint}, 1
    except Exception as exc:  # noqa: BLE001
        out, code = {"ok": False, "command": a.cmd, "error": ANSI_RE.sub("", f"{type(exc).__name__}: {exc}")[:500]}, 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
