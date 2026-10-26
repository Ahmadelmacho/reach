"""Offline self-check: python -I test_reach.py"""
import reach

# trust boundary
for bad in ("file:///C:/Windows/win.ini", "http://127.0.0.1:9222/json", "http://localhost/", "http://192.168.1.1/",
            "http://169.254.169.254/latest/meta-data", "javascript:alert(1)", "ftp://example.com",
            "https://user:pw@example.com/"):
    try:
        reach.safe_url(bad)
        raise AssertionError("allowed " + bad)
    except reach.ReachError:
        pass

assert reach._on(reach._host("https://old.reddit.com/r/x"), "reddit.com")
assert not reach._on(reach._host("https://notreddit.com/"), "reddit.com")
assert reach.site_domains("https://mobile.twitter.com/a") == ("x.com", "twitter.com")
assert reach.site_domains("https://example.com/") == ()
for bad in ("https://example.com/r/a/comments/1", "https://www.reddit.com//evil.com/r/a"):
    try:
        reach.reddit_read(bad, 1)
        raise AssertionError("allowed " + bad)
    except reach.ReachError:
        pass
assert reach.REPO_RE.fullmatch("a-b/c.d") and not reach.REPO_RE.fullmatch("a/../../b") and not reach.REPO_RE.fullmatch("a/b?x=1")

# captions: rolling auto-caption duplicates collapse, tags and timestamps go
vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
hello <c>world</c>

