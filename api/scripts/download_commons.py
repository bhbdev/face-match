"""Download public-domain portrait photos from Wikimedia Commons categories.

Examples (run inside the api container, see the Makefile):

    python -m scripts.download_commons --find "daguerreotype portraits"
    python -m scripts.download_commons -c "Category:Daguerreotype portraits" --limit 300
    python -m scripts.download_commons -c "Category:Cartes de visite" --depth 1

Each image is saved to data/historic/commons_<pageid>.<ext> with a .json sidecar
holding title, date, author, license and the Commons page URL. Only files whose
license matches --license-regex (public domain / CC0 by default) are kept, but
licensing metadata on Commons is crowd-sourced: spot check anything you plan to
publish.
"""

import argparse
import html
import json
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Iterator

import requests

from app import config

API = "https://commons.wikimedia.org/w/api.php"
POLITE_DELAY = 1.0  # seconds between requests; Wikimedia throttles fast bots
# Wikimedia only serves these thumbnail widths from cache. Other sizes are rendered on
# demand and rate-limited much harder, which is a common cause of HTTP 429.
STANDARD_WIDTHS = [250, 330, 500, 960, 1280, 1920]
EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png"}
META_FIELDS = (
    "LicenseShortName|Artist|DateTimeOriginal|ObjectName|ImageDescription|Copyrighted|UsageTerms"
)


class RateLimited(Exception):
    """Wikimedia kept answering 429/5xx even after waiting."""


def make_session() -> requests.Session:
    contact = os.environ.get("COMMONS_CONTACT", "").strip()
    if not contact:
        sys.exit(
            "COMMONS_CONTACT is not set.\n"
            "Wikimedia blocks anonymous bots with HTTP 429. Put an email or URL in .env, e.g.\n"
            "  COMMONS_CONTACT=you@example.com\n"
            "then run the command again."
        )
    s = requests.Session()
    s.headers["User-Agent"] = f"face-match-hobby/0.1 ({contact})"
    return s


