"""Check feed content and discovery timestamps without network access."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from scripts.hackertube import merge_videos, render_rss


class HackerTubeTests(unittest.TestCase):
    """Cover repeated recommendations and RSS content preservation."""

    def setUp(self) -> None:
        """Create a public video fixture."""
        self.video = {
            "vid": "abcdefghijk",
            "title": "C & Python",
            "channel": "Example Channel",
            "published": "2005-01-01T00:00:00Z",
            "duration_s": 600,
            "summary": "Explains <interfaces> & testing.",
            "why_hn": "A concrete implementation walkthrough.",
            "level": "intermediate",
            "primary_topic": "programming",
            "unexpected_private_field": "must not be copied",
        }

    def test_repeated_video_keeps_discovery_time_and_allowlisted_fields(self) -> None:
        """Refresh public metadata without changing the discovery date."""
        first = merge_videos([], [self.video], "2026-11-05T00:00:00+00:00")
        updated = dict(self.video, summary="Updated description.")
        second = merge_videos(first, [updated, updated], "2026-11-06T00:00:00+00:00")
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["first_seen"], first[0]["first_seen"])
        self.assertEqual(second[0]["summary"], "Updated description.")
        self.assertNotIn("unexpected_private_field", second[0])

    def test_rss_preserves_evidence_and_original_video_date(self) -> None:
        """Publish both evidence fields with safe HTML and stable identity."""
        videos = merge_videos([], [self.video], "2026-11-05T00:00:00+00:00")
        root = ET.fromstring(render_rss(videos, "https://example.org/hackertube.xml"))
        item = root.find("channel/item")
        self.assertIsNotNone(item)
        self.assertEqual(item.findtext("title"), self.video["title"])
        self.assertEqual(item.findtext("guid"), "hackertube:abcdefghijk")
        self.assertEqual(item.findtext("pubDate"), "Thu, 05 Nov 2026 00:00:00 GMT")
        description = item.findtext("description")
        self.assertIn("&lt;interfaces&gt; &amp; testing", description)
        self.assertIn(self.video["why_hn"], description)
        self.assertIn(self.video["published"], description)

    def test_missing_videos_remain_and_invalid_payload_fails(self) -> None:
        """Keep old recommendations and reject non-video API responses."""
        previous = merge_videos([], [self.video], "2026-11-05T00:00:00+00:00")
        newer = dict(self.video, vid="lmnopqrstuv")
        combined = merge_videos(previous, [newer], "2026-11-06T00:00:00+00:00")
        self.assertEqual(len(combined), 2)
        with self.assertRaises(ValueError):
            merge_videos(previous, {"error": "upstream failure"}, "2026-11-06T00:00:00+00:00")
        with self.assertRaises(ValueError):
            merge_videos(previous, [dict(self.video, vid="../invalid")], "2026-11-06T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
