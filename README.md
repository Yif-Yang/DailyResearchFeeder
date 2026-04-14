# Daily Research Feeder

Daily Research Feeder is a configurable tool for building a daily research digest from papers and news sources.

It collects items from paper APIs and RSS or Atom feeds, ranks them with your interests plus an LLM, renders an HTML report, and can send the final digest by email.

The repository is designed to be reusable by other people:

- choose your own keywords and research interests
- choose your own arXiv categories and feed sources
- switch between different LLM providers
- switch between different email providers
- run it once, backfill a date, or keep it running as a daily daemon

## What This Tool Can Do

- Collect papers from arXiv and Hugging Face Daily Papers
- Collect news from RSS or Atom feeds
- Rank items using your keywords, interests, source priors, and LLM review
- Generate a digest with separate paper and news sections
- Write a local HTML preview before sending
- Send the digest by email
- Track seen items to reduce duplicates across runs
- Run in dry-run, one-shot, backfill, or scheduled modes

## Quick Start

1. Create your local config files.

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

2. Install dependencies.

```bash
bash scripts/bootstrap.sh
```

3. Customize the digest inputs.

- [config.example.yaml](config.example.yaml): copy to local `config.yaml` and adjust runtime settings
- [.env.example](.env.example): copy to local `.env` and add provider credentials
- [user/keywords.txt](user/keywords.txt): keywords you care about
- [user/research_interests.txt](user/research_interests.txt): longer-form interest profile for ranking and summarization
- [user/arxiv_categories.txt](user/arxiv_categories.txt): arXiv categories to scan
- [user/feeds.yaml](user/feeds.yaml): RSS or Atom feeds to include

4. Run a dry run.

```bash
python main.py --config config.yaml --dry-run
```

The preview HTML is written to `artifacts/report_preview.html`.

## How To Customize It

This project is meant to support different topics, not a fixed preset.

Use these files to adapt it to your own use case:

- [user/keywords.txt](user/keywords.txt): short keywords and phrases for prioritization
- [user/research_interests.txt](user/research_interests.txt): a broader description of the topics you want the LLM to care about
- [user/arxiv_categories.txt](user/arxiv_categories.txt): paper domains to search
- [user/feeds.yaml](user/feeds.yaml): blogs, news sites, company feeds, research feeds, or any other RSS or Atom source

Typical customization patterns:

- switch from AI research to another technical area by replacing keywords and categories
- add company blogs, newsletters, or product feeds in [user/feeds.yaml](user/feeds.yaml)
- narrow the digest to a few sources or broaden it to many feeds
- tune limits such as paper count, news count, and scoring thresholds in local `config.yaml`

## LLM And Email Providers

Supported LLM providers:

- `copilot_cli`
- `azure_openai`
- `openai`

Supported email providers:

- `gmail_smtp`
- `smtp`
- `resend`
- `azure_cli_graph`
- `file`

Minimal local example using `copilot_cli` and `gmail_smtp`:

```bash
LLM_PROVIDER=copilot_cli
COPILOT_COMMAND=copilot

EMAIL_PROVIDER=gmail_smtp
EMAIL_TO=your-email@example.com
GMAIL_SMTP_USERNAME=your-account@gmail.com
GMAIL_SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=Daily Research Feeder <your-account@gmail.com>
```

See [.env.example](.env.example) for the full set of variables.

## Common Commands

Dry run:

```bash
python main.py --config config.yaml --dry-run
```

Real send:

```bash
python main.py --config config.yaml
```

Backfill a specific date:

```bash
python main.py --config config.yaml --backfill-date 2026-04-14 --dry-run
```

Run the scheduled mode once:

```bash
python main.py --config config.yaml --mode scheduled_day --dry-run
```

Start the daemon:

```bash
bash scripts/start_daily_digest_daemon.sh
```

Stop the daemon:

```bash
bash scripts/stop_daily_digest_daemon.sh
```

Run one immediate execution with the shell defaults:

```bash
bash scripts/run_daily_digest_now.sh
```

## Adding New Sources

To add new sources, edit [user/feeds.yaml](user/feeds.yaml).

You can organize feeds however you want, for example:

- company blogs
- research blogs
- tooling blogs
- industry news
- product release feeds
- community newsletters

As long as the source is available as RSS or Atom, it can be part of the digest.

For papers, expand or replace [user/arxiv_categories.txt](user/arxiv_categories.txt) to match your field.

## Configuration

Use [config.example.yaml](config.example.yaml) as the tracked template and keep your real settings in local `config.yaml`.

The config template covers:

- timezone and language
- input file paths
- LLM defaults
- score thresholds and item limits
- source toggles
- artifact paths
- scheduling options

Keep secrets and user-specific identifiers in local `.env`, not in tracked YAML.

## GitHub Actions

The repository includes [daily-digest.yml](.github/workflows/daily-digest.yml) for scheduled or manual runs on GitHub Actions.

The workflow uses [config.example.yaml](config.example.yaml) together with GitHub Secrets and Variables, so you do not need to commit a private `config.yaml`.

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

These tests cover ranking, configuration loading, and orchestration logic. They do not call live LLMs or send real email.

## Security

- Do not commit `.env`, `config.yaml`, `artifacts/`, `runtime/`, or `state/*.json`
- Keep API keys, app passwords, and recipient addresses in local environment variables or GitHub Secrets
- Review workflow secrets before enabling GitHub Actions in a public fork