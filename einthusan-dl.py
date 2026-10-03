#!/usr/bin/env python3
"""
Einthusan Downloader for Radarr/Plex integration

Usage:
    ./einthusan-dl.py "movie name" [--lang tamil|malayalam|hindi|telugu|kannada|bengali|marathi|punjabi]
    ./einthusan-dl.py --url "https://einthusan.tv/movie/watch/XXX/?lang=tamil"
    ./einthusan-dl.py --search "movie name" --lang tamil

Requires: pip install requests beautifulsoup4
Cookies: ~/.config/einthusan/cookies.txt (Netscape format) or auto-login with credentials

Output: ~/downloads/einthusan/Movie.Name.Year.Lang.WEB-DL.EINTHUSAN.mp4
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# Configuration
CONFIG_DIR = Path.home() / ".config" / "einthusan"
COOKIES_FILE = CONFIG_DIR / "cookies.txt"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
DOWNLOAD_DIR = Path.home() / "downloads" / "einthusan"
RADARR_IMPORT_DIR = None  # Set to Radarr's completed download folder if using Radarr

LANGUAGES = ["tamil", "malayalam", "hindi", "telugu", "kannada", "bengali", "marathi", "punjabi"]


class EinthusanDownloader:
    def __init__(self, lang="tamil"):
        self.lang = lang
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._load_cookies()

    def _load_cookies(self):
        """Load cookies from file if available."""
        if COOKIES_FILE.exists():
            # Parse Netscape cookie file
            with open(COOKIES_FILE) as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 7:
                        domain, _, path, secure, expires, name, value = parts[:7]
                        self.session.cookies.set(
                            name, value, domain=domain, path=path
                        )
            print(f"✓ Loaded cookies from {COOKIES_FILE}")

    def search(self, query: str) -> list[dict]:
        """Search for movies on Einthusan."""
        url = f"https://einthusan.tv/movie/results/?lang={self.lang}&query={query}"
        resp = self.session.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        for block in soup.select("#UIMovieSummary li, .block2"):
            title_elem = block.select_one("a.title h3")
            link_elem = block.select_one("a.title")
            if title_elem and link_elem:
                href = link_elem.get("href", "")
                movie_id = re.search(r"/movie/watch/([^/]+)/", href)
                if movie_id:
                    # Try to get year from info
                    info = block.select_one(".info p")
                    year = ""
                    if info:
                        year_match = re.search(r"(\d{4})", info.get_text())
                        if year_match:
                            year = year_match.group(1)
                    
                    results.append({
                        "id": movie_id.group(1),
                        "title": title_elem.get_text().strip(),
                        "year": year,
                        "url": f"https://einthusan.tv/movie/watch/{movie_id.group(1)}/?lang={self.lang}",
                    })
        
        # Deduplicate by ID
        seen = set()
        unique = []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)
        
        return unique

    def get_download_url(self, movie_url: str) -> dict:
        """Get the actual download URL via AJAX."""
        # Get movie page
        resp = self.session.get(movie_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract required data
        html_elem = soup.find("html")
        page_id = html_elem.get("data-pageid", "")
        
        video_player = soup.find("section", {"id": "UIVideoPlayer"})
        if not video_player:
            return {"error": "Video player not found - may need login"}
        
        ejpingables = video_player.get("data-ejpingables", "")
        content_title = video_player.get("data-content-title", "Unknown")
        
        # Check if premium page
        is_premium = "PGPremiumMovieWatch" in resp.text
        
        # Get movie info
        summary = soup.find("section", {"id": "UIMovieSummary"})
        year = ""
        if summary:
            info = summary.select_one(".info p")
            if info:
                year_match = re.search(r"(\d{4})", info.get_text())
                if year_match:
                    year = year_match.group(1)

        # Make AJAX call to get real URL
        # Handle both regular and premium URLs
        if "/premium/" in movie_url:
            ajax_url = movie_url.replace("/premium/movie/", "/ajax/premium/movie/")
        else:
            ajax_url = movie_url.replace("/movie/", "/ajax/movie/")
        payload = {
            "xEvent": "UIVideoPlayer.PingOutcome",
            "xJson": json.dumps({"EJOutcomes": ejpingables, "NativeHLS": False}),
            "gorilla.csrf.Token": page_id,
        }

        resp = self.session.post(ajax_url, data=payload)
        if resp.status_code != 200:
            return {"error": f"AJAX failed: {resp.status_code}"}

        try:
            data = resp.json()
            
            # Handle premium redirect
            if data.get("Event") == "redirect" and isinstance(data.get("Data"), str):
                premium_url = "https://einthusan.tv" + data["Data"]
                # Recursively get from premium URL
                return self.get_download_url(premium_url)
            
            # Get EJLinks from response
            if isinstance(data.get("Data"), dict):
                encoded = data["Data"].get("EJLinks", "")
            else:
                return {"error": "Unexpected response format"}
                
            if not encoded:
                return {"error": "No download links in response - may need premium"}

            # Decode using Einthusan's method
            value_len = len(encoded)
            encoded_value = encoded[0:10] + encoded[value_len - 1] + encoded[12 : value_len - 1]
            decoded = base64.b64decode(encoded_value).decode("utf-8")
            links = json.loads(decoded)

            # Check for priority parameter (premium quality)
            mp4_url = links.get("MP4Link", "")
            is_premium = is_premium or "p=priority" in mp4_url

            return {
                "title": content_title,
                "year": year,
                "mp4_url": mp4_url,
                "hls_url": links.get("HLSLink"),
                "is_premium": is_premium,
                "lang": self.lang,
            }
        except Exception as e:
            return {"error": f"Failed to decode: {e}"}

    def _hls_streams(self, url: str) -> list[dict]:
        """Expand an HLS master playlist, or keep a single media playlist."""
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            lines = [line.strip() for line in response.text.splitlines() if line.strip()]
        except requests.RequestException as e:
            print(f"   ⚠️ Could not inspect HLS playlist: {e.__class__.__name__}")
            return []

        streams = []
        for index, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF:"):
                next_url = next((item for item in lines[index + 1:] if not item.startswith("#")), None)
                if next_url:
                    streams.append({"kind": "hls", "url": urljoin(url, next_url)})
        return streams or [{"kind": "hls", "url": url}]

    @staticmethod
    def _probe_video(url: str) -> tuple[int, int] | None:
        """Read the encoded video dimensions without downloading the whole file."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "json", url],
                capture_output=True, text=True, timeout=45,
            )
            if result.returncode == 0:
                stream = json.loads(result.stdout).get("streams", [{}])[0]
                width, height = int(stream["width"]), int(stream["height"])
                if width > 0 and height > 0:
                    return width, height
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
            pass
        return None

    def select_best_stream(self, url_info: dict) -> dict | None:
        """Choose the highest resolution offered by the MP4 and HLS links."""
        candidates = []
        if url_info.get("mp4_url"):
            candidates.append({"kind": "mp4", "url": url_info["mp4_url"]})
        if url_info.get("hls_url"):
            candidates.extend(self._hls_streams(url_info["hls_url"]))

        for candidate in candidates:
            dimensions = self._probe_video(candidate["url"])
            if dimensions:
                candidate["width"], candidate["height"] = dimensions

        probed = [candidate for candidate in candidates if "height" in candidate]
        if not probed:
            return None
        # Keep the directly downloadable MP4 when the resolutions are equal.
        return max(probed, key=lambda item: (
            item["width"] * item["height"], item["height"], item["kind"] == "mp4"
        ))

    def download(self, url_info: dict, output_dir: Path = None) -> Path:
        """Download the movie."""
        if "error" in url_info:
            print(f"✗ Error: {url_info['error']}")
            return None

        stream = self.select_best_stream(url_info)
        if not stream:
            print("✗ Could not verify the resolution of any available stream (ffprobe required)")
            return None

        output_dir = output_dir or DOWNLOAD_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        title = re.sub(r"[^\w\s-]", "", url_info["title"]).replace(" ", ".")
        year = url_info.get("year", "")
        lang = url_info.get("lang", "").capitalize()
        # Don't assume resolution - premium just means highest available for that movie
        quality = "WEB-DL"
        tier = "Premium" if url_info.get("is_premium") else "Free"
        
        filename = f"{title}"
        if year:
            filename += f".{year}"
        filename += f".{lang}.{quality}.EINTHUSAN.mp4"
        
        output_path = output_dir / filename
        temp_path = output_dir / f"{output_path.stem}.part.mp4"

        print(f"📥 Downloading: {url_info['title']} ({year})")
        print(f"   Tier: {tier}; selected {stream['width']}x{stream['height']} {stream['kind'].upper()}")
        print(f"   Output: {output_path}")

        # A partial file may belong to a different stream from an earlier run.
        temp_path.unlink(missing_ok=True)
        if stream["kind"] == "mp4":
            cmd = [
                "curl", "--fail", "-L", "-o", str(temp_path), stream["url"],
                "--progress-bar", "--retry", "3", "--retry-delay", "5",
            ]
        else:
            # ffmpeg remuxes the selected HLS rendition without re-encoding it.
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-i", stream["url"], "-c", "copy", str(temp_path)]
        
        try:
            result = subprocess.run(cmd)
        except FileNotFoundError:
            print(f"✗ Download failed: {cmd[0]} is not installed")
            return None
        if result.returncode == 0 and temp_path.exists() and self._probe_video(str(temp_path)) == (
            stream["width"], stream["height"]
        ):
            temp_path.replace(output_path)
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"✓ Downloaded: {output_path.name} ({size_mb:.1f} MB, {stream['width']}x{stream['height']})")
            return output_path
        else:
            temp_path.unlink(missing_ok=True)
            print("✗ Download failed or video resolution did not match the selected stream")
            return None


