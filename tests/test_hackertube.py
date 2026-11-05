"""Check pacing, cursor movement, and RSS content without network access."""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.hackertube import (
    load_state,
    normalize_video,
    render_rss,
    select_batch,
)


def make_video(vid: str, title: str = "Talk") -> dict:
    """Build a minimal public video record."""
    return {
        "vid": vid,
        "title": title,
        "channel": "Example Channel",
        "published": "2005-01-01T00:00:00Z",
        "duration_s": 600,
        "summary": "Explains <interfaces> & testing.",
        "why_hn": "A concrete implementation walkthrough.",
        "level": "intermediate",
        "primary_topic": "programming",
        "unexpected_private_field": "must not be copied",
    }


class NormalizeVideoTests(unittest.TestCase):
    """Cover field allowlisting and response validation."""

    def test_copies_only_allowlisted_fields(self) -> None:
        """Drop fields that the feed does not need."""
        video = normalize_video(make_video("abcdefghijk"))
        self.assertNotIn("unexpected_private_field", video)
        self.assertEqual(video["vid"], "abcdefghijk")

    def test_rejects_invalid_records(self) -> None:
        """Fail on a bad ID, missing evidence, or a negative duration."""
        with self.assertRaises(ValueError):
            normalize_video(make_video("../invalid"))
        with self.assertRaises(ValueError):
            normalize_video(dict(make_video("abcdefghijk"), title=""))
        with self.assertRaises(ValueError):
            normalize_video(dict(make_video("abcdefghijk"), duration_s=-1))
        with self.assertRaises(ValueError):
            normalize_video({"error": "upstream failure"})


class SelectBatchTests(unittest.TestCase):
    """Cover the shared daily budget and the catalogue cursor."""

    def test_recent_uploads_come_first(self) -> None:
        """Publish unseen recent uploads before the ranked backlog."""
        recent = [make_video("aaaaaaaaaaa"), make_video("bbbbbbbbbbb")]
        page = [make_video("ccccccccccc")]
        selected, cursor = select_batch(set(), 0, recent, page, 2)
        self.assertEqual([video["vid"] for video in selected], ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        self.assertEqual(cursor, 0)

    def test_budget_is_shared_and_cursor_advances(self) -> None:
        """Move the cursor past entries that are published or already known."""
        page = [make_video("ccccccccccc"), make_video("ddddddddddd"), make_video("eeeeeeeeeee")]
        selected, cursor = select_batch({"ccccccccccc"}, 10, [], page, 1)
        self.assertEqual([video["vid"] for video in selected], ["ddddddddddd"])
        self.assertEqual(cursor, 12)

    def test_cursor_stops_before_unpublished_entry(self) -> None:
        """Leave the cursor on the first entry that the budget cannot cover."""
        page = [make_video("ccccccccccc"), make_video("ddddddddddd")]
        selected, cursor = select_batch(set(), 7, [], page, 1)
        self.assertEqual([video["vid"] for video in selected], ["ccccccccccc"])
        self.assertEqual(cursor, 8)

    def test_duplicates_across_lanes_are_emitted_once(self) -> None:
        """Deduplicate a video that appears in both the recent and ranked lanes."""
        video = make_video("ccccccccccc")
        selected, cursor = select_batch(set(), 3, [video], [video], 5)
        self.assertEqual(len(selected), 1)
        self.assertEqual(cursor, 4)

    def test_exhausted_catalogue_keeps_cursor(self) -> None:
        """Return no videos and no movement when the page is empty."""
        selected, cursor = select_batch({"ccccccccccc"}, 42, [], [], 5)
        self.assertEqual(selected, [])
        self.assertEqual(cursor, 42)


class StateTests(unittest.TestCase):
    """Cover state defaults and version 1 migration."""

    def test_missing_state_starts_empty(self) -> None:
        """Create an empty state before the first run."""
        with tempfile.TemporaryDirectory() as directory:
            state = load_state(Path(directory) / "missing.json")
        self.assertEqual(state["cursor"], 0)
        self.assertEqual(state["done"], [])
        self.assertEqual(state["published"], [])

    def test_version_one_list_is_migrated(self) -> None:
        """Convert the flat discovery list into the paced state format."""
        rows = [
            dict(make_video("aaaaaaaaaaa"), first_seen="2026-11-05T00:00:00+00:00"),
            dict(make_video("bbbbbbbbbbb"), first_seen="2026-11-06T00:00:00+00:00"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            state = load_state(path)
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["done"], ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        self.assertEqual(state["published"][0]["vid"], "bbbbbbbbbbb")


class RenderRssTests(unittest.TestCase):
    """Cover evidence preservation and stable identity."""

    def test_rss_preserves_evidence_and_original_video_date(self) -> None:
        """Publish both evidence fields with safe HTML and stable identity."""
        video = dict(normalize_video(make_video("abcdefghijk")), first_seen="2026-11-05T00:00:00+00:00")
        root = ET.fromstring(render_rss([video], "https://example.org/hackertube.xml"))
        item = root.find("channel/item")
        assert item is not None
        self.assertEqual(item.findtext("guid"), "hackertube:abcdefghijk")
        self.assertEqual(item.findtext("pubDate"), "Thu, 05 Nov 2026 00:00:00 GMT")
        description = item.findtext("description") or ""
        self.assertIn("&lt;interfaces&gt; &amp; testing", description)
        self.assertIn(str(video["why_hn"]), description)
        self.assertIn(str(video["published"]), description)


if __name__ == "__main__":
    unittest.main()
