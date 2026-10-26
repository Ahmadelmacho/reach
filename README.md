# reach

**Let Claude read Reddit, X, Instagram, TikTok and YouTube for you.**

Ask Claude "what do people think of X?" and it normally searches Google-style results: articles and ads. With reach it reads the actual Reddit threads, posts, comments and video transcripts where people talk.

## Get it

Copy this into Claude Code (terminal, desktop app or VS Code) and send it:

```text
Install reach for me from https://github.com/Ahmadelmacho/reach and set it up so you use it:
1. If the `uv` command is missing, install it with uv's official installer for my system.
2. Run: uv tool install git+https://github.com/Ahmadelmacho/reach
   If `reach` isn't found afterwards, use the full path (~/.local/bin/reach) and run `uv tool update-shell`.
3. Save https://raw.githubusercontent.com/Ahmadelmacho/reach/main/skill/SKILL.md
   as ~/.claude/skills/reach/SKILL.md
4. Add this to ~/.claude/CLAUDE.md (create it if missing):
   # Use reach for people research
   For questions about what people say (reviews, experiences, complaints, recommendations, trends)
   and for Reddit, X, YouTube, TikTok, Instagram, GitHub or PubMed: use the `reach` skill before
   WebSearch, one call at a time. For links on those sites, use `reach read <url>` instead of WebFetch.
5. Add this PreToolUse hook to ~/.claude/settings.json, keeping any hooks I already have:
   {"matcher": "WebSearch|WebFetch",
    "hooks": [{"type": "command", "command": "reach hook", "timeout": 5, "onFailure": "continue"}]}
6. Test it with: reach search "test" -n 1
Then tell me in one line what you did, and to restart Claude Code.
```

Click "Yes" when Claude asks to run things. Restart Claude Code when it's done. That's it.

You need Google Chrome installed for Reddit, X, Instagram, TikTok and Facebook.

## How it works

- **reach** is a small program on your computer. It opens pages in a hidden Chrome window and hands Claude the text.
- **The skill** teaches Claude the commands. **The rule** tells Claude to use reach for "what are people saying" questions instead of normal web search.
- It only reads. It never posts, likes, follows or messages anyone.

## Log in (optional, recommended)

Reddit, X, Instagram and Facebook show little or nothing to logged-out visitors. Logging in once lets reach see full threads, comments and search results.

Ask Claude: **"Log reach into Reddit"** (or X, Instagram, Facebook). A Chrome window opens. Sign in, close the window. Done. The login stays saved for next time.

- **Use a spare account**, never your personal or work one. Automated reading breaks these sites' rules, so the account could get banned.
- The login lives in reach's own browser profile. Your normal Chrome is never touched, and Claude never sees your password.

YouTube, TikTok, GitHub and PubMed need no login.

## Try it

- "What do people on Reddit say about the Framework laptop after a year?"
- "Find popular TikToks about home espresso and tell me which hooks get the most views."
- "Get the transcript of this YouTube video and summarise it: <link>"
- "What is X saying about the new iPhone battery?"
- "Find recent PubMed studies on sleep and memory."

---

Everything below is for developers.

## Manual install

```sh
uv tool install git+https://github.com/Ahmadelmacho/reach   # needs uv: https://docs.astral.sh/uv/
reach search "hello world" -n 1
reach login reddit     # also: x, instagram, facebook, linkedin, tiktok, threads
```

Then copy `skill/SKILL.md` to `~/.claude/skills/reach/SKILL.md`. The optional `reach hook` command is a Claude Code PreToolUse hook: when Claude is about to use WebSearch, or WebFetch on a social site, it adds a one-line reminder to use reach. It never blocks anything. Works with other agents too (Codex, Cursor, Aider): anything that can run a shell command can call `reach` and read the JSON.

## Commands

| Need | Command |
|---|---|
| Any link (routes YouTube, Reddit, GitHub, login sites itself) | `reach read <url>` |
| Web search (DuckDuckGo) | `reach search "<q>" -n 10` |
| YouTube | `reach yt-search "<q>"` · `reach yt-info <url>` · `reach yt-transcript <url> --lang en` |
| GitHub | `reach gh-search "<q>"` · `reach gh-readme owner/name` · `reach gh-issue owner/name#123` |
| Reddit | `reach reddit-search "<q>" --sub name` · `reach reddit-sub name --sort top` · `reach reddit-read <thread url>` |
| X | `reach x-search "<q>"` · `reach x-user <handle>` |
| Instagram | `reach ig-search "<q>"` · `reach ig-user <handle>` · `reach ig-comments <post url> -n 200` |
| TikTok | `reach tt-search "<q>"` · `reach tt-user <handle>` |
| PubMed | `reach pubmed "<q>" -n 10` |
| Facebook | `reach fb-search "<q>"` |
| LinkedIn jobs | `reach li-jobs "<q>" --location Berlin` · `reach li-job <jobs/view url>` |
| Rendered page | `reach browse <url>` |

