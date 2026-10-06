# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small set of standalone scripts that download South Asian movies from Einthusan.tv and integrate them into a Radarr/Plex media library. There is no test suite, package structure, or build step — it's three flat Python scripts plus bash wrappers.

## Running the scripts

Each Python script has a matching bash wrapper (`einthusan-dl`, `einthusan-login`, `einthusan-radarr-sync`) that runs it via `uv run --project <script-dir>`, so `uv` auto-creates/updates the `.venv` from `pyproject.toml` on every invocation — no manual install step needed.

```bash
./einthusan-dl "movie name" --lang tamil          # search + download
./einthusan-dl --url "https://einthusan.tv/movie/watch/XXX/?lang=tamil"
./einthusan-dl --search "movie name" --lang tamil # search only, no download
./einthusan-radarr-sync --dry-run --lang tamil    # preview Radarr sync
./einthusan-radarr-sync --lang tamil --limit 3    # download missing movies
./einthusan-login                                  # Playwright login for HD/premium cookies
./einthusan-login --visible                        # non-headless, for debugging login flow
```

There are no automated tests, lint configs, or CI. Verify changes by running the relevant script directly against real (or dry-run) data.

## Architecture

Three independent scripts that chain together via subprocess calls, not imports:

- **`einthusan-dl.py`** — the core downloader (`EinthusanDownloader` class). Scrapes Einthusan's search/movie pages with `requests` + `BeautifulSoup`, then calls Einthusan's internal AJAX endpoint (`/ajax/movie/...` or `/ajax/premium/movie/...`) to obtain the real video links. The response's `EJLinks` field is obfuscated (bytes rearranged + base64), decoded in `get_download_url`. Handles premium-redirect responses recursively. Downloads via `curl` (not `requests`) for resume/retry support, and names output files Plex-style: `Movie.Name.Year.Lang.WEB-DL.EINTHUSAN.mp4`.

- **`einthusan-login.py`** — uses Playwright (`playwright.sync_api`) to drive a real Chromium session through Einthusan's login form (including dismissing a GDPR/consent popup), then exports the resulting session cookies to a Netscape-format cookie file. This is required for premium/HD downloads; without it `einthusan-dl` only gets free-tier quality. Credentials can come from `--email`/`--password` flags, 1Password (`op item get einthusan`), a local JSON file, or an interactive prompt.

- **`einthusan-radarr-sync.py`** — the integration bridge. Queries Radarr's REST API (`/api/v3/movie`) for movies marked `hasFile: false`, filters to Indian-language originals by default (`INDIAN_LANGUAGES` set, toggle with `--all-movies`), then **shells out to the `einthusan-dl` bash wrapper as a subprocess** (not a Python import) for both search (`--search`) and download (`--url --output`), parsing its stdout with regex to extract matches. Fuzzy-matches Radarr titles against Einthusan search results using `difflib.SequenceMatcher` plus a year-proximity bonus (`similarity()`), requiring a `--min-score` (default 0.85) before downloading. After a successful download it calls Radarr's `RescanMovie` command for just that movie, then does one final full-library rescan at the end of the run.

Shared state between scripts lives on disk, not in memory:
- Cookies: `~/.config/einthusan/cookies.txt` (Netscape format, `chmod 600`)
- Saved credentials: `~/.config/einthusan/credentials.json` (`chmod 600`)
- Radarr config: `.env` file in the repo root (loaded manually via `_load_env()` in `einthusan-radarr-sync.py` — not python-dotenv), see `.env.example` for `RADARR_URL`, `RADARR_API_KEY`, optional `DOWNLOAD_DIR`

## Key things to know when modifying this code

- `einthusan-radarr-sync.py` depends on the exact stdout format of `einthusan-dl --search` (numbered `title (year)` lines followed by a URL line). If you change the print format in `einthusan-dl.py`'s `main()`, update the regexes in `search_einthusan()` accordingly.
- Radarr movie folder paths are translated from Radarr's container path (`/data/movies/...`) to a local path by simple string replacement against `DOWNLOAD_DIR` — this assumes Radarr and this script see the same media library at a different mount point.
- The `EJLinks` decoding scheme in `get_download_url` (byte-splicing before base64) is reverse-engineered from Einthusan's frontend JS; treat it as fragile and specific to their current site version.
