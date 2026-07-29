# health-report-agent

**Turn scattered medical reports — physicals, lab results, imaging — into one
self-contained HTML health dashboard you can double-click open.**

This is not another web template. You hand this directory to an agent (Claude Code,
Codex, …) and it **walks you through getting your records**, reads them, and builds the
page. Everything runs locally. Nothing is uploaded.

> 中文说明见 [README.md](README.md)（本项目的取数指南主要面向中国大陆的医院系统，中文文档更完整）。

**▶ Live demo: [see it in your browser](https://ghbhiee.github.io/health-report-agent/)** — all data is fabricated.

**▶ 30-second intro: [play it in your browser](https://ghbhiee.github.io/health-report-agent/#video)** (Chinese narration)

[![Intro video](media/intro-poster.jpg)](https://ghbhiee.github.io/health-report-agent/#video)

<sub>(GitHub's raw URLs download rather than play, so the video is served from GitHub Pages.)</sub>

---

## Why this exists: not just for you — **to hand to your doctor**

Keeping your own archive is only half of it. The real pain is in the exam room.

Your doctor asks "what was this value before?" — and you start scrolling through photos
on your phone, or pull a stack of paper out of your bag and read them out one by one.
**Most of a short appointment gets spent finding the data.** And what the doctor usually
wants isn't a single number, it's the **trend**: has this always been high, or is it
recent? When was it last checked? What was the reference range back then?

That is the scenario this dashboard is built for:

- **The trend on one screen** — a multi-year line per analyte with its reference band, so
  out-of-range visits are obvious at a glance
- **One click to the original** — when the doctor wants to check the source, the report
  PDF is embedded in the very same file
- **It travels with you** — a single HTML file: phone, tablet, USB stick, or emailed to
  yourself. **No network, nothing to install** — it works in an exam room with no signal
- **Switching hospitals or doctors costs you nothing** — the record is yours, not locked
  inside one hospital's portal

It also quietly solves a structural problem: **hospital systems don't talk to each other.**
An exam done at hospital A is invisible to a doctor at hospital B. This file is your own
complete, cross-hospital record.

> ⚠️ It **does not diagnose** and does not interpret anything for you. It reorganizes
> reports you already have, so your doctor can spend the appointment judging rather than
> hunting. Every conclusion remains your doctor's to make.


## What you get

One HTML file, five views:

- **Overview** — indicators worth watching, nodule-grading follow-up (TI-RADS / Lung-RADS
  / BI-RADS …), health storylines, and a timeline of every exam
- **Lab trends** — a trend chart per analyte with its reference band; filter to
  out-of-range items only, or search
- **Report library** — filter by type / year / status; open a drawer for the conclusion,
  the out-of-range items, and **the original PDF embedded inline**
- **Image gallery** — ultrasound / endoscopy frames pulled out of the report PDFs, with a
  lightbox
- **Compare** — pick two check-up batches and see which measurements moved most

The page has **no external links and no fetch calls** — every PDF and image is inlined.
It opens offline, from a USB stick, or after you email it to family.

## Three steps

```bash
# 1. Get the code and install deps (pure Python, no OCR engine)
git clone https://github.com/ghbhiee/health-report-agent.git
cd health-report-agent && pip install -r requirements.txt

# 2. Open this directory with your agent tool
claude          # or codex, or anything that reads AGENTS.md

# 3. Tell it: "build me a health dashboard from my medical reports"
```

It will ask where your reports are. Already have PDFs? Drop them in
`workspace/inbox/`. On a hospital portal? It guides you through a browser-extension
capture. Only inside a WeChat/Alipay mini-program? It shows you how to open the
mini-program in desktop WeChat and move the report link into Chrome.

First-timers: run **`/onboarding`** — it walks you from "see the demo" to "here's your
dashboard", one step at a time.

## Common commands

Slash commands in Claude Code; with other tools just say the plain-English version.

| Command | Or just say | What it does |
|---|---|---|
| `/onboarding` | "walk me through it, I'm new" | Demo → your own dashboard, one step at a time |
| `/collect` | "help me gather my reports" | Works out where your data is and guides you to `workspace/inbox/` |
| `/extract` | "read these reports into data" | Probe + three-tier extraction, checked against the 9 known data traps |
| `/build` | "build my health dashboard" | Writes the build scripts, produces the single HTML file |
| `/verify` | "check it for problems" | Contract compliance, zero external refs, and cross-checks derived flags against the ↑↓ printed on the reports |

Bare commands, no agent required:

```bash
python3 demo/make_demo.py && python3 -m webbrowser -t demo/index.html   # see the demo, learn the data contract
python3 tools/probe.py workspace/inbox              # what is each file; text layer? images?
python3 tools/extract.py text  <file.pdf>           # text layer: take it directly
python3 tools/extract.py pages <file.pdf>           # no text layer: render to PNG for the agent to read
python3 tools/verify.py data.json assets.json out.html
python3 tools/scan_privacy.py                       # make sure nothing private slipped into git
```

## Getting your reports

Three routes; the agent asks which one fits. In mainland China the middle one is the common case:

1. **You already have PDFs / photos** — drop them into `workspace/inbox/`.
2. **Reports live in a hospital WeChat mini-program** — a mini-program is essentially a
   skinned browser and the report is just a web page; it only solves login. So open desktop
   WeChat, find the hospital's mini-program or official account, open the report page, use
   「复制链接」 / 「在浏览器中打开」, paste it into Chrome, then let a browser extension
   (Claude in Chrome, the Codex extension, or Chrome's built-in AI sidebar) do a bulk capture.
   The ready-to-paste capture prompt is in the Chinese README and in
   [`docs/10-acquire-browser.md`](docs/10-acquire-browser.md).
3. **You can log into the hospital portal on a computer** — same extension + prompt.

If the link won't travel, fall back to long screenshots on the phone; the agent reads images.

> **Red line**: the agent never types your username, password or SMS code. You log in; it
> only navigates and downloads on a session you already opened.

Want to see the data contract without reading docs? Run the synthetic demo:

```bash
python3 demo/make_demo.py && python3 -m webbrowser -t demo/index.html
```

## Privacy

This is **personal health data**, so the whole project is designed so the data never
leaves your machine:

- Your source files and outputs live in `workspace/`, which is **gitignored** — they
  cannot be committed by accident.
- The generated HTML has **zero external references and zero fetch calls**; it never
  phones home. `tools/verify.py` re-checks this on every build.
- **The repository contains no real medical records.** Everything in `demo/` — names,
  dates, lab values, images — is synthetic, and every demo image carries a
  "DEMO · synthetic sample · not a real medical image" watermark.
- The agent is explicitly forbidden from: entering your passwords or SMS codes,
  uploading your data anywhere, or making medical judgements. See the red lines in
  [`AGENTS.md`](AGENTS.md).

## What it does not do

**It does not diagnose.** The page only reorganizes reports you already have —
conclusions, gradings and follow-up advice are quoted verbatim from your reports.
Interpretation belongs to your doctor. Keep the disclaimer in the page footer.

## Requirements

| | |
|---|---|
| Python | 3.9+ |
| Dependencies | `pymupdf` `pillow` `numpy` `openpyxl` — pure Python, one `pip install` |
| Platform | macOS / Linux / Windows |
| OCR engine | **Not needed.** Text-layer PDFs are read directly; images are read by the agent itself (it is already a multimodal model) |
| Agent tools | Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`, others: just `@AGENTS.md` |

## Output size

Original PDFs are embedded, so the file grows with the number of reports — roughly
**10–35 MB** for 20–50 real reports. To shrink it, skip the `pdf*` assets in
`build_assets.py` and keep only the page renders (about 1/5 the size); the trade-off is
that the drawer can show rendered pages but no longer offer the original PDF download.

## Docs

| | |
|---|---|
| [`AGENTS.md`](AGENTS.md) | **Main entry point for the agent** — the whole flow on one page |
| [`docs/00-overview.md`](docs/00-overview.md) | Mental model and overall flow |
| [`docs/10-acquire-browser.md`](docs/10-acquire-browser.md) | Bulk download from a portal with a browser extension |
| [`docs/11-acquire-mobile.md`](docs/11-acquire-mobile.md) | Getting reports out of WeChat/Alipay mini-programs |
| [`docs/12-acquire-manual.md`](docs/12-acquire-manual.md) | Handing over existing PDFs / photos / screen recordings |
| [`docs/20-extract.md`](docs/20-extract.md) | The three-tier extraction strategy + 9 recurring data traps |
| [`docs/30-build-verify.md`](docs/30-build-verify.md) | Build and browser acceptance checklist |
| [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md) | Exact field definitions for the three JSON files |

> Detailed guides are in Chinese: they target Chinese hospital portals and
> mini-programs, where the concrete steps matter. The code, the data contract and this
> README are in English.

## Author

Guo Hongbo · <guohongbo@outlook.com>

## License

MIT — see [`LICENSE`](LICENSE).
