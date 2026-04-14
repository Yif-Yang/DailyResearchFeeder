# Daily Research Feeder

Daily Research Feeder is a configurable daily research and AI-news pipeline. It collects papers from arXiv and Hugging Face Daily Papers, combines them with curated company blogs and industry news feeds, ranks the candidates, asks an LLM to review them, and renders a digest you can preview locally or deliver by email.

The project is designed to be safe for public use:

- no personal email addresses, API keys, or machine-specific paths are tracked in the repository
- local secrets belong in `.env`
- local runtime state belongs in `state/`, `runtime/`, and `artifacts/`
- personal config belongs in an untracked `config.yaml` copied from `config.example.yaml`

## Features

- Daily paper collection from arXiv and Hugging Face Daily Papers
- Daily AI news collection from company blogs, tooling blogs, and industry-news RSS feeds
- Exact local-day filtering for papers, so daily sends only include papers published on the target day
- LLM-based ranking and digest writing with support for `copilot_cli`, `azure_openai`, and `openai`
- Separate paper and news sections in the final digest
- Local preview mode, direct send mode, and a staged `scheduled_day` daemon mode
- JSON state tracking to suppress short-term duplicates

## Default Focus

The sample user profile in [user/keywords.txt](user/keywords.txt) and [user/research_interests.txt](user/research_interests.txt) is intentionally opinionated toward agent systems, evaluation harnesses, RL environments, and workplace creation agents such as slide or design copilots. Replace those files with your own interests if your use case differs.

## Quick Start

1. Create a local config and env file.

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

2. Create a Python environment and install dependencies.

```bash
bash scripts/bootstrap.sh
```

3. Edit the following local files.

- your local `config.yaml`, copied from [config.example.yaml](config.example.yaml)
- [.env.example](.env.example)
- [user/keywords.txt](user/keywords.txt)
- [user/research_interests.txt](user/research_interests.txt)
- [user/arxiv_categories.txt](user/arxiv_categories.txt)
- [user/feeds.yaml](user/feeds.yaml)

4. Run a dry run.

```bash
python main.py --config config.yaml --dry-run
```

The HTML preview is written to `artifacts/report_preview.html`.

## Configuration Model

The repository ships with a tracked template at [config.example.yaml](config.example.yaml). Keep your real local config in an untracked `config.yaml`.

`config.example.yaml` controls:

- timezone and language
- user file paths
- LLM defaults
- pipeline limits such as max papers, max news, and score threshold
- source toggles and feed limits
- delivery artifact locations
- local scheduling windows

Secrets and user-specific identifiers should not go into tracked files. Put them in `.env` instead.

## Environment Variables

The easiest local setup is `copilot_cli + gmail_smtp`.

Minimal local `.env` for real email sending:

```bash
LLM_PROVIDER=copilot_cli
COPILOT_COMMAND=copilot

EMAIL_PROVIDER=gmail_smtp
EMAIL_TO=your-email@example.com
GMAIL_SMTP_USERNAME=your-account@gmail.com
GMAIL_SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=Daily Research Feeder <your-account@gmail.com>
```

Optional Azure OpenAI settings:

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_API_KEY=...
```

Optional OpenAI settings:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

Optional daemon overrides:

```bash
DAILY_FEEDER_MODE=scheduled_day
DAILY_FEEDER_PREP_START_HOUR=8
DAILY_FEEDER_DAYS=2
DAILY_FEEDER_DRY_RUN=0
```

## Running The Pipeline

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

Run the staged day orchestrator locally:

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

Run one immediate execution using the same script defaults:

```bash
bash scripts/run_daily_digest_now.sh
```

Dry run without sending:

```bash
DAILY_FEEDER_DRY_RUN=1 bash scripts/run_daily_digest_now.sh
```

The daemon:

- uses the local timezone from config and shell env
- starts staged preparation at the configured hour
- checks paper freshness through the morning schedule
- sends a formal digest when ready
- logs to `runtime/daily_digest_daemon.log` and `runtime/daily_digest_runs.log`

## GitHub Actions

The repository includes [daily-digest.yml](.github/workflows/daily-digest.yml) for scheduled runs. It uses `config.example.yaml` plus GitHub Secrets and Variables, so there is no need to commit a real `config.yaml`.

You will typically want to set:

- `OPENAI_API_KEY` or other provider secrets
- `RESEND_API_KEY` or your preferred mail-provider secrets
- `EMAIL_TO`
- `EMAIL_FROM`
- optional model/version vars

## Included Sources

The default feed set in [user/feeds.yaml](user/feeds.yaml) includes:

- company blogs such as OpenAI, Google DeepMind, Google AI, Hugging Face, Together AI, and NVIDIA
- research blogs such as BAIR, Lil'Log, MIT News AI, and Microsoft Blog AI
- tooling blogs such as AWS ML Blog and LangChain Blog
- industry-news feeds such as TechCrunch AI, The Decoder, Latent Space, VentureBeat AI, The Verge AI, ZDNet AI, AI Business, AI News, and SiliconANGLE AI

The news selector is tuned to preserve both:

- at least one explicit keyword-related news item when available
- at least one hot industry or company item when available

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

```bash
pytest --rootdir=. tests/test_pipeline.py tests/test_orchestrator.py tests/test_config.py
```

The focused tests cover ranking, configuration loading, and orchestration logic. They do not call live LLMs or send real email.

## Security Notes

- Do not commit `.env`, `config.yaml`, `artifacts/`, `runtime/`, or `state/*.json`
- Keep API keys, email usernames, app passwords, and recipient addresses in local environment variables or GitHub Secrets
- If you publish the project, review new feed URLs and workflow secrets before pushing