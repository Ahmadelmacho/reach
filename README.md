# reach

**Give Claude Code (or any coding agent) read-only access to the places its built-in web search can't see:** Reddit threads, X posts, Instagram, TikTok, YouTube transcripts, GitHub issues, PubMed, LinkedIn jobs, and pages that block bots or need JavaScript.

One CLI. Every command prints one JSON object. It reads and never posts.

## Use it with Claude Code

Out of the box, Claude answers "what do people think of X?" with its own WebSearch tool. That returns articles and SEO pages, and almost never the Reddit threads, comments and videos where people actually talk. reach gives Claude those sources, plus a rule telling it when to use them.

### 1. Install the CLI

You need [uv](https://docs.astral.sh/uv/) (it brings its own Python). For the Reddit, X, Instagram, TikTok and Facebook commands you also need Google Chrome (or Chromium on Linux).

First install uv (skip this if `uv --version` already works):

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

**Close the terminal and open a new one** so it can find `uv`. Then install reach:

```sh
uv tool install git+https://github.com/Ahmadelmacho/reach
```

Open one more new terminal and check it works: `reach search "hello world" -n 1`. If the shell says `reach` isn't found, run `uv tool update-shell` and open a new terminal again.

### 2. Teach Claude to use it (one paste)

Open Claude Code and paste this:

```text
Set up the reach CLI for Claude Code (it is already installed; https://github.com/Ahmadelmacho/reach).
1. Download https://raw.githubusercontent.com/Ahmadelmacho/reach/main/skill/SKILL.md
   to ~/.claude/skills/reach/SKILL.md. Show me the file before saving it.
2. Add this section to my user-level ~/.claude/CLAUDE.md (create the file if missing):

   # People & social research: use reach first
   For any question about what people say (experiences, reviews, complaints, recommendations,
   "has anyone...", sentiment) and any Reddit, X, YouTube, TikTok, Instagram, GitHub or PubMed lookup:
   load the `reach` skill and use the `reach` CLI before WebSearch, one call at a time.
   WebSearch is for official or factual pages. For Reddit, X, YouTube, TikTok, Instagram,
   LinkedIn or Facebook links, use `reach read <url>` instead of WebFetch.

3. Optional reminder hook: in ~/.claude/settings.json add this PreToolUse hook, merged with any
   hooks I already have (don't overwrite them):
   {"matcher": "WebSearch|WebFetch",
    "hooks": [{"type": "command", "command": "reach hook", "timeout": 5, "onFailure": "continue"}]}
Then run `reach search "test" -n 1` to confirm it works.
```

Claude asks before each step. The first time it runs a `reach` command, pick "Yes, and don't ask again" so later research doesn't stop for permission prompts. Restart Claude Code afterwards so it loads the skill and the hook.

What each piece does:
- **The skill** (`skill/SKILL.md`) lists every command and the safety rules. Claude reads it when a task needs reach.
- **The CLAUDE.md rule** makes reach the default for people-research, so Claude stops going to WebSearch first.
- **The hook** (`reach hook`) adds a one-line reminder to Claude's context whenever it is about to use WebSearch, or WebFetch on a social site. It never blocks anything and stays silent for other tools. Skip it if the CLAUDE.md rule is enough for you.

### 3. Ask normally

- "What do people on Reddit say about the Framework 13 laptop after a year of use?"
- "Find TikToks about home espresso setups and tell me which hooks get the most views."
- "Get the transcript of this YouTube video and summarise the main points: <link>"
- "What are the open complaints in the issues of github.com/owner/repo?"
- "Find recent studies on intermittent fasting and sleep on PubMed."
- "What is X saying about the new iPhone battery?"

### 4. Log in (only for the sites you need)

YouTube, TikTok, GitHub, PubMed, LinkedIn jobs and web search need no login. Reddit, X, Instagram and Facebook work best (or only) logged in:

```sh
reach login reddit     # also: x, instagram, facebook, linkedin, tiktok, threads
```

A normal Chrome window opens on a separate reach profile (`~/.reach/profile`). Sign in and close the window. Your everyday Chrome is never touched. **Use a secondary account**, never your personal or a work account (see Security).

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

Works with other agents too (Codex, Cursor, Aider): anything that can run a shell command can call `reach` and read the JSON.

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
