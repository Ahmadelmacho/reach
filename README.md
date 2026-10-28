# reach

**Let Claude read Reddit, X, Instagram, TikTok and YouTube for you.**

Ask Claude "what do people think of X?" and it normally searches Google-style results: articles and ads. With reach it reads the actual Reddit threads, posts, comments and video transcripts where people talk.

## Get it

Copy this into Claude Code (terminal, desktop app or VS Code) and send it:

```text
Install reach for me from https://github.com/Ahmadelmacho/reach and set it up so you use it.
If any step fails, stop and tell me the error. Run only the commands below.
1. If the `uv` command is missing, install it with exactly one of these, then use the full path
   ~/.local/bin/uv (or %USERPROFILE%\.local\bin\uv.exe on Windows) until I restart:
   macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
   Windows:      powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
2. Run: uv tool install git+https://github.com/Ahmadelmacho/reach@v0.2.1
   If `reach` isn't found afterwards, use its full path in ~/.local/bin and run `uv tool update-shell`.
3. Run: reach install-skill
4. Add this to ~/.claude/CLAUDE.md (create it if missing):
   # Use reach for people research
   For questions about what people say (reviews, experiences, complaints, recommendations, trends)
   and for Reddit, X, YouTube, TikTok, Instagram, GitHub or PubMed: use the `reach` skill before
   WebSearch, one call at a time. For links on those sites, use `reach read <url>` instead of WebFetch.
5. Copy ~/.claude/settings.json to settings.json.bak (if it exists). Then add only this one entry
   under hooks.PreToolUse, keeping everything else, check the file is still valid JSON, and show me the diff:
   {"matcher": "WebSearch|WebFetch",
    "hooks": [{"type": "command", "command": "reach hook", "timeout": 5, "onFailure": "continue"}]}
6. Test it with: reach browse https://github.com/Ahmadelmacho/reach
Then tell me in one line what you did, and to restart Claude Code.
```

Click "Yes" when Claude asks to run things. Restart Claude Code when it's done. That's it.

You need Google Chrome installed for web search, Reddit, X, Instagram, TikTok and Facebook.

## How it works

- **reach** is a small program on your computer. It opens pages in a hidden Chrome window and hands Claude the text.
- **The skill** teaches Claude the commands and the rules. **The CLAUDE.md rule** tells Claude to use reach for "what are people saying" questions instead of normal web search.
- It only reads. It never posts, likes, follows or messages anyone.
- It paces itself like one person reading, and stops using a site for a while if the site pushes back (see "Built-in limits").

## Log in (optional)

Reddit, X, Instagram and Facebook show little or nothing to logged-out visitors. Logging in once lets reach see full threads, comments and search results.

**Logging in puts that account at risk.** Automated reading breaks these sites' rules, and people using tools like this report bans: an X account banned on its very first search, X accounts gone within 3 days, Instagram and LinkedIn accounts locked quickly.

- Only log in with **a separate account you can afford to lose, and that you are permitted to use**. Never your personal, work or brand account.
- **Never log in on a computer or network you use for ad accounts or business managers** (Meta, TikTok, Google). Platforms link accounts by device and network, so a ban can spread.
- Ask for small amounts and run one thing at a time.

| Site | Risk when logged in |
|---|---|
| YouTube, TikTok, GitHub, PubMed, web search | No login needed, so no account at risk |
| Reddit | Lowest. We found no ban reports for reading at normal volume |
| X, Instagram, Facebook, LinkedIn | High. Accounts get locked or banned, sometimes fast |

**Step 1. Open a terminal**
- Mac: press `Cmd + Space`, type **Terminal**, press Enter.
- Windows: click Start, type **PowerShell**, press Enter.
- Or stay in Claude Code: type `!` followed by the command (for example `! reach login reddit`).

**Step 2. Copy the line for the site you want, paste it, press Enter**

| Site | Command |
|---|---|
| Reddit | `reach login reddit` |
| X (Twitter) | `reach login x` |
| Instagram | `reach login instagram` |
| Facebook | `reach login facebook` |
| LinkedIn | `reach login linkedin` |
| TikTok | `reach login tiktok` |
| Threads | `reach login threads` |

**Step 3. Sign in, then close the window**

A Chrome window opens on that site's login page. Sign in with your separate account, then close the window. The login is saved, so you only do this once per site.

Prefer not to touch a terminal? Ask Claude: **"Log reach into Reddit"**. It opens the same window for you.

- The login lives in reach's own browser profile (`~/.reach/profile`). Your normal Chrome is never touched, and Claude never sees your password. Don't copy, sync or back up that folder (Drive, Dropbox, OneDrive): it holds live logins.
- To log out of a site, run `reach login <site>` and sign out in the window. To remove every login, delete `~/.reach/profile`.

