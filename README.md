# Einthusan-Radarr Sync

Download South Asian movies from Einthusan.tv and integrate with Radarr/Plex.

## Features

- **Search & Download** movies from Einthusan (Tamil, Hindi, Telugu, Malayalam, etc.)
- **Radarr Integration** — auto-download missing movies from your wanted list
- **Premium Support** — Playwright-based login for premium streams; resolution depends on the movie
- **Quality selection** — probes MP4 and HLS streams and downloads the highest resolution offered
- **Plex-friendly naming** — `Movie.Name.Year.Lang.WEB-DL.EINTHUSAN.mp4`

## Installation

```bash
git clone git@github.com:shyamsundar2007/einthusan-radarr-sync.git
cd einthusan-radarr-sync

# Scripts auto-create a .venv on first run
./einthusan-dl --help
```

Install `ffprobe` and `ffmpeg` (both provided by FFmpeg) on the host. The downloader uses
`ffprobe` to compare actual stream resolutions and `ffmpeg` when an HLS stream is best.
It reports the selected resolution during download. Premium access does not guarantee HD
when Einthusan only supplies a lower resolution source for a movie.

## Usage

### Download a movie
```bash
# Search and download
./einthusan-dl "movie name" --lang tamil

# Direct URL
./einthusan-dl --url "https://einthusan.tv/movie/watch/XXX/?lang=tamil"

# Search only (no download)
./einthusan-dl --search "movie name" --lang tamil

# Specify output directory
./einthusan-dl "movie name" --lang tamil --output /path/to/movies/
```

### Sync with Radarr
```bash
# Preview what would download
./einthusan-radarr-sync --dry-run --lang tamil

# Download missing movies (limit 3 per run)
./einthusan-radarr-sync --lang tamil --limit 3

# All missing movies
./einthusan-radarr-sync --lang tamil
```

### Login for Premium
```bash
# Interactive login
./einthusan-login

# With saved credentials
./einthusan-login --save-credentials
```

## Configuration

### Cookies
Stored at `~/.config/einthusan/cookies.txt` (Netscape format)

### Credentials (optional)
Stored at `~/.config/einthusan/credentials.json`
```json
{"email": "your@email.com", "password": "yourpassword"}
```

### Radarr
Set environment variables or edit `einthusan-radarr-sync.py`:
```bash
export RADARR_URL="http://localhost:7878"
export RADARR_API_KEY="your-api-key"
```

## Supported Languages

- Tamil
- Hindi  
- Telugu
- Malayalam
- Kannada
- Bengali
- Marathi
- Punjabi

## Cron Setup (optional)

```bash
# Refresh cookies before sync (5 mins before)
55 9,21 * * * /home/user/apps/einthusan-radarr-sync/einthusan-login

# Sync with Radarr twice daily
0 10,22 * * * /home/user/apps/einthusan-radarr-sync/einthusan-radarr-sync --lang tamil --limit 3
```

## License

MIT