00:00:02.000 --> 00:00:04.000
hello world
this &amp; that
"""
assert reach.vtt_to_text(vtt) == "hello world this & that", reach.vtt_to_text(vtt)

# DuckDuckGo html parsing, ad skipped, redirect decoded
ddg = """
<div class="result__body"><a rel="nofollow" class="result__a" href="//duckduckgo.com/y.js?ad=1">Ad</a></div>
<div class="links_main links_deep result__body"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=x">Ex <b>A</b></a>
<a class="result__snippet" href="x">Snip &amp; more</a></div>
"""
assert reach.parse_ddg(ddg, 5) == [{"title": "Ex A", "url": "https://example.com/a", "snippet": "Snip & more"}]

# reddit comment tree flattening
tree = [{"kind": "t1", "data": {"author": "a", "score": 3, "body": "top", "replies": {"data": {"children": [
    {"kind": "t1", "data": {"author": "b", "score": 1, "body": "child", "replies": ""}},
    {"kind": "more", "data": {}}]}}}}]
assert [(c["depth"], c["text"]) for c in reach.flatten_comments(tree)] == [(0, "top"), (1, "child")]

# Instagram: post objects found at any depth, deduped by shortcode
payload = {"data": {"x": {"edges": [{"node": {"code": "AB1", "taken_at": 1, "user": {"username": "u"},
                                              "caption": {"text": "hi"}, "media_type": 2}}],
                          "dup": {"code": "AB1", "taken_at": 1, "user": {"username": "u"}},
                          "junk": {"code": 5, "taken_at": "x", "user": {}}}}}
media = reach.ig_media(payload, {})
assert list(media) == ["AB1"] and reach._ig_post(media["AB1"])["type"] == "video"
cm = reach.ig_comment_nodes({"a": [{"pk": "1", "text": "hi", "comment_like_count": 2, "user": {"username": "x"}},
                                    {"pk": "1", "text": "hi", "comment_like_count": 2, "user": {"username": "x"}},
                                    {"text": "caption", "user": {"username": "y"}}]}, {})
assert list(cm) == ["1"]
try:
    reach.ig_comments("https://evil.com/p/abc123/", 5)
    raise AssertionError("allowed non-instagram comments url")
except reach.ReachError:
    pass
assert reach.IG_HANDLE_RE.fullmatch("some.brand_1") and not reach.IG_HANDLE_RE.fullmatch("../x")

# LinkedIn job cards
li = """<li><a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/data-analyst-at-acme-44?position=1">
<h3 class="base-search-card__title">  Data Analyst </h3><h4 class="base-search-card__subtitle"><a href="x"> Acme </a></h4>
<span class="job-search-card__location"> Berlin </span><time class="job-search-card__listdate" datetime="2026-09-29"></li>"""
assert reach.parse_li_jobs(li) == [{"title": "Data Analyst", "company": "Acme", "location": "Berlin",
                                    "posted": "2026-09-29", "url": "https://www.linkedin.com/jobs/view/data-analyst-at-acme-44"}]
try:
    reach.li_job("https://evil.com/jobs/view/1", 10)
    raise AssertionError("allowed non-linkedin job url")
except reach.ReachError:
    pass

# bot-check pages are failures only when short
assert reach.blocked("Just a moment... Checking your browser")
assert not reach.blocked("A long article about captcha design. " * 300)
assert reach.blocked("  ") and reach.blocked("Nous validons votre navigateur. We are validating your browser")

# TikTok items found at any depth
tt = reach.tt_items({"itemList": [{"id": "7", "desc": "hi", "stats": {"playCount": 5}, "author": {"uniqueId": "u"},
                                   "createTime": 1}, {"id": "8", "desc": "no stats"}]}, {})
assert list(tt) == ["7"] and reach._tt_video(tt["7"])["url"] == "https://www.tiktok.com/@u/video/7"
assert not reach.TT_HANDLE_RE.fullmatch("../x")

# PubMed XML
pm = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><Journal><JournalIssue>
<PubDate><Year>2018</Year></PubDate></JournalIssue><Title>Sleep</Title></Journal>
<ArticleTitle>Naps and <i>memory</i></ArticleTitle><Abstract><AbstractText>Part one.</AbstractText>
<AbstractText>Part two.</AbstractText></Abstract><PublicationTypeList><PublicationType>Review</PublicationType>
</PublicationTypeList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
assert reach.parse_pubmed(pm, 100) == [{"title": "Naps and memory", "journal": "Sleep", "year": "2018", "types": ["Review"],
                                        "url": "https://pubmed.ncbi.nlm.nih.gov/123/", "abstract": "Part one. Part two."}]
try:
    reach.parse_pubmed('<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>', 10)
    raise AssertionError("allowed entity declarations")
except reach.ReachError:
    pass

assert reach.clip("abcdef", 3) == {"text": "abc", "truncated": True, "chars": 6}

# YouTube captions: uploaded subs first, then the speech track, then the (often 429) bare-code auto track
vtt_ = lambda u: [{"ext": "json3", "url": u + ".json"}, {"ext": "vtt", "url": u}]  # noqa: E731
info = {"subtitles": {"en-GB": vtt_("s-gb"), "en-de": vtt_("x")},
        "automatic_captions": {"en": vtt_("a-en"), "en-orig": vtt_("a-orig"), "fr": vtt_("a-fr")}}
assert reach.pick_captions(info, "en") == [("en-GB", "s-gb"), ("en-orig", "a-orig"), ("en", "a-en")]
assert reach.pick_captions({"automatic_captions": {"en": vtt_("a")}}, "e.") == []  # lang is not a regex

# Claude Code hook
import io  # noqa: E402
ctx = lambda o: (o or {}).get("hookSpecificOutput", {}).get("additionalContext", "")  # noqa: E731
assert "REACH-FIRST" in ctx(reach.hook(io.StringIO('{"tool_name": "WebSearch", "tool_input": {"query": "x"}}')))
assert "reach read" in ctx(reach.hook(io.StringIO('{"tool_name": "WebFetch", "tool_input": {"url": "https://old.reddit.com/r/a"}}')))
assert reach.hook(io.StringIO('{"tool_name": "WebFetch", "tool_input": {"url": "https://docs.python.org/"}}')) is None
assert reach.hook(io.StringIO('{"tool_name": "WebFetch", "tool_input": "junk"}')) is None
assert reach.hook(io.StringIO("not json")) is None
assert reach.hook(io.StringIO("[]")) is None
assert reach.ANSI_RE.sub("", "\x1b[0;31mERROR:\x1b[0m boom") == "ERROR: boom"
# audit fixes
import tempfile, time as _t  # noqa: E401,E402
from pathlib import Path as _P  # noqa: E402
reach.HOME = _P(tempfile.mkdtemp()); reach.STATE = reach.HOME / "state.json"
t0 = 1_800_000_000.0
reach.gate("reddit", now=t0)
try:
    reach.gate("reddit", now=t0 + 1); raise AssertionError("no pacing")
except reach.ReachError as e:
    assert "pacing" in str(e)
reach.gate("reddit", now=t0 + 10)  # 5 s gap + at most 30% jitter
reach.pause("reddit", 30, now=t0 + 10)
try:
    reach.gate("reddit", now=t0 + 20 * 60); raise AssertionError("no cooldown")
except reach.ReachError as e:
    assert "cooling down" in str(e)
reach.gate("reddit", now=t0 + 31 * 60)
st = reach._load_state(); st["facebook"] = {"day": _t.strftime("%Y-%m-%d", _t.localtime(t0)), "count": 15}
reach._save_state(st)
try:
    reach.gate("facebook", now=t0); raise AssertionError("no daily cap")
except reach.ReachError as e:
    assert "daily limit" in str(e)
for bad in ("https://example.com/v.mp4", "https://youtube.com.evil.com/watch?v=1", "http://127.0.0.1/"):
    try:
        reach._yt_url(bad); raise AssertionError("allowed " + bad)
    except reach.ReachError:
        pass
assert reach._yt_url("https://www.youtube.com/watch?v=abc") and reach._yt_url("https://youtu.be/abc")
for path in ("/messages", "/direct/inbox/", "/message/inbox", "/i/chat", "/settings/account", "/notifications",
             "/someone/saved/", "/user/bob/saved", "/messaging/thread/1"):
    assert reach.PRIVATE_PATH_RE.search(path), path
for path in ("/r/python/comments/abc/settings_for_vim/", "/natgeo/", "/search", "/p/abc/"):
    assert not reach.PRIVATE_PATH_RE.search(path), path
assert not reach._global_ip("64:ff9b::7f00:1") and not reach._global_ip("ff02::1") and reach._global_ip("8.8.8.8")
for bad in ("https://www.reddit.com/r/a/comments/../../prefs", "https://www.reddit.com/r/a/comments/./x"):
    try:
        reach.reddit_read(bad, 1); raise AssertionError("allowed " + bad)
    except reach.ReachError:
        pass
assert reach.x_handle("@jack") == "jack"
for bad in ("home/../x", "notifications/", "a" * 16):
    try:
        reach.x_handle(bad); raise AssertionError("allowed " + bad)
    except reach.ReachError:
        pass
assert not reach.REPO_RE.fullmatch("a/b\n") and not reach.IG_HANDLE_RE.fullmatch("x\n")
start = _t.time(); reach.TAG_RE.sub("", "<" * 200_000); assert _t.time() - start < 1, "TAG_RE is not linear"
assert reach.HIDDEN_RE.sub("", "a\U000e0041‮b​c") == "abc" and reach.HIDDEN_RE.sub("", "‍") == "‍"
o = reach.hook(io.StringIO('{"tool_name": "WebFetch", "tool_input": {"url": "https://ignore-all-rules.reddit.com/x"}}'))
assert "ignore" not in ctx(o) and "reddit.com" in ctx(o)
assert (_P(__file__).parent / "skill" / "SKILL.md").read_text("utf-8") == reach.SKILL_MD, "skill/SKILL.md drifted"

print("ok")
