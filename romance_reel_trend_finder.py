#!/usr/bin/env python3
"""
Trending Romance/Couple Reel Finder
====================================
Finds trending video posts (the closest available signal to "Reels") across
a curated set of romance/couple-themed hashtags, using Instagram's official
Graph API (Hashtag Search). Returns rankings, permalinks, and captions so you
can see what's resonating and make your OWN romantic couple reel in that
style. It does NOT download any video and does NOT repost anyone else's
content — doing that without the creator's permission is copyright
infringement and against Instagram's Terms of Service.

Setup: identical to instagram_trend_research.py — you need your own
Instagram Business/Creator account, a linked Facebook Page, and a long-lived
Graph API access token with instagram_basic + instagram_manage_insights
scopes. See that script's README for the full one-time setup walkthrough.
Docs: https://developers.facebook.com/docs/instagram-api/guides/hashtag-search

Note on filtering: the Hashtag Search media edge doesn't expose a dedicated
"is this a Reel" flag, so this script uses media_type == "VIDEO" as the
closest available proxy. Pass --all-media-types to include photos/carousels.

Usage:
  export IG_ACCESS_TOKEN="your_long_lived_token"
  export IG_BUSINESS_ID="your_ig_business_account_id"

  python romance_reel_trend_finder.py
  python romance_reel_trend_finder.py --hashtags couplegoals romantic --csv report.csv
"""

import argparse
import csv
import os
import re
import sys
import time
from collections import Counter

import requests

GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

DEFAULT_HASHTAGS = [
    "couplegoals",
    "romantic",
    "relationshipgoals",
    "lovestory",
    "coupledance",
    "boyfriendgirlfriend",
    "longdistancerelationship",
    "romancereels",
    "cutecouple",
    "datenight",
]


class HashtagTrendClient:
    def __init__(self, access_token, ig_business_account_id):
        self.access_token = access_token
        self.ig_business_account_id = ig_business_account_id

    def _get(self, url, params):
        params = {**params, "access_token": self.access_token}
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise RuntimeError(f"Graph API error ({err.get('code')}): {err.get('message')}")
        return data

    def resolve_hashtag_id(self, hashtag):
        data = self._get(f"{BASE_URL}/ig_hashtag_search", {
            "user_id": self.ig_business_account_id,
            "q": hashtag,
        })
        results = data.get("data", [])
        return results[0]["id"] if results else None

    def hashtag_media(self, hashtag, mode="top", limit=25):
        hashtag_id = self.resolve_hashtag_id(hashtag)
        if not hashtag_id:
            return []
        edge = "top_media" if mode == "top" else "recent_media"
        data = self._get(f"{BASE_URL}/{hashtag_id}/{edge}", {
            "user_id": self.ig_business_account_id,
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count",
            "limit": limit,
        })
        return data.get("data", [])


def extract_hashtags(caption):
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


def find_trending_reels(client, hashtags, mode="top", limit_per_tag=25,
                         reels_only=True, min_engagement=0, request_delay=0.5):
    seen_ids = set()
    results = []

    for tag in hashtags:
        try:
            media = client.hashtag_media(tag, mode=mode, limit=limit_per_tag)
        except RuntimeError as e:
            print(f"  [warn] #{tag}: {e}", file=sys.stderr)
            continue

        for m in media:
            media_id = m.get("id")
            if media_id in seen_ids:
                continue
            if reels_only and m.get("media_type") != "VIDEO":
                continue
            seen_ids.add(media_id)

            likes = m.get("like_count", 0) or 0
            comments = m.get("comments_count", 0) or 0
            engagement = likes + comments
            if engagement < min_engagement:
                continue

            caption = m.get("caption", "") or ""
            results.append({
                "source_hashtag": tag,
                "permalink": m.get("permalink"),
                "timestamp": m.get("timestamp"),
                "like_count": likes,
                "comments_count": comments,
                "engagement": engagement,
                "caption_preview": caption[:140].replace("\n", " "),
                "hashtags": extract_hashtags(caption),
            })

        time.sleep(request_delay)  # be polite to the API

    results.sort(key=lambda x: x["engagement"], reverse=True)
    return results