def main():
    parser = argparse.ArgumentParser(description="Download movies from Einthusan")
    parser.add_argument("query", nargs="?", help="Movie name to search")
    parser.add_argument("--url", help="Direct Einthusan movie URL")
    parser.add_argument("--search", help="Search only, don't download")
    parser.add_argument("--lang", default="tamil", choices=LANGUAGES, help="Language")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--info", action="store_true", help="Show info only, don't download")
    args = parser.parse_args()

    dl = EinthusanDownloader(lang=args.lang)
    output_dir = Path(args.output) if args.output else DOWNLOAD_DIR

    if args.url:
        # Direct URL download
        info = dl.get_download_url(args.url)
        if args.info:
            print(json.dumps(info, indent=2))
        else:
            dl.download(info, output_dir)

    elif args.search or args.query:
        # Search mode
        query = args.search or args.query
        print(f"🔍 Searching for: {query}")
        results = dl.search(query)
        
        if not results:
            print("No results found")
            return

        print(f"\nFound {len(results)} result(s):\n")
        for i, r in enumerate(results, 1):
            year_str = f" ({r['year']})" if r['year'] else ""
            print(f"  {i}. {r['title']}{year_str}")
            print(f"     {r['url']}")
        
        if args.search:
            return  # Search only mode

        # Download first result
        print(f"\n📥 Downloading first result...")
        info = dl.get_download_url(results[0]["url"])
        if args.info:
            print(json.dumps(info, indent=2))
        else:
            dl.download(info, output_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