## Try it

- "What do people on Reddit say about the Framework laptop after a year?"
- "Find popular TikToks about home espresso and tell me which hooks get the most views."
- "Get the transcript of this YouTube video and summarise it: <link>"
- "What is X saying about the new iPhone battery?"
- "Find recent PubMed studies on sleep and memory."

## Rules for using it

1. One reach call at a time. Never in parallel or in a loop.
2. Keep it small: about 10 calls per task.
3. If reach says cooling down, daily limit, bot check, rate limit, login wall or verify: stop using that site. Never reword and retry.
4. Use logged-in sites only when logged-out sources won't do.
5. Don't pass private, signed, token or share links. Ordinary pages go through Jina Reader, a third party.
6. Analyse what people say in aggregate. Don't build lists of usernames, contact commenters, or link people across sites. Quote a line or two with credit; don't republish long posts or transcripts.

## Responsible use

reach is an independent project. It is not affiliated with or endorsed by Reddit, X, Meta, LinkedIn, TikTok, Google, YouTube, DuckDuckGo or Jina, and their trademarks belong to them. It is meant for low-volume personal or internal research. You are responsible for how you use it and for following the terms of any site and account you use it with: automated access may breach those terms, including YouTube transcript downloads. Prefer official APIs where they exist. reach is provided as is under the MIT License, without warranty. This is not legal advice.

---

Everything below is for developers.

## Manual install

```sh
uv tool install git+https://github.com/Ahmadelmacho/reach@v0.2.1   # needs uv: https://docs.astral.sh/uv/
reach install-skill        # writes ~/.claude/skills/reach/SKILL.md
reach browse https://github.com/Ahmadelmacho/reach
```

Install only from this git URL. Never `pip install reach` or `reach-cli`: anything on PyPI under those names is not this project.

The optional `reach hook` command is a Claude Code PreToolUse hook: when Claude is about to use WebSearch, or WebFetch on a social site, it adds a one-line reminder to use reach. It never blocks anything. Works with other agents too (Codex, Cursor, Aider): anything that can run a shell command can call `reach` and read the JSON.

## Commands

| Need | Command |
|---|---|
| Any link (routes YouTube, Reddit, GitHub, login sites itself) | `reach read <url>` |
| Web search (DuckDuckGo) | `reach search "<q>" -n 10` |
| YouTube | `reach yt-search "<q>"` · `reach yt-info <url>` · `reach yt-transcript <url> --lang en` |
| GitHub | `reach gh-search "<q>"` · `reach gh-readme owner/name` · `reach gh-issue owner/name#123` |
| Reddit | `reach reddit-search "<q>" --sub name` (titles + counts, first page only) · `reach reddit-sub name --sort top` · `reach reddit-read <thread url>` |
| X | `reach x-search "<q>"` · `reach x-user <handle>` |
| Instagram | `reach ig-search "<q>"` · `reach ig-user <handle>` · `reach ig-comments <post url> -n 30` |
| TikTok | `reach tt-search "<q>"` · `reach tt-user <handle>` |
| PubMed | `reach pubmed "<q>" -n 10` |
| Facebook | `reach fb-search "<q>"` |
| LinkedIn jobs (public postings, never logged in) | `reach li-jobs "<q>" --location Berlin` · `reach li-job <jobs/view url>` |
| Rendered page | `reach browse <url>` |

Output is `{"ok": true, "untrusted_content": true, "result": ...}` or `{"ok": false, "untrusted_content": true, "error": ..., "hint": ...}`. Put `--max-chars N` before the command to cap long text (default 40000). Commands that don't open a browser (YouTube, GitHub, PubMed, LinkedIn jobs, most `read` calls) work without Chrome. Web search runs in the same cookie-free Chrome as `reach read`, because DuckDuckGo answers plain HTTP clients from some networks with a bot check.

