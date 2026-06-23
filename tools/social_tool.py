"""
Social media tools for Wade — trend research, content saving, and posting
to Facebook, Instagram. TikTok and YouTube are script/idea only (no posting API).
"""
import os
import sys
import json as _json
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    TAVILY_API_KEY,
    META_PAGE_ACCESS_TOKEN, META_PAGE_ID, META_INSTAGRAM_ACCOUNT_ID,
    META_AD_ACCOUNT_ID,
    GENERATED_DOCS_DIR,
)

CONTENT_DIR = os.path.join(GENERATED_DOCS_DIR, "Wade")

DEFINITIONS = [
    {
        "name": "trends_research",
        "description": (
            "Search for trending topics, viral content formats, and what's performing well "
            "on social media in a given niche and platform. Use this before brainstorming "
            "content ideas to ground them in what's actually working right now."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "niche": {
                    "type": "string",
                    "description": "Topic or industry to research (e.g. 'IT services', 'small business', 'cybersecurity').",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform focus: 'instagram', 'tiktok', 'youtube', 'facebook', or 'general'.",
                },
                "region": {
                    "type": "string",
                    "description": "Country/region to focus on (e.g. 'Australia', 'global'). Defaults to Australia.",
                },
            },
            "required": ["niche"],
        },
    },
    {
        "name": "content_save",
        "description": (
            "Save a piece of content — post copy, video script, or video idea — to Wade's content library. "
            "Use this after drafting any content so Ky can review it and it persists across sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content_type": {
                    "type": "string",
                    "enum": ["post", "script", "video_idea", "campaign"],
                    "description": "Type of content being saved.",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the piece (used as filename).",
                },
                "platform": {
                    "type": "string",
                    "description": "Target platform: instagram, facebook, tiktok, youtube, or general.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content — post copy, script, or idea outline.",
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "approved", "posted"],
                    "description": "Current status of the content.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the content (strategy rationale, target audience, etc.).",
                },
            },
            "required": ["content_type", "title", "platform", "content"],
        },
    },
    {
        "name": "facebook_post",
        "description": (
            "Post content to the KLJ Facebook Page. "
            "NEVER call this unless Ky has explicitly approved the exact content. "
            "Set approved=true only after Ky has confirmed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The post text to publish.",
                },
                "link": {
                    "type": "string",
                    "description": "Optional URL to attach to the post.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "Must be true — only set after Ky has confirmed the content.",
                },
            },
            "required": ["message", "approved"],
        },
    },
    {
        "name": "instagram_post",
        "description": (
            "Post an image with caption to the KLJ Instagram Business account. "
            "Requires a publicly accessible image URL. "
            "NEVER call this unless Ky has explicitly approved the exact content. "
            "Set approved=true only after Ky has confirmed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "The caption to post with the image (include hashtags here).",
                },
                "image_url": {
                    "type": "string",
                    "description": "Publicly accessible URL of the image to post (must end in .jpg/.png or similar).",
                },
                "approved": {
                    "type": "boolean",
                    "description": "Must be true — only set after Ky has confirmed the content.",
                },
            },
            "required": ["caption", "image_url", "approved"],
        },
    },
    {
        "name": "meta_ads_overview",
        "description": (
            "Get Facebook/Instagram ad account performance — total spend, impressions, reach, "
            "clicks, CPM, CPC, and purchase conversions/ROAS if running conversion campaigns. "
            "Use to review paid ad performance and return on ad spend."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["last_7_days", "last_14_days", "last_30_days", "last_month", "this_month"],
                    "description": "Reporting period. Defaults to last_7_days.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "meta_ads_top_creatives",
        "description": (
            "List top performing ads sorted by spend, with impressions, clicks, CTR, and ROAS. "
            "Use to identify which creatives are working and which to pause."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["last_7_days", "last_14_days", "last_30_days", "last_month", "this_month"],
                    "description": "Reporting period. Defaults to last_7_days.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max ads to return. Defaults to 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "meta_page_analytics",
        "description": (
            "Get Facebook Page performance metrics — impressions, reach, engaged users, new page likes, "
            "page views, and recent post engagement. Use to review how KLJ's Facebook presence is performing "
            "and identify which posts got the most traction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["day", "week", "month"],
                    "description": "Reporting period for account-level metrics. Defaults to week.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "meta_instagram_analytics",
        "description": (
            "Get Instagram account performance metrics — impressions, reach, profile views — "
            "plus recent post engagement (likes and comments). Use to review how KLJ's Instagram is performing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back for account-level insights. Defaults to 7.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "content_list",
        "description": "List saved content from Wade's content library, optionally filtered by type, platform, or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_type": {
                    "type": "string",
                    "description": "Filter by type: post, script, video_idea, campaign. Omit for all.",
                },
                "platform": {
                    "type": "string",
                    "description": "Filter by platform. Omit for all.",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: draft, approved, posted. Omit for all.",
                },
            },
            "required": [],
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    if not TAVILY_API_KEY:
        return []
    import urllib.request
    payload = _json.dumps({
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
    }).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _json.loads(r.read()).get("results", [])
    except Exception as e:
        return [{"title": "Search error", "content": str(e), "url": ""}]


def _meta_post(endpoint: str, params: dict) -> dict:
    import urllib.request, urllib.parse
    if not META_PAGE_ACCESS_TOKEN:
        raise ValueError("META_PAGE_ACCESS_TOKEN not set in .env")
    params["access_token"] = META_PAGE_ACCESS_TOKEN
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"https://graph.facebook.com/v19.0/{endpoint}",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return _json.loads(r.read())


def _meta_get(endpoint: str, params: dict) -> dict:
    import urllib.request, urllib.parse
    if not META_PAGE_ACCESS_TOKEN:
        raise ValueError("META_PAGE_ACCESS_TOKEN not set in .env")
    params["access_token"] = META_PAGE_ACCESS_TOKEN
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"https://graph.facebook.com/v19.0/{endpoint}?{qs}",
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return _json.loads(r.read())


def _safe_filename(title: str) -> str:
    return re.sub(r'[^\w\-_]', '_', title.lower().strip())[:60]


# ── Handler ───────────────────────────────────────────────────────────────────

def handle(name: str, inputs: dict) -> str:

    if name == "trends_research":
        niche    = inputs.get("niche", "")
        platform = inputs.get("platform", "general")
        region   = inputs.get("region", "Australia")

        queries = [
            f"trending {platform} content {niche} {region} 2025",
            f"viral {niche} posts {platform} what's working",
            f"{niche} content strategy {platform} top performing formats",
        ]

        all_results = []
        for q in queries:
            all_results.extend(_tavily_search(q, max_results=3))

        if not all_results:
            return "No trend data found — check TAVILY_API_KEY in .env."

        lines = [f"TREND RESEARCH — {niche.upper()} on {platform.upper()} ({region})\n"]
        seen = set()
        for r in all_results:
            url = r.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            lines.append(f"• {r.get('title', 'No title')}")
            content = r.get("content", "")[:200]
            if content:
                lines.append(f"  {content}")
            if url:
                lines.append(f"  {url}")
            lines.append("")

        return "\n".join(lines)

    if name == "content_save":
        os.makedirs(CONTENT_DIR, exist_ok=True)

        content_type = inputs.get("content_type", "post")
        title        = inputs.get("title", "untitled")
        platform     = inputs.get("platform", "general")
        content      = inputs.get("content", "")
        status       = inputs.get("status", "draft")
        notes        = inputs.get("notes", "")

        from datetime import date
        filename = f"{date.today()}_{_safe_filename(title)}_{platform}.md"
        filepath = os.path.join(CONTENT_DIR, filename)

        frontmatter = f"""---
title: {title}
type: {content_type}
platform: {platform}
status: {status}
date: {date.today()}
---

"""
        body = content
        if notes:
            body += f"\n\n---\n**Notes:** {notes}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + body)

        return f"Saved {content_type} '{title}' ({platform}, {status}) → {filepath}"

    if name == "facebook_post":
        if not inputs.get("approved"):
            return "Cannot post — approved must be true. Show Ky the content and wait for explicit confirmation."
        if not META_PAGE_ID:
            return "META_PAGE_ID not set in .env — Facebook posting not configured."
        message = inputs.get("message", "")
        params  = {"message": message}
        if inputs.get("link"):
            params["link"] = inputs["link"]
        try:
            result = _meta_post(f"{META_PAGE_ID}/feed", params)
            post_id = result.get("id", "unknown")
            return f"Posted to Facebook Page. Post ID: {post_id}"
        except Exception as e:
            return f"Facebook post failed: {e}"

    if name == "instagram_post":
        if not inputs.get("approved"):
            return "Cannot post — approved must be true. Show Ky the content and wait for explicit confirmation."
        if not META_INSTAGRAM_ACCOUNT_ID:
            return "META_INSTAGRAM_ACCOUNT_ID not set in .env — Instagram posting not configured."
        caption   = inputs.get("caption", "")
        image_url = inputs.get("image_url", "")
        if not image_url:
            return "image_url is required for Instagram posts."
        try:
            # Step 1 — create media container
            container = _meta_post(f"{META_INSTAGRAM_ACCOUNT_ID}/media", {
                "image_url": image_url,
                "caption":   caption,
            })
            creation_id = container.get("id")
            if not creation_id:
                return f"Failed to create Instagram media container: {container}"
            # Step 2 — publish
            result = _meta_post(f"{META_INSTAGRAM_ACCOUNT_ID}/media_publish", {
                "creation_id": creation_id,
            })
            post_id = result.get("id", "unknown")
            return f"Posted to Instagram. Post ID: {post_id}"
        except Exception as e:
            return f"Instagram post failed: {e}"

    if name == "meta_ads_overview":
        if not META_AD_ACCOUNT_ID:
            return "META_AD_ACCOUNT_ID not set in .env — add your ad account ID (digits only, no 'act_' prefix)."
        period = inputs.get("period", "last_7_days")
        try:
            fields = "spend,impressions,reach,clicks,cpm,cpc,actions,action_values"
            data = _meta_get(f"act_{META_AD_ACCOUNT_ID}/insights", {
                "fields": fields,
                "date_preset": period,
                "level": "account",
            })
            rows = data.get("data", [])
            if not rows:
                return f"No ad data found for {period}. Ad account may have no activity in this period."
            row = rows[0]
            spend = float(row.get("spend", 0))
            impressions = int(row.get("impressions", 0))
            reach = int(row.get("reach", 0))
            clicks = int(row.get("clicks", 0))
            cpm = float(row.get("cpm", 0))
            cpc = float(row.get("cpc", 0))
            ctr = (clicks / impressions * 100) if impressions else 0

            # Extract purchase conversions and value
            actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
            action_values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
            purchases = actions.get("purchase", 0)
            purchase_value = action_values.get("purchase", 0)
            roas = (purchase_value / spend) if spend > 0 else 0

            lines = [f"META ADS OVERVIEW — {period.replace('_', ' ')}\n"]
            lines.append(f"  Spend:       ${spend:,.2f}")
            lines.append(f"  Impressions: {impressions:,}")
            lines.append(f"  Reach:       {reach:,}")
            lines.append(f"  Clicks:      {clicks:,}  (CTR: {ctr:.2f}%)")
            lines.append(f"  CPM:         ${cpm:.2f}")
            lines.append(f"  CPC:         ${cpc:.2f}")
            if purchases:
                lines.append(f"  Purchases:   {int(purchases)}")
                lines.append(f"  Revenue:     ${purchase_value:,.2f}")
                lines.append(f"  ROAS:        {roas:.2f}x")
            return "\n".join(lines)
        except Exception as e:
            return f"Meta ads overview failed: {e}"

    if name == "meta_ads_top_creatives":
        if not META_AD_ACCOUNT_ID:
            return "META_AD_ACCOUNT_ID not set in .env"
        period = inputs.get("period", "last_7_days")
        limit = int(inputs.get("limit", 10))
        try:
            fields = "ad_name,spend,impressions,clicks,ctr,cpc,actions,action_values"
            data = _meta_get(f"act_{META_AD_ACCOUNT_ID}/insights", {
                "fields": fields,
                "date_preset": period,
                "level": "ad",
                "sort": "spend_descending",
                "limit": str(limit),
            })
            rows = data.get("data", [])
            if not rows:
                return f"No ad creative data found for {period}."

            lines = [f"META ADS — TOP CREATIVES ({period.replace('_', ' ')})\n"]
            for row in rows:
                ad_name = row.get("ad_name", "Unnamed")[:50]
                spend = float(row.get("spend", 0))
                impressions = int(row.get("impressions", 0))
                clicks = int(row.get("clicks", 0))
                ctr = float(row.get("ctr", 0))
                cpc = float(row.get("cpc", 0))
                action_values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
                purchase_value = action_values.get("purchase", 0)
                roas = (purchase_value / spend) if spend > 0 else 0
                lines.append(f"  {ad_name}")
                lines.append(f"  Spend: ${spend:.2f}  Impressions: {impressions:,}  Clicks: {clicks:,}  CTR: {ctr:.2f}%  CPC: ${cpc:.2f}" + (f"  ROAS: {roas:.2f}x" if roas else ""))
            return "\n".join(lines)
        except Exception as e:
            return f"Meta ads top creatives failed: {e}"

    if name == "meta_page_analytics":
        period = inputs.get("period", "week")
        if not META_PAGE_ID:
            return "META_PAGE_ID not set in .env"
        try:
            metrics = [
                "page_impressions",
                "page_impressions_unique",
                "page_engaged_users",
                "page_fan_adds",
                "page_views_total",
            ]
            data = _meta_get(f"{META_PAGE_ID}/insights", {
                "metric": ",".join(metrics),
                "period": period,
            })
            lines = [f"FACEBOOK PAGE ANALYTICS ({period})\n"]
            for m in data.get("data", []):
                values = m.get("values", [])
                total = sum(v.get("value", 0) for v in values)
                label = m.get("name", "").replace("page_", "").replace("_", " ").title()
                lines.append(f"  {label}: {total:,}")
            posts_data = _meta_get(f"{META_PAGE_ID}/posts", {
                "fields": "id,message,created_time,permalink_url,likes.summary(true),comments.summary(true),shares",
                "limit": "5",
            })
            if posts_data.get("data"):
                lines.append("\nRECENT POSTS:")
                for post in posts_data["data"]:
                    msg = (post.get("message") or "")[:80].replace("\n", " ")
                    likes = post.get("likes", {}).get("summary", {}).get("total_count", 0)
                    comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                    shares = post.get("shares", {}).get("count", 0)
                    created = post.get("created_time", "")[:10]
                    lines.append(f"  [{created}] {msg}")
                    lines.append(f"  Likes: {likes}  Comments: {comments}  Shares: {shares}")
                    if post.get("permalink_url"):
                        lines.append(f"  {post['permalink_url']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Facebook analytics failed: {e}"

    if name == "meta_instagram_analytics":
        days = int(inputs.get("days", 7))
        if not META_INSTAGRAM_ACCOUNT_ID:
            return "META_INSTAGRAM_ACCOUNT_ID not set in .env"
        try:
            from datetime import datetime as _dt, timedelta as _td
            since = int((_dt.utcnow() - _td(days=days)).timestamp())
            until = int(_dt.utcnow().timestamp())
            insights = _meta_get(f"{META_INSTAGRAM_ACCOUNT_ID}/insights", {
                "metric": "impressions,reach,profile_views",
                "period": "day",
                "since": str(since),
                "until": str(until),
            })
            lines = [f"INSTAGRAM ANALYTICS (last {days} days)\n"]
            for m in insights.get("data", []):
                values = m.get("values", [])
                total = sum(v.get("value", 0) for v in values)
                label = m.get("name", "").replace("_", " ").title()
                lines.append(f"  {label}: {total:,}")
            media = _meta_get(f"{META_INSTAGRAM_ACCOUNT_ID}/media", {
                "fields": "id,caption,timestamp,media_type,permalink,like_count,comments_count",
                "limit": "5",
            })
            if media.get("data"):
                lines.append("\nRECENT POSTS:")
                for post in media["data"]:
                    caption = (post.get("caption") or "")[:80].replace("\n", " ")
                    likes = post.get("like_count", 0)
                    comments = post.get("comments_count", 0)
                    media_type = post.get("media_type", "")
                    ts = post.get("timestamp", "")[:10]
                    lines.append(f"  [{ts}] {media_type}: {caption}")
                    lines.append(f"  Likes: {likes}  Comments: {comments}")
                    if post.get("permalink"):
                        lines.append(f"  {post['permalink']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Instagram analytics failed: {e}"

    if name == "content_list":
        if not os.path.isdir(CONTENT_DIR):
            return "No content saved yet."
        type_filter     = inputs.get("content_type", "")
        platform_filter = inputs.get("platform", "")
        status_filter   = inputs.get("status", "")
        files = sorted(os.listdir(CONTENT_DIR), reverse=True)
        rows  = []
        for fname in files:
            if not fname.endswith(".md"):
                continue
            parts = fname.replace(".md", "").split("_")
            if type_filter and type_filter not in fname:
                continue
            if platform_filter and platform_filter not in fname:
                continue
            path = os.path.join(CONTENT_DIR, fname)
            status = "draft"
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("status:"):
                        status = line.split(":", 1)[1].strip()
                        break
            if status_filter and status != status_filter:
                continue
            rows.append(f"• {fname}  [{status}]")
        if not rows:
            return "No content found matching filters."
        return f"Saved content ({len(rows)} items):\n\n" + "\n".join(rows)

    return f"Unknown tool: {name}"