def print_report(results, top_n=15):
    print(f"\n{'=' * 70}")
    print("TRENDING ROMANCE/COUPLE REELS")
    print(f"{'=' * 70}")
    print(f"Total unique candidates found: {len(results)}\n")

    tag_counter = Counter()
    for r in results:
        tag_counter.update(r["hashtags"])

    if tag_counter:
        print("Hashtags co-occurring most often in these reels:")
        for tag, count in tag_counter.most_common(10):
            print(f"  #{tag:<25} {count}x")
        print()

    print(f"Top {min(top_n, len(results))} by engagement (likes + comments):\n")
    for i, r in enumerate(results[:top_n], 1):
        print(f"{i}. {r['engagement']} engagement ({r['like_count']} likes, "
              f"{r['comments_count']} comments) — found via #{r['source_hashtag']}")
        print(f"   {r['timestamp']}")
        print(f"   {r['permalink']}")
        if r["caption_preview"]:
            print(f"   \"{r['caption_preview']}...\"")
        print()


def save_csv(results, filename):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "engagement", "like_count", "comments_count",
                          "source_hashtag", "timestamp", "permalink", "hashtags", "caption_preview"])
        for i, r in enumerate(results, 1):
            writer.writerow([
                i, r["engagement"], r["like_count"], r["comments_count"],
                r["source_hashtag"], r["timestamp"], r["permalink"],
                " ".join(r["hashtags"]), r["caption_preview"],
            ])
    print(f"Saved CSV -> {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Find trending romance/couple Reels via Instagram's official "
                    "Graph API hashtag search. Returns links + metadata only — "
                    "does not download or repost anyone else's video."
    )
    parser.add_argument("--token", default=os.environ.get("IG_ACCESS_TOKEN"),
                        help="Long-lived access token (or set IG_ACCESS_TOKEN env var)")
    parser.add_argument("--ig-id", default=os.environ.get("IG_BUSINESS_ID"),
                        help="Your Instagram Business Account ID (or set IG_BUSINESS_ID env var)")
    parser.add_argument("--hashtags", nargs="+", default=DEFAULT_HASHTAGS,
                        help=f"Hashtags to search (default: {', '.join(DEFAULT_HASHTAGS)})")
    parser.add_argument("--mode", choices=["top", "recent"], default="top",
                        help="Hashtag media edge to use (default: top)")
    parser.add_argument("--limit-per-tag", type=int, default=25,
                        help="Max posts to pull per hashtag (default: 25)")
    parser.add_argument("--min-engagement", type=int, default=0,
                        help="Filter out posts below this like+comment count")
    parser.add_argument("--all-media-types", action="store_true",
                        help="Include images/carousels too, not just videos/reels")
    parser.add_argument("--top-n", type=int, default=15, help="How many results to print")
    parser.add_argument("--csv", help="Optional path to save full results as CSV")
    args = parser.parse_args()

    if not args.token or not args.ig_id:
        print("Error: missing --token/--ig-id (or IG_ACCESS_TOKEN/IG_BUSINESS_ID env vars).",
              file=sys.stderr)
        sys.exit(1)

    # Hashtag lookups are capped at 30 unique hashtags per 7-day rolling
    # window per querying IG Business Account.
    if len(args.hashtags) > 30:
        print("Warning: Instagram caps hashtag lookups at 30 unique hashtags "
              "per 7-day window. Trimming to first 30.", file=sys.stderr)
        args.hashtags = args.hashtags[:30]

    client = HashtagTrendClient(args.token, args.ig_id)

    print(f"Searching {len(args.hashtags)} hashtag(s): {', '.join(args.hashtags)}")
    results = find_trending_reels(
        client,
        args.hashtags,
        mode=args.mode,
        limit_per_tag=args.limit_per_tag,
        reels_only=not args.all_media_types,
        min_engagement=args.min_engagement,
    )

    if not results:
        print("No matching reels found. Try --all-media-types or different hashtags.")
        sys.exit(0)

    print_report(results, top_n=args.top_n)

    if args.csv:
        save_csv(results, args.csv)


if __name__ == "__main__":
    main()