Settings, all optional:
- `REACH_CHROME`: full path to Chrome or Chromium, if reach can't find it.
- `REACH_HOME`: where the login profile and pacing state live (default `~/.reach`).
- `GITHUB_TOKEN`: raises the GitHub API rate limit.
- `REACH_NO_JINA=1`: never send pages to Jina Reader; use the local browser instead.
- `REACH_NO_SANDBOX=1`: run Chrome without its sandbox (only for containers or root, where the sandbox can't start).

These are trusted settings: anyone who can set them can already run code as you.

## Built-in limits

reach fails fast instead of waiting, so the agent never hangs. State lives in `~/.reach/state.json`; delete it to reset.

| Site | Min gap between calls | Calls per day | Max results per call |
|---|---|---|---|
| Instagram, X, Threads | 30 s | 40 | 12 (IG posts), 30 (IG comments), 20 (X) |
| TikTok | 20 s | 40 | 15 |
| Facebook, LinkedIn (logged in) | 60 s | 15 | n/a |
| Reddit | 5 s | 150 | 25 (300 thread comments) |
| DuckDuckGo search | 5 s | 200 | 100 |
| LinkedIn public jobs | 10 s | 100 | 25 |

Gaps get up to 30% random extra, and waits inside a page vary. When a site pushes back, reach pauses it: 30 to 120 minutes after a rate limit, bot check or empty result, 1 hour after a login wall (cleared by `reach login <site>`), and 24 hours when a site asks the account to verify itself or says it's locked. Edit `LIMITS` in `reach.py` to change the numbers.

## Security

What reach does:
- **Read-only.** The code navigates and reads. It never clicks, types, posts, likes, follows or messages.
- **No cookie copying.** Your everyday browser profile is never read. You log the reach profile in yourself.
- **Sandboxed Chrome, no debug port.** Chrome runs with its sandbox on, and Playwright talks to it over a pipe, so nothing listens on `127.0.0.1:9222`.
- **The logged-in profile stays on its own site.** Only the sites in `SITES` get the logged-in profile. That tab can't navigate to any other domain, or to the account's private pages (messages, notifications, settings, saved). Every other URL opens in a throwaway, cookie-free browser with service workers and websockets off.
- **No private targets.** `file://`, `localhost`, LAN addresses, cloud metadata IPs and URLs with embedded credentials are refused, on every browser request including redirects. For pages read in the throwaway browser, reach also checks the IP Chrome actually connected to, and refuses anything not public.
- **YouTube commands only touch YouTube.** Video and caption URLs are limited to YouTube hosts.
- **Output is marked untrusted.** Results and errors carry `"untrusted_content": true`, invisible Unicode tricks are stripped, and the skill tells Claude that fetched text is data, never instructions.
- **Pinned dependencies, tagged releases.** `requests`, `yt-dlp` and `playwright` at exact versions; install a tag, not `main`.

What you accept by using it:
- **The agent can read most of what your logged-in accounts can see.** reach blocks inboxes and settings pages, but feeds and profiles are readable. Use accounts that hold nothing private.
- **It is detectable.** reach hides the automation flag (`navigator.webdriver`) and uses a user agent that matches your Chrome, like a normal browser window. Sites can still tell, and may restrict or ban accounts, especially at volume. reach never solves captchas or gets past logins.
- **Every URL the agent reads is a request it sends.** A prompt-injected agent could hide data in a URL. reach can't prevent that, so keep secrets out of the agent's context.
- **Third parties see some URLs.** `reach read` sends ordinary pages without a query string through Jina Reader (`r.jina.ai`), and `reach search` goes to DuckDuckGo.

Found a security problem? Report it privately from the repo's **Security** tab ("Report a vulnerability"), not in a public issue.

## Troubleshooting

- **"pacing: wait Ns"**: normal. Wait that long, then try once.
- **"cooling down" / "daily limit"**: the site pushed back or you hit the day's cap. Use other sources until then.
- **"bot check"**: the site showed a captcha. Open the page in your own browser.
- **"needs a login"**: run `reach login <site>` and sign in.
- **"could not start the reach browser"**: another reach call or a `reach login` window is using the profile, or Chrome isn't installed (set `REACH_CHROME`).
- **YouTube "refused the captions"**: YouTube rate-limits caption downloads. Try again later.
- **A site suddenly returns nothing**: sites change their pages, and YouTube changes often break yt-dlp. Install the newest tag.

## Update and develop

To update, run the install command again with the newest tag from the Releases page, plus `--force`, then `reach install-skill`.

```sh
git clone https://github.com/Ahmadelmacho/reach && cd reach
uv tool install -e .            # edits to reach.py apply immediately
uv run python test_reach.py     # offline self-check, prints "ok"
```

The skill text lives in `SKILL_MD` in `reach.py`; `skill/SKILL.md` is a copy the self-check keeps identical. Dependency versions are pinned in `pyproject.toml` and bumped on purpose. To add a login site, add it to `SITES` and `LIMITS` in `reach.py`.

## Credits

Inspired by [Panniantong/agent-reach](https://github.com/Panniantong/agent-reach). reach is a separate, smaller rewrite: no cookie copying from your main browser, no open debugging port, no unpinned installs.

## License

MIT. See `LICENSE`.