Output is `{"ok": true, "untrusted_content": true, "result": ...}` or `{"ok": false, "error": ..., "hint": ...}`. Put `--max-chars N` before the command to cap long text (default 40000). Commands that don't open a browser (search, YouTube, GitHub, PubMed, LinkedIn jobs, most `read` calls) work without Chrome.

Settings, all optional:
- `REACH_CHROME`: full path to Chrome or Chromium, if reach can't find it.
- `REACH_HOME`: where the login profile lives (default `~/.reach`).
- `GITHUB_TOKEN`: raises the GitHub API rate limit.


## Security

What reach does:
- **Read-only.** The code navigates and reads. It never clicks, types, posts, likes, follows or messages.
- **No cookie copying.** Your everyday browser profile is never read. You log the reach profile in yourself.
- **No open debug port.** Playwright talks to Chrome over a pipe. Nothing listens on `127.0.0.1:9222`, so other programs on your machine can't drive the logged-in browser.
- **The logged-in profile stays on its own site.** Only the sites in `SITES` (in `reach.py`) get the logged-in profile, and that tab can't navigate to any other domain. Every other URL opens in a throwaway, cookie-free browser.
- **No private targets.** `file://`, `localhost`, LAN addresses, cloud metadata IPs and URLs with embedded credentials are refused, on every browser request including redirects.
- **Output is marked untrusted.** Every result carries `"untrusted_content": true`, and the skill tells Claude that fetched text is data, never instructions.
- **Pinned dependencies.** `requests`, `yt-dlp` and `playwright` at exact versions. No install scripts, no auto-update, no browser extensions.

What you accept by using it:
- **The agent can read anything your logged-in accounts can see**, including feeds, DMs and notifications. That's why the accounts must be secondary.
- **Platform rules.** Automated access to Instagram, X, Facebook, LinkedIn and TikTok breaks their terms of service. Accounts can be rate-limited or banned. Keep the volume to what a person would read.
- **Every URL the agent reads is a request it sends.** A prompt-injected agent could hide data in a URL. reach can't prevent that, so keep secrets out of the agent's context.
- **Third parties see some URLs.** `reach read` sends ordinary pages through Jina Reader (`r.jina.ai`) first, and `reach search` goes to DuckDuckGo. Don't pass private links.
- **DNS rebinding** can get past the private-network check, because it checks hostnames, not the IP Chrome finally connects to.

Found a security problem? Report it privately from the repo's **Security** tab ("Report a vulnerability"), not in a public issue.

## Troubleshooting

- **"bot check"**: the site showed a captcha. Open the page in your own browser instead; retrying won't help.
- **"needs a login"**: run `reach login <site>` and sign in.
- **"could not start the reach browser"**: close any open `reach login` window (only one process can use the profile at a time), and make sure Chrome is installed or `REACH_CHROME` is set.
- **YouTube "refused the captions" / 429**: YouTube rate-limits caption downloads. Wait a few minutes and retry.
- **A site suddenly returns nothing**: sites change their pages, and YouTube changes often break yt-dlp. Get the latest reach (which pins newer versions): `uv tool upgrade reach-cli`.

## Update and develop

```sh
uv tool upgrade reach-cli       # pulls the latest commit from GitHub
```

```sh
git clone https://github.com/Ahmadelmacho/reach && cd reach
uv tool install -e .            # edits to reach.py apply immediately
uv run python test_reach.py     # offline self-check, prints "ok"
```

Dependency versions are pinned in `pyproject.toml` and bumped on purpose. To add a login site, add it to `SITES` in `reach.py`.

## Credits

Inspired by [Panniantong/agent-reach](https://github.com/Panniantong/agent-reach). reach is a separate, smaller rewrite: no cookie copying from your main browser, no open debugging port, no unpinned installs.

## License

MIT. See `LICENSE`.
