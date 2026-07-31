# Job Applier Agent (from scratch)

A provider-agnostic **AI job-application system**: it discovers the freshest
matching roles every day (curated GitHub feeds + the free public JSON APIs of
Greenhouse/Lever/Ashby/SmartRecruiters/Workable), tailors your closest-matching
master resume per job (Summary, Technical Skills, top-2 bullets  nothing else),
scores every application with a composite **Application Quality Score**, renders a
dashboard, and can fill + submit applications (Greenhouse deterministically; other
portals via a Playwright browser agent with human confirmation).

LLM judgment is isolated behind a single **Brain** seam, so the whole pipeline runs
either on the Anthropic/OpenAI APIs (`--brain api`) or with **no API key at all**
(`--brain manual`  prompt packets on disk that any LLM, including Claude Code
driving this repo, can answer).

> ⚠️ **Read the [Responsible use](#responsible-use) section first.** Auto-submitting
> applications and automating LinkedIn can violate site Terms of Service and get
> accounts restricted. This repo defaults to **human-in-the-loop** (it pauses for
> your confirmation before any irreversible action).

---

## How it works (architecture)

```


                ┌─────────────────────────────────────────────┐
   you ───────▶ │  cli.py   "apply <url>"                      │
                └───────────────┬─────────────────────────────┘
                                │
                                ▼
                ┌─────────────────────────────────────────────┐
                │  agent.py   the agent loop                  │
                │  • calls Claude (Opus 4.8) with a tool set   │
                │  • Claude decides which tool to call next    │
                │  • we execute the tool, feed the result back │
                │  • repeat until Claude says it's done        │
                └───────┬───────────────┬───────────────┬──────┘
                        │               │               │
            ┌───────────▼──┐  ┌─────────▼────────┐  ┌───▼──────────┐
            │ tools/       │  │ tools/ats.py     │  │ tools/       │
            │ browser.py   │  │ keyword scoring  │  │ tracker.py   │
            │ (Playwright) │  │                  │  │ applications │
            └──────────────┘  └──────────────────┘  └──────────────┘
```

The **agent loop** is the heart of it. Claude is given a set of *tools* (functions
it can ask to run). On each turn Claude either replies with text or asks to call a
tool; we run the tool, return the result, and loop. This is the standard Anthropic
"manual agentic loop"  see `src/agent.py`. Nothing is hidden in a framework.

### The tools Claude can call

| Tool | File | What it does |
|---|---|---|
| `open_page` / `read_page` | `browser.py` | Navigate, then read the page as an accessibility snapshot (cheaper + more reliable than screenshots) |
| `click` / `type_text` / `fill_form` | `browser.py` | Interact with the live page |
| `upload_file` | `browser.py` | Attach your resume PDF to a file input |
| `screenshot` | `browser.py` | Capture proof of submission |
| `ats_score` | `ats.py` | Keyword-match the JD against your resume, 0–100 |
| `read_profile` | `tracker.py` | Load your `config/profile.json` |
| `save_application` | `tracker.py` | Append the outcome to `data/applications.json` |
| `ask_human` | `agent.py` | **Pause and ask you** before submitting / sending anything |

You add new capabilities by writing a Python function and registering it in
`TOOLS`  that's the "build your own tools/agents" part.

---

## Setup

### Fastest path  one command (any machine, nothing pre-installed)

```bash
cd job-applier-agent
./setup.sh            # macOS / Linux / WSL   (Windows: ./setup.ps1 in PowerShell)
```

`setup.sh` is idempotent and does everything: checks Python, creates the `.venv`,
installs dependencies, downloads the Chromium browser, and seeds `.env`,
`config/profile.json`, and `resume/master_resume.md` from the examples. The only
prerequisite is **Python 3.11+** (the script tells you how to install it if missing).

Then:
1. Put your key in `.env` → `ANTHROPIC_API_KEY=sk-ant-...` (get one at https://console.anthropic.com)
2. Edit `config/profile.json` and replace `resume/master_resume.md` with your resume (Markdown).
3. `source .venv/bin/activate` (re-run in each new terminal).

### Manual install (if you prefer)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium                          # downloads the browser
cp .env.example .env                                 # add ANTHROPIC_API_KEY
cp config/profile.example.json config/profile.json   # fill in your details
cp resume/master_resume.example.md resume/master_resume.md   # then edit with your resume
```

### Using PyCharm
PyCharm can do the venv + deps for you: open the folder → it detects `requirements.txt`
and offers to create a virtualenv and install them. After that, run once in the built-in
terminal: `python -m playwright install chromium`. Set `ANTHROPIC_API_KEY` in
Run → Edit Configurations → Environment variables (or use the `.env`). Or just run
`./setup.sh` from PyCharm's terminal  same result.

### 4. Run
```bash
# Daily driver: discover top fresh roles (24h) -> tailor + score top 10 -> dashboard:
python -m src.cli pipeline --hours 24 --top 10

# Same, with zero API usage (answer the data/brain/ packets with any LLM, re-run):
python -m src.cli pipeline --top 10 --brain manual

# Just the discovery shortlist (no LLM at all):
python -m src.cli discover --hours 24 --target 100

# Submit one role (agent fills the form, asks you before submitting):
python -m src.cli apply "<job-url>"
# Greenhouse-only deterministic fill (no key; you click submit):
python -m src.cli fill "<job-url>"

# Inspect:
python -m src.cli status --verbose
open data/dashboard.html
```

See **RUNBOOK.md** for the full daily flow and **CLAUDE.md** for the architecture.

---

## Extending it

### Add a LinkedIn integration
The simplest path is an **MCP server**. Two popular ones:
- `stickerdaniel/linkedin-mcp-server`  profiles, companies, **jobs**, messages
- `Linked-API/linkedapi-mcp`  control a LinkedIn account + real-time data

You can wire an MCP server into this agent with the Anthropic SDK's MCP helpers
(`pip install "anthropic[mcp]"`)  see the commented `# MCP` block in `src/agent.py`.

### Swap the browser layer for Playwright MCP
Instead of driving Playwright in-process (`tools/browser.py`), you can run
Microsoft's [`@playwright/mcp`](https://github.com/microsoft/playwright-mcp) as an
MCP server and let Claude call its `browser_*` tools. Same agent loop, the tools
just come from MCP instead of local functions.

### Make the LLM provider swappable
`agent.py` isolates every Claude call in one place. To support OpenAI/Gemini/local
models, put an interface in front of `client.messages.create(...)`. (Kept as a
single provider here for clarity  this repo targets Claude.)

---

## Responsible use

This tool can submit real applications and act on real accounts. Before you point
it at anything:

1. **LinkedIn, Indeed, Workday, etc. prohibit most automation** in their ToS.
   Automating them risks account suspension. Prefer official APIs / job boards
   that allow it, or keep yourself in the loop on every action.
2. **Never fabricate.** The prompts instruct Claude to only re-order and emphasize
   real resume content  never invent skills, employers, or metrics. Keep it that way.
3. **Human-in-the-loop is the default.** The `ask_human` tool fires before any
   submit / send / connect. Don't remove it for unattended runs unless you fully
   own the consequences.
4. **No credential storage.** Use a persistent browser profile you log into
   yourself (`--user-data-dir`); the agent never handles your passwords.
5. **Rate-limit yourself.** Bulk applying looks like spam to both ATS systems and
   recruiters, and degrades your own signal.

You are responsible for how you use this.

## License
MIT  do what you like, no warranty.