def request(s: requests.Session, url: str, params: dict | None = None, tries: int = 6) -> requests.Response:
    """GET with backoff. Honours Retry-After when Wikimedia sends it."""
    for attempt in range(tries):
        r = s.get(url, params=params, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504):
            retry_after = r.headers.get("Retry-After", "")
            wait = float(retry_after) if retry_after.isdigit() else min(5 * 2 ** attempt, 120)
            print(f"  HTTP {r.status_code}, waiting {wait:.0f}s before retrying...", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RateLimited(url)


def api_get(s: requests.Session, **params) -> dict:
    params.update(format="json", formatversion=2)
    data = request(s, API, params).json()
    time.sleep(POLITE_DELAY)
    return data


def clean(text: str, limit: int = 300) -> str:
    """Commons metadata is HTML; reduce it to plain text."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def normalize_category(name: str) -> str:
    name = name.strip().replace("_", " ")
    return name if name.lower().startswith("category:") else f"Category:{name}"


def find_categories(s: requests.Session, query: str) -> list[str]:
    data = api_get(
        s, action="query", list="search", srnamespace=14, srlimit=20, srsearch=query
    )
    return [r["title"] for r in data.get("query", {}).get("search", [])]


def iter_subcategories(s: requests.Session, category: str) -> Iterator[str]:
    params = dict(
        action="query", list="categorymembers", cmtitle=category, cmtype="subcat", cmlimit=500
    )
    while True:
        data = api_get(s, **params)
        for m in data.get("query", {}).get("categorymembers", []):
            yield m["title"]
        if "continue" not in data:
            return
        params.update(data["continue"])


def iter_files(s: requests.Session, category: str, width: int) -> Iterator[dict]:
    params = dict(
        action="query",
        generator="categorymembers",
        gcmtitle=category,
        gcmtype="file",
        gcmlimit=50,
        prop="imageinfo",
        iiprop="url|mime|size|extmetadata",
        iiurlwidth=width,
        iiextmetadatafilter=META_FIELDS,
    )
    while True:
        data = api_get(s, **params)
        yield from data.get("query", {}).get("pages", [])
        if "continue" not in data:
            return
        params.update(data["continue"])


def meta_value(meta: dict, key: str) -> str:
    return clean(meta.get(key, {}).get("value", ""), 400)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("-c", "--category", action="append", default=[],
                    help="Commons category (repeatable), e.g. 'Category:Daguerreotype portraits'")
    ap.add_argument("--find", metavar="QUERY",
                    help="Search Commons for category names matching QUERY, then exit")
    ap.add_argument("--limit", type=int, default=300, help="Max images to download (default 300)")
    ap.add_argument("--depth", type=int, default=0,
                    help="Also descend into subcategories this many levels (default 0)")
    ap.add_argument("--width", type=int, default=960, choices=STANDARD_WIDTHS,
                    help="Download thumbnails this many px wide (default 960). Only Wikimedia's\n"
                         "standard sizes are allowed; other sizes get rate-limited.")
    ap.add_argument("--min-side", type=int, default=250,
                    help="Skip originals smaller than this on their short side (default 250)")
    ap.add_argument("--license-regex", default=r"public domain|^pd\b|^pd-|cc0|pdm",
                    help="Keep files whose license short name matches (case-insensitive)")
    args = ap.parse_args()

    s = make_session()

    if args.find:
        names = find_categories(s, args.find)
        print("\n".join(names) if names else "No matching categories.")
        return
    if not args.category:
        ap.error("give at least one --category (or use --find to look for one)")

    out_dir = config.HISTORIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    license_ok = re.compile(args.license_regex, re.I).search

    queue = deque((normalize_category(c), 0) for c in args.category)
    visited: set[str] = set()
    saved = skipped_license = skipped_other = already = 0

    while queue and saved < args.limit:
        category, depth = queue.popleft()
        if category in visited:
            continue
        visited.add(category)
        print(f"\n{category}  (depth {depth})")

        seen_any = False
        for page in iter_files(s, category, args.width):
            seen_any = True
            if saved >= args.limit:
                break
            info = (page.get("imageinfo") or [None])[0]
            if not info or info.get("mime") not in EXT_BY_MIME:
                skipped_other += 1
                continue
            if min(info.get("width", 0), info.get("height", 0)) < args.min_side:
                skipped_other += 1
                continue

            meta = info.get("extmetadata", {})
            license_name = meta_value(meta, "LicenseShortName")
            if not license_ok(license_name):
                skipped_license += 1
                continue

            stem = f"commons_{page['pageid']}"
            img_path = out_dir / f"{stem}{EXT_BY_MIME[info['mime']]}"
            if img_path.exists():
                already += 1
                continue

            url = info.get("thumburl") or info["url"]
            try:
                r = request(s, url)
            except requests.RequestException as e:
                print(f"  ! download failed: {page['title']} ({e})")
                continue
            img_path.write_bytes(r.content)

            title = meta_value(meta, "ObjectName") or re.sub(
                r"^File:|\.\w+$", "", page["title"]
            )
            sidecar = {
                "title": title,
                "year": meta_value(meta, "DateTimeOriginal"),
                "author": meta_value(meta, "Artist"),
                "license": license_name,
                "source_url": info.get("descriptionurl", ""),
            }
            img_path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2))

            saved += 1
            if saved % 25 == 0:
                print(f"  {saved} saved")
            time.sleep(POLITE_DELAY)

        if not seen_any and depth == 0:
            print("  (no files found; check the category name, or try --find)")

        if depth < args.depth:
            for sub in iter_subcategories(s, category):
                queue.append((sub, depth + 1))

    print(
        f"\nDone. saved={saved} already_had={already} "
        f"skipped_license={skipped_license} skipped_other={skipped_other}"
    )
    print(f"Photos are in {out_dir}. Next: make index")


if __name__ == "__main__":
    try:
        main()
    except RateLimited:
        sys.exit(
            "\nWikimedia is still rate limiting this connection. Wait 10-15 minutes and run the\n"
            "same command again: files that were already downloaded are skipped, so it resumes."
        )
