"""Convert public HackerTube recommendations into a paced RSS feed.

HackerTube is a static catalogue. The same video IDs stay in its API for
months, so polling alone never produces new feed entries. This converter owns
the schedule instead:

* Recent uploads are the fast lane. Every run scans the newest uploads and
  publishes any video that was never published before.
* The ranked catalogue is the slow lane. A cursor walks down the score-ordered
  list and publishes a fixed number of unseen videos per run.

Both lanes share one daily budget so a feed never outruns its consumer.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ATOM = "http://www.w3.org/2005/Atom"
RSS_LIMIT = 200
STATE_VERSION = 2
VID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")
TEXT_FIELDS = (
    "title", "channel", "published", "summary", "why_hn", "content_type",
    "level", "shelf_life", "primary_topic",
)
Video = dict[str, str | int]


class State(TypedDict):
    """Converter state that survives between Actions runs."""

    version: int
    cursor: int
    done: list[str]
    published: list[Video]


def require_timestamp(value: object) -> str:
    """Return an ISO timestamp that carries a timezone."""
    if not isinstance(value, str) or not value:
        raise ValueError("Discovery timestamps are required")
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("Discovery timestamps must include a timezone")
    return value


def normalize_video(row: object) -> Video:
    """Validate one public video and copy only its allowlisted fields."""
    if not isinstance(row, dict):
        raise ValueError("Video record is not an object")
    vid = row.get("vid")
    if not isinstance(vid, str) or VID_PATTERN.fullmatch(vid) is None:
        raise ValueError("Invalid YouTube video ID")
    video: Video = {"vid": vid}
    for field in TEXT_FIELDS:
        value = row.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"Expected text for {field}")
        video[field] = value
    if not video["title"] or not (video["summary"] or video["why_hn"]):
        raise ValueError("Video is missing its title or evidence")
    duration = row.get("duration_s", 0)
    if type(duration) is not int or duration < 0:
        raise ValueError("Invalid video duration")
    video["duration_s"] = duration
    return video


def fetch_videos(url: str, what: str, allow_empty: bool = False) -> list[Video]:
    """Fetch one API page and validate every record it returns."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "mxzel-feed/2.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of videos from {what}")
    if not payload and not allow_empty:
        raise ValueError(f"Expected a non-empty video list from {what}")
    return [normalize_video(row) for row in payload]


