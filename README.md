# feed

Feed converters for public sources that do not provide usable RSS feeds.

Each source has its own converter. GitHub Actions fetches public content on a schedule, generates RSS, and publishes it through GitHub Pages at a stable URL.

## Public content only

**`mxzel/feed` is a public repository. Treat its code, commit history, state files, Actions logs, and Pages output as public.**

Store only converter code and the public metadata required to build feeds. Never upload credentials, tokens, cookies, account exports, private subscriptions, reading history, personal profiles, private notes, or internal material. Do not copy configuration, data directories, or runtime logs wholesale from other projects.

## Feeds

- [HackerTube RSS](https://mxzel.github.io/feed/hackertube.xml)
- [Feed index](https://mxzel.github.io/feed/)

The HackerTube converter preserves each video's summary, HN recommendation rationale, channel, duration, level, and topic.
The source provides the summaries and recommendation rationale. They are not full transcripts.
Recommendations include older videos. RSS publication dates use the time this converter first discovered a video; the original publication date appears in the item body.
Video IDs identify entries. The RSS feed contains the 200 most recently discovered videos.

## Persistent state

`data/hackertube.json` stores previously discovered video IDs, their first discovery timestamps, and the public metadata needed to rebuild the feed.
Each Actions run starts in a fresh environment. Committing this state lets later runs recognize existing videos and preserve their dates.
The state retains older recommendations even when they disappear from the current API response. Only the latest 200 discoveries appear in RSS.
The converter copies an explicit list of public fields. This file contains no account data, private subscriptions, or reading history.

## Updates and publishing

`.github/workflows/publish.yml` runs daily at 00:17 UTC (08:17 UTC+8).
Changes to converters or the workflow also trigger a run. To start one manually, select **Update feeds and publish** in the Actions tab, or run:

```sh
gh workflow run publish.yml -R mxzel/feed
```

1. Run offline tests.
2. Build RSS from the public API.
3. Commit public video state to `data/hackertube.json`.
4. Upload only `public/` and deploy it to GitHub Pages.

If an API request or response validation fails, publishing stops and the previous site remains available.
Scheduled runs may be delayed. GitHub disables scheduled workflows in public repositories after 60 days without repository activity.
The default workflow token is read-only. The state update and deployment jobs request their required permissions separately.

## Local usage

Requires Python 3.10+ and its standard library. No third-party dependencies are required.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/hackertube.py \
  --api-url https://hackertube.org/api/feed \
  --feed-url https://mxzel.github.io/feed/hackertube.xml \
  --state data/hackertube.json \
  --output-dir public
```

`public/` contains generated files and is not committed. When adding a converter, reuse the workflow and write only publishable files to this directory.
