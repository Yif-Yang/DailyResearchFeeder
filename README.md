# Daily Research Feeder

Daily Research Feeder is an LLM-assisted pipeline for turning papers and AI ecosystem updates into a daily digest you can actually read.

It collects papers from arXiv and Hugging Face Daily Papers, combines them with curated company blogs and industry-news feeds, ranks the candidates, asks an LLM to review them, and renders a structured email-ready report.

This repository is meant to be public-safe and reusable:

- no personal email addresses, API keys, or machine-specific paths are committed
- local secrets live in `.env`
- local runtime state lives in `state/`, `runtime/`, and `artifacts/`
- personal settings live in an untracked `config.yaml`, copied from `config.example.yaml`

## Why This Repo Exists

Most paper digests fail in one of two ways:

- they are just keyword filters, so they miss important adjacent work
- they are too broad, so they become unreadable and repetitive

Daily Research Feeder takes a different approach:

- use keywords and source priors only for soft prioritization, not hard gating
- let an LLM do final relevance judgment, summarization, and ranking
- treat papers and news as two distinct channels in one digest
- preserve both keyword-relevant updates and high-signal industry launches or leaks
- support a staged morning workflow instead of a single blind cron run

## What It Does

- Collects papers from arXiv and Hugging Face Daily Papers
- Collects AI news from company blogs, tooling blogs, research blogs, and industry-news feeds
- Filters papers to the exact target local day, so a daily run only sends that day's papers
- Uses an LLM to score, summarize, and rank candidates
- Produces a digest with separate paper and news sections
- Supports one-shot runs, backfills, dry runs, and a long-running scheduled daemon
- Tracks seen items to suppress short-term duplicates

## High-Level Workflow

```text
Sources -> Dedup -> Seen Filter -> Soft Prioritization -> LLM Review -> Paper / News Selection -> HTML Digest -> Preview or Email
```

For the staged day scheduler, the flow is intentionally more operational:

```text
08:00 start prep -> fetch news early -> poll paper freshness -> review candidates -> send final digest when ready
```

## Default Focus Profile

The sample profile is intentionally opinionated toward:

- agent systems
- evaluation harnesses
- RL environments and tool-use training
- infrastructure for long-horizon or multi-turn agents
- workplace creation agents such as slide, presentation, or design copilots

You can replace the defaults in [user/keywords.txt](user/keywords.txt), [user/research_interests.txt](user/research_interests.txt), [user/arxiv_categories.txt](user/arxiv_categories.txt), and [user/feeds.yaml](user/feeds.yaml) with your own profile.

## Quick Start

1. Create your local config and env files.

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

2. Create a Python environment and install dependencies.

```bash
bash scripts/bootstrap.sh
```

3. Edit your local settings.

- local `config.yaml`, copied from [config.example.yaml](config.example.yaml)
- local `.env`, copied from [.env.example](.env.example)
- [user/keywords.txt](user/keywords.txt)
- [user/research_interests.txt](user/research_interests.txt)
- [user/arxiv_categories.txt](user/arxiv_categories.txt)
- [user/feeds.yaml](user/feeds.yaml)

4. Run a dry run.

```bash
python main.py --config config.yaml --dry-run
```

The preview HTML is written to `artifacts/report_preview.html`.

## Recommended Local Setup

The simplest working setup is:

- `copilot_cli` for LLM calls
- `gmail_smtp` for delivery

Minimal `.env` example:

```bash
LLM_PROVIDER=copilot_cli
COPILOT_COMMAND=copilot

EMAIL_PROVIDER=gmail_smtp
EMAIL_TO=your-email@example.com
GMAIL_SMTP_USERNAME=your-account@gmail.com
GMAIL_SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=Daily Research Feeder <your-account@gmail.com>
```

