#!/usr/bin/env python3
"""
Einthusan-Radarr Sync Bridge

Checks Radarr wanted list → searches Einthusan → downloads matches

Usage:
    ./einthusan-radarr-sync.py              # Sync all missing movies
    ./einthusan-radarr-sync.py --dry-run    # Preview what would download
    ./einthusan-radarr-sync.py --lang tamil # Specify language
    ./einthusan-radarr-sync.py --limit 5    # Limit downloads per run

Requires: pip install requests beautifulsoup4
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from difflib import SequenceMatcher

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

# Configuration
RADARR_URL = os.environ.get("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "***REDACTED***")
DOWNLOAD_DIR = Path("/mnt/synology/shyamflix-media/movies")  # Direct to Plex folder
EINTHUSAN_SCRIPT = Path(__file__).parent / "einthusan-dl"

# Language mapping (Radarr language ID -> Einthusan language)
LANGUAGE_MAP = {
    "tamil": "tamil",
    "hindi": "hindi",
    "telugu": "telugu",
    "malayalam": "malayalam",
    "kannada": "kannada",
    "bengali": "bengali",
    "marathi": "marathi",
    "punjabi": "punjabi",
}


def similarity(a: str, b: str) -> float:
    """Calculate string similarity ratio."""
    a = re.sub(r'[^\w\s]', '', a.lower())
    b = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()


def get_radarr_missing(language_filter: str = None) -> list[dict]:
    """Get missing movies from Radarr."""
    headers = {"X-Api-Key": RADARR_API_KEY}
    
    # Get all movies
    resp = requests.get(f"{RADARR_URL}/api/v3/movie", headers=headers)
    resp.raise_for_status()
    movies = resp.json()
    
    missing = []
    for movie in movies:
        # Check if movie is missing (not downloaded)
        if not movie.get("hasFile", False):
            # Get language if available
            lang = None
            if movie.get("originalLanguage"):
                lang = movie["originalLanguage"].get("name", "").lower()
            
            # Filter by language if specified
            if language_filter and lang != language_filter.lower():
                continue
                
            missing.append({
                "id": movie["id"],
                "title": movie["title"],
                "year": movie.get("year"),
                "imdbId": movie.get("imdbId"),
                "tmdbId": movie.get("tmdbId"),
                "language": lang,
                "path": movie.get("path"),
            })
    
    return missing


def search_einthusan(title: str, year: int = None, lang: str = "tamil") -> dict | None:
    """Search Einthusan for a movie, return best match."""
    try:
        result = subprocess.run(
            [str(EINTHUSAN_SCRIPT), "--search", title, "--lang", lang],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Parse output
        matches = []
        for line in result.stdout.split("\n"):
            # Match lines like "  1. Movie Name (2024)"
            m = re.match(r'\s+\d+\.\s+(.+?)\s*\((\d{4})\)', line)
            if m:
                matches.append({
                    "title": m.group(1).strip(),
                    "year": int(m.group(2)),
                })
            # Match URL lines
            m = re.match(r'\s+(https://einthusan\.tv/movie/watch/[^\s]+)', line)
            if m and matches:
                matches[-1]["url"] = m.group(1)
        
        if not matches:
            return None
        
        # Find best match by title similarity and year
        best = None
        best_score = 0
        
        for match in matches:
            score = similarity(title, match["title"])
            
            # Boost score if year matches
            if year and match.get("year") == year:
                score += 0.3
            elif year and abs(match.get("year", 0) - year) <= 1:
                score += 0.1
            
            if score > best_score:
                best_score = score
                best = match
        
        # Only return if good enough match
        if best and best_score >= 0.6:
            best["score"] = best_score
            return best
        
        return None
        
    except Exception as e:
        print(f"  ⚠️ Search error: {e}")
        return None


def download_movie(url: str, output_dir: Path) -> bool:
    """Download movie from Einthusan."""
    try:
        result = subprocess.run(
            [str(EINTHUSAN_SCRIPT), "--url", url, "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=1800  # 30 min timeout for large files
        )
        return "Downloaded:" in result.stdout
    except Exception as e:
        print(f"  ⚠️ Download error: {e}")
        return False


def trigger_radarr_scan(movie_id: int = None):
    """Trigger Radarr to scan for new files. If movie_id provided, scans just that movie."""
    headers = {"X-Api-Key": RADARR_API_KEY}
    try:
        payload = {"name": "RescanMovie"}
        if movie_id:
            payload["movieIds"] = [movie_id]
        resp = requests.post(
            f"{RADARR_URL}/api/v3/command",
            headers=headers,
            json=payload
        )
        return resp.status_code == 201
    except:
        return False


def main():
    parser = argparse.ArgumentParser(description="Sync Radarr wanted list with Einthusan")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't download")
    parser.add_argument("--lang", nargs="+", default=["tamil", "hindi", "malayalam", "telugu"],
                        help="Languages to search (default: tamil hindi malayalam telugu)")
    parser.add_argument("--limit", type=int, default=0, help="Max downloads per run (0=unlimited)")
    parser.add_argument("--min-score", type=float, default=0.85, help="Minimum match score (0-1)")
    args = parser.parse_args()

    languages = args.lang if isinstance(args.lang, list) else [args.lang]
    print(f"🔍 Checking Radarr for missing movies (languages: {', '.join(languages)})...")
    
    # Get missing movies without language filter - we'll search all languages
    missing = get_radarr_missing(language_filter=None)
    
    if not missing:
        print("✓ No missing movies found")
        return
    
    print(f"📋 Found {len(missing)} missing movies\n")
    
    downloaded = 0
    for movie in missing:
        title = movie["title"]
        year = movie.get("year")
        radarr_lang = movie.get("language")
        
        print(f"🎬 {title} ({year or '?'})")
        
        # Search Einthusan across all specified languages
        best_match = None
        best_lang = None
        
        # Prioritize Radarr's detected language if it's in our search list
        search_order = list(languages)
        if radarr_lang and radarr_lang in search_order:
            search_order.remove(radarr_lang)
            search_order.insert(0, radarr_lang)
        
        for lang in search_order:
            match = search_einthusan(title, year, lang)
            if match:
                if best_match is None or match.get("score", 0) > best_match.get("score", 0):
                    best_match = match
                    best_lang = lang
                # If perfect match (>= 0.9), stop searching
                if match.get("score", 0) >= 0.9:
                    break
        
        if not best_match:
            print(f"   ❌ Not found on Einthusan ({', '.join(languages)})")
            continue
        
        score = best_match.get("score", 0)
        if score < args.min_score:
            print(f"   ⚠️ Low match: {best_match['title']} ({best_match['year']}) [{best_lang}] - score {score:.2f}")
            continue
        
        print(f"   ✓ Found: {best_match['title']} ({best_match['year']}) [{best_lang}] - score {score:.2f}")
        
        # Check if file already exists locally (prevents re-download before Radarr scan)
        match_title = re.sub(r"[^\w\s-]", "", best_match["title"]).replace(" ", ".")
        match_year = best_match.get("year", "")
        existing = list(DOWNLOAD_DIR.glob(f"{match_title}.{match_year}.*EINTHUSAN*.mp4"))
        if existing:
            print(f"   ⏭️ Already downloaded: {existing[0].name}")
            continue
        
        if args.dry_run:
            print(f"   📦 Would download: {best_match['url']}")
            continue
        
        # Download
        print(f"   📥 Downloading...")
        if download_movie(best_match["url"], DOWNLOAD_DIR):
            print(f"   ✓ Downloaded!")
            downloaded += 1
            # Immediately tell Radarr to rescan this specific movie
            if trigger_radarr_scan(movie["id"]):
                print(f"   🔄 Radarr notified")
        else:
            print(f"   ❌ Download failed")
        
        # Check limit
        if args.limit > 0 and downloaded >= args.limit:
            print(f"\n⏸️ Reached download limit ({args.limit})")
            break
    
    if downloaded > 0:
        print(f"\n✓ Downloaded {downloaded} movie(s)")
        # Per-movie scans already triggered above, but do a final full scan as backup
        print("🔄 Final Radarr library scan...")
        if trigger_radarr_scan():
            print("✓ Done")
        else:
            print("⚠️ Could not trigger final scan")


if __name__ == "__main__":
    main()
