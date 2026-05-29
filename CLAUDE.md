# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python automation system that scrapes the [UCC 影城](http://www.ucc-cinema.com.tw/main03.asp) website daily, detects newly released movies, and sends Telegram notifications with poster images. It runs entirely on GitHub Actions — no server required.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full pipeline locally (requires env vars set)
python main.py

# Run only the scraper to inspect what the website returns
python scraper.py

# Environment variables required for notifier
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...   # personal chat ID, group ID, or channel ID (e.g. -1001234567890)
```

Run tests with `pip install -r requirements-dev.txt` then `pytest` (`test_movies.py`). You can also run `python scraper.py` to inspect raw parse output or `python main.py` end-to-end. Despite the `.env.example` file, **`.env` is not auto-loaded** — there is no `python-dotenv` dependency, so env vars must be exported into the shell (or set as GitHub Secrets) before running.

## Architecture

The pipeline runs in four sequential steps orchestrated by `main.py`:

```
scraper.py   →   detector.py   →   notifier.py   →   detector.save_history()
 (fetch)         (diff vs JSON)     (Telegram)         (write JSON)
```

**`scraper.py`** — Fetches `http://www.ucc-cinema.com.tw/main03.asp` (Big5 encoding). Uses BeautifulSoup to find `<img>` tags whose `src` contains `upload/data`, then walks up to the nearest `<table>` ancestor as the movie block. Each block is parsed for name (from image filename), period, rating, duration, and showtimes. Paired movies (片(一)/片(二)) are split into separate records via `_expand_paired_movie`.

**`detector.py`** — Loads `movies_data.json` (dict keyed by `"{name}|{period}"`). Compares current scrape against history; returns movies whose key is absent. On first run (empty history), all movies are treated as new. Saves updated data back to `movies_data.json` after each run.

**`notifier.py`** — Reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from environment. For each new movie: downloads the poster to a temp file and calls `sendPhoto`; falls back to `sendMessage` with a poster URL link if download or send fails.

**`movies_data.json`** — Acts as the persistent state store. GitHub Actions commits this file back to the repo after each run so history survives between workflow executions.

**`.github/workflows/check_movies.yml`** — Scheduled daily at UTC 01:00 (Taiwan 09:00). Also supports `workflow_dispatch` for manual runs. Commits `movies_data.json` only when it changes.

## Key Implementation Details

- **Encoding**: The target website uses Big5/CP950. `response.apparent_encoding` is used as a hint, with `"big5"` as fallback.
- **Movie ID**: Uniqueness is `"{name}|{period}"` — changing either field triggers a new notification.
- **Paired movies**: When a block contains `片(一)` and `片(二)` with different names, `_expand_paired_movie` splits them into two separate movie dicts sharing the same poster, period, duration, and showtimes.
- **Poster URL**: Spaces in the original URL must be preserved as-is (do not encode or strip them) — the server requires the exact raw URL path.
- **Telegram target**: `TELEGRAM_CHAT_ID` can be a personal ID, group ID (negative), or public channel ID (`-100...` prefix) or username (`@channel_name`).
- **HTML parser**: `scraper.py` uses BeautifulSoup with `"html.parser"` (no `lxml` dependency).
- **History is cumulative**: `detector.save_history` merges the current scrape into existing history rather than overwriting, so a partial/failed scrape never causes already-notified movies to be re-notified when the site recovers. `raw_text` is stripped before saving.
- **Telegram formatting**: messages use `parse_mode="HTML"` with `html.escape` on all dynamic fields. `_send_photo`/`_send_message` retry once on HTTP 429 using the `retry_after` hint.
- **Tests**: `pip install -r requirements-dev.txt` then `pytest` (covers `_expand_paired_movie` and the cumulative-history detection in `test_movies.py`).