def load_state(path: Path) -> State:
    """Load converter state and migrate the flat version 1 format."""
    if not path.exists():
        return {"version": STATE_VERSION, "cursor": 0, "done": [], "published": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        published = []
        for row in raw:
            video = normalize_video(row)
            video["first_seen"] = require_timestamp(row.get("first_seen"))
            published.append(video)
        published.sort(key=lambda video: str(video["first_seen"]), reverse=True)
        return {
            "version": STATE_VERSION,
            "cursor": 0,
            "done": sorted({str(video["vid"]) for video in published}),
            "published": published[:RSS_LIMIT],
        }
    if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
        raise ValueError("Unsupported state format")
    cursor = raw.get("cursor")
    if type(cursor) is not int or cursor < 0:
        raise ValueError("Invalid catalogue cursor")
    done = raw.get("done")
    if not isinstance(done, list) or not all(
        isinstance(vid, str) and VID_PATTERN.fullmatch(vid) for vid in done
    ):
        raise ValueError("Invalid published video IDs")
    published = raw.get("published")
    if not isinstance(published, list):
        raise ValueError("Invalid published video list")
    history: list[Video] = []
    for row in published:
        video = normalize_video(row)
        video["first_seen"] = require_timestamp(row.get("first_seen"))
        history.append(video)
    return {
        "version": STATE_VERSION,
        "cursor": cursor,
        "done": done,
        "published": history,
    }


def select_batch(
    done: set[str],
    cursor: int,
    recent: list[Video],
    page: list[Video],
    limit: int,
) -> tuple[list[Video], int]:
    """Pick this run's videos and the next catalogue cursor.

    Recent uploads are considered first, then the ranked page that starts at
    ``cursor``. Both lanes share ``limit``. The cursor moves past every page
    entry that is already published or selected in this run, so a shifting
    catalogue cannot make it skip or repeat a video.

    Args:
        done: Video IDs already published.
        cursor: Current offset in the score-ordered catalogue.
        recent: Newest uploads, newest first.
        page: Catalogue window that starts at ``cursor``.
        limit: Maximum number of videos to select.

    Returns:
        The selected videos and the next catalogue cursor.
    """
    selected: list[Video] = []
    queued: set[str] = set()
    for video in recent + page:
        vid = str(video["vid"])
        if vid in done or vid in queued:
            continue
        queued.add(vid)
        selected.append(video)
        if len(selected) >= limit:
            break
    next_cursor = cursor
    for index, video in enumerate(page):
        vid = str(video["vid"])
        if vid in done or vid in queued:
            next_cursor = cursor + index + 1
        else:
            break
    return selected, next_cursor


def render_rss(videos: list[Video], feed_url: str) -> bytes:
    """Render the most recent discoveries with evidence and stable IDs."""
    ET.register_namespace("atom", ATOM)
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    for tag, value in (
        ("title", "HackerTube"),
        ("link", "https://hackertube.org/"),
        ("description", "HackerTube video discoveries: summaries, HN recommendations, and public metadata."),
    ):
        ET.SubElement(channel, tag).text = value
    ET.SubElement(channel, f"{{{ATOM}}}link", href=feed_url, rel="self", type="application/rss+xml")
    for video in videos[:RSS_LIMIT]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(video["title"])
        ET.SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video['vid']}"
        ET.SubElement(item, "guid", isPermaLink="false").text = f"hackertube:{video['vid']}"
        discovered = datetime.fromisoformat(str(video["first_seen"])).astimezone(timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(discovered, usegmt=True)
        paragraphs = []
        for label, field in (
            ("Summary", "summary"), ("Why HN recommends it", "why_hn"), ("Channel", "channel"),
            ("Original publication date", "published"), ("Duration (seconds)", "duration_s"),
            ("Content type", "content_type"), ("Level", "level"),
            ("Shelf life", "shelf_life"), ("Topic", "primary_topic"),
        ):
            if video.get(field):
                escaped = html.escape(str(video[field])).replace("\n", "<br>")
                paragraphs.append(f"<p><strong>{label}</strong>: {escaped}</p>")
        ET.SubElement(item, "description").text = "\n".join(paragraphs)
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    """Fetch both catalogue lanes and write state plus publishable files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="HackerTube API root, e.g. https://hackertube.org/api")
    parser.add_argument("--feed-url", required=True)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--daily-limit", required=True, type=int)
    parser.add_argument("--recent-window", type=int, default=50)
    args = parser.parse_args()
    if args.daily_limit < 1:
        raise SystemExit("--daily-limit must be positive")
    if args.recent_window < args.daily_limit:
        raise SystemExit("--recent-window must be at least --daily-limit")

    state = load_state(args.state)
    done = set(str(vid) for vid in state["done"])
    cursor = int(state["cursor"])

    recent = fetch_videos(
        f"{args.api_base}/list?{urlencode({'sort': 'date', 'n': args.recent_window, 'offset': 0})}",
        "recent uploads",
    )
    window = max(3 * args.daily_limit, 20)
    page = fetch_videos(
        f"{args.api_base}/list?{urlencode({'n': window, 'offset': cursor})}",
        "ranked catalogue",
        allow_empty=True,
    )

    selected, next_cursor = select_batch(done, cursor, recent, page, args.daily_limit)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    published = [dict(video, first_seen=now) for video in selected] + list(state["published"])
    new_state: State = {
        "version": STATE_VERSION,
        "cursor": next_cursor,
        "done": sorted(done | {str(video["vid"]) for video in selected}),
        "published": published[:RSS_LIMIT],
    }
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rss = render_rss(published, args.feed_url)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "hackertube.xml").write_bytes(rss)
    (args.output_dir / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>feed</title>'
        '<h1>Public feeds</h1><p><a href="hackertube.xml">HackerTube RSS</a></p>'
        '<p><a href="https://github.com/mxzel/feed">Source and documentation</a></p></html>\n',
        encoding="utf-8",
    )
    print(
        f"Published {len(selected)} videos; cursor {cursor} -> {next_cursor}; "
        f"{len(published[:RSS_LIMIT])} entries in RSS; {len(new_state['done'])} known IDs"
    )


if __name__ == "__main__":
    main()