Optional Azure OpenAI setup:

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_API_KEY=...
```

Optional OpenAI setup:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

## Running Modes

One-shot dry run:

```bash
python main.py --config config.yaml --dry-run
```

One-shot real send:

```bash
python main.py --config config.yaml
```

Backfill a specific local date:

```bash
python main.py --config config.yaml --backfill-date 2026-04-14 --dry-run
```

Run the staged scheduler logic directly:

```bash
python main.py --config config.yaml --mode scheduled_day --dry-run
```

## Local Daemon

Start the background daemon:

```bash
bash scripts/start_daily_digest_daemon.sh
```

Stop it:

```bash
bash scripts/stop_daily_digest_daemon.sh
```

Run one immediate execution using the same shell defaults:

```bash
bash scripts/run_daily_digest_now.sh
```

Dry run without sending:

```bash
DAILY_FEEDER_DRY_RUN=1 bash scripts/run_daily_digest_now.sh
```

The daemon:

- uses your local config and `.env`
- respects shell overrides such as `DAILY_FEEDER_MODE`, `DAILY_FEEDER_EMAIL_PROVIDER`, and `PYTHON_BIN`
- starts staged preparation at the configured hour
- checks paper freshness before final send
- writes operational logs to `runtime/daily_digest_daemon.log` and `runtime/daily_digest_runs.log`

## Scheduling Behavior

The `scheduled_day` mode is designed for daily operations rather than raw cron simplicity.

Typical behavior:

- begin early with news collection
- wait for paper sources to refresh
- review papers and news separately
- send a formal digest once the target-day paper set is ready

Paper handling is intentionally strict:

- regular daily paper selection only includes papers whose local publication date matches the target day
- paper freshness is date-based, not just unseen-item based
- arXiv fetching paginates until the cutoff so the current-day sweep is not limited to one page

News handling is intentionally balanced:

- at least one explicit keyword-related news item is preserved when available
- at least one hot industry or company item is preserved when available
- the rest of the news section is filled by overall score

## Default Source Coverage

The tracked feed set in [user/feeds.yaml](user/feeds.yaml) includes:

- company blogs such as OpenAI, Google DeepMind, Google AI, Hugging Face, Together AI, and NVIDIA
- research blogs such as BAIR, Lil'Log, MIT News AI, and Microsoft Blog AI
- tooling blogs such as AWS ML Blog and LangChain Blog
- industry-news feeds such as TechCrunch AI, The Decoder, Latent Space, VentureBeat AI, The Verge AI, ZDNet AI, AI Business, AI News, and SiliconANGLE AI

## Configuration Surface

The tracked template at [config.example.yaml](config.example.yaml) controls:

- timezone and language
- input file locations for keywords, feeds, and categories
- LLM defaults and fast-mode thresholds
- pipeline limits such as max papers, max news, and score thresholds
- source toggles and feed depth
- artifact output locations
- local scheduling windows

Put user-specific identifiers and secrets in `.env`, not in tracked YAML.

## GitHub Actions

The repository includes [daily-digest.yml](.github/workflows/daily-digest.yml) for scheduled or manual runs.

The workflow uses `config.example.yaml` plus GitHub Secrets and Variables, which means you do not need to commit a real `config.yaml` to use the hosted path.

Typical GitHub Secrets / Variables:

- provider secrets such as `OPENAI_API_KEY` or `RESEND_API_KEY`
- `EMAIL_TO`
- `EMAIL_FROM`
- optional model or reasoning variables

## Repository Layout

```text
DailyResearchFeeder/
├── .github/workflows/
├── dailyresearchfeeder/
│   ├── sources/
│   ├── config.py
│   ├── emailer.py
│   ├── llm.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── pipeline.py
│   ├── renderer.py
│   └── state.py
├── scripts/
├── tests/
├── user/
├── config.example.yaml
├── .env.example
├── main.py
└── requirements.txt
```

## Testing

Run the focused local suite with:

```bash
pytest --rootdir=. tests/test_pipeline.py tests/test_orchestrator.py tests/test_config.py
```

These tests cover ranking, configuration loading, and orchestration logic. They do not call live LLMs or send real email.

## Security And Privacy

- Do not commit `.env`, `config.yaml`, `artifacts/`, `runtime/`, or `state/*.json`
- Keep API keys, recipient addresses, and app passwords in local environment variables or GitHub Secrets
- Review workflow secrets before enabling GitHub Actions in a public fork
- Treat feed URLs as code: if a source is stale or noisy, replace it in [user/feeds.yaml](user/feeds.yaml)