"""Convert public HackerTube recommendations into a persistent RSS feed."""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.request import Request, urlopen

TEXT_FIELDS = (
    "title", "channel", "published", "summary", "why_hn", "content_type",
    "level", "shelf_life", "primary_topic",
)
ATOM = "http://www.w3.org/2005/Atom"
Video = dict[str, str | int]


def merge_videos(previous: list[Video], incoming: object, now: str) -> list[Video]:
    """Merge public metadata by video ID while preserving discovery dates.

    Args:
        previous: Previously discovered public videos.
        incoming: Decoded API response, expected to be a list of videos.
        now: UTC discovery timestamp for videos not seen before.

    Returns:
        All discovered videos, sorted newest first.

    Raises:
        ValueError: A response or video does not match the public data format.
    """
    if not isinstance(previous, list) or not isinstance(incoming, list) or not incoming:
        raise ValueError("Expected a non-empty list of public videos")
    by_id: dict[str, Video] = {}
    for index, row in enumerate(previous + incoming):
        if not isinstance(row, dict) or not isinstance(row.get("vid"), str):
            raise ValueError("Video is missing its ID")
        vid = row["vid"]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) is None:
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
        first_seen = row.get("first_seen") if index < len(previous) else now
        video["first_seen"] = by_id.get(vid, {}).get("first_seen", first_seen)
        timestamp = datetime.fromisoformat(str(video["first_seen"]))
        if timestamp.utcoffset() is None:
            raise ValueError("Discovery timestamps must include a timezone")
        by_id[vid] = video
    return sorted(by_id.values(), key=lambda video: (str(video["first_seen"]), str(video["vid"])), reverse=True)


def render_rss(videos: list[Video], feed_url: str) -> bytes:
    """Render recent discoveries with both evidence fields and stable IDs."""
    ET.register_namespace("atom", ATOM)
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    for tag, value in (
        ("title", "HackerTube"),
        ("link", "https://hackertube.org/"),
        ("description", "HackerTube 视频发现：简介、HN 推荐理由和公开元数据。"),
    ):
        ET.SubElement(channel, tag).text = value
    ET.SubElement(channel, f"{{{ATOM}}}link", href=feed_url, rel="self", type="application/rss+xml")
    for video in videos[:200]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(video["title"])
        ET.SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video['vid']}"
        ET.SubElement(item, "guid", isPermaLink="false").text = f"hackertube:{video['vid']}"
        discovered = datetime.fromisoformat(str(video["first_seen"])).astimezone(timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(discovered, usegmt=True)
        paragraphs = []
        for label, field in (
            ("简介", "summary"), ("HN 推荐理由", "why_hn"), ("频道", "channel"),
            ("原始发布时间", "published"), ("时长（秒）", "duration_s"),
            ("内容类型", "content_type"), ("难度", "level"),
            ("时效类型", "shelf_life"), ("主题", "primary_topic"),
        ):
            if video.get(field):
                escaped = html.escape(str(video[field])).replace("\n", "<br>")
                paragraphs.append(f"<p><strong>{label}</strong>：{escaped}</p>")
        ET.SubElement(item, "description").text = "\n".join(paragraphs)
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    """Fetch public recommendations and write state plus publishable files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--feed-url", required=True)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    previous = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else []
    request = Request(args.api_url, headers={"Accept": "application/json", "User-Agent": "mxzel-feed/1.0"})
    with urlopen(request, timeout=30) as response:
        incoming = json.load(response)
    videos = merge_videos(previous, incoming, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    rss = render_rss(videos, args.feed_url)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(videos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "hackertube.xml").write_bytes(rss)
    (args.output_dir / "index.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>feed</title>'
        '<h1>公开订阅源</h1><p><a href="hackertube.xml">HackerTube RSS</a></p>'
        '<p><a href="https://github.com/mxzel/feed">源码与说明</a></p></html>\n',
        encoding="utf-8",
    )
    print(f"Built RSS: {min(len(videos), 200)} entries; {len(videos)} known video IDs")


if __name__ == "__main__":
    main()
