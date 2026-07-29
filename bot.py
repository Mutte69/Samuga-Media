"""
═══════════════════════════════════════════════════════════════════════════════
  SAMUGA AI  —  Maldivian AI-Powered Newsroom Bot
  Version: 15.9.6 |  github.com/samuga-news-bot  |  Railway + PostgreSQL
═══════════════════════════════════════════════════════════════════════════════

  WHAT THIS FILE CONTAINS (search these tags to jump to a section):

    [CONFIG]      Environment vars, feeds, constants          (top of file)
    [DATABASE]    PostgreSQL: articles, stories, memory, kv
    [MODELS]      Article dataclass + helpers
    [FETCHERS]    RSS, Google News, MvCrisis scraping
    [SCORING]     Article scoring, dedup, clustering, reliability
    [STORIES]     Story Intelligence — timeline threads
    [AI]          Claude rewrite, Gemini Dhivehi, core-team brain
    [CARDS]       Pillow card generation (news + weather)
    [WEATHER]     MMS official alerts, multi-model forecasts, marine data, prayer times
    [PUBLISHING]  Telegram, Buffer, Meta Graph API
    [COMMANDS]    All /command handlers
    [SCHEDULER]   Cron jobs (news loop, weather, briefs)

  DEPLOYMENT:  push bot.py to GitHub → Railway auto-deploys
  COST:        ~$25/month (Claude Haiku + Railway + Buffer)
═══════════════════════════════════════════════════════════════════════════════
"""

import os, io, threading, time, logging, hashlib, json, feedparser, requests, anthropic, re, subprocess, shutil, mimetypes, inspect

from ai_usage import (
    AIRequestTracker, request_context as _ai_usage_context,
    configure as _configure_ai_usage, prompt_from_anthropic_kwargs,
    cleanup as _cleanup_ai_usage, normalize_feature as _normalize_ai_feature,
    current_context as _ai_usage_current_context,
    FEATURES as AI_USAGE_FEATURES, PROVIDERS as AI_USAGE_PROVIDERS,
)
import gemini_guard as _gemini_guard
import buffer_diagnostics as _buffer_diag
import runtime_leader as _runtime_leader
from contextlib import contextmanager
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from io import BytesIO
from cards import generate_card, generate_dhivehi_card, fetch_background_image, draw_weather_icon, generate_web_cover
from weather import (
    get_weather_data, get_island_forecasts, get_prayer_times,
    generate_weather_card, weather_code_to_info,
    detect_weather_alert, send_weather_alert, send_weather_update,
    check_official_weather_alerts, get_weather_system_status,
    MMS_ALERT_LEVELS, weather_alerts_today, ISLAND_LOCATIONS,
    HIJRI_SPECIAL_DAYS, SPECIAL_DAY_DETAILS, ISLAMIC_REMINDERS
)
from fetchers import (
    fetch_news, fetch_mvcrisis, fetch_all_dv_channels, fetch_dv_telegram,
    fetch_latest_web_pages, fetch_local_rss_recovery, fetch_world_updates,
    get_local_headlines, rewrite_news, gemini_translate,
    RSS_FEEDS, LOCAL_FEEDS, DV_TELEGRAM_CHANNELS, DEFAULT_KEYWORDS, WEB_LATEST_SOURCES,
    has_public_placeholder, public_text_is_safe, fallback_rewritten_news,
    clean_ai_line, safe_image_keyword,
    get_source_health_snapshot, load_source_health, source_health_score, source_health_summary
)
from scoring import (
    is_breaking, is_dhivehi, source_reliability,
    score_article, score_breakdown, confidence_score,
    should_hold_for_review, format_score_breakdown,
    is_duplicate_story, remember_story_title, register_in_cluster,
    recent_posts, user_conversations, recent_story_titles,
    BREAKING_KEYWORDS, BREAKING_BLACKLIST, SOURCE_RELIABILITY,
    get_cluster_store_snapshot, load_cluster_store
)
import front_desk
from db import (
    init_database, db_execute, db_record_article, db_mark_status,
    db_publish_article_for_website, db_log_learning,
    db_set_article_message, db_set_article_matchkey,
    db_hide_article, db_unhide_article, db_delete_article_by_url, db_hide_all_website, db_hide_all_dhivehi, db_unhide_all_dhivehi, db_bot_stats,
    db_list_website_articles, db_search_website_articles, db_website_analytics,
    db_get_featured_articles, db_feature_article, db_unfeature_article, db_get_article_by_identifier,
    kv_get, kv_set, mem_add, mem_list, mem_clear_all, mem_delete_last,
    detect_trends, is_trending_topic, find_or_create_story,
    get_story_timeline, search_stories, get_active_stories,
    canonical_category, strip_source_links, samuga_public_summary,
    normalize_article_language_for_public, _caption_match_key,
    make_article_slug, generate_website_article_body,
    TREND_THEMES, DB_ENABLED, is_dhivehi, looks_latin_thaana,
    gemini_latin_thaana_to_thaana, gemini_latin_thaana_to_english,
    _detect_themes,
    db_backfill_author_defaults, db_update_article_meta,
    compute_reading_time, auto_seo, _last_publish_block,
    website_article_body_is_consistent,
    retry_held_website_articles, db_retry_held_article_body,
    db_get_held_website_articles, db_hold_invalid_live_ai_articles,
    website_body_is_publishable, WEBSITE_HELD_STATUS,
)


# Story builder -- full article generation from headlines
try:
    from story_builder import (
        build_full_article, parse_rate_update, format_rate_card,
        make_website_caption, make_dv_website_caption,
        get_thread_context_for_article,
    )
    _STORY_BUILDER_AVAILABLE = True
except ImportError:
    _STORY_BUILDER_AVAILABLE = False

# Samuga OS event layer — emit structured events for the Master Data Hub
try:
    from samuga_events import (
        emit_event, event_summary, get_recent_events,
        event_article_published, event_breaking_detected,
        event_story_approved, event_ai_decision,
        event_social_published, event_website_published,
    )
    print("📡 Samuga OS event layer loaded")  # log not yet defined at import time
except ImportError:
    # Safe no-op if samuga_events.py is not yet on the deployment path
    def emit_event(event_type, payload=None): pass
    def event_summary(): return {}
    def get_recent_events(limit=50, event_type=None): return []
    def event_article_published(*a, **kw): pass
    def event_breaking_detected(*a, **kw): pass
    def event_story_approved(*a, **kw): pass
    def event_ai_decision(*a, **kw): pass
    def event_social_published(*a, **kw): pass
    def event_website_published(*a, **kw): pass

# ── Structured logging: tags make Railway logs readable ──────────────────────
# Usage: log.info("[FETCH] pulled 12 articles")  →  easy to filter in Railway
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

SAMUGA_VERSION = "15.9.6"

def _safe_env_int(name, default, minimum=None, maximum=None):
    """Read an integer environment variable without allowing a typo to crash startup."""
    raw = os.environ.get(name, str(default))
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        log.error(f"[CONFIG] Invalid integer for {name}={raw!r}; using {default}")
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value

def _log_event(stage, **kwargs):
    """
    Structured pipeline event logger.
    Emits a single log line with key=value pairs for easy Railway log filtering.

    Usage:
        _log_event("FETCH", source="Mihaaru", items=12, duration_ms=340)
        _log_event("SCORE", title="...", score=142, cat="LOCAL")
        _log_event("PUBLISH", platform="Telegram", ok=True, article_id="en42")
    """
    parts = [f"[{stage}]"]
    for k, v in kwargs.items():
        if isinstance(v, str) and len(v) > 120:
            v = v[:117] + "..."
        parts.append(f"{k}={v!r}")
    log.info(" ".join(parts))

def _mask_secrets(text):
    """Remove sensitive tokens from strings before logging."""
    s = str(text or "")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in s:
        s = s.replace(TELEGRAM_BOT_TOKEN, "***BOT_TOKEN***")
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY in s:
        s = s.replace(ANTHROPIC_API_KEY, "***ANTHROPIC_KEY***")
    if GEMINI_API_KEY and GEMINI_API_KEY in s:
        s = s.replace(GEMINI_API_KEY, "***GEMINI_KEY***")
    if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY in s:
        s = s.replace(DEEPSEEK_API_KEY, "***DEEPSEEK_KEY***")
    if CLOUDFLARE_ANALYTICS_TOKEN and CLOUDFLARE_ANALYTICS_TOKEN in s:
        s = s.replace(CLOUDFLARE_ANALYTICS_TOKEN, "***CLOUDFLARE_TOKEN***")
    if IMGBB_API_KEY and IMGBB_API_KEY in s:
        s = s.replace(IMGBB_API_KEY, "***IMGBB_KEY***")
    if BUFFER_TOKEN and BUFFER_TOKEN in s:
        s = s.replace(BUFFER_TOKEN, "***BUFFER_TOKEN***")
    if META_PAGE_TOKEN and META_PAGE_TOKEN in s:
        s = s.replace(META_PAGE_TOKEN, "***META_TOKEN***")
    if TAVILY_API_KEY and TAVILY_API_KEY in s:
        s = s.replace(TAVILY_API_KEY, "***TAVILY_KEY***")
    return s

# Module-level timezone alias (used by utcnow() below and elsewhere).
from datetime import timezone as _tz

# Public destination shown to readers. We never expose competitor/source links on
# Samuga public platforms; readers are directed back to Samuga Community.
SAMUGA_PUBLIC_SOURCE = os.environ.get("SAMUGA_PUBLIC_SOURCE", "Samuga Media")
SAMUGA_PUBLIC_LINK   = os.environ.get("SAMUGA_PUBLIC_LINK", "https://t.me/samugacommunity")
SAMUGA_CAPTION_LINK  = os.environ.get("SAMUGA_CAPTION_LINK", "https://samugamedia.com")
SAMUGA_API_BASE      = os.environ.get("SAMUGA_API_BASE", "https://samuga-news-bot-production.up.railway.app")
IMAGE_TELEGRAM_CDN_FALLBACK_ENABLED = os.environ.get("IMAGE_TELEGRAM_CDN_FALLBACK_ENABLED", "false").lower() == "true"
_AI_PHOTO = {"url": None}  # mutable wrapper — no global keyword needed in nested functions


def samuga_public_caption(caption):
    """Sanitize a caption for public posting and append Samuga website."""
    if not caption:
        return caption
    try:
        clean = strip_source_links(caption).strip()
        site = (SAMUGA_CAPTION_LINK or "").strip()
        if site and site not in clean:
            clean = (clean + "\n\n" + site).strip()
        return clean
    except Exception:
        return caption


def sanitize_public_news_text(text):
    """Remove source links, attribution residue and Telegram metadata from public copy."""
    clean = strip_source_links(text).strip()
    try:
        clean = _strip_telegram_metadata(clean).strip()
    except Exception:
        pass
    return strip_source_links(clean).strip()


def utcnow():
    """Naive UTC datetime — same value as the old utcnow() but not deprecated."""
    return datetime.now(_tz.utc).replace(tzinfo=None)

def mvt_now():
    """Current Maldives time (UTC+5) as naive datetime."""
    return utcnow() + timedelta(hours=5)

def mvt_display_time(dt):
    """Display DB UTC timestamps as Maldives time for website/API output."""
    if not dt:
        return "Recent"
    try:
        # psycopg2 TIMESTAMPTZ may be timezone-aware; normalize by adding offset only for naive UTC.
        if getattr(dt, "tzinfo", None) is not None:
            return dt.astimezone(_tz.utc).replace(tzinfo=None).__add__(timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
        return (dt + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
    except Exception:
        return "Recent"

def posting_paused():
    """Live Railway env kill switch: POSTING_PAUSED=true blocks all public posting."""
    return os.environ.get("POSTING_PAUSED", "false").lower() == "true"

def social_paused():
    """Live Railway env kill switch: SOCIAL_PAUSED=true blocks Buffer/social posting."""
    return os.environ.get("SOCIAL_PAUSED", "false").lower() == "true" or posting_paused()

def _posting_block_reason():
    if posting_paused():
        return "POSTING_PAUSED=true"
    if social_paused():
        return "SOCIAL_PAUSED=true"
    return ""

# ═══════════════════════════════════════════════════════════════════════════
# [CONFIG] — Environment variables & API keys
# ═══════════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@samugacommunity")
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY", "")
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY    = os.environ.get("DEEPSEEK_API_KEY", "")
# Optional server-side Cloudflare Zone Analytics import. Keep this token only in
# Railway; it is never exposed to the public website or dashboard JavaScript.
CLOUDFLARE_ZONE_ID  = os.environ.get("CLOUDFLARE_ZONE_ID", "").strip()
CLOUDFLARE_ANALYTICS_TOKEN = (
    os.environ.get("CLOUDFLARE_ANALYTICS_TOKEN", "").strip()
    or os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
)
CLOUDFLARE_ANALYTICS_MAX_DAYS = max(1, min(365, int(os.environ.get("CLOUDFLARE_ANALYTICS_MAX_DAYS", "31"))))
TAVILY_API_KEY      = os.environ.get("TAVILY_API_KEY", "")
BOT_USERNAME        = os.environ.get("BOT_USERNAME", "SamugaNewsBot")
IMGBB_API_KEY       = os.environ.get("IMGBB_API_KEY", "")
BUFFER_TOKEN        = os.environ.get("BUFFER_ACCESS_TOKEN", "")
BUFFER_FB_ID        = os.environ.get("BUFFER_FACEBOOK_ID", "")
BUFFER_IG_ID        = os.environ.get("BUFFER_INSTAGRAM_ID", "")
BUFFER_TW_ID        = os.environ.get("BUFFER_TWITTER_ID", "")
_last_buffer_error  = {"response": "No posts attempted yet"}
# Meta Graph API — reads FB + IG engagement off your own page
META_PAGE_TOKEN     = os.environ.get("META_PAGE_TOKEN", "")
META_PAGE_ID        = os.environ.get("META_PAGE_ID", "")
META_APP_SECRET     = os.environ.get("META_APP_SECRET", "")
META_IG_ID          = os.environ.get("META_IG_ID", "")  # optional; auto-resolved if blank
META_API_VER        = os.environ.get("META_API_VER", "v21.0")
TOMORROW_API_KEY    = os.environ.get("TOMORROW_API_KEY", "")  # weather data

# ── Killer posting switches ──────────────────────────────────────────────────
# POSTING_PAUSED=true blocks all public Telegram + Buffer/social posting.
# SOCIAL_PAUSED=true blocks Buffer/social only.
# These are read live from Railway env vars on every post attempt.
POSTING_PAUSED = os.environ.get("POSTING_PAUSED", "false").lower() == "true"
SOCIAL_PAUSED  = os.environ.get("SOCIAL_PAUSED",  "false").lower() == "true"

# ── Daily AI budget guard (Maldives Time) ─────────────────────────────────────
# Counts real Claude/Gemini API attempts. The first AI_BUDGET_CUTOFF_DAILY calls
# are allowed; every later call that Maldives calendar day uses the caller's
# existing non-AI fallback. State is persisted in PostgreSQL bot_kv so a Railway
# restart does not reset the allowance.
AI_SHARED_EDITORIAL_BUDGET_ENABLED = os.environ.get("AI_SHARED_EDITORIAL_BUDGET_ENABLED", "false").lower() == "true"
AI_BUDGET_CUTOFF_DAILY = _safe_env_int("AI_BUDGET_CUTOFF_DAILY", 500, minimum=1)
_AI_BUDGET_KV_KEY = "ai_budget_daily_v1"
_AI_BUDGET_LOCK = threading.RLock()
_AI_BUDGET_STATE = {
    "date": None, "count": 0, "alerted": False, "loaded": False,
    "by_provider": {}, "by_purpose": {},
}
_AI_CALL_CONTEXT = threading.local()
_AI_FAILURE_ALERT_LOCK = threading.RLock()

# Website maintenance must never consume the newsroom allowance in a burst.
WEBSITE_BODY_AUTO_RETRY_ENABLED = os.environ.get("WEBSITE_BODY_AUTO_RETRY_ENABLED", "true").lower() == "true"
WEBSITE_BODY_RETRY_INTERVAL_MINUTES = _safe_env_int("WEBSITE_BODY_RETRY_INTERVAL_MINUTES", 60, minimum=30, maximum=1440)
WEBSITE_BODY_RETRY_BATCH = _safe_env_int("WEBSITE_BODY_RETRY_BATCH", 1, minimum=1, maximum=2)
WEBSITE_BODY_REPAIR_DAILY_LIMIT = _safe_env_int("WEBSITE_BODY_REPAIR_DAILY_LIMIT", 2, minimum=0, maximum=12)
LEGACY_BODY_AUDIT_ENABLED = os.environ.get("LEGACY_BODY_AUDIT_ENABLED", "false").lower() == "true"
_WEBSITE_REPAIR_KV_KEY = "website_body_repair_budget_v1"
_WEBSITE_REPAIR_LOCK = threading.RLock()
_WEBSITE_REPAIR_STATE = {"date": None, "count": 0, "loaded": False}
_AI_FAILURE_ALERTED_AT = {}
_AI_FAILURE_ALERT_COOLDOWN_SECONDS = _safe_env_int(
    "AI_FAILURE_ALERT_COOLDOWN_SECONDS", 900, minimum=60
)


class AIBudgetExceeded(RuntimeError):
    """Raised internally so existing helpers immediately enter safe fallback mode."""


def _is_ai_budget_exceeded(exc):
    return isinstance(exc, AIBudgetExceeded)


def _ai_budget_today():
    return mvt_now().strftime("%Y-%m-%d")


def _persist_ai_budget_state(snapshot):
    try:
        kv_set(_AI_BUDGET_KV_KEY, {
            "date": snapshot.get("date"),
            "count": int(snapshot.get("count") or 0),
            "alerted": bool(snapshot.get("alerted")),
            "by_provider": dict(snapshot.get("by_provider") or {}),
            "by_purpose": dict(snapshot.get("by_purpose") or {}),
        })
    except Exception as exc:
        log.error(f"[AI BUDGET] state persistence failed: {_mask_secrets(exc)}")


def _send_ai_budget_alert_once(day):
    chat_id = globals().get("CORE_TEAM_CHAT_ID")
    sender = globals().get("send_text")
    if chat_id and callable(sender):
        try:
            sender(chat_id, "Daily editorial AI budget exceeded. Claude/Gemini generation is paused until Maldives midnight.")
        except Exception as exc:
            log.error(f"[AI BUDGET] Telegram alert failed: {_mask_secrets(exc)}")


def _load_or_roll_ai_budget_locked():
    today = _ai_budget_today()
    if not _AI_BUDGET_STATE.get("loaded"):
        stored = None
        try:
            stored = kv_get(_AI_BUDGET_KV_KEY, None)
        except Exception as exc:
            log.error(f"[AI BUDGET] state load failed: {_mask_secrets(exc)}")
        if isinstance(stored, dict) and stored.get("date") == today:
            _AI_BUDGET_STATE.update(
                date=today,
                count=max(0, int(stored.get("count") or 0)),
                alerted=bool(stored.get("alerted")),
                by_provider=dict(stored.get("by_provider") or {}),
                by_purpose=dict(stored.get("by_purpose") or {}),
                loaded=True,
            )
        else:
            _AI_BUDGET_STATE.update(
                date=today, count=0, alerted=False,
                by_provider={}, by_purpose={}, loaded=True,
            )
    elif _AI_BUDGET_STATE.get("date") != today:
        _AI_BUDGET_STATE.update(
            date=today, count=0, alerted=False,
            by_provider={}, by_purpose={}, loaded=True,
        )
    return today


def _current_ai_purpose(default="generation"):
    return str(getattr(_AI_CALL_CONTEXT, "purpose", "") or default)


@contextmanager
def _ai_call_purpose(purpose, **metadata):
    previous = getattr(_AI_CALL_CONTEXT, "purpose", None)
    _AI_CALL_CONTEXT.purpose = str(purpose or "generation")
    with _ai_usage_context(
        purpose=str(purpose or "generation"),
        feature=metadata.get("feature"),
        article_id=metadata.get("article_id"),
        article_title=metadata.get("article_title"),
        source_url=metadata.get("source_url"),
        metadata=metadata.get("metadata"),
    ):
        try:
            yield
        finally:
            if previous is None:
                try:
                    delattr(_AI_CALL_CONTEXT, "purpose")
                except AttributeError:
                    pass
            else:
                _AI_CALL_CONTEXT.purpose = previous


def _record_ai_usage(provider, purpose, *, count_toward_budget=False):
    """Record one real provider request. DeepSeek is tracked separately but does
    not consume the Claude/Gemini editorial cutoff."""
    with _AI_BUDGET_LOCK:
        _load_or_roll_ai_budget_locked()
        provider = str(provider or "AI")
        purpose = str(purpose or "generation")
        providers = _AI_BUDGET_STATE.setdefault("by_provider", {})
        purposes = _AI_BUDGET_STATE.setdefault("by_purpose", {})
        providers[provider] = int(providers.get(provider) or 0) + 1
        purposes[purpose] = int(purposes.get(purpose) or 0) + 1
        if count_toward_budget:
            _AI_BUDGET_STATE["count"] = int(_AI_BUDGET_STATE.get("count") or 0) + 1
        snapshot = dict(_AI_BUDGET_STATE)
        snapshot["by_provider"] = dict(providers)
        snapshot["by_purpose"] = dict(purposes)
    _persist_ai_budget_state(snapshot)
    return snapshot


def _reserve_ai_call(provider="AI", purpose="generation", *, feature="", article_id="", article_title="", source_url="", retry_count=None):
    """Reserve one physical provider request.

    Gemini receives its own hourly/daily/cost/idempotency guard before the older
    shared editorial cutoff. The latest block reason is kept in thread-local
    state so telemetry reports the real reason rather than calling every block
    a generic daily-budget failure.
    """
    should_alert = False
    state_changed = False
    purpose = _current_ai_purpose(purpose)
    _AI_CALL_CONTEXT.block_reason = ""

    if str(provider).lower() == "gemini":
        ctx = _ai_usage_current_context()
        feature = str(feature or ctx.get("feature") or _normalize_ai_feature(purpose=purpose))
        if feature in {"Manual Article", "Manual Card"} and os.environ.get("GEMINI_ALLOW_MANUAL_POST_AI", "false").lower() != "true":
            _AI_CALL_CONTEXT.block_reason = "manual_post_must_not_use_gemini"
            log.error("[GEMINI GUARD] blocked Gemini from %s", feature)
            return False
        attempt_match = re.search(r"attempt\s+(\d+)", purpose, flags=re.I)
        effective_retry = (max(0, int(attempt_match.group(1)) - 1) if attempt_match else 0) if retry_count is None else max(0, int(retry_count or 0))
        allowed_guard, guard_reason, guard_snapshot = _gemini_guard.reserve(
            feature=feature, purpose=purpose,
            article_id=str(article_id or ctx.get("article_id") or ""),
            article_title=str(article_title or ctx.get("article_title") or ""),
            source_url=str(source_url or ctx.get("source_url") or ""),
            retry_count=effective_retry,
        )
        if not allowed_guard:
            _AI_CALL_CONTEXT.block_reason = guard_reason or "gemini_guard_blocked"
            log.warning("[GEMINI GUARD] request blocked: %s | %s", guard_reason, guard_snapshot)
            return False

    if not AI_SHARED_EDITORIAL_BUDGET_ENABLED:
        # Provider-specific cost/retry/idempotency controls are authoritative.
        # Keep lightweight counters for diagnostics without blocking production.
        snapshot = _record_ai_usage(provider, purpose, count_toward_budget=False)
        log.info(f"[AI USAGE] {provider} {purpose}: shared call cap disabled")
        return True

    with _AI_BUDGET_LOCK:
        today = _load_or_roll_ai_budget_locked()
        if _AI_BUDGET_STATE["count"] >= AI_BUDGET_CUTOFF_DAILY:
            if not _AI_BUDGET_STATE.get("alerted"):
                _AI_BUDGET_STATE["alerted"] = True
                should_alert = True
                state_changed = True
            snapshot = dict(_AI_BUDGET_STATE)
            allowed = False
            _AI_CALL_CONTEXT.block_reason = "shared_editorial_daily_budget"
        else:
            _AI_BUDGET_STATE["count"] += 1
            providers = _AI_BUDGET_STATE.setdefault("by_provider", {})
            purposes = _AI_BUDGET_STATE.setdefault("by_purpose", {})
            providers[provider] = int(providers.get(provider) or 0) + 1
            purposes[purpose] = int(purposes.get(purpose) or 0) + 1
            state_changed = True
            snapshot = dict(_AI_BUDGET_STATE)
            snapshot["by_provider"] = dict(providers)
            snapshot["by_purpose"] = dict(purposes)
            allowed = True
    if state_changed:
        _persist_ai_budget_state(snapshot)
    if should_alert:
        log.critical(
            f"[AI BUDGET] Daily cutoff reached ({AI_BUDGET_CUTOFF_DAILY}); "
            f"blocking {provider} calls until Maldives midnight"
        )
        _send_ai_budget_alert_once(today)
    if allowed:
        log.info(
            f"[AI BUDGET] {provider} {purpose}: "
            f"{snapshot['count']}/{AI_BUDGET_CUTOFF_DAILY} editorial calls used for {today}"
        )
    return allowed


def _ai_reserve_block_reason(default="daily_budget_exceeded"):
    return str(getattr(_AI_CALL_CONTEXT, "block_reason", "") or default)


def _ai_usage_snapshot():
    with _AI_BUDGET_LOCK:
        today = _load_or_roll_ai_budget_locked()
        return {
            "date": today,
            "editorial_total": int(_AI_BUDGET_STATE.get("count") or 0),
            "editorial_limit": AI_BUDGET_CUTOFF_DAILY,
            "by_provider": dict(_AI_BUDGET_STATE.get("by_provider") or {}),
            "by_purpose": dict(_AI_BUDGET_STATE.get("by_purpose") or {}),
        }


def _reserve_website_repair_attempt():
    if WEBSITE_BODY_REPAIR_DAILY_LIMIT <= 0:
        return False

    # Do not consume a maintenance-repair allowance after the shared editorial
    # budget is already exhausted. Check under the AI lock, release it, then
    # acquire the repair lock so lock ordering can never deadlock.
    if AI_SHARED_EDITORIAL_BUDGET_ENABLED:
        with _AI_BUDGET_LOCK:
            _load_or_roll_ai_budget_locked()
            if int(_AI_BUDGET_STATE.get("count") or 0) >= AI_BUDGET_CUTOFF_DAILY:
                log.info("[WEBSITE] repair skipped — shared editorial call cap exhausted")
                return False

    today = _ai_budget_today()
    with _WEBSITE_REPAIR_LOCK:
        if not _WEBSITE_REPAIR_STATE.get("loaded"):
            stored = kv_get(_WEBSITE_REPAIR_KV_KEY, None)
            if isinstance(stored, dict) and stored.get("date") == today:
                _WEBSITE_REPAIR_STATE.update(date=today, count=int(stored.get("count") or 0), loaded=True)
            else:
                _WEBSITE_REPAIR_STATE.update(date=today, count=0, loaded=True)
        elif _WEBSITE_REPAIR_STATE.get("date") != today:
            _WEBSITE_REPAIR_STATE.update(date=today, count=0, loaded=True)
        if _WEBSITE_REPAIR_STATE["count"] >= WEBSITE_BODY_REPAIR_DAILY_LIMIT:
            log.info(f"[WEBSITE] repair allowance exhausted ({WEBSITE_BODY_REPAIR_DAILY_LIMIT}/day); held article remains queued")
            return False
        _WEBSITE_REPAIR_STATE["count"] += 1
        snapshot = dict(_WEBSITE_REPAIR_STATE)
    kv_set(_WEBSITE_REPAIR_KV_KEY, snapshot)
    log.info(f"[WEBSITE] repair allowance: {snapshot['count']}/{WEBSITE_BODY_REPAIR_DAILY_LIMIT} attempts used for {today}")
    return True


def _reset_ai_budget_for_new_day():
    """Hard reset scheduled at 00:00 Maldives Time; lazy date rollover also exists."""
    today = _ai_budget_today()
    with _AI_BUDGET_LOCK:
        _AI_BUDGET_STATE.update(
            date=today, count=0, alerted=False, loaded=True,
            by_provider={}, by_purpose={},
        )
        snapshot = dict(_AI_BUDGET_STATE)
    with _WEBSITE_REPAIR_LOCK:
        _WEBSITE_REPAIR_STATE.update(date=today, count=0, loaded=True)
        repair_snapshot = dict(_WEBSITE_REPAIR_STATE)
    _persist_ai_budget_state(snapshot)
    kv_set(_WEBSITE_REPAIR_KV_KEY, repair_snapshot)
    log.info(f"[AI BUDGET] Daily counters reset for {today} MVT")


def _critical_ai_failure(component, error):
    """Log every critical AI failure and rate-limit direct team alerts by component."""
    if _is_ai_budget_exceeded(error):
        return
    safe_error = _mask_secrets(str(error or "unknown AI error"))[:1200]
    logging.critical(f"[AI CRITICAL] {component}: {safe_error}")
    now = time.time()
    key = str(component or "AI")[:120]
    with _AI_FAILURE_ALERT_LOCK:
        last = float(_AI_FAILURE_ALERTED_AT.get(key) or 0)
        if now - last < _AI_FAILURE_ALERT_COOLDOWN_SECONDS:
            return
        _AI_FAILURE_ALERTED_AT[key] = now
    chat_id = globals().get("CORE_TEAM_CHAT_ID")
    sender = globals().get("send_text")
    if not chat_id or not callable(sender):
        return
    safe_html = (
        safe_error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    try:
        sender(
            chat_id,
            f"⚠️ <b>AI pipeline temporarily failed</b>\n\n"
            f"<b>Component:</b> {key}\n<code>{safe_html[:900]}</code>",
        )
    except Exception as alert_error:
        log.error(f"[AI CRITICAL] Telegram warning failed: {_mask_secrets(alert_error)}")


class _BudgetedAnthropicMessages:
    def __init__(self, raw_messages):
        self._raw_messages = raw_messages

    def create(self, *args, **kwargs):
        purpose = _current_ai_purpose("generation")
        caller_frame = inspect.currentframe().f_back
        caller = caller_frame.f_code.co_name if caller_frame else "unknown"
        prompt = prompt_from_anthropic_kwargs(kwargs)
        model = str(kwargs.get("model") or "unknown")
        tracker = AIRequestTracker.start(
            "Claude", model, purpose=purpose, caller=caller, prompt=prompt,
            retry_count=int(kwargs.pop("_samuga_retry_count", 0) or 0),
        )
        if not _reserve_ai_call("Claude", purpose):
            tracker.blocked(_ai_reserve_block_reason())
            raise AIBudgetExceeded(
                f"Daily AI budget exceeded ({AI_BUDGET_CUTOFF_DAILY} calls)"
            )
        try:
            result = self._raw_messages.create(*args, **kwargs)
            usage = getattr(result, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            provider_request_id = str(
                getattr(result, "_request_id", "") or getattr(result, "id", "") or ""
            )
            response_text = ""
            try:
                response_text = "\n".join(
                    str(getattr(block, "text", "") or "") for block in (getattr(result, "content", None) or [])
                )
            except Exception:
                pass
            tracker.success(
                input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_tokens=cache_read, cache_write_tokens=cache_write,
                cached_tokens=cache_read + cache_write, http_status=200,
                provider_request_id=provider_request_id, response_text=response_text,
            )
            return result
        except AIBudgetExceeded:
            raise
        except Exception as exc:
            status = int(getattr(exc, "status_code", 0) or getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            tracker.failure(exc, http_status=status)
            _critical_ai_failure("Claude API", exc)
            raise


class _BudgetedAnthropicClient:
    def __init__(self, raw_client):
        self._raw_client = raw_client
        self.messages = _BudgetedAnthropicMessages(raw_client.messages)

    def __getattr__(self, name):
        return getattr(self._raw_client, name)


# Disable SDK-internal retries so every physical Claude HTTP attempt is visible
# as its own Samuga telemetry row instead of being hidden inside the SDK.
ai = _BudgetedAnthropicClient(anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=0))

try:
    from ai_pipeline import extract_fact_pack as _deepseek_extract_fact_pack
    from ai_pipeline import compact_fact_pack as _compact_fact_pack
    from ai_pipeline import health_snapshot as _deepseek_health_snapshot
except Exception as _deepseek_import_error:
    log.warning(f"[AI][DEEPSEEK] optional pipeline unavailable: {_deepseek_import_error}")
    def _deepseek_extract_fact_pack(*args, **kwargs): return None
    def _compact_fact_pack(pack, max_chars=10000): return ""
    def _deepseek_health_snapshot():
        return {"configured": bool(DEEPSEEK_API_KEY), "enabled": False, "status": "unavailable"}


def _claude_write_article_from_facts(headline, fact_pack, source_count=1):
    """Final English newsroom draft from DeepSeek's evidence-only JSON."""
    if not ANTHROPIC_API_KEY or not fact_pack:
        return ""
    facts_json = _compact_fact_pack(fact_pack, 12000)
    if not facts_json:
        return ""
    prompt = f"""You are the final English editor for Samuga Media.
Write a clean original news article using ONLY the verified JSON fact pack below.

Rules:
- 3 to 4 short paragraphs, maximum 300 words.
- Lead with the newest and most important confirmed fact.
- Do not repeat the headline as the opening sentence.
- Never add a name, office, number, date, location, quote, cause, motive or outcome that is absent from the fact pack.
- Treat confidence=reported as attributed reporting, not independently confirmed fact.
- If an important detail is in unknowns, say it was not disclosed or remains unclear rather than guessing.
- Do not mention DeepSeek, JSON, prompts or AI.
- Do not mention the original publisher, media outlet, feed, source name, source link or where Samuga found the story.
- Attribute official actions only when the authority is itself part of the verified fact (for example, police or a court).
- No headline, markdown, bullets, labels, hashtags or emojis. Return article paragraphs only.

Headline: {str(headline or '')[:500]}
Sources reporting: {max(1, int(source_count or 1))}
Verified fact pack JSON:
{facts_json}
"""
    try:
        with _ai_call_purpose(
            _current_ai_purpose("newsroom_english_writer"),
            feature="Story Builder", article_title=headline,
            metadata={"source_count": max(1, int(source_count or 1))},
        ):
            msg = ai.messages.create(
                model=os.environ.get("CLAUDE_EDITOR_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=1000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
        return (msg.content[0].text if msg.content else "").strip()
    except Exception as exc:
        if not _is_ai_budget_exceeded(exc):
            _critical_ai_failure("Claude fact-pack article writer", exc)
        return ""

# ═══════════════════════════════════════════════════════════════════════════
# [MODELS] — Article shape (documentation + optional helper)
# ═══════════════════════════════════════════════════════════════════════════
# Articles flow through the pipeline as plain dicts for flexibility. This
# dataclass documents the canonical shape so future-you (and any new dev) can
# see at a glance what fields an article carries. Use Article.from_dict() if you
# ever want type safety, but the dict form remains the working currency.
@dataclass
class Article:
    id: str                       # unique hash of the article
    title: str                    # headline
    summary: str = ""             # body/excerpt
    link: str = ""                # source URL
    source: str = ""              # outlet name (Mihaaru, Sun, etc)
    cat: str = "LOCAL"            # BREAKING | LOCAL | POLITICAL | SPORTS | LIFESTYLE | WORLD
    lang: str = "en"              # en | dv
    # ── runtime fields added during processing ──
    score: int = 0                # newsroom priority score
    reliability: int = 0          # source trust score
    is_breaking: bool = False
    cluster_size: int = 1         # how many sources reporting this (_cluster_size)
    story_id: int = None          # attached Story Intelligence thread (_story_id)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(
            id=d.get("id",""), title=d.get("title",""), summary=d.get("summary",""),
            link=d.get("link",""), source=d.get("source",""), cat=d.get("cat","LOCAL"),
            lang=d.get("lang","en"), score=d.get("score",0),
            reliability=d.get("reliability",0), is_breaking=d.get("is_breaking",False),
            cluster_size=d.get("_cluster_size",1), story_id=d.get("_story_id"),
        )

# ═══════════════════════════════════════════════════════════════════════════
# [FETCHERS] — RSS Feeds
# ═══════════════════════════════════════════════════════════════════════════
# ── RSS Feeds (v4 Strategy) ───────────────────────────────────────────────────
# LOCAL (70%) — Maldivian sources, priority order
core_team_session_context = {}  # user_id -> stored context

# Pending manual card waiting for /confirm before firing to all platforms
# Only one at a time — new "create card and post" replaces the previous pending one.
_pending_manual_post = {}  # {card_bytes, full_caption, chat_id, thread_id, first_name}
_pending_author_photo = {}  # {user_id, target: "self"|"ai", chat_id, thread_id, expires_at}
_pending_cover_photo = {}   # {user_id, article_data, chat_id, thread_id, expires_at}

# ── Samuga AI proactive mode toggle ─────────────────────────────────────────
# /ai on  → bot reads every core team message and decides whether to jump in
# /ai off → bot only responds when directly tagged (default safe mode)
_ai_proactive_mode = os.environ.get("CORE_TEAM_PROACTIVE_AI_ENABLED", "false").lower() == "true"
_cortex_comments_enabled = False  # Build 15.7 removed Cortex follow-up comments
_cortex_ranking_enabled = os.environ.get("CORTEX_RANKING_ENABLED", "true").lower() == "true"
_cortex_news_director_enabled = True  # Build 15.7: mandatory final pre-AI editorial gate
_cortex_news_director_env_requested = os.environ.get("CORTEX_NEWS_DIRECTOR_ENABLED", "true").lower() == "true"


def _cortex_gate_article(article):
    """Run the single final pre-AI editorial gate, once per candidate.

    This function never calls DeepSeek, Claude or Gemini. It caches Cortex's
    deterministic decision on the article so the funnel and publisher reuse the
    same verdict instead of re-evaluating or allowing another gate to override it.
    """
    cached = article.get("_cortex_gate")
    if isinstance(cached, dict) and cached.get("action"):
        return cached
    try:
        from samuga_cortex import cortex_news_director_gate
        full_gate = cortex_news_director_gate({
            "title": article.get("title", ""),
            "summary": article.get("summary", "") or article.get("body", ""),
            "source": article.get("source", ""),
            "cat": article.get("cat", article.get("category", "LOCAL")),
            "lang": article.get("lang", "en"),
            "published": article.get("published") or article.get("published_at"),
            "_cluster_size": article.get("_cluster_size", article.get("cluster_size", 1)),
            "_duplicate": bool(article.get("_duplicate") or article.get("is_duplicate")),
            "score": article.get("score", 0),
        })
        decision = full_gate.pop("decision", None)
        gate = dict(full_gate)
        article["_cortex_gate"] = gate
        article["_cortex_decision"] = decision
        return gate
    except Exception as exc:
        # Editorial gates fail closed. A broken Cortex must not send hundreds of
        # unreviewed leads into paid AI providers.
        log.error(f"[CORTEX NEWS DIRECTOR] gate failed closed: {exc}", exc_info=True)
        gate = {
            "action": "reject", "accepted": False, "ai_allowed": False,
            "requires_human_review": False, "breaking_candidate": False, "breaking": False,
            "score": 0, "confidence": 0, "risk": 100,
            "story_type": "gate_error", "route": "skip",
            "reason": "Cortex gate error — rejected before AI",
            "reasons": [str(exc)[:180]], "angle": "",
        }
        article["_cortex_gate"] = gate
        return gate


def _cortex_gate_log(article, gate):
    return (
        f"action={gate.get('action')} score={gate.get('score')}/100 "
        f"confidence={gate.get('confidence')}% risk={gate.get('risk')} "
        f"type={gate.get('story_type')} title={str(article.get('title',''))[:80]}"
    )

# ── Universal Approval Queue (in-memory) ─────────────────────────────────────
# Every card (English + Dhivehi) waits here for Content Lab approval before posting.
# Cards expire after 2 hours if not approved.
ENGLISH_AUTOPOST_SECONDS  = 2700   # Regular: auto-post after 45 min if nobody reviews
BREAKING_AUTOPOST_SECONDS = 900    # Breaking held for confidence: auto-posts in 15 min
# TELEGRAM_GAP_SECONDS and DAILY_TG_POST_MAX removed — Part 1 of Sprint A.
# Content Lab buttons are now the single source of truth for publishing destinations.
DHIVEHI_EXPIRY_SECONDS    = 7200   # Dhivehi: expire (delete) after 2h if not approved

approval_queue = {}  # key -> {card_bytes, caption, title, link, cat, lang, dv_text, created_at, ...}
_approval_counter = [0]
_approval_lock = threading.RLock()  # guards approval_queue + _approval_counter

# ── Global state variables (removed from db block, restored here) ──────────────
analytics           = {"posts_by_cat": {}, "breaking_count": 0, "social_success": 0, "social_fail": 0, "week_start": None}
last_regular_post_time = None
daily_sports_count  = {"date": None, "count": 0}
daily_world_count   = {"date": None, "count": 0}
daily_tourism_count = {"date": None, "count": 0}
_state_counters_lock = threading.RLock()  # guards all daily counters + last_regular_post_time


def can_post_cat_today(counter, max_per_day):
    """Check a per-category daily counter against its cap. Resets on a new MVT
    day and increments the counter when posting is allowed. Returns True if a
    post in this category is still within today's budget."""
    today = (utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
    if counter.get("date") != today:
        counter["date"] = today
        counter["count"] = 0
    if counter["count"] >= max_per_day:
        return False
    counter["count"] += 1
    try:
        persist_state()
    except Exception:
        pass
    return True


# ── Content Lab flood control ────────────────────────────────────────────────
# Goal: normal newsroom flow = max 4 approval cards/hour.
# Exception: very high priority stories can use up to 6/hour.
# Breaking with strong confidence posts automatically; breaking with weak confidence
# goes to Alert Chat, not Content Lab, so Uly's workspace does not get flooded.
CONTENT_LAB_NORMAL_MAX_PER_HOUR = int(os.environ.get("CONTENT_LAB_NORMAL_MAX_PER_HOUR", "4"))  # legacy — kept for _content_lab_slots_available
CONTENT_LAB_HIGH_MAX_PER_HOUR   = int(os.environ.get("CONTENT_LAB_HIGH_MAX_PER_HOUR", "6"))   # legacy
CONTENT_LAB_HIGH_SCORE          = int(os.environ.get("CONTENT_LAB_HIGH_SCORE", "180"))         # threshold for "very high score" — 2 cards per scan
HOURLY_CARD_CAP                 = _safe_env_int("HOURLY_CARD_CAP", 6, minimum=1, maximum=6)
AUTO_DHIVEHI_CARD_ENABLED       = os.environ.get("AUTO_DHIVEHI_CARD_ENABLED", "true").lower() == "true"
SCAN_NORMAL_CARDS               = 1    # cards per 15-min scan normally
SCAN_HIGH_CARDS                 = 2    # cards per scan when top article scores 180+
FUNNEL_KEEP_RATIO               = 0.5  # each funnel pass keeps top 50%
FUNNEL_MIN_SCORE                = 80   # articles below this get cut at first pass
_content_lab_sent_log = []  # datetime stamps for approval previews actually sent
_content_lab_lock = threading.RLock()  # guards _content_lab_sent_log

def _prune_content_lab_log(now=None):
    now = now or utcnow()
    cutoff = now - timedelta(hours=1)
    with _content_lab_lock:
        _content_lab_sent_log[:] = [t for t in _content_lab_sent_log if t > cutoff]

def _content_lab_slots_available(item=None):
    now = utcnow()
    _prune_content_lab_log(now)
    with _content_lab_lock:
        sent = len(_content_lab_sent_log)
    priority = int((item or {}).get("_priority") or (item or {}).get("score") or 0)
    high_priority = bool((item or {}).get("is_breaking")) or priority >= CONTENT_LAB_HIGH_SCORE
    limit = CONTENT_LAB_HIGH_MAX_PER_HOUR if high_priority else CONTENT_LAB_NORMAL_MAX_PER_HOUR
    return sent < limit, limit, sent, high_priority

def _mark_content_lab_sent(item=None):
    _prune_content_lab_log()
    with _content_lab_lock:
        _content_lab_sent_log.append(utcnow())
    if item is not None:
        item["_content_lab_sent"] = True
        item["_content_lab_sent_at"] = utcnow().isoformat()

def release_content_lab_drip():
    """Send delayed approval cards slowly so Content Lab gets max 4/hour, 6 if high priority."""
    try:
        pending = [
            (k, v) for k, v in approval_queue.items()
            if not v.get("_content_lab_sent") and not v.get("_content_lab_suppressed")
        ]
        pending.sort(key=lambda kv: kv[1].get("created_at") or utcnow())
        if not pending:
            return
        for k, v in pending:
            ok, limit, sent, high = _content_lab_slots_available(v)
            if not ok:
                log.info(f"🧯 Content Lab drip paused: {sent}/{limit} sent in last hour, {len(pending)} waiting")
                return
            _send_approval_card(k, v, force=True)
    except Exception as e:
        log.error(f"Content Lab drip: {e}")

def store_pending_approval(card_bytes, caption, title, link, cat="LOCAL", lang="en",
                           dv_text=None, keyword="maldives news", source="LOCAL",
                           is_breaking=False, allow_social=True, dedup_title=None, summary="",
                           cortex_gate=None):
    """Store a fully-built card awaiting approval. Returns the key or None if blocked."""
    # Central public-copy safety net. Most AI paths are already sanitized, but
    # manual cards, restored queue items and future integrations also pass here.
    title = sanitize_public_news_text(title)
    summary = sanitize_public_news_text(summary)
    dv_text = sanitize_public_news_text(dv_text) if dv_text else dv_text
    caption = strip_source_links(caption).strip() if caption else caption
    safe_ok, safe_reason = contentlab_candidate_is_safe(
        title=title,
        summary=(dv_text or caption or summary or ""),
        source=source,
        lang=lang,
    )
    if not safe_ok:
        log.warning(f"🧱 Content Lab blocked candidate: {safe_reason} — {str(title)[:90]}")
        return None

    with _approval_lock:
        _approval_counter[0] += 1
        prefix = "dv" if lang == "dv" else "en"
        key = f"{prefix}{_approval_counter[0]}"
        approval_queue[key] = {
            "card_bytes": card_bytes,   # PNG bytes of the finished card (None for dv until approved)
            "caption": caption,          # full telegram caption
            "title": title,
            "link": link,
            "cat": cat,
            "lang": lang,
            "dv_text": dv_text,          # Dhivehi text (for dv cards, editable)
            "keyword": keyword,
            "source": source,
            "is_breaking": is_breaking,
            "allow_social": allow_social,
            "created_at": utcnow(),
            "_dedup_title": dedup_title or title,
            "summary": summary or "",
            # Private editorial metadata. It is shown only inside Content Lab
            # and never rendered into a public card, caption or website article.
            "_cortex_gate": dict(cortex_gate or {}),
        }
        # Cap queue size
        if len(approval_queue) > 40:
            oldest = list(approval_queue.keys())[0]
            del approval_queue[oldest]
    persist_state()
    # Immediately backup to PostgreSQL so queue survives any crash
    try:
        kv_set("approval_queue_backup", _serialize_approval_queue_for_pg())
        kv_set("approval_counter_backup", _approval_counter[0])
        log.debug(f"[PG] Queue backup saved: {len(approval_queue)} items")
    except Exception as pg_err:
        log.warning(f"[PG] Queue backup failed: {pg_err}")
    return key

def _queue_mms_alert_review(alert):
    """Place a low-confidence @MaldivesMET extraction in Content Lab.

    The preview is branded and persistent, but manual-only: it never reaches the
    normal 45-minute English auto-publish path. Approval invokes the official
    weather alert publisher rather than creating a website news article.
    """
    try:
        alert = dict(alert or {})
        review_id = str(
            alert.get("alert_id") or alert.get("telegram_message_id") or alert.get("source_id") or ""
        ).strip()
        # Low-confidence reviews are also restart-safe. The official publisher
        # already persists posted IDs; this separate ledger prevents the same
        # ambiguous image from being re-queued after a Railway restart.
        if review_id:
            try:
                review_seen = kv_get("met_telegram_review_seen_v1", {}) or {}
                if isinstance(review_seen, dict) and review_id in review_seen:
                    log.info("[MMS TELEGRAM] duplicate review skipped: %s", review_id)
                    return False
            except Exception as review_seen_error:
                log.warning("[MMS TELEGRAM] review dedup lookup failed open: %s", review_seen_error)
        level = str(alert.get("level") or "possible").upper()
        confidence = float(alert.get("confidence") or alert.get("vision_confidence") or 0.0)
        hazard = str(alert.get("hazard") or alert.get("title") or "Possible official weather alert").strip()
        area = str(alert.get("area") or "Area not confidently extracted").strip()
        valid_from = str(alert.get("valid_from") or "")
        valid_until = str(alert.get("valid_until") or "")
        title = f"{level} MMS alert — manual confirmation required"
        summary = f"{hazard}. Area: {area}."
        if valid_from and valid_until:
            summary += f" Valid {valid_from} to {valid_until}."
        source_url = str(alert.get("source_url") or "https://t.me/MaldivesMET")
        content = f"{title}\n\n{summary}"
        # A weather alert is not a normal news card. Even manual-review previews
        # use the dedicated MMS white/yellow/orange/red renderer so the dashboard
        # shows the exact card that will be published after confirmation.
        try:
            import weather as _weather_review_card
            _level_key = str(alert.get("level") or "white").lower()
            if _level_key not in {"white", "yellow", "orange", "red"}:
                _level_key = "white"
            _weather_data = _weather_review_card.get_weather_data() or _weather_review_card._minimal_weather_data("alert")
            _weather_data = dict(_weather_data)
            _weather_data["official_alert"] = alert
            _islands = _weather_review_card.get_island_forecasts()
            _prayers = _weather_review_card.get_prayer_times(time_of_day="alert")
            card = _weather_review_card.generate_weather_card(
                _weather_data,
                alert_mode=True,
                alert_text=_weather_review_card._official_alert_text(alert),
                alert_level=_level_key,
                island_data=_islands,
                prayer_data=_prayers,
            )
        except Exception as review_card_error:
            log.warning("[MMS TELEGRAM] dedicated review card failed; using safe news-card fallback: %s", review_card_error)
            timestamp = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
            background = fetch_background_image(None, cat="WEATHER", title=title)
            card = generate_card(content, "Maldives Meteorological Service", timestamp, "WEATHER", background)
        key = store_pending_approval(
            card.getvalue(),
            f"⚠️ <b>{title}</b>\n\n{summary}\n\nSource: {source_url}",
            title, source_url, cat="WEATHER", lang="en", source="@MaldivesMET",
            is_breaking=True, allow_social=True, summary=summary,
        )
        if not key:
            return False
        with _approval_lock:
            approval_queue[key]["_weather_alert_review"] = True
            approval_queue[key]["_manual_only"] = True
            approval_queue[key]["_raw_weather_alert"] = alert
            approval_queue[key]["_confidence"] = confidence
            approval_queue[key]["article_id"] = None
        persist_state()
        if review_id:
            try:
                review_seen = kv_get("met_telegram_review_seen_v1", {}) or {}
                if not isinstance(review_seen, dict):
                    review_seen = {}
                review_seen[review_id] = {
                    "queued_at": utcnow().isoformat(), "content_lab_key": key,
                    "confidence": confidence,
                }
                if len(review_seen) > 500:
                    review_seen = dict(list(review_seen.items())[-500:])
                kv_set("met_telegram_review_seen_v1", review_seen)
            except Exception as review_seen_error:
                log.warning("[MMS TELEGRAM] review dedup save failed: %s", review_seen_error)
        _send_approval_card(key, approval_queue[key])
        log.info("[MMS TELEGRAM] low-confidence alert queued as %s (%.2f)", key.upper(), confidence)
        return True
    except Exception as exc:
        log.error("[MMS TELEGRAM] Content Lab review queue failed: %s", exc, exc_info=True)
        try:
            send_text(CORE_TEAM_CHAT_ID,
                      f"⚠️ <b>Possible @MaldivesMET alert needs manual review</b>\n{str(alert)[:1200]}",
                      thread_id=CONTENT_LAB_THREAD_ID)
        except Exception:
            pass
        return False


def expire_old_approvals():
    """
    Runs every few minutes:
    - Breaking held (low confidence): auto-posts after 30 min if no team action
    - Regular English: auto-posts after 45 min via queue
    - Dhivehi breaking: auto-posts after 2h
    - Regular Dhivehi: deleted after 2h
    """
    with _running_jobs_lock:
        if "expire_old_approvals" in _running_jobs:
            log.debug("expire_old_approvals already running — skipping overlap")
            return
        _running_jobs.add("expire_old_approvals")
    try:
        _expire_old_approvals_impl()
    finally:
        with _running_jobs_lock:
            _running_jobs.discard("expire_old_approvals")

def _expire_old_approvals_impl():
    now = utcnow()

    # Breaking held for confidence — auto-post after 30 min
    with _approval_lock:
        breaking_held = [k for k, v in approval_queue.items()
                         if v.get("lang") == "en"
                         and v.get("is_breaking", False)
                         and v.get("_held_for_confidence", False)
                         and not v.get("_manual_only")
                         and (now - v["created_at"]).total_seconds() > BREAKING_AUTOPOST_SECONDS]
    for k in breaking_held:
        with _approval_lock:
            item = approval_queue.pop(k, None)
        if not item:
            continue
        log.info(f"⏰ Breaking {k} auto-posting (30min, no review): {item.get('title','')[:50]}")
        try:
            buf = io.BytesIO(item["card_bytes"])
            queue_for_social(buf, item["caption"],
                key_label=f"{k.upper()} (breaking auto)",
                tg_ok=False, post_telegram=False, is_breaking=True,
                article_id=item.get("article_id"), title=item.get("title",""),
                summary=item.get("summary",""), cat=item.get("cat","BREAKING"),
                source=item.get("source","Samuga Media"), link=item.get("link",""),
                lang=item.get("lang","en"))
            send_text(CORE_TEAM_CHAT_ID,
                f"⏰ <b>{k.upper()} Breaking auto-posted</b> (30min, no review)\n"
                f"📰 {item.get('title','')[:80]}",
                thread_id=ALERT_THREAD_ID)
        except Exception as e:
            log.error(f"Breaking auto-post {k}: {e}")

    # Regular English auto-post after 45 min
    with _approval_lock:
        en_due = [k for k, v in approval_queue.items()
                  if v.get("lang") == "en"
                  and not v.get("is_breaking", False)
                  and not v.get("_manual_only")
                  and (now - v["created_at"]).total_seconds() > ENGLISH_AUTOPOST_SECONDS]
    for k in en_due:
        with _approval_lock:
            item = approval_queue.pop(k, None)
        if not item:
            continue
        title = item.get("title","")[:50]
        log.info(f"⏰ English {k} auto-queuing (45min, no review): {title}")
        try:
            buf = io.BytesIO(item["card_bytes"])
            queue_for_social(buf, item["caption"],
                key_label=f"{k.upper()} (auto)",
                tg_ok=False, post_telegram=False,
                article_id=item.get("article_id"), title=item.get("title",""),
                summary=item.get("summary",""), cat=item.get("cat","LOCAL"),
                source=item.get("source","Samuga Media"), link=item.get("link",""),
                lang=item.get("lang","en"), is_breaking=item.get("is_breaking", False))
            send_text(CORE_TEAM_CHAT_ID,
                f"⏰ <b>{k.upper()}</b> auto-posted (45min, no review)\n📰 {item.get('title','')[:80]}",
                thread_id=ALERT_THREAD_ID)
        except Exception as e:
            log.error(f"Auto-post queue {k}: {e}")

    # DV 30-min warning — alert team before card expires (DV never auto-posts)
    with _approval_lock:
        dv_warning = [k for k, v in approval_queue.items()
                      if v.get("lang") == "dv"
                      and not v.get("_manual_only")
                      and not v.get("_warned_30min")
                      and (now - v["created_at"]).total_seconds() > (DHIVEHI_EXPIRY_SECONDS - 1800)]
    for k in dv_warning:
        with _approval_lock:
            if k not in approval_queue:
                continue
            approval_queue[k]["_warned_30min"] = True
            title = approval_queue[k].get("title","")[:60]
            is_brk = approval_queue[k].get("is_breaking", False)
        brk_tag = "🚨 Breaking " if is_brk else ""
        send_text(CORE_TEAM_CHAT_ID,
            f"⚠️ <b>30-min warning</b> — {brk_tag}Dhivehi <code>{k.upper()}</code> expires in 30 minutes!\n"
            f"📰 {title}\n\n"
            f"Approve: <code>/approved {k}</code>  |  Reject: <code>/reject {k}</code>\n"
            f"<i>Dhivehi never auto-posts — it will be deleted if not approved.</i>",
            thread_id=ALERT_THREAD_ID)
        persist_state()

    # Dhivehi expiry — breaking ones auto-post after 2h, regular ones delete
    with _approval_lock:
        dv_due = [k for k, v in approval_queue.items()
                  if v["lang"] == "dv" and not v.get("_manual_only") and (now - v["created_at"]).total_seconds() > DHIVEHI_EXPIRY_SECONDS]
    for k in dv_due:
        with _approval_lock:
            item = approval_queue.pop(k, None)
        if not item:
            continue
        title = item.get("title","")[:40]
        # Dhivehi NEVER auto-posts — all DV cards just expire and get deleted
        if False and item.get("_auto_post_breaking") and item.get("dv_text"):
            log.info(f"⏰ Breaking Dhivehi {k} auto-posting after 2h: {title}")
            try:
                kw = item.get("keyword","local")
                bg = _approval_bg_from_item(item)
                ts_now = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
                card = generate_card(item["dv_text"], SAMUGA_PUBLIC_SOURCE, ts_now, item.get("cat","BREAKING"), bg)
                full_caption = (
                    f"🇲🇻 <b>{item['title']}</b>\n\n"
                    f"{item['dv_text']}\n\n"
                    f"📡 <b>ސަމުގާ މީޑިއާ</b> | @samugacommunity"
                )
                card.seek(0)
                tg_ok = send_to_telegram(card, full_caption)
                if tg_ok:
                    card.seek(0)
                    queue_for_social(io.BytesIO(card.getvalue()), full_caption,
                                     key_label=k.upper(), tg_ok=True,
                                     article_id=item.get("article_id"), title=item.get("title",""),
                                     summary=item.get("summary",""), cat=item.get("cat","BREAKING"),
                                     source=item.get("source","Samuga Media"), link=item.get("link",""),
                                     lang="dv", is_breaking=True)
                    send_text(CORE_TEAM_CHAT_ID,
                        f"⏰ <b>{k.upper()} Breaking Dhivehi auto-posted</b> (2h, no review)\n"
                        f"📰 {item['title'][:70]}",
                        thread_id=ALERT_THREAD_ID)
                    log.info(f"⏰ Breaking Dhivehi {k} auto-posted to community")
            except Exception as e:
                log.error(f"Breaking DV auto-post {k}: {e}")
        else:
            log.info(f"⏰ Dhivehi {k} expired (2h, not breaking, deleted): {title}")

    if en_due or dv_due:
        persist_state()

# Backwards-compat alias (old code references dhivehi_pending)
dhivehi_pending = approval_queue

# ── Core Team Config ──────────────────────────────────────────────────────────
CORE_TEAM_CHAT_ID = "-1002829230299"
CONTENT_LAB_THREAD_ID = 9061   # approvals, queue confirmations — Uly's workspace
ALERT_THREAD_ID       = 10169  # bot suggestions, developing stories, briefs, proactive insights
CORE_TEAM_MEMBERS = {
    "manchii": {"name": "Manchii", "full": "Abdul Muhsin", "role": "Founder & MD", "notes": "Big ideas, entrepreneur, boss, loves to push boundaries"},
    "mutte":   {"name": "Manchii", "full": "Abdul Muhsin", "role": "Founder & MD", "notes": "Big ideas, entrepreneur, boss, loves to push boundaries"},
    "uly":     {"name": "Uly", "full": "Mariyam Ulya", "role": "Co-Founder & Editor-in-Chief", "notes": "Journalist brain, editorial standards, keeps content sharp"},
    "ulya":    {"name": "Uly", "full": "Mariyam Ulya", "role": "Co-Founder & Editor-in-Chief", "notes": "Journalist brain, editorial standards, keeps content sharp"},
    "thooma":  {"name": "Thooma", "full": "Aminath Thooma", "role": "Presenter & Marketing Assistant", "notes": "Content face, presenter energy, needs confidence boosts sometimes"},
    "kit":     {"name": "Kity", "full": "Kit", "role": "Manchii's wife & idea contributor", "notes": "Creative, boosts team morale, great at boosting Thooma, shares fresh ideas"},
    "kity":    {"name": "Kity", "full": "Kit", "role": "Manchii's wife & idea contributor", "notes": "Creative, boosts team morale, great at boosting Thooma, shares fresh ideas"},
}

CORE_TEAM_PROACTIVE_TRIGGERS = [
    "?", "idea", "what do you think", "thoughts", "suggest", "brainstorm",
    "samuga", "content", "post", "story", "plan", "strategy", "marketing",
    "tiktok", "instagram", "facebook", "caption", "script", "video", "reel",
    "haha", "lol", "😂", "anyone", "guys", "let's", "lets", "what if", "how about"
]

# ── Rejection humor responses ────────────────────────────────────────────────
REJECT_RESPONSES = [
    "Okay okay, deleted. The article didn't make the cut. Just like my invite to your last outing. 💔",
    "Gone. Rejected. Just like that one pitch Manchii had at 2am. We don't talk about it. 🗑️",
    "Poof. Vanished. The article felt it too. 😭",
    "Rejected faster than a loan application. Card deleted. 🚮",
    "Understood. We move. The article does not. 👋",
    "That article just got voted off the island. Maldivian style. 🏝️",
    "Fine fine, I'll delete it. But between us — I thought it was good. Just saying. 🤷",
    "Deleted! The article is now in a better place. (The bin.) 🗑️✨",
    "I already knew you'd reject it. I just wanted to see if you'd catch it. You did. Respect. 🫡",
    "Card deleted. The source is probably crying somewhere. Not my problem. 😌",
    "Gone with the wind. And the article. Bye bye. 🌬️",
    "Noted, rejected, deleted. Three words that describe both this article and my weekend plans. 🙂",
    "You know what, I respect the standards. Card is gone. Moving on. 💪",
    "Deleted so fast the article didn't even see it coming. Neither did I honestly. 😅",
    "That one wasn't it. Removed. You're basically my editor brain at this point. 🧠",
    "Rejected. I'll add it to the list of things that didn't make it. The list is getting long. 📋",
    "Gone. The article will not be missed. By anyone. Especially not the readers. 🫠",
    "Okay the bin got a new resident. Hope it's comfortable in there. 🗑️",
    "Deleted faster than Manchii's sleep schedule. Which is saying something. ⚡",
    "Fair enough. Some stories aren't worth telling. This was one of them. Card gone. ✂️",
]

# ── PostgreSQL Database Layer (v6) ────────────────────────────────────────────
# Railway auto-injects DATABASE_URL when Postgres is in the project.
# The bot uses Postgres for the article archive + intelligence, but ALWAYS falls
# back to JSON files if the DB is unavailable, so it never breaks.
# ── Source Reliability Scoring ────────────────────────────────────────────────
# Higher = more trusted. Used as a tie-breaker and a scoring boost so a direct
# Mihaaru/MvCrisis story outranks a Google News scrape of the same topic.
def track_analytics(cat, is_breaking=False, social_ok=None):
    global analytics
    from datetime import timezone as _tz
    week = (datetime.now(_tz.utc) + timedelta(hours=5)).isocalendar()[1]
    if analytics["week_start"] != week:
        analytics = {"posts_by_cat": {}, "breaking_count": 0, "social_success": 0, "social_fail": 0, "week_start": week}
    if cat != "SOCIAL":
        analytics["posts_by_cat"][cat] = analytics["posts_by_cat"].get(cat, 0) + 1
    if is_breaking: analytics["breaking_count"] += 1
    if social_ok is True: analytics["social_success"] += 1
    if social_ok is False: analytics["social_fail"] += 1

def remember_post(title, cat, timestamp, is_breaking=False):
    today = (utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
    recent_posts.append({"title": title, "cat": cat, "time": timestamp,
                          "is_breaking": is_breaking, "date": today})
    if len(recent_posts) > 50: recent_posts.pop(0)
    track_analytics(cat)
    persist_state()

def get_conversation(uid):
    if uid not in user_conversations: user_conversations[uid] = []
    return user_conversations[uid]

def add_to_conversation(uid, role, content):
    conv = get_conversation(uid)
    conv.append({"role":role,"content":content})
    if len(conv) > 10:
        user_conversations[uid] = conv[-10:]
    # Evict stale sessions to bound memory growth (keep most recent 500 users)
    if len(user_conversations) > 500:
        keys = list(user_conversations.keys())
        for k in keys[:100]:
            user_conversations.pop(k, None)

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_mvt_hour(): return (utcnow().hour + 5) % 24
def is_day_mode(): return 6 <= get_mvt_hour() < 22

def is_fresh(entry, hours=24):
    try:
        pub = entry.get("published","")
        if pub:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo: dt = dt.replace(tzinfo=None)
            return utcnow() - dt < timedelta(hours=hours)
    except Exception as e: log.debug(f"is_fresh parse: {e}")
    return True

def can_post_regular():
    """
    Sprint A Part 1: Telegram daily limits removed.
    Content Lab buttons are now the single source of truth.
    AI pipeline still calls this so the funnel log line still works —
    it now always returns True.
    """
    return True

# ── Social filter — only quality LOCAL/DISASTER/relevant WORLD goes to socials ─
def allowed_for_social(article):
    """Only high-value articles go to Facebook/Instagram/X."""
    cat = article["cat"]
    # Never post these to social
    if cat in ["SPORTS", "FOOTBALL", "WEATHER", "TOURISM"]:
        return False
    if cat == "WORLD":
        # Only Maldives-relevant world news
        text = (article["title"] + " " + article.get("summary","")).lower()
        mv_terms = ["maldives","indian ocean","south asia","india","china","un ","dollar","oil price","global economy"]
        return any(t in text for t in mv_terms)
    # LOCAL and DISASTER always allowed
    return True

# ── Pending article queue — best article waiting for 90min window ─────────────
# Instead of posting to social every scan, we store the best article and post
# it only when the 90min Telegram window opens.
_pending_article = None  # holds the best unseen article between scans

# ── Social post daily counter (MVT based) ─────────────────────────────────────
social_post_counts = {"date": None, "count": 0}

def is_day_social():
    """6AM to 10PM MVT = day mode for socials"""
    h = mvt_now().hour
    return 6 <= h < 22

def _social_editorial_cap():
    """Samuga's own editorial pacing cap; this is not a Buffer plan limit."""
    if os.environ.get("SAMUGA_SOCIAL_EDITORIAL_CAP_ENABLED", "true").lower() != "true":
        return None
    default = 20 if is_day_social() else 3
    env_name = "SAMUGA_SOCIAL_EDITORIAL_CAP_DAY" if is_day_social() else "SAMUGA_SOCIAL_EDITORIAL_CAP_NIGHT"
    return _safe_env_int(env_name, default, minimum=1, maximum=500)

def can_post_social():
    """Apply Samuga editorial pacing independently from Buffer/API limits."""
    global social_post_counts
    today = mvt_now().date()
    if social_post_counts["date"] != today:
        social_post_counts = {"date": today, "count": 0}
    limit = _social_editorial_cap()
    return True if limit is None else social_post_counts["count"] < limit

def increment_social_count():
    global social_post_counts
    today = mvt_now().date()
    if social_post_counts["date"] != today:
        social_post_counts = {"date": today, "count": 0}
    social_post_counts["count"] += 1
    persist_state()
    limit = _social_editorial_cap()
    cap_text = "disabled" if limit is None else str(limit)
    log.info(f"📊 Samuga editorial social posts today: {social_post_counts['count']} (editorial cap: {cap_text})")
# ── Telegram ──────────────────────────────────────────────────────────────────
def send_to_telegram(buf, caption):
    """Post a photo to the community channel. Returns message_id (int) or False.
    Respects Telegram's retry_after on 429 with up to 2 retries."""
    import random as _rnd
    if posting_paused():
        log.warning("🛑 Telegram public post blocked — POSTING_PAUSED=true")
        return False
    safe_caption = samuga_public_caption(caption)
    if not public_text_is_safe(safe_caption):
        log.error(f"🚫 Telegram blocked unsafe public caption: {str(safe_caption)[:120]}")
        return False
    for attempt in range(3):
        try:
            if hasattr(buf, "seek"):
                buf.seek(0)
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={"chat_id": TELEGRAM_CHANNEL_ID, "caption": safe_caption, "parse_mode": "HTML"},
                files={"photo": ("card.png", buf, "image/png")}, timeout=30)
            if resp.status_code == 200:
                mid = resp.json().get("result", {}).get("message_id")
                log.info(f"✅ Posted to Telegram (msg {mid})")
                return mid or True
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                retry_after = min(int(retry_after or 5), 60)
                log.warning(f"Telegram 429: retry_after={retry_after}s (attempt {attempt+1}/3)")
                time.sleep(retry_after + _rnd.uniform(0.5, 2))
                continue
            else:
                resp.raise_for_status()
        except requests.exceptions.Timeout:
            log.warning(f"Telegram sendPhoto timeout (attempt {attempt+1}/3)")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
        except Exception as e:
            log.error(f"Telegram: {_mask_secrets(str(e))}")
            return False
    log.error("Telegram: all retries exhausted")
    return False

def download_telegram_photo(photo_list):
    """Download the highest quality photo from a Telegram photo array"""
    try:
        # Get largest photo (last in list)
        file_id = photo_list[-1]["file_id"]
        # Get file path
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
            params={"file_id": file_id}, timeout=10
        )
        file_path = resp.json()["result"]["file_path"]
        # Download the file
        img_resp = requests.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
            timeout=20
        )
        from PIL import Image
        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
        log.info("✅ Telegram photo downloaded — returning PIL Image for card generation")
        return img  # generate_card expects PIL Image, not BytesIO
    except Exception as e:
        log.error(f"Photo download: {e}")
        return None

def _make_inline_kb(buttons):
    """Build Telegram inline_keyboard JSON from list of (text, callback_data) tuples per row."""
    return {"inline_keyboard": [[{"text": t, "callback_data": c} for t, c in row] for row in buttons]}

def send_photo(chat_id, buf, caption, thread_id=None, reply_markup=None):
    """Send a photo to any Telegram chat/channel, optionally to a topic thread"""
    try:
        buf.seek(0)
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        if thread_id:    data["message_thread_id"] = thread_id
        if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data=data,
            files={"photo": ("card.png", buf, "image/png")},
            timeout=30
        )
        resp.raise_for_status()
        msg_id = resp.json().get("result", {}).get("message_id")
        log.info("✅ Photo sent to Telegram")
        return msg_id
    except Exception as e:
        log.error(f"send_photo: {e}")
        return None

def send_text(chat_id, text, reply_to=None, thread_id=None, reply_markup=None):
    import random as _rnd
    # Telegram hard limit is 4096 chars. Truncate rather than get a 400 error.
    if text and len(text) > 4090:
        text = text[:4087] + "…"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to:     payload["reply_to_message_id"] = reply_to
    if thread_id:    payload["message_thread_id"] = thread_id
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    for attempt in range(3):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=payload, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("result", {}).get("message_id")
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                retry_after = min(int(retry_after or 5), 60)
                log.warning(f"send_text 429: retry_after={retry_after}s (attempt {attempt+1}/3)")
                time.sleep(retry_after + _rnd.uniform(0.5, 1.5))
                continue
            else:
                log.error(f"Send text HTTP {resp.status_code}: {resp.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            log.warning(f"send_text timeout (attempt {attempt+1}/3)")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
        except Exception as e:
            log.error(f"Send text: {e}")
            return None
    return None

def edit_message_reply_markup(chat_id, message_id, reply_markup):
    """Remove or update buttons on a previously sent message."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup",
            json={"chat_id": chat_id, "message_id": message_id,
                  "reply_markup": json.dumps(reply_markup)},
            timeout=10)
    except Exception as e:
        log.error(f"edit_markup: {e}")

def answer_callback_query(callback_query_id, text="", show_alert=False):
    """Acknowledge a button tap so Telegram stops showing the loading spinner."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
            timeout=10)
    except Exception as e:
        log.error(f"answer_callback: {e}")

_ops_last_alerts = {}
_ops_alerts_lock = threading.RLock()  # guards _ops_last_alerts
_ops_watchdog_state = {
    "source_health_alerts": {},
    "duplicate_hits_recent": [],   # utc datetimes
    "manual_post_failures": [],    # utc datetimes
    "social_queue_stuck_since": None,
    "last_posted_dv": 0,
}
website_banner = {"active": False, "text": "", "image_url": "", "updated_at": None}

def alert_admin(message, dedupe_key=None, cooloff_minutes=20):
    """Send an operational alert into the Alert thread without spamming duplicates."""
    try:
        key = dedupe_key or _caption_match_key(message) or str(hash(message))
        now = utcnow()
        with _ops_alerts_lock:
            last = _ops_last_alerts.get(key)
            if last and (now - last).total_seconds() < cooloff_minutes * 60:
                return False
            _ops_last_alerts[key] = now
            # Evict old entries to bound memory growth
            if len(_ops_last_alerts) > 500:
                cutoff = now - timedelta(hours=2)
                for k in [k for k, v in list(_ops_last_alerts.items()) if v < cutoff]:
                    _ops_last_alerts.pop(k, None)
        send_text(CORE_TEAM_CHAT_ID, f"⚠️ <b>Samuga Ops Alert</b>\n\n{message}", thread_id=ALERT_THREAD_ID)
        return True
    except Exception as e:
        log.error(f"alert_admin: {e}")
        return False

def delete_telegram_message(chat_id, message_id):
    """Delete a Telegram message when the bot has rights in the chat."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=15
        )
        data = r.json() if r.ok else {}
        ok = bool(r.ok and data.get("ok"))
        if not ok:
            log.warning(f"deleteMessage failed: {str(data)[:200]}")
        return ok
    except Exception as e:
        log.error(f"delete_telegram_message: {e}")
        return False

def download_telegram_photo_bytes(photo_list):
    """Download the highest quality Telegram photo and return raw bytes."""
    try:
        if not photo_list:
            return None
        file_id = photo_list[-1]["file_id"]
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
            params={"file_id": file_id}, timeout=15
        )
        data = resp.json()
        file_path = data["result"]["file_path"]
        img_resp = requests.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
            timeout=25
        )
        if img_resp.ok and img_resp.content:
            return img_resp.content
    except Exception as e:
        log.error(f"download_telegram_photo_bytes: {e}")
    return None

def website_article_url(article_id=None, slug=None):
    """Return the public website URL for an article."""
    base = (SAMUGA_CAPTION_LINK or "https://samugamedia.com").rstrip("/")
    if article_id:
        return f"{base}/article?id={article_id}"
    if slug:
        return f"{base}/article?slug={slug}"
    return base

def article_share_url(article_id):
    """
    Return the SSR share URL for an article — use this when sharing on socials.
    This URL hits the Railway Flask /share endpoint which serves real OG meta tags
    that Facebook, X, Telegram and WhatsApp can read without executing JavaScript.
    The user gets redirected to the actual article page instantly.
    """
    base = (SAMUGA_API_BASE or "https://samuga-news-bot-production.up.railway.app").rstrip("/")
    return f"{base}/share?id={article_id}"

def extract_inline_post_to_web_body(text):
    """Allow admins to send article text + /post to web in the same message."""
    raw = str(text or "")
    clean = re.sub(r'@SamugaNewsBot\b', '', raw, flags=re.I)
    clean = re.sub(r'(?im)^\s*/post\s+to\s+web\s*$', '', clean)
    clean = re.sub(r'(?im)^\s*/postweb\s*$', '', clean)
    clean = re.sub(r'(?im)^\s*/posttoweb\s*$', '', clean)
    clean = re.sub(r'(?im)^\s*/post\s+web\s*$', '', clean)
    clean = clean.strip()
    return clean

# ── Gemini Dhivehi Caption ────────────────────────────────────────────────────
# Production model chain. Override with GEMINI_MODELS="model-a,model-b".
# Shut-down 2.0/1.5 model IDs are deliberately excluded.
_GEMINI_MODELS_ENV = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()]
GEMINI_MODELS = _GEMINI_MODELS_ENV or [
    # Emergency cost-safe default. Add another model explicitly through
    # GEMINI_MODELS only after reviewing AI Usage diagnostics.
    "gemini-2.5-flash-lite",
]
GEMINI_MAX_MODELS_PER_REQUEST = _safe_env_int("GEMINI_MAX_MODELS_PER_REQUEST", 1, minimum=1, maximum=2)

# A 429 is normally project quota pressure, not a model-quality failure. By
# default, stop after the first 429 instead of immediately doubling the failed
# task against the fallback model. Non-429 model failures may still fall back.
GEMINI_FALLBACK_ON_429 = os.environ.get("GEMINI_FALLBACK_ON_429", "false").lower() == "true"

# Only the top Dhivehi finalists receive semantic Gemini translation for
# cross-language deduplication. Bulk scoring and same-language dedup stay local.
DV_GEMINI_SHORTLIST_MAX = max(1, int(os.environ.get("DV_GEMINI_SHORTLIST_MAX", "5")))
BREAKING_DV_GEMINI_MAX_PER_CHECK = max(0, int(os.environ.get("BREAKING_DV_GEMINI_MAX_PER_CHECK", "1")))
SEMANTIC_SIGNAL_CACHE_MAX = max(200, int(os.environ.get("SEMANTIC_SIGNAL_CACHE_MAX", "1500")))

# Shared health state keeps diagnostics accurate and prevents a quota storm from
# launching dozens of identical requests during one newsroom scan.
_GEMINI_LAST_OK = {"ts": None, "model": None}
_GEMINI_HEALTH = {
    "status": "unknown",      # healthy | rate_limited | timeout | auth_failure | unavailable
    "http": None,
    "reason": "",
    "circuit_until": 0.0,
    "model": None,
}
_GEMINI_LOCK = threading.RLock()


def _gemini_post(prompt, timeout=30):
    """Call Gemini with fallback, circuit protection and full request telemetry."""
    caller_frame = inspect.currentframe().f_back
    caller = caller_frame.f_code.co_name if caller_frame else "unknown"
    feature = _normalize_ai_feature(
        purpose=_current_ai_purpose("generation/translation"),
        caller=caller,
        prompt=str(prompt or "")[:1200],
    )
    if not GEMINI_API_KEY:
        with _GEMINI_LOCK:
            _GEMINI_HEALTH.update(status="auth_failure", http=None,
                                  reason="GEMINI_API_KEY not set", model=None)
        # No provider request was sent; keep the blocked attempt visible.
        AIRequestTracker.start(
            "Gemini", "unconfigured", feature=feature, caller=caller,
            purpose=_current_ai_purpose("generation/translation"), prompt=prompt,
        ).blocked("authentication")
        return None

    now_ts = time.time()
    with _GEMINI_LOCK:
        circuit_until = float(_GEMINI_HEALTH.get("circuit_until") or 0)
        if circuit_until > now_ts:
            remaining = int(circuit_until - now_ts)
            log.debug(f"[AI] Gemini circuit open — retry in {remaining}s")
            AIRequestTracker.start(
                "Gemini", str(_GEMINI_HEALTH.get("model") or "circuit"),
                feature=feature, caller=caller,
                purpose=_current_ai_purpose("generation/translation"), prompt=prompt,
            ).blocked("circuit_open")
            return None

    saw_429 = False
    longest_retry_after = 0
    timeout_count = 0

    for model_index, model in enumerate(GEMINI_MODELS[:GEMINI_MAX_MODELS_PER_REQUEST]):
        tracker = AIRequestTracker.start(
            "Gemini", model, feature=feature, caller=caller,
            purpose=_current_ai_purpose("generation/translation"), prompt=prompt,
            retry_count=model_index,
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            if not _reserve_ai_call("Gemini", f"generation/translation ({model})", feature=tracker.feature, article_id=tracker.article_id, article_title=tracker.article_title, source_url=tracker.source_url, retry_count=tracker.retry_count):
                tracker.blocked(_ai_reserve_block_reason())
                return None
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=timeout,
            )
            status = int(resp.status_code)
            provider_request_id = str(
                resp.headers.get("x-request-id") or resp.headers.get("x-goog-request-id") or ""
            )

            if status == 200:
                data = resp.json()
                usage = data.get("usageMetadata") or {}
                input_tokens = int(usage.get("promptTokenCount") or 0)
                output_tokens = int(usage.get("candidatesTokenCount") or 0)
                cached_tokens = int(usage.get("cachedContentTokenCount") or 0)
                candidates = data.get("candidates") or []
                parts = (candidates[0].get("content", {}).get("parts", [])
                         if candidates else [])
                text = (parts[0].get("text", "").strip() if parts else "")
                if not text:
                    tracker.failure(
                        "Gemini returned a blank response", http_status=200,
                        error_code="invalid_response", input_tokens=input_tokens,
                        output_tokens=output_tokens, cached_tokens=cached_tokens,
                        provider_request_id=provider_request_id,
                    )
                    log.warning(f"[AI] Gemini {model}: blank response")
                    continue
                tracker.success(
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    cached_tokens=cached_tokens, cache_read_tokens=cached_tokens,
                    http_status=200, provider_request_id=provider_request_id,
                    response_text=text,
                )
                with _GEMINI_LOCK:
                    _GEMINI_LAST_OK["ts"] = utcnow()
                    _GEMINI_LAST_OK["model"] = model
                    _GEMINI_HEALTH.update(
                        status="healthy", http=200, reason="", model=model,
                        circuit_until=0.0,
                    )
                log.info(f"[AI] Gemini {model}: OK")
                return text

            error_text = ""
            try:
                error_text = (resp.json().get("error") or {}).get("message") or resp.text[:500]
            except Exception:
                error_text = resp.text[:500]
            tracker.failure(
                error_text or f"HTTP {status}", http_status=status,
                provider_request_id=provider_request_id,
            )

            if status == 429:
                saw_429 = True
                try:
                    retry_after = int(float(resp.headers.get("Retry-After", "0") or 0))
                except Exception:
                    retry_after = 0
                longest_retry_after = max(longest_retry_after, retry_after)
                log.warning(f"[AI] Gemini {model}: rate limited (429)")
                if not GEMINI_FALLBACK_ON_429:
                    pause_seconds = max(300, longest_retry_after)
                    with _GEMINI_LOCK:
                        _GEMINI_HEALTH.update(
                            status="rate_limited", http=429,
                            reason=f"quota limited; retry in {pause_seconds}s",
                            circuit_until=time.time() + pause_seconds,
                            model=model,
                        )
                    log.warning(f"[AI] Gemini circuit open after first 429 — retry after {pause_seconds}s")
                    return None
                continue

            if status in (400, 401, 403):
                with _GEMINI_LOCK:
                    _GEMINI_HEALTH.update(
                        status="auth_failure", http=status,
                        reason=f"HTTP {status}", model=model,
                        circuit_until=0.0,
                    )
                log.error(f"[AI] Gemini {model}: AUTH/REQUEST FAILURE HTTP {status}")
                return None

            if status in (500, 502, 503, 504):
                with _GEMINI_LOCK:
                    _GEMINI_HEALTH.update(
                        status="unavailable", http=status,
                        reason=f"HTTP {status}", model=model,
                    )
                log.warning(f"[AI] Gemini {model}: unavailable HTTP {status}")
                continue

            with _GEMINI_LOCK:
                _GEMINI_HEALTH.update(
                    status="unavailable", http=status,
                    reason=f"HTTP {status}", model=model,
                )
            log.warning(f"[AI] Gemini {model}: HTTP {status}")

        except requests.exceptions.Timeout as exc:
            tracker.failure(exc, error_code="timeout")
            timeout_count += 1
            with _GEMINI_LOCK:
                _GEMINI_HEALTH.update(
                    status="timeout", http=None,
                    reason=f"timeout after {timeout}s", model=model,
                )
            log.warning(f"[AI] Gemini {model}: timeout after {timeout}s")
        except Exception as exc:
            tracker.failure(exc)
            with _GEMINI_LOCK:
                _GEMINI_HEALTH.update(
                    status="unavailable", http=None,
                    reason=str(exc)[:160], model=model,
                )
            _critical_ai_failure(f"Gemini {model}", exc)

    if saw_429:
        pause_seconds = max(300, longest_retry_after)
        with _GEMINI_LOCK:
            _GEMINI_HEALTH.update(
                status="rate_limited", http=429,
                reason=f"quota limited; retry in {pause_seconds}s",
                circuit_until=time.time() + pause_seconds,
            )
        _critical_ai_failure("Gemini quota", RuntimeError(
            f"All configured Gemini models were rate limited; retry after {pause_seconds}s"
        ))
    elif timeout_count:
        _critical_ai_failure("Gemini timeout", RuntimeError(
            f"All configured Gemini models timed out after {timeout}s"
        ))
    else:
        _critical_ai_failure("Gemini API", RuntimeError("All configured Gemini models failed"))
    return None


def _strip_telegram_metadata(text):
    """Remove Telegram forwarding/relay artifacts that leak into scraped DV/EN
    channel text before it reaches public captions (Instagram/Facebook/X).

    Strips:
      - forward arrows  -->  and leading/trailing  >  relay markers
      - Telegram relative timestamps: "8 hour 36 minutes ago",
        including the Dhivehi filler "ވަރަށް" wedged inside them
      - @channel mentions and t.me / telegram.me links
      - "Forwarded from ..." / "via @..." attribution lines
    """
    if not text:
        return text
    s = str(text)

    # t.me / telegram.me links
    s = re.sub(r"https?://(?:t\.me|telegram\.me)/\S+", "", s, flags=re.I)
    # Forwarded-from / via attribution lines
    s = re.sub(r"(?im)^\s*(?:forwarded\s+from|via)\b.*$", "", s)
    # @channel mentions
    s = re.sub(r"(?<!\w)@[A-Za-z0-9_]{4,}", "", s)
    # Telegram relative timestamps, e.g. "8 hour 36 minutes ago",
    # "about 2 hours ago", with optional Dhivehi filler words in between.
    s = re.sub(
        r"(?i)(?:about\s+)?\d+\s*(?:[^\d\n]{0,12}?)"
        r"(?:second|minute|min|hour|hr|day|week|month|year)s?"
        r"(?:\s*[^\d\n]{0,12}?\d+\s*(?:second|minute|min|hour|hr|day|week|month|year)s?)?"
        r"\s*ago\b",
        "",
        s,
    )
    # Forward arrows and stray relay markers
    s = s.replace("-->", "").replace("—>", "").replace("→", "")
    s = re.sub(r"(?m)^\s*>+\s*", "", s)   # leading quote/relay markers
    s = re.sub(r"\s*-->\s*", " ", s)

    # Tidy whitespace left behind
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"^\s+|\s+$", "", s)
    return s

def _claude_confirm_breaking(title, summary=""):
    """
    Final editorial sanity check before a breaking story auto-posts to every
    platform with no human review. One tiny Claude Haiku call (~10 tokens out).

    Returns:
      True  — confirmed real, ongoing/urgent incident → OK to auto-post
      False — drill/training/routine/diplomatic/old news → hold for review
      None  — API unavailable/unclear → caller decides (we fail-open so an
              Anthropic outage never silences genuine multi-source breaking)
    """
    if not ANTHROPIC_API_KEY:
        return None
    try:
        prompt = (
            "You are the breaking-news gatekeeper for a Maldivian newsroom.\n"
            "Decide if this story is a REAL, CURRENT, URGENT incident that justifies "
            "an immediate BREAKING NEWS alert to the public.\n\n"
            "Answer NO if it is any of: a drill/exercise/training/simulation, a signing/"
            "agreement/MOU/diplomatic event, an appointment, a report about statistics or "
            "studies, an anniversary/retrospective of a past event, routine government or "
            "business news, or promotional content.\n"
            "Answer YES only for a genuinely urgent incident happening now or just "
            "confirmed (deaths, fire, accident, disaster, major security event, sudden "
            "major political crisis).\n\n"
            f"Title: {title}\n"
            f"Summary: {str(summary)[:400]}\n\n"
            "Reply with exactly one word: YES or NO"
        )
        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = (msg.content[0].text or "").strip().upper()
        if answer.startswith("YES"):
            return True
        if answer.startswith("NO"):
            return False
        return None
    except Exception as exc:
        if not _is_ai_budget_exceeded(exc):
            _critical_ai_failure("Claude breaking-news gate", exc)
        return None


def _claude_dhivehi_caption_fallback(english_text, title):
    """Single-call emergency fallback for the FINAL Dhivehi winner only.

    This is never used for bulk scoring or deduplication. It protects Content
    Lab quality when Gemini is rate-limited so raw Latin Thaana is not shown as
    a finished Dhivehi caption.
    """
    if not ANTHROPIC_API_KEY:
        return None
    try:
        prompt = f"""You are a Maldivian news editor for Samuga Media.

Write a short public news caption in proper Dhivehi Thaana script.

Rules:
- Output ONLY Dhivehi Thaana.
- 2 to 3 natural sentences.
- Clean Maldivian news style.
- Preserve the facts exactly; do not add anything.
- Do not include source links.
- Never output Latin Thaana or romanized Dhivehi.
- Brand names may remain in English only when necessary.

Title:
{title}

Summary:
{english_text}
"""
        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=420,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            getattr(block, "text", "") for block in (getattr(msg, "content", None) or [])
        ).strip()
        if text and is_dhivehi(text):
            log.info("✅ Claude emergency Dhivehi fallback done")
            return _strip_telegram_metadata(strip_source_links(text).strip())
        if text:
            log.warning("Claude Dhivehi fallback returned non-Thaana text — rejected")
    except Exception as exc:
        if not _is_ai_budget_exceeded(exc):
            _critical_ai_failure("Claude Dhivehi fallback", exc)
    return None


def make_dhivehi_caption(english_text, title):
    """Convert English/Latin news text to clean Dhivehi Thaana using Gemini.

    Uses system_instruction (hard constraint), few-shot examples (quality anchor),
    loanword glossary (prevents token panic on technical terms), low temperature
    (0.2 — critical for low-resource language), and 3 retries per model with backoff.
    Thaana lines are extracted so English preamble/apologies are discarded rather
    than causing a full rejection. Returns None on failure — callers skip gracefully.

    Respects the shared circuit breaker. When quota is exhausted, firing 6 more
    retries makes recovery worse — the circuit must be allowed to breathe.
    """
    import random as _rnd
    if not GEMINI_API_KEY:
        return None

    # Respect the circuit — if quota is exhausted, don't burn more calls
    with _GEMINI_LOCK:
        circuit_until = float(_GEMINI_HEALTH.get("circuit_until") or 0)
    if circuit_until > time.time():
        remaining = int(circuit_until - time.time())
        log.debug(f"[AI] Dhivehi caption skipped — circuit open for {remaining}s more")
        return None

    english_text = _strip_telegram_metadata(english_text)
    title = _strip_telegram_metadata(title)

    # Build a compact, evidence-only fact pack first when DeepSeek is configured.
    # Gemini then spends its tokens on natural Thaana and fili instead of re-reading
    # or reasoning over the raw source. The old direct path remains as a safe fallback.
    fact_pack = None
    try:
        fact_pack = _deepseek_extract_fact_pack(
            title=title,
            summary=english_text,
            source_text=english_text,
            category="LOCAL",
            source_count=1,
        )
    except Exception as exc:
        log.warning(f"[AI][DEEPSEEK] Dhivehi fact-pack fallback: {exc}")
        fact_pack = None

    # Hard role + constraints in system_instruction — not in user prompt
    system_instruction = (
        "You are an expert Maldivian translator and native Dhivehi copywriter for Samuga Media.\n"
        "Your sole task is to write news captions in fluent, natural, grammatically correct Dhivehi "
        "using the Thaana script.\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Output ONLY Unicode Thaana script characters and standard punctuation.\n"
        "2. NEVER include English words, Latin script, or preambles. "
        "Do NOT write 'Here is the translation:', 'I apologize', or any English at all.\n"
        "3. If a modern technical word has no direct Dhivehi equivalent, transliterate its sound "
        "phonetically into Thaana script (e.g., write 'ޓީވީ' for TV, 'ޔޫޓިލިޓީ' for utility, "
        "'ޑިޝް' for dish, 'ބަޖެޓް' for budget, 'ސޯޝަލް މީޑިއާ' for social media). "
        "Never leave the English word as-is.\n"
        "4. Do not explain your choices. Output the final Dhivehi caption immediately and nothing else."
    )

    # Few-shot examples — critical for low-resource language quality
    few_shot = (
        "###\n"
        "Examples of expected quality:\n\n"
        "Input: \"Please check your electricity bill today.\"\n"
        "Output: \"މިއަދު ތިޔަބޭފުޅުންގެ ކަރަންޓު ބިލް ޗެކްކޮށްލައްވާ.\"\n\n"
        "Input: \"The ferry service to the island has been delayed due to bad weather.\"\n"
        "Output: \"ވިއްސާރަވުމުގެ ސަބަބުން ރަށަށް ކުރާ ފެރީ ދަތުރުތައް ވަނީ ލަސްވެފައެވެ.\"\n\n"
        "Input: \"Police arrested three people in connection with a drug case in Malé.\"\n"
        "Output: \"މާލޭގައި ހިންގި މަސްތުވާތަކެތީގެ މައްސަލައަކާ ގުޅިގެން ތިން މީހަކު ފުލުހުން ހައްޔަރުކޮށްފިއެވެ.\"\n"
        "###\n\n"
    )

    if fact_pack:
        verified_input = (
            "VERIFIED FACT PACK (JSON):\n"
            + json.dumps(fact_pack, ensure_ascii=False, separators=(",", ":"))
        )
        input_rule = (
            "Use only the verified claims in this JSON. Do not add background, names, "
            "numbers, dates, causes, quotes, or outcomes that are not present. "
            "Translate into natural Maldivian Dhivehi using correct Thaana Unicode and proper fili. "
            "Use English only for a genuinely non-translatable proper noun; otherwise transliterate it into Thaana."
        )
    else:
        verified_input = f"Title: {title}\nSummary: {english_text}"
        input_rule = (
            "Only use facts from the supplied title and summary. Translate into natural Maldivian Dhivehi "
            "using correct Thaana Unicode and proper fili."
        )

    user_prompt = (
        f"{few_shot}"
        f"Now write a 2-3 sentence Dhivehi Thaana news caption for Samuga Media.\n"
        f"Clean Maldivian news style. No source links. {input_rule}\n\n"
        f"{verified_input}"
    )

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.2},
    }

    max_attempts_per_model = 1 + _safe_env_int("GEMINI_MAX_RETRIES", 2, minimum=0, maximum=2)
    for i, model in enumerate(GEMINI_MODELS[:GEMINI_MAX_MODELS_PER_REQUEST]):
        retry_delay = 0
        for attempt in range(max_attempts_per_model):
            tracker = AIRequestTracker.start(
                "Gemini", model, feature="Translation", caller="make_dhivehi_caption",
                purpose="Dhivehi caption", prompt=user_prompt,
                retry_count=(i * 3) + attempt, article_title=title,
            )
            try:
                if retry_delay > 0:
                    time.sleep(retry_delay)
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={GEMINI_API_KEY}"
                )
                if not _reserve_ai_call("Gemini", f"Dhivehi caption ({model}, attempt {attempt + 1})", feature=tracker.feature, article_id=tracker.article_id, article_title=tracker.article_title, source_url=tracker.source_url, retry_count=tracker.retry_count):
                    tracker.blocked(_ai_reserve_block_reason())
                    return None
                resp = requests.post(url, json=payload, timeout=30)
                status = int(resp.status_code)
                provider_request_id = str(resp.headers.get("x-request-id") or resp.headers.get("x-goog-request-id") or "")
                data = resp.json() if status == 200 else {}
                usage = data.get("usageMetadata") or {}
                input_tokens = int(usage.get("promptTokenCount") or 0)
                output_tokens = int(usage.get("candidatesTokenCount") or 0)
                cached_tokens = int(usage.get("cachedContentTokenCount") or 0)

                if status == 200:
                    candidates = data.get("candidates") or []
                    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                    raw = (parts[0].get("text", "").strip() if parts else "")
                    if not raw:
                        tracker.failure(
                            "Gemini returned a blank Dhivehi response", http_status=200,
                            error_code="invalid_response", input_tokens=input_tokens,
                            output_tokens=output_tokens, cached_tokens=cached_tokens,
                            provider_request_id=provider_request_id,
                        )
                        log.warning(f"[AI] Gemini {model}: blank Dhivehi response")
                        break
                    thaana_lines = [line for line in raw.splitlines() if any('\u0780' <= c <= '\u07BF' for c in line)]
                    thaana_only = "\n".join(thaana_lines).strip()
                    if thaana_only:
                        tracker.success(
                            input_tokens=input_tokens, output_tokens=output_tokens,
                            cached_tokens=cached_tokens, cache_read_tokens=cached_tokens,
                            provider_request_id=provider_request_id, response_text=thaana_only,
                        )
                        log.info(f"✅ Gemini Dhivehi caption done ({model}, attempt {attempt+1})")
                        with _GEMINI_LOCK:
                            _GEMINI_LAST_OK["ts"] = utcnow()
                            _GEMINI_LAST_OK["model"] = model
                            _GEMINI_HEALTH.update(status="healthy", http=200, reason="", model=model, circuit_until=0.0)
                        return _strip_telegram_metadata(strip_source_links(thaana_only).strip())
                    tracker.failure(
                        "Gemini response did not contain valid Thaana", http_status=200,
                        error_code="invalid_response", input_tokens=input_tokens,
                        output_tokens=output_tokens, cached_tokens=cached_tokens,
                        provider_request_id=provider_request_id,
                    )
                    log.warning(f"[AI] Gemini {model}: no Thaana lines in response — skipping")
                    break

                error_text = ""
                try:
                    error_text = (resp.json().get("error") or {}).get("message") or resp.text[:500]
                except Exception:
                    error_text = resp.text[:500]
                tracker.failure(error_text or f"HTTP {status}", http_status=status, provider_request_id=provider_request_id)
                if status == 429:
                    try:
                        retry_after = int(resp.headers.get("Retry-After", 0))
                    except Exception:
                        retry_after = 0
                    backoff = retry_after if retry_after > 0 else (2 ** attempt * 2 + _rnd.uniform(0.5, 1.5))
                    backoff = min(backoff, 30)
                    log.warning(f"[AI] Gemini {model}: quota (429), backoff {backoff:.1f}s")
                    retry_delay = backoff
                    continue
                if status == 404:
                    log.warning(f"[AI] Gemini {model}: model not available on this API key (404) — skipping")
                    break
                if status == 503:
                    backoff = 2 ** attempt + _rnd.uniform(0.5, 1.5)
                    log.warning(f"[AI] Gemini {model}: unavailable (503), backoff {backoff:.1f}s")
                    retry_delay = backoff
                    continue
                if status in (400, 401, 403):
                    log.error(f"[AI] Gemini {model}: auth failure HTTP {status}")
                    return None
                log.warning(f"[AI] Gemini {model}: HTTP {status} — skipping")
                break
            except requests.exceptions.Timeout as exc:
                tracker.failure(exc, error_code="timeout")
                backoff = 2 ** attempt + _rnd.uniform(0, 1)
                log.warning(f"[AI] Gemini {model}: timeout (attempt {attempt+1}), backoff {backoff:.1f}s")
                retry_delay = backoff
                continue
            except Exception as exc:
                tracker.failure(exc)
                _critical_ai_failure(f"Gemini Dhivehi caption ({model})", exc)
                break
        if i < len(GEMINI_MODELS) - 1:
            time.sleep(_rnd.uniform(0.5, 1.5))

    _critical_ai_failure(
        "Gemini Dhivehi caption",
        RuntimeError("All configured Gemini models failed to produce valid Thaana"),
    )
    return None

# ── Safety + dedup normalization layer ────────────────────────────────────────
_INTERNAL_NEWS_BLOCKLIST = [
    "technical issue", "being fixed", "sorry for the trouble", "sorry for the inconvenience",
    "temporarily unavailable", "maintenance", "test post", "debug", "samuga media is facing",
    "issue is being fixed", "we are fixing", "service interruption"
]
_MARKUP_JUNK_PATTERNS = [
    r"\.cls-\d", r"fill-rule\s*:", r"evenodd", r"<svg", r"</svg", r"xmlns=",
    r"viewbox", r"path\s+d=", r"fill:\s*#"
]
_signal_key_cache = {}
_signal_key_cache_lock = threading.RLock()  # guards _signal_key_cache

def gemini_dhivehi_to_english(text):
    """Translate Thaana or Latin-Thaana news text into clean English for finalist dedup."""
    if not GEMINI_API_KEY or not text:
        return None
    prompt = f"""Translate this Dhivehi news text (Thaana or Latin transliteration) into clean English.

Rules:
- Output ONLY English.
- Do not add new facts.
- Keep names and places accurate.
- Clean short newsroom style.

Text:
{text}
"""
    out = _gemini_post(prompt, timeout=18)
    if out and not is_dhivehi(out):
        return strip_source_links(out).strip()
    return None

def contentlab_candidate_is_safe(title="", summary="", source="", lang="en"):
    """Block internal/system chatter, CSS/SVG junk, and fake newsroom items before Content Lab."""
    combined = strip_source_links(f"{title}\n{summary}").strip()
    c_lower = combined.lower()
    for bad in _INTERNAL_NEWS_BLOCKLIST:
        if bad in c_lower:
            return False, f"internal/system text: {bad}"
    for pat in _MARKUP_JUNK_PATTERNS:
        if re.search(pat, combined, re.I):
            return False, f"markup/css junk: {pat}"
    if combined.startswith(".") and "{" in combined and "}" in combined:
        return False, "css-like content"
    # Extremely short Samuga-self lines with no news detail are not news.
    if source.lower().startswith("samuga") and len(combined.split()) < 8:
        return False, "samuga internal short text"
    # Title is a raw URL — rewrite_news failed to produce a headline.
    # A URL stored as the title produces blank social posts and broken website cards.
    _title_stripped = str(title or "").strip()
    if re.match(r'https?:/{1,2}', _title_stripped):
        return False, f"title is a raw URL — no rewritten headline: {_title_stripped[:80]}"
    return True, ""

def should_publish_dhivehi_to_website(item=None, approved=False):
    """
    Dhivehi must never appear on the website unless a human approved it.
    For safety, approved Dhivehi website publishing stays OFF unless
    DHIVEHI_WEBSITE_APPROVED=true is set in Railway.
    """
    if not approved:
        return False
    return os.environ.get("DHIVEHI_WEBSITE_APPROVED", "false").lower() == "true"

# Semantic cross-language keys are cached in PostgreSQL so a repeated article
# is not translated again after a Railway restart.
_SEMANTIC_SIGNAL_CACHE_KV = "story_signal_semantic_cache_v1"
_semantic_signal_cache = {}
_semantic_signal_cache_loaded = False
_semantic_signal_cache_lock = threading.RLock()


def _load_semantic_signal_cache():
    global _semantic_signal_cache_loaded
    with _semantic_signal_cache_lock:
        if _semantic_signal_cache_loaded:
            return
        _semantic_signal_cache_loaded = True
        try:
            stored = kv_get(_SEMANTIC_SIGNAL_CACHE_KV, {}) or {}
            if isinstance(stored, dict):
                _semantic_signal_cache.update(stored)
                log.info(f"[AI CACHE] Loaded {len(_semantic_signal_cache)} semantic story keys")
        except Exception as exc:
            log.debug(f"[AI CACHE] load skipped: {exc}")


def _save_semantic_signal_cache():
    """Persist a bounded semantic-key cache without blocking the news flow on errors."""
    try:
        with _semantic_signal_cache_lock:
            if len(_semantic_signal_cache) > SEMANTIC_SIGNAL_CACHE_MAX:
                ordered = sorted(
                    _semantic_signal_cache.items(),
                    key=lambda kv: float((kv[1] or {}).get("ts", 0) if isinstance(kv[1], dict) else 0),
                    reverse=True,
                )[:SEMANTIC_SIGNAL_CACHE_MAX]
                _semantic_signal_cache.clear()
                _semantic_signal_cache.update(dict(ordered))
            snapshot = dict(_semantic_signal_cache)
        kv_set(_SEMANTIC_SIGNAL_CACHE_KV, snapshot)
    except Exception as exc:
        log.debug(f"[AI CACHE] persist skipped: {exc}")


def story_signal_key(title="", summary="", lang="en"):
    """Create a cheap local duplicate key without making any Gemini request.

    This is safe to call for every fetched candidate. It handles exact and
    same-language duplicate detection; semantic cross-language comparison is
    performed later only for shortlisted Dhivehi finalists.
    """
    raw = strip_source_links(" ".join(x for x in [title, summary] if x)).strip()
    if not raw:
        return ""
    cache_key = f"local|{lang}|{raw[:500]}"
    with _signal_key_cache_lock:
        if cache_key in _signal_key_cache:
            return _signal_key_cache[cache_key]

    key = _caption_match_key(raw)
    with _signal_key_cache_lock:
        _signal_key_cache[cache_key] = key
        if len(_signal_key_cache) > 2000:
            for old_k in list(_signal_key_cache.keys())[:200]:
                _signal_key_cache.pop(old_k, None)
    return key


def gemini_dhivehi_to_english_cached(text, budget=None, stats=None):
    """Translate one shortlisted Dhivehi text, reusing PostgreSQL cache when possible."""
    raw = strip_source_links(str(text or "")).strip()
    if not raw:
        return None

    digest = hashlib.sha256(raw[:1200].encode("utf-8", errors="ignore")).hexdigest()
    _load_semantic_signal_cache()
    with _semantic_signal_cache_lock:
        cached = _semantic_signal_cache.get(digest)
    if isinstance(cached, dict) and cached.get("english"):
        if stats is not None:
            stats["cache_hits"] = stats.get("cache_hits", 0) + 1
        return cached["english"]

    if budget is not None:
        limit = int(budget.get("limit", DV_GEMINI_SHORTLIST_MAX))
        used = int(budget.get("used", 0))
        if used >= limit:
            if stats is not None:
                stats["budget_skips"] = stats.get("budget_skips", 0) + 1
            return None
        budget["used"] = used + 1

    if stats is not None:
        stats["attempts"] = stats.get("attempts", 0) + 1

    english = gemini_dhivehi_to_english(raw)
    if not english:
        if stats is not None:
            stats["local_fallbacks"] = stats.get("local_fallbacks", 0) + 1
        return None

    with _semantic_signal_cache_lock:
        existing = _semantic_signal_cache.get(digest)
        if not isinstance(existing, dict):
            existing = {}
        existing.update({"english": english[:1000], "ts": time.time()})
        _semantic_signal_cache[digest] = existing
    _save_semantic_signal_cache()
    if stats is not None:
        stats["success"] = stats.get("success", 0) + 1
    return english


def story_signal_key_semantic(title="", summary="", lang="dv", budget=None, stats=None):
    """Return an English semantic key for a shortlisted Dhivehi candidate.

    Gemini is called only when the text is Dhivehi/Latin-Thaana, the result is
    not already cached, and the caller's per-scan budget still has capacity.
    Any failure falls back to the local key, so Content Lab never stops merely
    because Gemini is unavailable.
    """
    raw = strip_source_links(" ".join(x for x in [title, summary] if x)).strip()
    local_key = story_signal_key(title, summary, lang)
    if not raw:
        return local_key

    needs_semantic = (lang == "dv") or is_dhivehi(raw) or looks_latin_thaana(raw)
    if not needs_semantic:
        return local_key

    digest = hashlib.sha256(raw[:1200].encode("utf-8", errors="ignore")).hexdigest()
    _load_semantic_signal_cache()
    with _semantic_signal_cache_lock:
        cached = _semantic_signal_cache.get(digest)
    if isinstance(cached, dict) and cached.get("key"):
        if stats is not None:
            stats["cache_hits"] = stats.get("cache_hits", 0) + 1
        return cached["key"]

    english = gemini_dhivehi_to_english_cached(raw, budget=budget, stats=stats)
    if not english:
        return local_key

    semantic_key = _caption_match_key(english) or local_key
    with _semantic_signal_cache_lock:
        existing = _semantic_signal_cache.get(digest)
        if not isinstance(existing, dict):
            existing = {}
        existing.update({
            "key": semantic_key,
            "english": english[:1000],
            "ts": time.time(),
        })
        _semantic_signal_cache[digest] = existing
    _save_semantic_signal_cache()
    return semantic_key

# ── Dhivehi Quality Layer: Latin Thaana → Proper Thaana / English ─────────────
# (Implemented in db.normalize_article_language_for_public — imported above.)

# ── Auto Poll ─────────────────────────────────────────────────────────────────
POLL_KEYWORDS = [
    "government","president","parliament","minister","policy","law","vote","election",
    "decision","budget","tax","fee","regulation","announce","reform","appointed",
    "resign","fired","arrested","court","judge","sentence","verdict","accused",
    "protest","rally","strike","ban","approve","reject","pass","failed"
]

# Poll daily counter (max 3/day MVT)
polls_today = {"date": None, "count": 0}
_polls_lock = threading.RLock()  # guards polls_today

def can_post_poll():
    global polls_today
    today = (utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
    with _polls_lock:
        if polls_today["date"] != today:
            polls_today = {"date": today, "count": 0}
        return polls_today["count"] < 3

def increment_poll_count():
    global polls_today
    today = (utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
    with _polls_lock:
        if polls_today["date"] != today:
            polls_today = {"date": today, "count": 0}
        polls_today["count"] += 1
    persist_state()
    log.info(f"🗳️ Polls today: {polls_today['count']}/3")

def should_create_poll(title, summary, cat):
    """Check if news warrants a poll (max 3/day)"""
    if cat not in ["LOCAL", "WORLD"]: return False
    if not can_post_poll(): return False
    text = (title + " " + summary).lower()
    return any(kw in text for kw in POLL_KEYWORDS)

def generate_poll_question(title, rewritten):
    """Use Claude to generate a relevant poll question"""
    try:
        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role":"user","content":f"""Based on this news, create a simple Telegram poll.

News: {title}
Summary: {rewritten}

Return EXACTLY in this format (nothing else):
QUESTION: [one short poll question in English]
OPT1: [option 1, max 4 words]
OPT2: [option 2, max 4 words]
OPT3: [option 3, max 4 words]

Keep it simple, neutral and relevant to the news."""}]
        )
        text = msg.content[0].text.strip()
        question, options = "", []
        for line in text.split('\n'):
            if line.startswith("QUESTION:"): question = line[9:].strip()
            elif line.startswith("OPT"): options.append(line.split(":",1)[1].strip())
        return question, options[:3]
    except Exception as e:
        log.error(f"Poll generation: {e}")
        return None, []

def send_poll(question, options):
    """Send a Telegram poll to the channel"""
    if not question or len(options) < 2:
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPoll",
            json={
                "chat_id": TELEGRAM_CHANNEL_ID,
                "question": f"🗳️ {question}",
                "options": options,
                "is_anonymous": True,
            },
            timeout=15
        )
        if resp.status_code == 200:
            log.info(f"✅ Poll sent: {question[:50]}")
        else:
            log.error(f"Poll error: {resp.status_code}")
    except Exception as e:
        log.error(f"Poll send: {e}")

# ── Buffer / Social ───────────────────────────────────────────────────────────
def _public_backend_base():
    """Return the externally reachable Railway API base without request context."""
    candidates = [
        os.environ.get("SAMUGA_API_BASE", ""),
        os.environ.get("PUBLIC_API_BASE", ""),
        os.environ.get("RAILWAY_STATIC_URL", ""),
    ]
    railway_domain = str(os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    if railway_domain:
        candidates.append("https://" + railway_domain.lstrip("/"))
    candidates.append("https://samuga-news-bot-production.up.railway.app")
    for candidate in candidates:
        value = str(candidate or "").strip().rstrip("/")
        if value.startswith(("https://", "http://")):
            return value
    return "https://samuga-news-bot-production.up.railway.app"


def _store_first_party_public_image(img_bytes, *, namespace="social"):
    """Persist an image on the Railway volume and return a stable public URL."""
    import hashlib as _img_hash
    if not isinstance(img_bytes, (bytes, bytearray)) or not img_bytes:
        raise ValueError("Image payload is empty")
    _media_root = _cms_media_directory()
    _now = mvt_now()
    _digest = _img_hash.sha256(bytes(img_bytes)).hexdigest()[:24]
    safe_namespace = re.sub(r"[^a-z0-9_-]+", "-", str(namespace or "social").lower()).strip("-") or "social"
    _relative = os.path.join(safe_namespace, _now.strftime("%Y"), _now.strftime("%m"), f"{_digest}.png")
    _full = _cms_media_full_path(_relative, _media_root)
    os.makedirs(os.path.dirname(_full), exist_ok=True)
    if not os.path.exists(_full):
        _tmp = _full + ".tmp"
        with open(_tmp, "wb") as _handle:
            _handle.write(bytes(img_bytes))
            _handle.flush()
            try:
                os.fsync(_handle.fileno())
            except Exception:
                pass
        os.replace(_tmp, _full)
    if not os.path.isfile(_full) or os.path.getsize(_full) < 100:
        raise RuntimeError("Stored media file failed verification")
    _url = _absolute_api_url("/media/cms/" + _relative.replace(os.sep, "/"))
    log.info("✅ First-party public image stored: %s → %s", _relative, _url)
    return _url


def upload_to_imgbb(img_bytes):
    """Publish an image safely; first-party storage is primary, ImgBB is fallback.

    The function name is retained for compatibility with older call sites. New
    builds no longer depend on ImgBB for normal website/social cover delivery.
    """
    prefer_first_party = os.environ.get("MEDIA_STORAGE_PREFER_FIRST_PARTY", "true").lower() == "true"

    if prefer_first_party:
        try:
            return _store_first_party_public_image(img_bytes, namespace="news")
        except Exception as exc:
            log.error("[IMAGE] first-party primary storage failed: %s", _mask_secrets(str(exc)))

    import base64 as _b64
    if IMGBB_API_KEY:
        try:
            resp = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY, "image": _b64.b64encode(img_bytes).decode()},
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                url = str((data.get("data") or {}).get("url") or "").strip()
                if url.startswith("https://"):
                    log.info("✅ ImgBB fallback image stored: %s", url[:80])
                    return url
            safe_error = ""
            try:
                payload = resp.json() or {}
                safe_error = str((payload.get("error") or {}).get("message") or payload.get("error") or "")
            except Exception:
                safe_error = resp.text[:300]
            log.warning("[IMAGE] ImgBB fallback HTTP %s: %s", resp.status_code, _mask_secrets(safe_error)[:300])
        except Exception as exc:
            log.warning("[IMAGE] ImgBB fallback failed: %s", _mask_secrets(str(exc)))

    if not prefer_first_party:
        try:
            return _store_first_party_public_image(img_bytes, namespace="news")
        except Exception as exc:
            log.error("[IMAGE] first-party fallback failed: %s", _mask_secrets(str(exc)))

    # URL redacted by design: never expose a Telegram Bot API file URL. It embeds the bot credential.
    log.error("[IMAGE] all secure public image storage methods failed; Telegram credential CDN is disabled")
    return None

def resolve_url(url):
    """Follow redirects to get real URL (fixes Google News RSS links)"""
    if not url: return url
    try:
        if "news.google.com" in url or "feedproxy" in url:
            r = requests.get(url, allow_redirects=True, timeout=10)
            log.info(f"🔗 Resolved: {r.url[:80]}")
            return r.url
    except Exception as e:
        log.warning(f"URL resolve failed: {e}")
    return url

def post_to_buffer(image_url, caption, channel_id, metadata=None, *, story_id="",
                   channel_name="", social_network="", force_retry=False):
    """Publish one channel through the tracked, idempotent Buffer client."""
    if social_paused():
        reason = _posting_block_reason()
        _last_buffer_error["response"] = reason
        log.warning(f"🛑 Buffer post blocked — {reason}")
        return False
    if not BUFFER_TOKEN or not channel_id:
        _last_buffer_error["response"] = "Buffer token or channel ID is not configured"
        return False
    clean = re.sub(r'<[^>]+>', '', caption)
    clean = clean.replace('&amp;', '&').replace('&#039;', "'").replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').strip()
    if not public_text_is_safe(clean):
        _last_buffer_error["response"] = "unsafe public caption"
        log.error(f"🚫 Buffer blocked unsafe caption: {clean[:120]}")
        return False
    if not channel_name:
        channel_name = "Facebook" if channel_id == BUFFER_FB_ID else "Instagram" if channel_id == BUFFER_IG_ID else "X" if channel_id == BUFFER_TW_ID else "Unknown"
    if not social_network:
        social_network = channel_name.lower().replace("twitter", "x")
    ok, diag = _buffer_diag.create_post(
        text=clean, channel_id=channel_id, channel_name=channel_name,
        social_network=social_network, story_id=str(story_id or ""),
        image_url=str(image_url or ""), metadata=metadata or {},
        force_retry=bool(force_retry),
    )
    if ok:
        post_id = str(diag.get("post_id") or "")
        _last_buffer_error["response"] = "Success"
        log.info("✅ Buffer posted channel=%s network=%s post_id=%s", channel_name, social_network, post_id or "unknown")
        return True
    error_class = str(diag.get("error_class") or "unknown_error")
    message = str(diag.get("message") or diag.get("error") or error_class)
    _last_buffer_error["response"] = f"{error_class}: {message}"[:300]
    log.error("Buffer failed channel=%s network=%s class=%s http=%s retry=%s message=%s",
              channel_name, social_network, error_class, diag.get("http_status", 0),
              diag.get("retry_number", 0), _mask_secrets(message)[:300])
    return False

# ── Social posting queue — dynamic gap for FB/IG/X only ──────────────────────
# Telegram is intentionally NOT handled by this queue. Telegram posts are sent
# directly from the manual Telegram / All buttons, so a Telegram cap/gap can
# never hold FB/IG/X hostage again.
# Each item: {"img_bytes": bytes, "caption": str, "queued_at": datetime}
_social_queue = []
_social_queue_lock = threading.RLock()  # RLock: reentrant — persist_state() acquires
                                        # this same lock, and several call sites invoke
                                        # persist_state() while already holding it. A plain
                                        # Lock self-deadlocks there and freezes the whole bot.
_last_social_post_time = None
SOCIAL_NORMAL_GAP_SECONDS = int(os.environ.get("SOCIAL_NORMAL_GAP_SECONDS", "300"))       # 5 minutes normally
SOCIAL_BACKLOG_GAP_SECONDS = int(os.environ.get("SOCIAL_BACKLOG_GAP_SECONDS", "60"))      # 1 minute catch-up
SOCIAL_BACKLOG_TRIGGER = int(os.environ.get("SOCIAL_BACKLOG_TRIGGER", "5"))               # queue size for catch-up
SOCIAL_MAX_WAIT_SECONDS = int(os.environ.get("SOCIAL_MAX_WAIT_SECONDS", "600"))           # oldest item target wait
SOCIAL_STUCK_ALERT_SECONDS = int(os.environ.get("SOCIAL_STUCK_ALERT_SECONDS", "900"))     # 15 minute ops alert
SOCIAL_QUEUE_EXPIRY_SECONDS = _safe_env_int("SOCIAL_QUEUE_EXPIRY_SECONDS", 86400, minimum=3600)  # 24h hard expiry

# Personality messages for queue notifications
QUEUE_PERSONALITY = [
    "yea yea it's in the queue. 😮‍💨",
    "queued. The algorithm likes it spaced out. Unlike Uly's approvals. 😅",
    "in the queue. Good things take time. 🕐",
    "queued. You're too bossy today, but I'll speed up if backlog gets big. 😤",
    "in the queue. Quality over quantity. 💅",
    "queued. I'm tired, not lazy. There's a difference. 😴",
    "queued. Back-to-back posting is so 2022. ⏳",
    "in the queue. The platforms will thank us. 🙏",
    "queued. I'm pacing myself unlike some people in this group. 👀",
    "yea yea, added to queue. I only have two hands. Metaphorically. 🤲",
]

def _get_queue_msg():
    import random
    return random.choice(QUEUE_PERSONALITY)

def _oldest_social_queue_age_seconds():
    """Age of the oldest queued social item in seconds."""
    with _social_queue_lock:
        if not _social_queue:
            return 0
        qa = _social_queue[0].get("queued_at")
    if isinstance(qa, str):
        try:
            qa = datetime.fromisoformat(qa)
        except Exception:
            qa = None
    if not qa:
        return SOCIAL_MAX_WAIT_SECONDS
    return max(0, (utcnow() - qa).total_seconds())

def _current_social_gap_seconds():
    """Dynamic social gap: 5min normally, 1min during backlog/catch-up."""
    with _social_queue_lock:
        qlen = len(_social_queue)
    oldest_age = _oldest_social_queue_age_seconds()
    if qlen >= SOCIAL_BACKLOG_TRIGGER or oldest_age >= SOCIAL_MAX_WAIT_SECONDS:
        return SOCIAL_BACKLOG_GAP_SECONDS
    return SOCIAL_NORMAL_GAP_SECONDS

def _calc_eta_seconds():
    """How many seconds until the next social post can go out."""
    if _last_social_post_time is None:
        return 0
    gap = _current_social_gap_seconds()
    elapsed = (utcnow() - _last_social_post_time).total_seconds()
    return max(0, gap - elapsed)

def _social_queue_item_age_seconds(item, now=None):
    queued_at = item.get("queued_at") if isinstance(item, dict) else None
    if isinstance(queued_at, str):
        try:
            queued_at = datetime.fromisoformat(queued_at)
        except Exception as exc:
            log.error(f"[QUEUE] invalid queued_at value; expiring malformed job: {exc}")
            return SOCIAL_QUEUE_EXPIRY_SECONDS + 1
    if not isinstance(queued_at, datetime):
        log.error("[QUEUE] missing queued_at value; expiring malformed job")
        return SOCIAL_QUEUE_EXPIRY_SECONDS + 1
    if queued_at.tzinfo is not None:
        queued_at = queued_at.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0, ((now or utcnow()) - queued_at).total_seconds())

def _expire_old_social_queue_items():
    """Drop jobs older than 24h so failed/paused work cannot leak memory forever."""
    now = utcnow()
    expired = []
    with _social_queue_lock:
        retained = []
        for item in _social_queue:
            if _social_queue_item_age_seconds(item, now) > SOCIAL_QUEUE_EXPIRY_SECONDS:
                expired.append(item)
            else:
                retained.append(item)
        if expired:
            _social_queue[:] = retained
    for item in expired:
        label = str(item.get("key_label") or item.get("title") or "Post")[:120]
        log.error(
            f"[QUEUE] permanently failed: {label} expired after more than "
            f"{SOCIAL_QUEUE_EXPIRY_SECONDS // 3600} hours and was removed"
        )
        notify_cid = item.get("notify_chat_id")
        if notify_cid:
            try:
                send_text(
                    notify_cid,
                    f"❌ <b>{label}</b> permanently failed after waiting more than "
                    f"{SOCIAL_QUEUE_EXPIRY_SECONDS // 3600} hours and was removed from the social queue.",
                    thread_id=item.get("notify_thread_id"),
                )
            except Exception as notify_error:
                log.error(f"[QUEUE] expired-job notification failed: {notify_error}")
    if expired:
        try:
            persist_state()
        except Exception as exc:
            log.error(f"[QUEUE] failed to persist expired-job cleanup: {exc}")
    return len(expired)

def _social_queue_worker():
    """
    Background thread — drains FB/IG/X only.
    Normal pace is 1 post every 5 minutes. If the queue builds up or the oldest
    item reaches the max-wait target, it switches to 1 post every minute until
    caught up. Telegram is never posted from this worker.
    """
    global _last_social_post_time
    while True:
        time.sleep(15)
        try:
            _expire_old_social_queue_items()
            with _social_queue_lock:
                if not _social_queue:
                    continue
                now = utcnow()
                gap = _current_social_gap_seconds()
                next_is_manual = bool(_social_queue[0].get("manual_post", False))
                if (not next_is_manual and _last_social_post_time and
                        (now - _last_social_post_time).total_seconds() < gap):
                    continue
                item = _social_queue.pop(0)

            if posting_paused():
                log.warning("🛑 Social queue holding because POSTING_PAUSED=true")
                with _social_queue_lock:
                    _social_queue.insert(0, item)
                time.sleep(60)
                continue

            combined_public_text = f"{item.get('title','')}\n{item.get('summary','')}\n{item.get('caption','')}"
            if not public_text_is_safe(combined_public_text):
                log.error(f"🚫 Social queue dropped unsafe post: {item.get('key_label','Post')} — {str(item.get('title',''))[:80]}")
                notify_cid = item.get("notify_chat_id")
                notify_tid = item.get("notify_thread_id")
                if notify_cid:
                    send_text(notify_cid, "🚫 Post blocked by placeholder safety gate before publishing.", thread_id=notify_tid)
                continue

            remaining = len(_social_queue)
            key_label  = item.get("key_label", "Post")
            notify_cid = item.get("notify_chat_id")
            notify_tid = item.get("notify_thread_id")
            log.info(f"[QUEUE] Posting {key_label} to FB+IG+X only — {remaining} remaining")

            # Telegram is deliberately separated from the social queue.
            # Older persisted queue items may still have post_telegram=True; ignore it
            # so Telegram cap/gap can never re-queue or block social publishing.
            tg_ok = item.get("tg_ok", False)
            if item.get("post_telegram"):
                log.info(f"[QUEUE] Telegram skipped for {key_label} — social queue is FB/IG/X only")
                item["post_telegram"] = False

            # Human-confirmed posts do not consume or delay the automatic bot pacing gate.
            _manual_social = bool(item.get("manual_post", False))
            if not _manual_social:
                _last_social_post_time = utcnow()

            # 2. Post to FB + IG + X
            if _manual_social:
                log.info(f"[QUEUE] Manual post bypassing Samuga bot pacing cap: {key_label}")
            results = _post_to_social_now(
                io.BytesIO(item["img_bytes"]), item["caption"],
                bypass_daily_limit=_manual_social,
                story_id=item.get("article_id", ""),
                count_toward_editorial_cap=not _manual_social)

            # 3. Send per-platform confirmation
            tg_icon = "✅ already" if tg_ok else "⏭️ skipped"
            fb_icon = "✅" if results.get("Facebook")  else "❌"
            ig_icon = "✅" if results.get("Instagram") else "❌"
            x_icon  = "✅" if results.get("Twitter")   else "❌"
            conf_msg = (f"📤 <b>{key_label}</b> social posted\n"
                        f"Telegram {tg_icon} · FB {fb_icon} · IG {ig_icon} · X {x_icon}")
            if notify_cid:
                send_text(notify_cid, conf_msg, thread_id=notify_tid)
            else:
                # Auto-post — send to Content Lab so team knows what went out
                send_text(CORE_TEAM_CHAT_ID, conf_msg, thread_id=CONTENT_LAB_THREAD_ID)
            try:
                persist_state()
            except Exception as persist_error:
                log.error(f"[QUEUE] state persistence failed: {persist_error}")
        except Exception as e:
            log.error(f"[QUEUE] Worker error: {e}", exc_info=True)

def queue_for_social(img_buf, caption, notify_chat_id=None, notify_thread_id=None,
                     key_label="Post", tg_ok=True, post_telegram=False,
                     article_id=None, title="", summary="", cat="LOCAL",
                     source="Samuga Media", link="", lang="en", is_breaking=False,
                     manual_post=False):
    """
    Add a card to the dynamic FB/IG/X publish queue.
    Telegram is not posted from this queue. Use the separate Telegram / All
    buttons for Telegram; this prevents Telegram caps from blocking socials.

    Website sync fix:
    If article_id/title are passed, the article is marked as posted for /api/stories
    immediately when it enters the public publishing queue.
    """
    img_bytes = img_buf.getvalue() if hasattr(img_buf, "getvalue") else img_buf
    if posting_paused():
        log.warning("🛑 Public queue refused post — POSTING_PAUSED=true")
        if notify_chat_id:
            send_text(notify_chat_id, "🛑 Public posting is paused (POSTING_PAUSED=true). Post was not queued.", thread_id=notify_thread_id)
        return False

    combined_public_text = f"{title}\n{summary}\n{caption}"
    if not public_text_is_safe(combined_public_text):
        log.error(f"🚫 Social queue refused unsafe post: {str(title)[:90]}")
        if notify_chat_id:
            send_text(notify_chat_id, "🚫 Post blocked by placeholder safety gate. It was not queued.", thread_id=notify_thread_id)
        return False

    if article_id and (lang != "dv"):
        try:
            db_publish_article_for_website(
                article_id=article_id, title=title, summary=summary, category=cat,
                source=SAMUGA_PUBLIC_SOURCE, link=SAMUGA_PUBLIC_LINK, lang=lang, is_breaking=is_breaking,
                # AI pipeline — Samuga AI as author
                author_id="samuga_ai",
                author_name="Samuga AI",
                author_role="AI Newsroom",
                author_photo_url=_AI_PHOTO["url"],
            )
        except Exception as e:
            log.error(f"[WEBSITE] publish sync before queue failed: {e}")

    with _social_queue_lock:
        _queue_item = {
            "img_bytes":        img_bytes,
            "caption":          caption,
            "queued_at":        utcnow(),
            "notify_chat_id":   notify_chat_id,
            "notify_thread_id": notify_thread_id,
            "key_label":        key_label,
            "tg_ok":            tg_ok,
            "post_telegram":    post_telegram,
            "article_id":       article_id,
            "title":            title,
            "summary":          summary,
            "cat":              cat,
            "source":           source,
            "link":             link,
            "lang":             lang,
            "is_breaking":      is_breaking,
            # Human-triggered posts bypass only Samuga's 20-day/3-night bot pacing
            # cap and do not consume it. Provider/API safety guards still apply.
            "manual_post":      bool(manual_post),
        }
        if manual_post:
            # Human-confirmed publishing has priority over automatic bot backlog.
            _social_queue.insert(0, _queue_item)
            queue_pos = 1
        else:
            _social_queue.append(_queue_item)
            queue_pos = len(_social_queue)

    # Calculate real ETA with the current dynamic gap
    eta_secs = _calc_eta_seconds() + (queue_pos - 1) * _current_social_gap_seconds()
    eta_min  = max(1, round(eta_secs / 60))

    if notify_chat_id:
        if eta_secs <= 30:
            msg = f"📲 {key_label} — {_get_queue_msg()} Posts right away."
        else:
            msg = f"📲 {key_label} — {_get_queue_msg()} Posts in ~{eta_min} min."
        send_text(notify_chat_id, msg, thread_id=notify_thread_id)

    log.info(f"[SOCIAL] Queued pos #{queue_pos}, ETA ~{eta_min}m, gap={_current_social_gap_seconds()}s")
    try: persist_state()
    except Exception: pass

# Keep old name as the "post now" internal function
def _post_to_social_now(img_buf, caption, bypass_daily_limit=False, story_id="",
                        count_toward_editorial_cap=True):
    if social_paused():
        log.warning(f"🛑 Social post blocked — {_posting_block_reason()}")
        return {"Facebook": False, "Instagram": False, "Twitter": False}
    """
    Post to all social platforms via Buffer (FB + IG + X), with the card image.

    REVERTED TO BUFFER: previously this used the Meta Graph API for FB/IG, which
    hit a #200 permissions error. Buffer was working perfectly before, so all
    three platforms now go through Buffer's GraphQL API (image hosted via imgbb).
    Returns the same {"Facebook","Instagram","Twitter"} dict the queue expects.
    """
    results = {"Facebook": False, "Instagram": False, "Twitter": False}
    if not BUFFER_TOKEN:
        log.warning("[SOCIAL] no BUFFER_TOKEN, skipping")
        return results
    if not bypass_daily_limit and not can_post_social():
        log.info("[SOCIAL] Samuga editorial pacing cap reached — skipping")
        return results
    if bypass_daily_limit:
        bypass_kind = "manual/editorial" if not count_toward_editorial_cap else "priority alert"
        log.info(f"[SOCIAL] {bypass_kind} bypassing Samuga automatic bot pacing cap")

    try:
        img_bytes = img_buf.getvalue() if hasattr(img_buf, "getvalue") else img_buf
        image_url = upload_to_imgbb(img_bytes)
        if not image_url:
            _buffer_diag.record_local_failure(operation="mediaHostUpload", error_class="media_upload_failed",
                                              error_message="No safe public image URL could be created",
                                              story_id=str(story_id or ""), media_attached=True)
            log.error("[SOCIAL] secure media hosting failed; Buffer was not called")
            return results

        # Strip HTML for all social platforms
        clean = re.sub(r'<[^>]+>', '', caption)
        clean = clean.replace('&amp;', '&').replace('&#039;', "'").replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').strip()

        # Public Samuga posts must never expose original source links.
        # Send viewers to Samuga Community only.
        clean = _strip_telegram_metadata(clean)
        clean = strip_source_links(clean)
        if not public_text_is_safe(clean):
            log.error(f"🚫 Social post blocked unsafe caption: {clean[:120]}")
            return results
        community_link = SAMUGA_CAPTION_LINK

        # FB/IG: full text + Samuga community link only
        fb_ig = clean
        if community_link and community_link not in fb_ig:
            fb_ig = fb_ig + "\n\n" + community_link
        fb_ig = fb_ig[:2200]

        # Twitter/X: first line + Samuga community link only
        lines = [l.strip() for l in clean.split('\n') if l.strip()]
        tw = (lines[0] if lines else clean)[:220]
        if community_link:
            tw = tw + "\n\n" + community_link
        tw = tw[:280]

        for cid, cap, name, meta in [
            (BUFFER_FB_ID, fb_ig, "Facebook",  {"facebook":  {"type": "post"}}),
            (BUFFER_IG_ID, fb_ig, "Instagram", {"instagram": {"type": "post", "shouldShareToFeed": True}}),
            (BUFFER_TW_ID, tw,    "Twitter",   None),
        ]:
            if not cid:
                log.warning(f"[SOCIAL] skipping {name} — no channel ID set")
                continue
            results[name] = post_to_buffer(image_url, cap, cid, metadata=meta, story_id=story_id, channel_name=name, social_network=("x" if name == "Twitter" else name.lower()))
            time.sleep(2)

        ok_list = [k for k, v in results.items() if v]
        if ok_list:
            if count_toward_editorial_cap:
                increment_social_count()
            else:
                log.info("[SOCIAL] Manual/editorial post completed — not counted toward Samuga bot pacing cap")
            track_analytics("SOCIAL", social_ok=True)
        log.info(f"[SOCIAL] Results: FB={'✅' if results['Facebook'] else '❌'} "
                 f"IG={'✅' if results['Instagram'] else '❌'} "
                 f"X={'✅' if results['Twitter'] else '❌'}")
    except Exception as e:
        log.error(f"[SOCIAL] _post_to_social_now: {e}")
    return results

def post_to_social(img_buf, caption):
    """Delegates to _post_to_social_now. Always returns a dict for consistent callers."""
    if social_paused():
        log.warning(f"🛑 Social post blocked — {_posting_block_reason()}")
        return {"Facebook": False, "Instagram": False, "Twitter": False}
    if not BUFFER_TOKEN:
        log.warning("Social: no BUFFER_TOKEN, skipping")
        return {"Facebook": False, "Instagram": False, "Twitter": False}
    if not can_post_social():
        limit = 20 if is_day_social() else 3
        log.info(f"📵 Samuga editorial social cap reached ({limit} posts, {'day' if is_day_social() else 'night'} mode) — Buffer was not called")
        return {"Facebook": False, "Instagram": False, "Twitter": False}
    return _post_to_social_now(img_buf, caption) or {"Facebook": False, "Instagram": False, "Twitter": False}


def _build_card_and_caption(article):
    """Build one approval/social card.

    Returns exactly five values:
      (card_bytes, caption, rewritten, keyword, background_image)

    All callers in this file unpack five values. Keeping this contract prevents
    the silent Content Lab failure introduced when a five-tuple was unpacked as
    four values.
    """
    raw_cat = article["cat"]
    _cx_gate = article.get("_cortex_gate") or {}
    breaking = (
        bool(_cx_gate.get("breaking_candidate"))
        if _cx_gate.get("action")
        else is_breaking(article["title"], article.get("summary", ""), raw_cat)
    )
    display_cat = "BREAKING" if breaking else canonical_category(
        raw_cat, article["title"], article.get("summary", "")
    )

    # Developing-story context is optional. A first-seen story returns "".
    if _STORY_BUILDER_AVAILABLE:
        try:
            thread_context = get_thread_context_for_article(article)
            if thread_context:
                article["_thread_context"] = thread_context
        except Exception as exc:
            log.debug(f"[THREAD] context error: {exc}")

    # Pass the complete article so URL enrichment and thread context are used.
    rewritten, keyword = rewrite_news(
        _strip_telegram_metadata(article.get("title", "")),
        _strip_telegram_metadata(article.get("summary", "")),
        raw_cat,
        article=article,
    )
    rewritten = sanitize_public_news_text(rewritten)
    if not public_text_is_safe(rewritten):
        log.warning(f"🚫 Card rewrite unsafe; using fallback for: {article['title'][:80]}")
        rewritten = sanitize_public_news_text(
            fallback_rewritten_news(article.get("title", ""), article.get("summary", ""))
        )

    keyword = safe_image_keyword(keyword, cat=raw_cat)
    bg = fetch_background_image(keyword, cat=display_cat, title=article["title"])
    ts = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
    card = generate_card(rewritten, SAMUGA_PUBLIC_SOURCE, ts, display_cat, bg)
    card_bytes = card.getvalue()

    cat_emoji = {
        "BREAKING": "🚨", "LOCAL": "🇲🇻", "POLITICAL": "🏛️",
        "LIFESTYLE": "🌴", "SPORTS": "🏅",
    }.get(display_cat, "📰")
    breaking_tag = "🚨 <b>BREAKING NEWS</b>\n\n" if breaking else ""
    update_num = int(article.get("_story_update_num") or 1)
    developing_tag = (
        f"📈 <b>DEVELOPING — Update #{update_num}</b>\n\n"
        if update_num >= 2 and not breaking else ""
    )
    caption = (
        f"{breaking_tag}{developing_tag}{cat_emoji} <b>{article['title']}</b>\n\n"
        f"{rewritten}\n\n"
        f"📡 <b>Samuga Media</b> | @samugacommunity"
    )
    return card_bytes, caption, rewritten, keyword, bg

def _publish_now(card_bytes, caption, cat, title, link, is_breaking_flag, allow_social,
                 rewritten="", summary="", report_to=None, article_id=None, bg=None,
                 website_article_body=None):
    """
    Post a card to Telegram + socials. Returns (tg_ok, social_results).
    report_to: optional (chat_id, thread_id) to send a per-platform status report.
    article_id: if given, the Telegram message_id is stored for later view tracking.
    """
    global last_regular_post_time
    if posting_paused():
        log.warning(f"🛑 Publish blocked — POSTING_PAUSED=true: {str(title)[:80]}")
        if report_to:
            rchat, rthread = report_to
            send_text(rchat, "🛑 Public posting is paused (POSTING_PAUSED=true). It was not published.", thread_id=rthread)
        return False, {}
    buf = io.BytesIO(card_bytes)
    ts = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
    social_results = {}

    log.info(f"📰 [{'🔴BREAKING' if is_breaking_flag else '🟡REGULAR'}][{cat}] {title[:60]}...")
    combined_public_text = f"{title}\n{summary}\n{rewritten}\n{caption}"
    if not public_text_is_safe(combined_public_text):
        log.error(f"🚫 Publish blocked unsafe public text: {str(title)[:90]}")
        if report_to:
            rchat, rthread = report_to
            send_text(rchat, "🚫 Post blocked by placeholder safety gate. It was not published.", thread_id=rthread)
        return False, {}
    buf.seek(0)
    tg_ok = send_to_telegram(buf, caption)

    if tg_ok:
        remember_post(title, cat, ts)
        if article_id:
            _lang_for_web = ("dv" if is_dhivehi(title + " " + summary) else "en")
            if _lang_for_web != "dv" or should_publish_dhivehi_to_website(None, approved=True):
                # Generate a branded 1200×630 web cover using the same Pexels
                # background that was already fetched for the social card —
                # zero extra API calls needed.
                _web_cover_url = None
                try:
                    _web_cover_buf = generate_web_cover(
                        title=title,
                        category=cat,
                        bg_image=bg,
                        source=SAMUGA_PUBLIC_SOURCE,
                    )
                    _web_cover_url = upload_to_imgbb(_web_cover_buf.read())
                except Exception as _wce:
                    log.debug(f"[WEB COVER] auto-generate failed: {_wce}")
                db_publish_article_for_website(
                    article_id=article_id, title=title, summary=summary, category=cat,
                    source=SAMUGA_PUBLIC_SOURCE, link=SAMUGA_PUBLIC_LINK, lang=_lang_for_web,
                    is_breaking=is_breaking_flag,
                    # AI pipeline — always attributed to Samuga AI
                    author_id="samuga_ai",
                    author_name="Samuga AI",
                    author_role="AI Newsroom",
                    author_photo_url=_AI_PHOTO["url"],
                    cover_image_url=_web_cover_url,
                    generated_article_body=website_article_body,
                )
            else:
                log.info(f"🌐 Dhivehi website publish skipped (approval-only policy): {str(title)[:70]}")
        if isinstance(tg_ok, int) and article_id:        # Phase 2: store msg id
            db_set_article_message(article_id, tg_ok)
        if article_id:                                    # Phase 2.5: store match key for FB/IG
            db_set_article_matchkey(article_id, title)
        if is_breaking_flag:
            log.info("🔴 Breaking posted!")
            event_breaking_detected(
                article_id=article_id or "", title=title,
                category=cat, source="",
            )

    # Social posting — ONLY breaking bypasses the queue
    if allow_social:
        social_buf = io.BytesIO(card_bytes)
        if is_breaking_flag:
            # BREAKING — blast everywhere immediately, no queue
            log.info("🔴 Breaking — posting to FB+IG+X immediately (no queue)")
            social_results = post_to_social(social_buf, caption) or {}
        else:
            # Regular — queue handles it. DO NOT call post_to_social here.
            # The caller (approval handler or auto-expiry) is responsible for queuing.
            # _publish_now only handles Telegram for non-breaking.
            pass

    # Poll
    if tg_ok and should_create_poll(title, summary, cat):
        log.info("🗳️ Generating poll...")
        question, options = generate_poll_question(title, rewritten or title)
        if question and options:
            time.sleep(3)
            send_poll(question, options)
            increment_poll_count()

    # Report per-platform status back to Content Lab
    if report_to:
        rchat, rthread = report_to
        tg_icon  = "✅" if tg_ok else "❌"
        fb_icon  = "✅" if social_results.get("Facebook")  else ("❌" if "Facebook"  in social_results else "⏭️")
        ig_icon  = "✅" if social_results.get("Instagram") else ("❌" if "Instagram" in social_results else "⏭️")
        tw_icon  = "✅" if social_results.get("Twitter")   else ("❌" if "Twitter"   in social_results else "⏭️")
        status = (
            f"{tg_icon} Telegram  {fb_icon} Facebook  {ig_icon} Instagram  {tw_icon} Twitter"
        )
        if tg_ok:
            msg = f"✅ <b>{title[:70]}</b>\n\n📡 {status}"
        else:
            msg = (f"⚠️ <b>Post had issues</b>\n\n"
                   f"📡 {status}\n\n"
                   f"Telegram failed — card not posted to community.")
        # Show retry tip if anything failed
        has_failure = not tg_ok or any(v is False for v in social_results.values())
        if has_failure:
            msg += "\n\n💡 <i>Telegram failed? The article may have expired. Create a manual card instead.</i>"
        send_text(rchat, msg, thread_id=rthread)

    return tg_ok, social_results


# ── Editorial Publishing Pipeline ─────────────────────────────────────────────
# Single entry point for ALL manual/human-initiated publishing.
# NEVER checks: AI queue, night mode, daily caps, cooldowns, or spacing.
# Editors press a button → this fires immediately → structured result returned.
#
# AI pipeline:  post_article() → approval_queue → expire_old_approvals()
# Editorial:    editorial_publish() → immediate publish → done

def editorial_publish(
    card_bytes, caption, title, summary, cat, lang, link,
    article_id=None, source="Samuga Media",
    destinations=None,
    is_breaking=False,
    report_to=None,
    approver="Editor",
    bg=None,
):
    """
    Editorial publishing pipeline — bypasses ALL AI automation.

    destinations: set of platform names to publish to immediately.
    Default: {"telegram","facebook","instagram","twitter","website"}

    Returns dict with per-platform bool results + article_url.
    """
    if destinations is None:
        destinations = {"telegram", "facebook", "instagram", "twitter", "website"}

    result = {
        "ok": False,
        "telegram": False,
        "facebook": False,
        "instagram": False,
        "twitter": False,
        "website": False,
        "article_url": None,
        "tg_message_id": None,
        "error": None,
    }

    if posting_paused():
        result["error"] = "POSTING_PAUSED=true"
        log.warning(f"🛑 Editorial publish blocked — POSTING_PAUSED=true: {title[:60]}")
        if report_to:
            send_text(report_to[0], "🛑 Public posting is paused (POSTING_PAUSED=true).",
                      thread_id=report_to[1])
        return result

    combined = f"{title}\n{summary}\n{caption}"
    if not public_text_is_safe(combined):
        result["error"] = "unsafe_content"
        log.error(f"🚫 Editorial publish blocked — unsafe content: {title[:60]}")
        return result

    # ── 1. Website (always first so URL is ready) ─────────────────────────────
    if "website" in destinations:
        try:
            # Generate web cover — use bg if available, otherwise gradient-only
            _web_cover_url = None
            try:
                _web_cover_buf = generate_web_cover(
                    title=title, category=cat, bg_image=bg, source=SAMUGA_PUBLIC_SOURCE,
                )
                _web_cover_url = upload_to_imgbb(_web_cover_buf.read())
            except Exception as _wce:
                log.debug(f"[WEB COVER] editorial generate failed: {_wce}")
            # ── Authorship: NEVER use the approving team member's name here. ──
            # Every item reaching editorial_publish() comes from store_pending_approval(),
            # which is only used by AI/discovery paths (_build_card_and_caption, breaking
            # news, auto-DV). There is no human-submitted content in this path — that
            # goes through /article's own publish flow instead. Authorship is decided
            # at creation time, never at approval time, so this always resolves to the
            # live Samuga AI profile regardless of who clicked approve.
            _ep_author_name, _ep_author_role, _ep_author_photo = "Samuga AI", "AI Newsroom", None
            try:
                from db import db_list_authors
                _ai_profile = next(
                    (a for a in db_list_authors(active_only=False) if a["author_id"] == "samuga_ai"),
                    None
                )
                if _ai_profile:
                    _ep_author_name  = _ai_profile["name"]
                    _ep_author_role  = _ai_profile["role"]
                    _ep_author_photo = _ai_profile.get("photo_url")
            except Exception as _ep_auth_err:
                log.debug(f"[EDITORIAL] author profile lookup failed, using default: {_ep_auth_err}")
            _web_article_id = db_publish_article_for_website(
                article_id=article_id, title=title, summary=summary,
                category=cat, source=source, link=link or SAMUGA_PUBLIC_LINK,
                lang=lang, is_breaking=is_breaking,
                author_id="samuga_ai",
                author_name=_ep_author_name,
                author_role=_ep_author_role,
                author_photo_url=_ep_author_photo,
                cover_image_url=_web_cover_url,
            )
            _web_status_row = db_execute(
                "SELECT status FROM articles WHERE id=%s LIMIT 1",
                (_web_article_id,), fetch="one"
            ) if _web_article_id else None
            _web_status = _web_status_row[0] if _web_status_row else None
            result["website"] = _web_status in ("posted", "published", "social_posted")
            result["article_url"] = (
                website_article_url(article_id=_web_article_id)
                if result["website"] else ""
            )
            if result["website"]:
                log.info(f"🌐 Editorial website publish OK: {title[:60]}")
                event_article_published(
                    article_id=_web_article_id, title=title, category=cat,
                    lang=lang, is_breaking=is_breaking, source=source,
                    published_by=approver, pipeline="editorial",
                    url=result["article_url"],
                )
            else:
                log.warning(f"🌐 Editorial website held pending body: {title[:60]}")
        except Exception as e:
            log.error(f"[EDITORIAL] website publish failed: {e}")

    # ── 2. Telegram (direct — never through queue) ────────────────────────────
    if "telegram" in destinations:
        try:
            buf = io.BytesIO(card_bytes)
            tg_ok = send_to_telegram(buf, caption)
            result["telegram"] = bool(tg_ok)
            if isinstance(tg_ok, int):
                result["tg_message_id"] = tg_ok
                if article_id:
                    db_set_article_message(article_id, tg_ok)
            if tg_ok and article_id:
                db_set_article_matchkey(article_id, title)
            log.info(f"📣 Editorial Telegram post: {'✅' if tg_ok else '❌'}")
        except Exception as e:
            log.error(f"[EDITORIAL] Telegram post failed: {e}")

    # ── 3. Social (Buffer — immediate, not queued) ────────────────────────────
    social_platforms = {"facebook", "instagram", "twitter"} & set(destinations)
    if social_platforms and BUFFER_TOKEN:
        try:
            image_url = upload_to_imgbb(card_bytes)
            if image_url:
                clean_cap = re.sub(r'<[^>]+>', '', caption)
                clean_cap = clean_cap.replace('&amp;', '&').replace('&#039;', "'") \
                                     .replace('&quot;', '"').replace('&lt;', '<') \
                                     .replace('&gt;', '>').strip()
                clean_cap = _strip_telegram_metadata(clean_cap)
                clean_cap = strip_source_links(clean_cap)
                community_link = SAMUGA_CAPTION_LINK
                fb_ig = (clean_cap + ("\n\n" + community_link if community_link and community_link not in clean_cap else ""))[:2200]
                lines_tw = [l.strip() for l in clean_cap.split('\n') if l.strip()]
                tw = ((lines_tw[0] if lines_tw else clean_cap)[:220]
                      + ("\n\n" + community_link if community_link else ""))[:280]
                platform_map = [
                    ("facebook",  BUFFER_FB_ID, fb_ig, {"facebook":  {"type": "post"}}),
                    ("instagram", BUFFER_IG_ID, fb_ig, {"instagram": {"type": "post", "shouldShareToFeed": True}}),
                    ("twitter",   BUFFER_TW_ID, tw,    None),
                ]
                posted_platforms = []
                for plat, cid, cap, meta in platform_map:
                    if plat not in social_platforms:
                        continue
                    if not cid:
                        log.warning(f"[EDITORIAL] {plat} channel ID not set")
                        continue
                    ok = post_to_buffer(image_url, cap, cid, metadata=meta, story_id=article_id, channel_name=("X" if plat == "twitter" else plat.title()), social_network=("x" if plat == "twitter" else plat))
                    result[plat] = bool(ok)
                    if ok:
                        posted_platforms.append(plat)
                    log.info(f"[EDITORIAL] {plat}: {'✅' if ok else '❌'}")
                    time.sleep(1)
                if posted_platforms:
                    event_social_published(article_id=article_id, title=title,
                                           platforms=posted_platforms, success=True)
            else:
                _buffer_diag.record_local_failure(operation="mediaHostUpload", error_class="media_upload_failed",
                                                  error_message="No safe public image URL could be created",
                                                  story_id=str(article_id or ""), media_attached=True)
                log.error("[EDITORIAL] secure media hosting failed — social platforms skipped")
        except Exception as e:
            log.error(f"[EDITORIAL] social post failed: {e}")

    # ── 4. DB status + analytics ──────────────────────────────────────────────
    try:
        if article_id:
            db_mark_status(article_id, "posted", posted=True)
        ts_now = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
        remember_post(title, cat, ts_now, is_breaking)
        db_log_learning(article_id=article_id, action="post_all", member=approver,
                        category=cat, source=source, lang=lang)
    except Exception as e:
        log.error(f"[EDITORIAL] bookkeeping failed: {e}")

    # ── 5. Result ─────────────────────────────────────────────────────────────
    result["ok"] = any([result["telegram"], result["facebook"],
                        result["instagram"], result["twitter"], result["website"]])

    if report_to:
        rchat, rthread = report_to
        def _icon(plat):
            if result[plat]: return "✅"
            return "⏭️" if plat not in destinations else "❌"
        url_line = f"\n🔗 {result['article_url']}" if result["article_url"] else ""
        msg = (
            f"{'✅' if result['ok'] else '⚠️'} <b>{title[:70]}</b>\n\n"
            f"🌐 Web {_icon('website')} · 📣 TG {_icon('telegram')} · "
            f"FB {_icon('facebook')} · IG {_icon('instagram')} · X {_icon('twitter')}"
            f"{url_line}"
        )
        send_text(rchat, msg, thread_id=rthread)

    log.info(f"[EDITORIAL] {title[:60]} | "
             f"TG={'✅' if result['telegram'] else '❌'} "
             f"FB={'✅' if result['facebook'] else '❌'} "
             f"IG={'✅' if result['instagram'] else '❌'} "
             f"X={'✅' if result['twitter'] else '❌'} "
             f"Web={'✅' if result['website'] else '❌'}")
    return result



_content_lab_card_cache = {}
_content_lab_card_cache_lock = threading.Lock()


def _approval_bg_from_item(itm):
    """Restore the background image used by an approval item."""
    import base64 as _b64
    encoded = itm.get("_bg_image_b64")
    if encoded:
        try:
            raw = _b64.b64decode(encoded)
            with Image.open(BytesIO(raw)) as image:
                return image.convert("RGB").copy()
        except Exception as exc:
            log.debug(f"bg restore failed, refetching: {exc}")
    keyword = itm.get("keyword", itm.get("cat", "LOCAL").lower())
    return fetch_background_image(keyword, cat=itm.get("cat"), title=itm.get("title", ""))


def _content_lab_build_card_bytes(item):
    """Return a publishable Content Lab card, rebuilding a restored card when needed.

    The state-file backup keeps card bytes, while the PostgreSQL crash backup strips
    large images.  This helper lets both the dashboard preview and the existing
    publisher recover the same Samuga card after a Railway restart.
    """
    # Upgrade weather-review cards created by Build 15 before this hotfix. They
    # may already contain a normal social-card PNG, so rebuild once through the
    # dedicated MMS renderer instead of returning the stale stored bytes.
    if item.get("_weather_alert_review") and item.get("_raw_weather_alert") and not item.get("_weather_card_v15_1"):
        try:
            import weather as _weather_preview
            raw_alert = dict(item.get("_raw_weather_alert") or {})
            level = str(raw_alert.get("level") or "white").lower()
            if level not in {"white", "yellow", "orange", "red"}:
                level = "white"
            weather_data = _weather_preview.get_weather_data() or _weather_preview._minimal_weather_data("alert")
            weather_data = dict(weather_data)
            weather_data["official_alert"] = raw_alert
            weather_card = _weather_preview.generate_weather_card(
                weather_data,
                alert_mode=True,
                alert_text=_weather_preview._official_alert_text(raw_alert),
                alert_level=level,
                island_data=_weather_preview.get_island_forecasts(),
                prayer_data=_weather_preview.get_prayer_times(time_of_day="alert"),
            )
            item["card_bytes"] = weather_card.getvalue()
            item["_weather_card_v15_1"] = True
            persist_state()
            return bytes(item["card_bytes"])
        except Exception as weather_preview_error:
            log.warning("[CONTENT LAB] weather review preview upgrade failed: %s", weather_preview_error)

    existing = item.get("card_bytes")
    if isinstance(existing, (bytes, bytearray)) and existing:
        return bytes(existing)

    lang = str(item.get("lang") or "en").lower()
    if lang == "dv":
        card_text = item.get("dv_text") or item.get("summary") or item.get("title") or ""
    else:
        card_text = item.get("rewritten") or item.get("summary") or ""
        if not card_text:
            raw_caption = _strip_telegram_metadata(item.get("caption") or "")
            # Remove the headline and Samuga footer when the caption is the only
            # surviving source after a crash restore.
            plain = re.sub(r"<[^>]+>", "", raw_caption)
            title = str(item.get("title") or "").strip()
            if title and plain.strip().startswith(title):
                plain = plain.strip()[len(title):].lstrip("\n :-–—")
            plain = re.sub(r"(?is)\n*📡\s*Samuga Media.*$", "", plain).strip()
            card_text = plain or title

    if not str(card_text).strip():
        return None
    background = _approval_bg_from_item(item)
    created = item.get("created_at")
    if not isinstance(created, datetime):
        try:
            created = datetime.fromisoformat(str(created))
        except Exception:
            created = utcnow()
    timestamp = (created + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
    card = generate_card(
        str(card_text).strip(), SAMUGA_PUBLIC_SOURCE, timestamp,
        item.get("cat", "LOCAL"), background,
    )
    card.seek(0)
    rebuilt = card.getvalue()
    item["card_bytes"] = rebuilt
    item.pop("_needs_card_rebuild", None)
    return rebuilt


def publish_approved_item(item, key, approver="Team", corrected=None, destination="all"):
    """The existing approval publisher, shared by Telegram and the dashboard."""
    want_telegram = destination in ("telegram", "all")
    want_social = destination in ("social", "all")
    item, corrected, was_corrected = _content_lab_apply_structured_correction(item, corrected)
    try:
        if item["lang"] == "dv":
            final_text = corrected if corrected else item.get("dv_text", "")
            background = _approval_bg_from_item(item)
            timestamp = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
            card = generate_card(final_text, SAMUGA_PUBLIC_SOURCE, timestamp, item["cat"], background)
            card.seek(0)
            card_bytes = card.getvalue()
            full_caption = (
                f"🇲🇻 <b>{item['title']}</b>\n\n"
                f"{final_text}\n\n"
                f"📡 <b>ސަމުގާ މީޑިއާ</b> | @samugacommunity"
            )
            db_log_learning(
                article_id=item.get("article_id"), action=("edited" if was_corrected else "approved"),
                member=approver, category=item.get("cat", ""), source=item.get("source", ""),
                theme=item.get("_trend_theme", ""), original_caption=item.get("dv_text", ""),
                final_caption=final_text, lang="dv")
        else:
            card_bytes = _content_lab_build_card_bytes(item)
            if not card_bytes:
                raise ValueError("Content Lab card could not be rebuilt for publishing")
            full_caption = corrected if corrected else item.get("caption", "")
            db_log_learning(
                article_id=item.get("article_id"), action=("edited" if was_corrected else "approved"),
                member=approver, category=item.get("cat", ""), source=item.get("source", ""),
                theme=item.get("_trend_theme", ""), original_caption=item.get("caption", ""),
                final_caption=full_caption, lang="en")

        try:
            from brain_memory import record_editor_action
            record_editor_action(
                human_action=destination, source=item.get("source", ""), category=item.get("cat", ""),
                language=item.get("lang", "en"), title=item.get("title", ""),
                summary=item.get("summary", ""), article_id=item.get("article_id"), created_by=approver)
        except Exception as exc:
            log.debug(f"[BRAIN] record approval skipped: {exc}")

        lang = item["lang"]
        destinations = set()
        if lang != "dv" or should_publish_dhivehi_to_website(item, approved=True):
            destinations.add("website")
        if want_telegram:
            destinations.add("telegram")
        if want_social:
            destinations.update({"facebook", "instagram", "twitter"})

        result = editorial_publish(
            card_bytes=card_bytes, caption=full_caption, title=item.get("title", ""),
            summary=item.get("summary", ""), cat=item.get("cat", "LOCAL"), lang=lang,
            link=item.get("link", ""), article_id=item.get("article_id"),
            source=item.get("source", "Samuga Media"), destinations=destinations,
            is_breaking=item.get("is_breaking", False),
            report_to=(CORE_TEAM_CHAT_ID, CONTENT_LAB_THREAD_ID), approver=approver,
            bg=_approval_bg_from_item(item),
        )
        return result or {"ok": False}
    except Exception as exc:
        log.error(f"publish_approved_item error: {exc}")
        send_text(CORE_TEAM_CHAT_ID, f"❌ Error publishing {key}: {exc}", thread_id=CONTENT_LAB_THREAD_ID)
        return {"ok": False, "error": str(exc)}



def _content_lab_clean_edit_text(value):
    """Return only public card copy: no HTML, source line, URL, or Samuga footer."""
    import html as _html
    text = _html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    text = _strip_telegram_metadata(text)
    text = re.sub(r"(?im)^\s*(?:source|މަސްދަރު)\s*[:：].*$", "", text)
    text = re.sub(r"(?im)^\s*(?:📡\s*)?(?:Samuga Media|ސަމުގާ މީޑިއާ).*$", "", text)
    text = re.sub(r"https?:/{1,2}\S+", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _content_lab_public_edit_copy(item):
    """Headline and paragraph exactly as editors should see and change."""
    if item.get("_weather_alert_review"):
        raw_alert = dict(item.get("_raw_weather_alert") or {})
        level = str(raw_alert.get("level") or "white").lower()
        try:
            import weather as _weather_copy
            cfg = _weather_copy.MMS_ALERT_LEVELS.get(level, _weather_copy.MMS_ALERT_LEVELS["white"])
            hazard = _content_lab_clean_edit_text(raw_alert.get("hazard") or "")
            if not hazard or "manual confirmation" in hazard.lower() or hazard.lower().startswith(("white mms alert", "yellow mms alert", "orange mms alert", "red mms alert")):
                hazard = cfg.get("headline") or "Official weather alert"
            headline = f"{cfg.get('label', level.title() + ' Alert')} — {hazard}".strip(" —")
            paragraph = _content_lab_clean_edit_text(_weather_copy._official_alert_text(raw_alert))
        except Exception:
            headline = _content_lab_clean_edit_text(raw_alert.get("hazard") or item.get("title") or "Official MMS weather alert")
            paragraph = _content_lab_clean_edit_text(item.get("summary") or "")
    else:
        headline = _content_lab_clean_edit_text(item.get("title") or "")
        if str(item.get("lang") or "en").lower() == "dv":
            paragraph = _content_lab_clean_edit_text(item.get("dv_text") or item.get("summary") or "")
        else:
            paragraph = _content_lab_clean_edit_text(item.get("summary") or item.get("rewritten") or "")
            if not paragraph:
                paragraph = _content_lab_clean_edit_text(item.get("caption") or "")
    if headline and paragraph.startswith(headline):
        paragraph = paragraph[len(headline):].lstrip("\n :-–—")
    return headline, paragraph.strip()


def _content_lab_apply_structured_correction(item, corrected):
    """Apply dashboard headline/paragraph edits while preserving legacy text edits."""
    if not isinstance(corrected, dict):
        return item, corrected, bool(str(corrected or "").strip())
    headline = sanitize_public_news_text(
        _content_lab_clean_edit_text(corrected.get("headline") or corrected.get("title") or "")
    )
    paragraph = sanitize_public_news_text(
        _content_lab_clean_edit_text(corrected.get("paragraph") or corrected.get("summary") or "")
    )
    if not headline and not paragraph:
        return item, None, False
    edited = dict(item)
    if headline:
        edited["title"] = headline
    else:
        headline = _content_lab_clean_edit_text(item.get("title") or "")
    edited["summary"] = paragraph
    public_copy = "\n\n".join(part for part in (headline, paragraph) if part).strip()
    if str(edited.get("lang") or "en").lower() == "dv":
        edited["dv_text"] = public_copy
    else:
        edited["rewritten"] = public_copy
        edited["caption"] = (
            f"<b>{headline}</b>\n\n{paragraph}\n\n"
            f"📡 <b>Samuga Media</b> | @samugacommunity"
        ).strip()
    # Force the card to be rebuilt with the corrected public copy.
    edited["card_bytes"] = None
    edited["_needs_card_rebuild"] = True
    return edited, None, True

def _content_lab_review_details(item):
    """Human-readable facts shown below the dashboard card, separate from edit fields."""
    if item.get("_weather_alert_review"):
        raw = dict(item.get("_raw_weather_alert") or {})
        level = str(raw.get("level") or "white").upper()
        hazard = _content_lab_clean_edit_text(raw.get("hazard") or item.get("summary") or "Official weather alert")
        area = _content_lab_clean_edit_text(raw.get("area") or "Maldives")
        valid_from = str(raw.get("valid_from") or "").strip()
        valid_until = str(raw.get("valid_until") or "").strip()
        source_url = str(raw.get("source_url") or item.get("link") or "").strip()
        rows = [f"Level: {level}", f"Hazard: {hazard}", f"Area: {area}"]
        if valid_from or valid_until:
            rows.append(f"Valid: {valid_from or 'Not stated'} — {valid_until or 'Not stated'}")
        if source_url:
            rows.append(f"Source: {source_url}")
        return "\n".join(rows)
    raw = item.get("dv_text") if str(item.get("lang") or "en").lower() == "dv" else (item.get("caption") or item.get("rewritten") or item.get("summary") or "")
    import html as _html
    text = _html.unescape(re.sub(r"<[^>]+>", "", str(raw or "")))
    text = re.sub(r"(?im)^\s*(?:📡\s*)?(?:Samuga Media|ސަމުގާ މީޑިއާ).*?$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    source_url = str(item.get("link") or "").strip()
    if source_url and source_url not in text:
        text = (text + f"\n\nSource: {source_url}").strip()
    return text[:2400]


def _content_lab_public_item(key, item):
    created = item.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    edit_headline, edit_paragraph = _content_lab_public_edit_copy(item)
    return {
        "key": str(key).lower(), "title": item.get("title", ""),
        "edit_headline": edit_headline, "edit_paragraph": edit_paragraph,
        "review_details": _content_lab_review_details(item),
        "summary": item.get("summary", ""), "caption": item.get("caption", ""),
        "dv_text": item.get("dv_text", ""), "category": item.get("cat", "LOCAL"),
        "lang": item.get("lang", "en"), "source": item.get("source", ""),
        "breaking": bool(item.get("is_breaking")), "article_id": item.get("article_id"),
        "created_at": created, "has_card": bool(
            item.get("card_bytes") or item.get("dv_text") or item.get("rewritten")
            or item.get("summary") or item.get("caption")
        ),
        "telegram_message_id": item.get("_lab_message_id"),
        "review_type": "weather_alert" if item.get("_weather_alert_review") else "news",
        "manual_only": bool(item.get("_manual_only")),
        "confidence": item.get("_confidence"),
    }


def _content_lab_db_upsert(key, item, status="pending"):
    try:
        payload = _content_lab_public_item(key, item)
        db_execute("""
            INSERT INTO cms_content_lab_items
                (card_key,status,title,category,lang,source,is_breaking,telegram_message_id,payload,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,COALESCE(%s,NOW()),NOW())
            ON CONFLICT (card_key) DO UPDATE SET
                status=EXCLUDED.status,title=EXCLUDED.title,category=EXCLUDED.category,
                lang=EXCLUDED.lang,source=EXCLUDED.source,is_breaking=EXCLUDED.is_breaking,
                telegram_message_id=COALESCE(EXCLUDED.telegram_message_id,cms_content_lab_items.telegram_message_id),
                payload=EXCLUDED.payload,updated_at=NOW()
        """, (
            str(key).lower(), status, payload["title"], payload["category"], payload["lang"],
            payload["source"], payload["breaking"], payload["telegram_message_id"],
            json.dumps(payload, ensure_ascii=False, default=str), item.get("created_at")))
    except Exception as exc:
        log.debug(f"[CONTENT LAB] state upsert skipped: {exc}")


def _content_lab_db_mark(key, status, action=None, actor=None, origin=None, error=None):
    try:
        db_execute("""
            UPDATE cms_content_lab_items SET status=%s,action=%s,action_by=%s,action_origin=%s,
                error=%s,updated_at=NOW(),
                actioned_at=CASE WHEN %s IN ('published','rejected','failed') THEN NOW() ELSE actioned_at END
            WHERE card_key=%s
        """, (status, action, actor, origin, str(error or "")[:1000] or None, status, str(key).lower()))
    except Exception as exc:
        log.debug(f"[CONTENT LAB] state mark skipped: {exc}")


def _content_lab_remember_card(key, item):
    card = item.get("card_bytes")
    if not card:
        return
    with _content_lab_card_cache_lock:
        _content_lab_card_cache[str(key).lower()] = card
        while len(_content_lab_card_cache) > 30:
            _content_lab_card_cache.pop(next(iter(_content_lab_card_cache)), None)


def _content_lab_reject_item(item, actor):
    if item.get("article_id"):
        db_mark_status(item["article_id"], "rejected")
    db_log_learning(
        article_id=item.get("article_id"), action="rejected", member=actor,
        category=item.get("cat", ""), source=item.get("source", ""),
        theme=item.get("_trend_theme", ""),
        original_caption=item.get("dv_text") or item.get("caption", ""), lang=item.get("lang", "en"))
    try:
        from brain_memory import record_editor_action
        record_editor_action(
            human_action="reject", source=item.get("source", ""), category=item.get("cat", ""),
            language=item.get("lang", "en"), title=item.get("title", ""),
            summary=item.get("summary", ""), article_id=item.get("article_id"), created_by=actor)
    except Exception as exc:
        log.debug(f"[BRAIN] record rejection skipped: {exc}")
    try:
        remember_story_title(item.get("_dedup_title") or item.get("title", ""))
    except Exception:
        pass


def _content_lab_take_action(key, action, actor="Team", corrected=None, origin="dashboard", background=False):
    """Atomically action one approval card from Telegram or the dashboard."""
    key = str(key or "").strip().lower()
    destination_map = {"post_tg": "telegram", "post_soc": "social", "post_all": "all", "approve": "all"}
    if action not in {*destination_map, "reject"}:
        return {"ok": False, "error": "Unsupported Content Lab action."}
    with _approval_lock:
        item = approval_queue.pop(key, None)
    if not item:
        return {"ok": False, "error": "Card is no longer waiting. It may already be actioned or expired."}

    _content_lab_remember_card(key, item)
    _content_lab_db_upsert(key, item, status="pending")
    persist_state()
    message_id = item.get("_lab_message_id")
    if message_id:
        try:
            edit_message_reply_markup(CORE_TEAM_CHAT_ID, message_id, {"inline_keyboard": []})
        except Exception as exc:
            log.debug(f"[CONTENT LAB] Telegram keyboard close skipped: {exc}")

    if action == "reject":
        try:
            _content_lab_reject_item(item, actor)
            _content_lab_db_mark(key, "rejected", action="reject", actor=actor, origin=origin)
            if origin == "dashboard":
                send_text(CORE_TEAM_CHAT_ID,
                          f"🖥️ ❌ <b>{actor}</b> rejected <b>{key.upper()}</b> from the Newsroom dashboard.",
                          thread_id=CONTENT_LAB_THREAD_ID)
            return {"ok": True, "status": "rejected", "message": f"{key.upper()} rejected"}
        except Exception as exc:
            with _approval_lock:
                approval_queue[key] = item
            persist_state()
            _content_lab_db_mark(key, "pending", action="reject", actor=actor, origin=origin, error=exc)
            return {"ok": False, "error": str(exc)}

    destination = destination_map[action]
    _content_lab_db_mark(key, "processing", action=action, actor=actor, origin=origin)
    if origin == "dashboard":
        label = {"telegram": "Telegram", "social": "Socials", "all": "everywhere"}[destination]
        send_text(CORE_TEAM_CHAT_ID,
                  f"🖥️ 📤 <b>{actor}</b> approved <b>{key.upper()}</b> from the Newsroom dashboard → {label}.",
                  thread_id=CONTENT_LAB_THREAD_ID)

    def runner():
        if item.get("_weather_alert_review"):
            try:
                import weather as _weather_review
                _review_alert = dict(item.get("_raw_weather_alert") or {})
                if corrected:
                    if isinstance(corrected, dict):
                        _corrected_headline = _content_lab_clean_edit_text(corrected.get("headline") or "")
                        _corrected_headline = re.sub(r"(?i)^(?:white|yellow|orange|red)\s+alert\s*[—:–-]\s*", "", _corrected_headline).strip()
                        _corrected_paragraph = _content_lab_clean_edit_text(corrected.get("paragraph") or "")
                        _corrected_text = "\n\n".join(
                            part for part in (_corrected_headline, _corrected_paragraph) if part
                        ).strip()
                    else:
                        _corrected_headline = ""
                        _corrected_paragraph = ""
                        _corrected_text = str(corrected).strip()
                    parsed_corrections = _weather_review.parse_mms_alert_text(
                        _corrected_text,
                        source_url=_review_alert.get("source_url") or item.get("link") or "https://t.me/MaldivesMET",
                        source_label=_review_alert.get("source") or "Maldives Meteorological Service / @MaldivesMET",
                        source_id=str(_review_alert.get("source_id") or _review_alert.get("telegram_message_id") or "manual"),
                        extra={"manually_corrected": True},
                    )
                    if parsed_corrections:
                        original_id = _review_alert.get("alert_id")
                        _review_alert.update(parsed_corrections[0])
                        if original_id:
                            _review_alert["alert_id"] = original_id
                    else:
                        if _corrected_headline:
                            _review_alert["hazard"] = _corrected_headline
                        elif _corrected_text:
                            _review_alert["hazard"] = _corrected_text
                        if _corrected_paragraph:
                            _review_alert["editor_note"] = _corrected_paragraph
                        _review_alert["manually_corrected"] = True
                result = _weather_review.ingest_official_alert(_review_alert, force=True)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
        else:
            result = publish_approved_item(item, key, approver=actor, corrected=corrected, destination=destination)
        if result.get("ok"):
            _content_lab_db_mark(key, "published", action=action, actor=actor, origin=origin)
        else:
            with _approval_lock:
                approval_queue[key] = item
            persist_state()
            _content_lab_db_mark(key, "failed", action=action, actor=actor, origin=origin,
                                 error=result.get("error") or "Publishing failed")
            if origin == "dashboard":
                send_text(CORE_TEAM_CHAT_ID,
                          f"⚠️ Dashboard action for <b>{key.upper()}</b> failed. The card was restored to Content Lab.",
                          thread_id=CONTENT_LAB_THREAD_ID)
        return result

    if background:
        threading.Thread(target=runner, daemon=True, name=f"content-lab-{key}").start()
        return {"ok": True, "status": "processing", "message": f"{key.upper()} is publishing"}
    result = runner()
    return {"ok": bool(result.get("ok")),
            "status": "published" if result.get("ok") else "failed",
            "error": result.get("error")}


def _send_approval_card(key, item, force=False):
    """Send a card preview to Content Lab with approve/reject buttons, rate-limited."""
    safe_ok, safe_reason = contentlab_candidate_is_safe(
        title=item.get("title",""),
        summary=item.get("dv_text") or item.get("caption") or item.get("summary",""),
        source=item.get("source",""),
        lang=item.get("lang","en"),
    )
    if not safe_ok:
        approval_queue.pop(key, None)
        persist_state()
        log.warning(f"🧱 Approval preview blocked and removed: {key} — {safe_reason}")
        return False
    if item.get("_content_lab_suppressed"):
        log.info(f"🧯 Content Lab suppressed for {key}")
        return False
    if item.get("_content_lab_sent") and not force:
        return False
    # No drip throttle — cards go to Content Lab immediately when ready
    # The hourly CARD GENERATION budget (6/hr) is the gating, not Content Lab sending
    cat = item["cat"]
    lang_tag = "🇲🇻 Dhivehi" if item["lang"] == "dv" else "🇬🇧 English"
    brk = "🚨 BREAKING " if item["is_breaking"] else ""
    cat_emoji = {"BREAKING":"🚨","LOCAL":"🇲🇻","POLITICAL":"🏛️","LIFESTYLE":"🌴","SPORTS":"🏅","FOOTBALL":"⚽","WORLD":"🌍","DISASTER":"🚨","WEATHER":"🌤️","TOURISM":"✈️"}.get(cat,"📰")
    # KEY first and BIG so stacked cards are instantly identifiable
    header = (
        f"🔑 <b>{key.upper()}</b>  •  {cat_emoji} {cat}\n"
        f"{brk}<b>{lang_tag} Card — Review Needed</b>\n\n"
        f"<b>📰 {item['title']}</b>\n\n"
    )
    _cx_gate = item.get("_cortex_gate") or {}
    if _cx_gate.get("action"):
        _cx_action = "REVIEW" if _cx_gate.get("requires_human_review") else "APPROVED"
        header += (
            f"🧭 <b>Cortex News Director: {_cx_action}</b> · "
            f"{int(_cx_gate.get('score') or 0)}/100 · "
            f"confidence {int(_cx_gate.get('confidence') or 0)}%\n"
            f"<i>{str(_cx_gate.get('story_type') or 'news').replace('_', ' ')}</i>\n\n"
        )
    if item.get("_ai_unavailable"):
        header += "⚠️ <b>AI unavailable — manual review required.</b>\n\n"
    if item["lang"] == "dv" and item.get("dv_text"):
        header += f"<b>Bot wrote:</b>\n{item['dv_text']}\n\n"
    footer = (
        f"{'Confirm this official alert' if item.get('_weather_alert_review') else 'Choose where to post — <b>website is always published</b> on approval'}:\n"
        f"📣 Telegram only · 📱 Socials only · 🌐 All · ✏️ Edit · ❌ Reject\n\n"
        f"Text fallback: <code>/approved {key}</code> (posts everywhere)\n"
    )
    if item["lang"] == "dv":
        footer += f"✏️ <code>/approved {key} [corrected dhivehi text]</code>\n"
    footer += f"❌ <code>/reject {key}</code>\n\n"
    # Tell the team the auto-post / expiry behaviour
    if item.get("_weather_alert_review"):
        footer += f"<i>🔎 Vision confidence: {float(item.get('_confidence') or 0):.0%} · manual decision required · never auto-posts</i>"
    elif item["lang"] == "en":
        if item.get("is_breaking") and item.get("_held_for_confidence"):
            footer += "<i>⏰ Breaking (held for review) — auto-posts in 15 min if no action</i>"
        elif item.get("is_breaking"):
            footer += "<i>⏰ Breaking — auto-posts in 15 min if no action</i>"
        else:
            footer += "<i>⏰ Auto-posts in 45 min if not reviewed</i>"
    else:
        # Dhivehi NEVER auto-posts — team must approve every single one
        footer += "<i>⏰ Expires in 2h if not approved — Dhivehi never auto-posts</i>"
    msg = header + footer

    # ── Inline buttons — choose destination per post ─────────────────────────
    # post_tg  → Telegram community only (+ website)
    # post_soc → FB/IG/X only (+ website)
    # post_all → everywhere (+ website)
    # Website is always published on any approval.
    if item["lang"] == "dv":
        buttons = [
            [("📣 Post to Telegram", f"post_tg:{key}"), ("📱 Post to Social", f"post_soc:{key}")],
            [("🌐 Post to All", f"post_all:{key}")],
            [("✏️ Edit", f"edit_approve:{key}"), ("❌ Reject", f"reject:{key}")],
        ]
    else:
        buttons = [
            [("📣 Post to Telegram", f"post_tg:{key}"), ("📱 Post to Social", f"post_soc:{key}")],
            [("🌐 Post to All", f"post_all:{key}")],
            [("✏️ Edit", f"edit_approve:{key}"), ("❌ Reject", f"reject:{key}")],
        ]
    kb = _make_inline_kb(buttons)

    # If we have a finished card image, send it as a photo with the caption
    msg_id = None
    if item.get("card_bytes"):
        buf = io.BytesIO(item["card_bytes"])
        msg_id = send_photo(CORE_TEAM_CHAT_ID, buf, msg,
                            thread_id=CONTENT_LAB_THREAD_ID, reply_markup=kb)
    else:
        msg_id = send_text(CORE_TEAM_CHAT_ID, msg,
                           thread_id=CONTENT_LAB_THREAD_ID, reply_markup=kb)

    # Store message_id so we can remove buttons after action
    if msg_id:
        item["_lab_message_id"] = msg_id

    _mark_content_lab_sent(item)
    _content_lab_db_upsert(key, item, status="pending")
    log.info(f"📨 Approval card sent to Content Lab: {key} ({item['lang']})")

    # Cortex already made the pre-AI decision. No separate commenter message.

    return True


def post_article(article, seen, social_only=False, allow_social=True):
    """
    New v5 flow:
      - English BREAKING → publish instantly (1 at a time, no approval)
      - Everything else (English regular + ALL Dhivehi) → queue for Content Lab approval
    Marks an article as seen only after it is safely queued or published.

    NOTE: social_only param retained for call-site compatibility but is always False.
    The social_only=True path was removed in Sprint A (Part 1 — editorial pipeline
    now handles all destination routing via Content Lab buttons).
    """
    article = dict(article)
    article["_original_title"] = article.get("title", "")
    article["_original_summary"] = article.get("summary", "")
    article["title"] = sanitize_public_news_text(article.get("title", ""))
    article["summary"] = sanitize_public_news_text(article.get("summary", ""))
    cat = article["cat"]
    # Cortex sets breaking status after the mandatory gate below. Do not let the
    # legacy keyword classifier make an editorial decision before Cortex.
    breaking = False
    is_dv = article.get("lang") == "dv"

    # Hard safety wall before Content Lab / cards / website.
    safe_ok, safe_reason = contentlab_candidate_is_safe(
        title=article.get("title",""),
        summary=article.get("summary",""),
        source=article.get("source",""),
        lang=article.get("lang","en"),
    )
    if not safe_ok:
        seen.add(article["id"]); save_seen(seen)
        db_record_article(article, score=0,
                          reliability=source_reliability(article.get("source","")),
                          status="filtered", is_breaking=False)
        log.warning(f"🧱 Blocked unsafe story before queue: {safe_reason} — {article['title'][:90]}")
        return False

    # Central safety guarantee: every route, including breaking and direct
    # Discovery/manual integrations, must pass Cortex before semantic dedup or
    # any DeepSeek/Claude/Gemini work. The cached decision from run_job is reused.
    cortex_gate = _cortex_gate_article(article)
    if not cortex_gate.get("ai_allowed"):
        seen.add(article["id"]); save_seen(seen)
        db_record_article(
            article, score=int(cortex_gate.get("score") or 0),
            reliability=source_reliability(article.get("source", "")),
            status="cortex_rejected", is_breaking=False,
        )
        log.info(
            "[CORTEX NEWS DIRECTOR] publisher blocked lead before AI: %s | %s",
            cortex_gate.get("reason", "rejected"), _cortex_gate_log(article, cortex_gate),
        )
        return False
    cortex_decision = article.get("_cortex_decision")
    breaking = bool(getattr(cortex_decision, "breaking", False))
    cortex_review_required = bool(cortex_gate.get("requires_human_review"))

    dedup_title = article.get("_dedup_title")
    if not dedup_title and is_dv:
        # Direct/breaking DV paths may bypass the regular shortlist. Allow one
        # semantic dedup call for the actual article, never for the bulk feed.
        dedup_title = story_signal_key_semantic(
            article.get("title", ""), article.get("summary", ""), "dv",
            budget={"limit": 1, "used": 0},
        )
    if not dedup_title:
        dedup_title = story_signal_key(
            article.get("title", ""), article.get("summary", ""), article.get("lang", "en")
        )
    article["_dedup_title"] = dedup_title or article.get("title", "")

    # Commit dedup/seen state only after the story is safely queued or published.
    # This prevents a temporary card/image/Telegram failure from permanently
    # swallowing a valid story before Content Lab receives it.
    _processed_committed = False

    def _commit_processed(status=None, posted=False):
        nonlocal _processed_committed
        if _processed_committed:
            return
        seen.add(article["id"])
        save_seen(seen)
        remember_story_title(article["_dedup_title"])
        if status:
            db_mark_status(article["id"], status, posted=posted)
        _processed_committed = True
        log.info(f"[PIPELINE] committed article={article['id']} status={status or 'processed'}")

    # Archive every article we process (DB no-op if Postgres unavailable)
    db_record_article(article, score=score_article(article),
                      reliability=source_reliability(article.get("source","")),
                      status="seen", is_breaking=breaking)

    # ── Story clustering — track which sources report this event ──
    cluster_size, cluster_sources = register_in_cluster(article["_dedup_title"], article.get("source",""))

    # ── Duplicate story check — skip if same event already posted/queued/rejected ──
    if is_duplicate_story(article["_dedup_title"]):
        note_duplicate_skip()
        log.info(f"⏭️ Skipping duplicate ({cluster_size} sources): {article['title'][:55]}")
        # A confirmed duplicate is intentionally consumed so it does not return
        # every 15 minutes. Do not add it to recent_story_titles again.
        seen.add(article["id"])
        save_seen(seen)
        db_mark_status(article["id"], "duplicate")
        return False
    # Stash cluster info on the article so the card can show "X sources reporting"
    article["_cluster_size"] = cluster_size
    article["_cluster_sources"] = cluster_sources

    # ── STORY INTELLIGENCE — attach this article to a story thread ──
    try:
        story_id, is_new_story, update_num = find_or_create_story(
            article["title"], cat, article["id"],
            article.get("summary", ""), article.get("source", ""), article.get("link", "")
        )
        article["_story_id"] = story_id
        article["_story_update_num"] = update_num
        article["_story_is_new"] = is_new_story
        # If this is an update to an existing developing story, notify core team
        if story_id and not is_new_story and update_num >= 2:
            log.info(f"📚 This is update #{update_num} to Story #{story_id}")
    except Exception as e:
        log.debug(f"Story attach: {e}")

    # ── Confidence gate — high-priority but unconfirmed news gets held ──
    priority = score_article(article)
    confidence, conf_reasons = confidence_score(article)
    article["_priority"] = priority
    article["_confidence"] = confidence
    hold, hold_reason = should_hold_for_review(priority, confidence, breaking)
    if cortex_review_required:
        hold = True
        hold_reason = cortex_gate.get("reason") or "Cortex requires human review"

    # ── English BREAKING: Cortex may post instantly or require review ──
    if breaking and not is_dv:
        # Breaking-specific strict dedup: a repeated breaking post is far more
        # costly than a repeated regular card (it bypasses Content Lab and
        # blasts every platform instantly). Re-check against the dedup memory
        # with a much lower similarity threshold before auto-posting. The
        # Japan-grant story posted 3× because differently-worded headlines from
        # different outlets scored below the normal 0.55 threshold while the
        # Gemini semantic layer was rate-limited.
        try:
            if is_duplicate_story(article["_dedup_title"], threshold=0.35):
                note_duplicate_skip()
                seen.add(article["id"]); save_seen(seen)
                db_mark_status(article["id"], "duplicate")
                log.info(f"⏭️ Breaking strict-dedup skip (≥35% match): {article['title'][:60]}")
                return False
        except Exception as _bd_err:
            log.debug(f"breaking strict dedup: {_bd_err}")

        # Build 15.7: Cortex is the final editorial authority. There is no
        # second Claude yes/no call and no separate keyword veto after Cortex.
        # Deterministic safety checks may still route an accepted lead to review,
        # but no other editor can reverse Cortex's accept/reject decision.
        if hold:
            # Don't auto-post — queue for review with a warning instead
            log.info(f"🛑 Breaking held for review: {hold_reason} — {article['title'][:50]}")
            try:
                card_bytes, caption, rewritten, keyword, bg = _build_card_and_caption(article)
                key = store_pending_approval(
                    card_bytes, caption, article["title"], article["link"], cat=cat, lang="en",
                    dv_text=None, keyword=keyword, source=article.get("source","LOCAL"),
                    is_breaking=True, allow_social=allow_social,
                    dedup_title=article.get("_dedup_title"), summary=article.get("summary",""),
                    cortex_gate=cortex_gate
                )
                if not key:
                    return False
                approval_queue[key]["rewritten"] = rewritten
                approval_queue[key]["summary"] = article.get("summary","")
                approval_queue[key]["article_id"] = article["id"]
                approval_queue[key]["_priority"] = article.get("_priority", priority)
                approval_queue[key]["_confidence"] = confidence
                try:
                    # Held breaking previously published bare — no author, no
                    # cover — leaking byline-less, cover-less articles onto the
                    # website. Attribute to Samuga AI and reuse the bg already
                    # fetched for the card to build a branded web cover.
                    _held_cover_url = None
                    try:
                        _held_cover_buf = generate_web_cover(
                            title=article["title"], category=cat,
                            bg_image=bg, source=SAMUGA_PUBLIC_SOURCE,
                        )
                        _held_cover_url = upload_to_imgbb(_held_cover_buf.read())
                    except Exception as _held_wce:
                        log.debug(f"[WEB COVER] held breaking cover failed: {_held_wce}")
                    db_publish_article_for_website(
                        article_id=article["id"], title=article["title"],
                        summary=samuga_public_summary(article.get("title", ""), article.get("summary", ""), rewritten), category=cat,
                        source=SAMUGA_PUBLIC_SOURCE,
                        link=SAMUGA_PUBLIC_LINK, lang="en",
                        score=article.get("_priority", 0),
                        reliability=source_reliability(article.get("source", "")),
                        is_breaking=True,
                        author_id="samuga_ai",
                        author_name="Samuga AI",
                        author_role="AI Newsroom",
                        author_photo_url=_AI_PHOTO["url"],
                        cover_image_url=_held_cover_url,
                    )
                    log.info(f"🌐 Website published held EN breaking story: {article['title'][:60]}")
                except Exception as e:
                    log.error(f"[WEBSITE] held breaking publish failed: {e}")
                approval_queue[key]["_cluster_size"] = article.get("_cluster_size", 1)
                approval_queue[key]["_confidence"] = confidence
                approval_queue[key]["_hold_reason"] = hold_reason
                approval_queue[key]["_content_lab_suppressed"] = True
                db_mark_status(article["id"], "queued")
                _commit_processed(status="queued")
                approval_queue[key]["_held_for_confidence"] = False
                approval_queue[key]["_alert_only"] = True
                # Low-confidence breaking goes to Alert thread only — not Content Lab.
                send_text(CORE_TEAM_CHAT_ID,
                    f"⚠️ <b>BREAKING held for review</b>\n{hold_reason}\n\n"
                    f"<b>{article['title'][:90]}</b>\n"
                    f"Source: {article.get('source','?')} · Confidence: {confidence}%\n\n"
                    f"Approve with <code>/approved {key}</code> if verified.\n"
                    f"<i>Not sent to Content Lab to prevent flooding.</i>",
                    thread_id=ALERT_THREAD_ID)
            except Exception as e:
                log.error(f"Breaking hold queue: {e}")
            return False
        # Confidence OK — publish instantly as normal
        card_bytes, caption, rewritten, keyword, bg = _build_card_and_caption(article)
        tg_ok, _social = _publish_now(card_bytes, caption, cat, article["title"], article["link"],
                            is_breaking_flag=True, allow_social=allow_social,
                            rewritten=rewritten, summary=article.get("summary",""),
                            article_id=article["id"], bg=bg,
                            website_article_body=article.get("_website_article_body"))
        db_mark_status(article["id"], "posted" if tg_ok else "seen", posted=bool(tg_ok))
        if tg_ok:
            _commit_processed(status="posted", posted=True)
        # Send reference copy to Content Lab (for team awareness, no action needed)
        if tg_ok:
            try:
                send_text(CORE_TEAM_CHAT_ID,
                    f"🚨 <b>BREAKING posted automatically</b>\n"
                    f"📰 {article['title'][:100]}\n"
                    f"Source: {article.get('source','?')} · Score: {score_article(article)}\n"
                    f"<i>Already posted to Telegram + socials. This is for reference only.</i>",
                    thread_id=CONTENT_LAB_THREAD_ID)
            except Exception: pass

        # ── Auto-generate Dhivehi version for breaking news ──────────────────
        # Sent to Content Lab for review. If nobody acts in 2 hours, posts automatically.
        if tg_ok and GEMINI_API_KEY:
            def _auto_dv_breaking(_title=article["title"], _rewritten=rewritten,
                                  _link=article["link"], _cat=cat, _kw=keyword,
                                  _source=article.get("source","LOCAL"), _aid=article["id"]):
                try:
                    dv_text = make_dhivehi_caption(_rewritten, _title)
                    if not dv_text:
                        return
                    key = store_pending_approval(
                        None, None, _title, _link, cat=_cat, lang="dv",
                        dv_text=dv_text, keyword=_kw, source=_source,
                        is_breaking=True, allow_social=True,
                        dedup_title=story_signal_key(_title, _rewritten, "dv"),
                        summary=article.get("summary",""), cortex_gate=cortex_gate
                    )
                    if not key:
                        return
                    approval_queue[key]["article_id"] = f"{_aid}_dv"
                    approval_queue[key]["_auto_post_breaking"] = False  # DV never auto-posts
                    approval_queue[key]["summary"] = article.get("summary","")
                    # Pre-fetch bg
                    bg = fetch_background_image(_kw, cat=_cat, title=_title)
                    if key in approval_queue:
                        # Store as base64 string so it survives json.dump() in persist_state().
                        # Raw bytes and PIL Images are NOT JSON-serializable.
                        try:
                            if bg is not None:
                                import base64 as _b64
                                _bg_thumb = bg.convert("RGB").resize((400, 400), Image.LANCZOS)
                                _bg_buf = BytesIO()
                                _bg_thumb.save(_bg_buf, format="JPEG", quality=75)
                                approval_queue[key]["_bg_image_b64"] = _b64.b64encode(_bg_buf.getvalue()).decode("ascii")
                            else:
                                approval_queue[key]["_bg_image_b64"] = None
                        except Exception as _bge:
                            log.debug(f"bg store failed: {_bge}")
                            approval_queue[key]["_bg_image_b64"] = None
                    _send_approval_card(key, approval_queue[key])
                    # Notify Content Lab
                    send_text(CORE_TEAM_CHAT_ID,
                        f"🇲🇻 <b>Dhivehi version ready</b> — <code>{key}</code>\n"
                        f"<i>{_title[:80]}</i>\n\n"
                        f"Approve, edit or reject within 2 hours.\n"
                        f"If no action taken — <b>posts automatically at 2h mark.</b>\n\n"
                        f"/approved {key} · /approved {key} [corrected text] · /reject {key}",
                        thread_id=CONTENT_LAB_THREAD_ID)
                    log.info(f"🇲🇻 Breaking Dhivehi version queued: {key}")
                except Exception as e:
                    log.debug(f"Auto-DV breaking: {e}")
            threading.Thread(target=_auto_dv_breaking, daemon=True).start()

        return bool(tg_ok)

    # ── Dhivehi cards: generate Dhivehi text, queue for approval (card built on approval) ──
    if is_dv:
        try:
            rewritten, keyword = rewrite_news(
                _strip_telegram_metadata(article["title"]),
                _strip_telegram_metadata(article.get("summary", "")),
                cat,
                article=article,
            )
            dv_text = make_dhivehi_caption(rewritten, article["title"])
            if not dv_text:
                # Final safety net: proper source Thaana may be shown for manual
                # review, but raw Latin Thaana must never be labelled "Bot wrote".
                raw_fallback = (article.get("summary") or article.get("title") or "").strip()
                if not raw_fallback:
                    log.warning(f"Dhivehi fallback empty for: {article['title'][:50]}")
                    return False
                if not is_dhivehi(raw_fallback):
                    log.warning(
                        f"[AI] Final DV caption unavailable; refusing raw Latin fallback: "
                        f"{article['title'][:50]}"
                    )
                    return False
                dv_text = raw_fallback
                article["_ai_unavailable"] = True
                log.warning(f"[AI] Proper-Thaana source fallback queued for manual review: {article['title'][:50]}")
            key = store_pending_approval(
                None, None, article["title"], article["link"], cat=cat, lang="dv",
                dv_text=dv_text, keyword=keyword, source=article.get("source","LOCAL"),
                is_breaking=breaking, allow_social=allow_social,
                dedup_title=article.get("_dedup_title"), summary=article.get("summary",""),
                cortex_gate=cortex_gate
            )
            if not key:
                return False
            approval_queue[key]["article_id"] = article["id"]
            approval_queue[key]["_priority"] = article.get("_priority", priority)
            approval_queue[key]["_confidence"] = confidence
            approval_queue[key]["_cluster_size"] = article.get("_cluster_size", 1)
            approval_queue[key]["_trend_theme"] = article.get("_trend_theme", "")
            approval_queue[key]["summary"] = article.get("summary", "")
            if article.get("_ai_unavailable"):
                approval_queue[key]["_ai_unavailable"] = True
                approval_queue[key]["_hold_reason"] = "AI unavailable — manual review required"
            # Pre-fetch background in background thread so card builds instantly on approval
            def _prefetch_bg(_key=key, _kw=keyword, _title=article["title"], _cat=cat):
                try:
                    bg = fetch_background_image(_kw, cat=_cat, title=_title)
                    if _key in approval_queue:
                        # Store as base64 string (see note above)
                        try:
                            if bg is not None:
                                import base64 as _b64
                                _bg_thumb2 = bg.convert("RGB").resize((400, 400), Image.LANCZOS)
                                _bg_buf2 = BytesIO()
                                _bg_thumb2.save(_bg_buf2, format="JPEG", quality=75)
                                approval_queue[_key]["_bg_image_b64"] = _b64.b64encode(_bg_buf2.getvalue()).decode("ascii")
                            else:
                                approval_queue[_key]["_bg_image_b64"] = None
                        except Exception as _bge2:
                            log.debug(f"bg store failed: {_bge2}")
                            approval_queue[_key]["_bg_image_b64"] = None
                except Exception: pass
            threading.Thread(target=_prefetch_bg, daemon=True).start()
            _send_approval_card(key, approval_queue[key])
            db_mark_status(article["id"], "queued")
            _commit_processed(status="queued")
            return True
        except Exception as e:
            log.error(f"Dhivehi approval queue: {e}")
            return False

    # ── English regular: build card, queue for approval ──
    try:
        card_bytes, caption, rewritten, keyword, bg = _build_card_and_caption(article)
        key = store_pending_approval(
            card_bytes, caption, article["title"], article["link"], cat=cat, lang="en",
            dv_text=None, keyword=keyword, source=article.get("source","LOCAL"),
            is_breaking=breaking, allow_social=allow_social,
            dedup_title=article.get("_dedup_title"), summary=article.get("summary",""),
            cortex_gate=cortex_gate
        )
        if not key:
            return False
        # Stash rewritten + summary for poll generation on approval
        approval_queue[key]["rewritten"] = rewritten
        approval_queue[key]["summary"] = article.get("summary","")
        approval_queue[key]["article_id"] = article["id"]
        approval_queue[key]["_priority"] = article.get("_priority", priority)
        approval_queue[key]["_confidence"] = confidence
        approval_queue[key]["_bg_image_b64"] = article.get("_bg_image_b64")
        approval_queue[key]["_cluster_size"] = article.get("_cluster_size", 1)
        approval_queue[key]["_trend_theme"] = article.get("_trend_theme", "")

        # Content Lab is the critical path. Deliver/queue the approval card before
        # optional web-cover upload or website work can delay the newsroom flow.
        _send_approval_card(key, approval_queue[key])
        db_mark_status(article["id"], "queued")
        _commit_processed(status="queued")

        # Website-first publishing: every English story selected by the bot
        # goes to the website immediately, even while Telegram/socials wait for
        # approval or the queue. Dhivehi stays private until approved/posted.
        # Reuse the exact Pexels background already fetched for the social card,
        # generate a branded 1200x630 web cover, upload it, and persist its URL.
        try:
            _en_cover_url = None
            try:
                _en_cover_buf = generate_web_cover(
                    title=article["title"],
                    category=cat,
                    bg_image=bg,
                    source=SAMUGA_PUBLIC_SOURCE,
                )
                _en_cover_url = upload_to_imgbb(_en_cover_buf.read())
                if _en_cover_url:
                    log.info(f"[WEB COVER] EN auto cover uploaded: {article['title'][:60]}")
                else:
                    log.warning(f"[WEB COVER] EN auto cover upload returned no URL: {article['title'][:60]}")
            except Exception as _en_cover_err:
                log.warning(f"[WEB COVER] EN auto cover failed: {_en_cover_err}")

            db_publish_article_for_website(
                article_id=article["id"],
                title=article["title"],
                summary=samuga_public_summary(article.get("title", ""), article.get("summary", ""), rewritten),
                category=cat,
                source=SAMUGA_PUBLIC_SOURCE,
                link=SAMUGA_PUBLIC_LINK,
                lang="en",
                score=article.get("_priority", 0),
                reliability=source_reliability(article.get("source", "")),
                is_breaking=breaking,
                author_id="samuga_ai",
                author_name="Samuga AI",
                author_role="AI Newsroom",
                author_photo_url=_AI_PHOTO["url"],
                cover_image_url=_en_cover_url,
                generated_article_body=article.get("_website_article_body"),
            )
            if _last_publish_block.get("reason"):
                log.warning(f"🌐 Website EN story held: {article['title'][:60]} — {_last_publish_block.get('reason')}")
            else:
                log.info(f"🌐 Website published EN story immediately: {article['title'][:60]} cover={'yes' if _en_cover_url else 'no'}")
        except Exception as e:
            log.error(f"[WEBSITE] EN immediate publish failed: {e}")

        # ── Auto-generate Dhivehi version in background ──────────────────────
        # Every English article also gets a Dhivehi card queued for approval.
        # Runs in a thread so it doesn't delay the English card.
        if GEMINI_API_KEY and AUTO_DHIVEHI_CARD_ENABLED and article.get("_allow_auto_dv", True):
            def _auto_dv(_rewritten=rewritten, _title=article["title"],
                         _link=article["link"], _cat=cat, _keyword=keyword,
                         _source=article.get("source","LOCAL"), _aid=article["id"],
                         _summary=article.get("summary", "")):
                try:
                    dv_text = make_dhivehi_caption(_rewritten, _title)
                    if not dv_text:
                        log.debug(f"[AI] Auto-Dhivehi: Gemini returned nothing for {_title[:40]}")
                        return
                    dv_key = store_pending_approval(
                        None, None, _title, _link, cat=_cat, lang="dv",
                        dv_text=dv_text, keyword=_keyword, source=_source,
                        is_breaking=breaking, allow_social=allow_social,
                        dedup_title=story_signal_key(_title, _rewritten, "dv"), summary=_summary,
                        cortex_gate=cortex_gate
                    )
                    if not dv_key:
                        return
                    approval_queue[dv_key]["article_id"] = f"{_aid}_dv"
                    approval_queue[dv_key]["_priority"] = 0
                    approval_queue[dv_key]["summary"] = _summary
                    _send_approval_card(dv_key, approval_queue[dv_key])
                    log.info(f"[AI] Auto-Dhivehi queued: {_title[:50]}")
                except Exception as e:
                    log.debug(f"[AI] Auto-Dhivehi: {e}")
            threading.Thread(target=_auto_dv, daemon=True).start()

        return True
    except Exception as e:
        log.error(f"English approval queue: {e}")
        return False


# ── Run Job ───────────────────────────────────────────────────────────────────
def run_job(social_only=False, breaking_only=False):  # social_only always False — see Sprint A
    """
    Every 15-min scan:
      - Breaking news: posts immediately to all platforms (no queue, no limit)
      - Breaking low-confidence: goes to Alert, auto-posts in 30 min if no action
      - Regular English: max 2-3 best per HOUR go to Content Lab - bot picks, not all
      - Regular Dhivehi: max 2-3 best per HOUR go to Content Lab
      - Total Content Lab cards: max 6 per hour (3 EN + 3 DV)
      - Breaking is completely separate - never counts toward hourly budget
    """
    global daily_sports_count, daily_world_count, daily_tourism_count, _pending_article
    h = get_mvt_hour()
    log.info(f"🕐 MVT {h:02d}:xx | {'DAY' if is_day_mode() else 'NIGHT'}")
    seen = load_seen()
    articles = fetch_news()

    fresh = [a for a in articles if a["id"] not in seen]
    if not fresh:
        log.info("No fresh articles."); return

    # Pre-build clusters for corroboration scoring
    for a in fresh:
        size, srcs = register_in_cluster(a["title"], a.get("source",""))
        a["_cluster_size"] = size
        a["_cluster_sources"] = srcs

    # Build 15.7 Cortex News Director: the single final pre-AI gate.
    # Cheap duplicate hygiene may reject first, but no DeepSeek/Claude/Gemini
    # work is allowed until Cortex explicitly returns accept or review.
    directed = []
    consumed = 0
    gate_counts = {}
    for article in fresh:
        local_signal = story_signal_key(
            article.get("title", ""), article.get("summary", ""), article.get("lang", "en")
        )
        if local_signal and is_duplicate_story(local_signal):
            article["_duplicate"] = True
        gate = _cortex_gate_article(article)
        action = str(gate.get("action") or "reject")
        gate_counts[action] = gate_counts.get(action, 0) + 1
        if not gate.get("ai_allowed"):
            seen.add(article["id"])
            consumed += 1
            try:
                db_record_article(
                    article, score=int(gate.get("score") or 0),
                    reliability=source_reliability(article.get("source", "")),
                    status="cortex_rejected", is_breaking=False,
                )
            except Exception:
                pass
            log.info(
                "[CORTEX NEWS DIRECTOR] rejected: %s | %s",
                gate.get("reason", "not selected"), _cortex_gate_log(article, gate),
            )
            continue
        directed.append(article)
        log.info("[CORTEX NEWS DIRECTOR] selected: %s", _cortex_gate_log(article, gate))

    fresh = directed
    if consumed:
        save_seen(seen)
    log.info(
        "[CORTEX NEWS DIRECTOR] decisions=%s selected=%s rejected=%s ai_calls=0",
        gate_counts, len(fresh), consumed,
    )

    if not fresh:
        log.info("[CORTEX NEWS DIRECTOR] No story deserves the AI pipeline in this scan")
        return

    fresh.sort(key=lambda article: (
        int((article.get("_cortex_gate") or {}).get("score") or 0),
        int((article.get("_cortex_gate") or {}).get("confidence") or 0),
        score_article(article),
    ), reverse=True)

    # Cortex alone determines whether a lead is genuinely breaking. Review-only
    # breaking leads still enter post_article(), which sends them to human review.
    breaking_articles = [
        a for a in fresh
        if bool(getattr(a.get("_cortex_decision"), "breaking", False))
    ]
    regular_articles = [] if breaking_only else [a for a in fresh if a not in breaking_articles]

    if breaking_only and not breaking_articles:
        log.info("🌙 Night mode: no breaking news found"); return

    log.info(f"🔴 {len(breaking_articles)} breaking | 🟡 {len(regular_articles)} regular")

    # ── 1. BREAKING — fires immediately, no budget, no throttle ─────────────
    if breaking_articles:
        a = breaking_articles[0]
        log.info(f"🔴 BREAKING: {a['title'][:60]}")
        post_article(a, seen, social_only=False, allow_social=True)

    if breaking_only:
        return

    # ── 2. PROGRESSIVE SCORING FUNNEL ────────────────────────────────────────
    # Each 15-min scan: score all fresh articles → funnel down to 1-2 winners
    # No hard quota cut — exceptional articles always get through
    # Hour safety cap: HOURLY_CARD_CAP (default 6) so Railway doesn't get spammed

    now_mvt = utcnow() + timedelta(hours=5)
    hour_start = now_mvt.replace(minute=0, second=0, microsecond=0)
    hour_start_utc = hour_start - timedelta(hours=5)

    # Count cards already created this hour (across both languages)
    cards_this_hour = sum(1 for v in approval_queue.values()
                          if v.get("created_at", utcnow()) >= hour_start_utc)

    # Normal hours stop at four cards. A genuinely high-priority lead may open
    # the exceptional ceiling of six, but the hard cap can never exceed six.
    high_priority_hour = any(
        int((a.get("_cortex_gate") or {}).get("score") or 0) >= 78
        or score_article(a) >= CONTENT_LAB_HIGH_SCORE
        for a in regular_articles
    )
    hourly_card_limit = min(
        HOURLY_CARD_CAP,
        CONTENT_LAB_HIGH_MAX_PER_HOUR if high_priority_hour else CONTENT_LAB_NORMAL_MAX_PER_HOUR,
    )
    if cards_this_hour >= hourly_card_limit:
        log.info(f"📵 Hourly Content Lab cap hit ({cards_this_hour}/{hourly_card_limit}) — skipping scan")
        return

    scan_slots = hourly_card_limit - cards_this_hour  # remaining capacity this hour
    _prefiltered_duplicate_ids = set()

    # One shared budget for all Dhivehi semantic duplicate checks in this scan.
    # Cached translations do not consume the budget.
    _dv_semantic_budget = {"limit": DV_GEMINI_SHORTLIST_MAX, "used": 0}
    _dv_semantic_stats = {
        "attempts": 0, "success": 0, "cache_hits": 0,
        "budget_skips": 0, "local_fallbacks": 0,
    }

    def _cortex_ranking_bonus(article, label):
        """Rank by the already-cached Cortex News Director decision.

        Cortex ran before this funnel. This function makes no decision and no
        provider call; it only converts the final Cortex score into a small
        ordering bonus so the most important approved leads rise first.
        """
        if not _cortex_ranking_enabled:
            return 0
        gate = article.get("_cortex_gate") or {}
        score = int(gate.get("score") or 0)
        risk = int(gate.get("risk") or 0)
        bonus = min(24, max(0, round(score * 0.24)))
        if risk >= 70:
            bonus -= 20
        return bonus

    def progressive_funnel(articles, label=""):
        """
        Progressive scoring funnel:
        Score all → keep top 50% → score again → keep top 50% → repeat
        until 1-3 articles remain. Returns ordered list of winners.
        This mirrors how a senior editor thinks — first cut obvious low quality,
        then keep re-evaluating until the best stories surface naturally.
        """
        if not articles:
            return []

        # First: attach scores to all articles (sort by recency bonus too)
        scored = []
        for a in articles:
            s = score_article(a)
            # Freshness bonus: articles from this scan get +10 so newest rises faster
            pub = a.get("published")
            if pub:
                try:
                    age_mins = (utcnow() - pub).total_seconds() / 60
                    if age_mins < 30:
                        s += 15   # very fresh — just posted
                    elif age_mins < 60:
                        s += 8    # fresh — within the hour
                except Exception:
                    pass
            s += _cortex_ranking_bonus(a, label)
            a["_funnel_score"] = s
            scored.append(a)

        # Cut anything below minimum threshold immediately
        scored = [a for a in scored if a["_funnel_score"] >= FUNNEL_MIN_SCORE]
        if not scored:
            log.info(f"[FUNNEL] {label}: all articles below min score {FUNNEL_MIN_SCORE}")
            return []

        scored.sort(key=lambda a: a["_funnel_score"], reverse=True)
        log.info(f"[FUNNEL] {label}: {len(articles)} → {len(scored)} after min score cut")

        # Progressive halving passes
        pool = scored
        pass_num = 0
        while len(pool) > 3:
            pass_num += 1
            # Re-score with latest context (cluster size may have grown)
            for a in pool:
                a["_funnel_score"] = score_article(a) + _cortex_ranking_bonus(a, label)
            pool.sort(key=lambda a: a["_funnel_score"], reverse=True)
            keep = max(1, int(len(pool) * FUNNEL_KEEP_RATIO))
            prev = len(pool)
            pool = pool[:keep]
            log.info(f"[FUNNEL] {label} pass {pass_num}: {prev} → {len(pool)}")

        # Final sort — highest score first
        pool.sort(key=lambda a: a["_funnel_score"], reverse=True)

        if not pool:
            return []

        # Decide how many cards this scan gets. Then choose that many from the
        # ranked list *after* removing story-level duplicates. The old flow chose
        # one winner first and only discovered afterward that it was a duplicate,
        # wasting the whole scan instead of promoting the runner-up.
        top_score = pool[0]["_funnel_score"]
        target_count = 2 if (
            top_score >= CONTENT_LAB_HIGH_SCORE
            and len(pool) >= 2
            and pool[1]["_funnel_score"] >= CONTENT_LAB_HIGH_SCORE
        ) else 1

        # Preserve the editorial funnel ordering, but fall back to the next best
        # scored articles when a finalist is already posted/queued/rejected.
        candidate_order = []
        candidate_ids = set()
        for candidate in pool + scored:
            identity = candidate.get("id") or id(candidate)
            if identity in candidate_ids:
                continue
            candidate_ids.add(identity)
            candidate_order.append(candidate)

        winners = []
        duplicates_removed = 0
        max_duplicate_checks = min(len(candidate_order), 16)
        is_dv_funnel = str(label).upper() == "DV"

        def _consume_duplicate(candidate, reason="duplicate"):
            nonlocal duplicates_removed
            duplicates_removed += 1
            note_duplicate_skip()
            if candidate.get("id"):
                seen.add(candidate["id"])
                _prefiltered_duplicate_ids.add(candidate["id"])
                try:
                    db_mark_status(candidate["id"], "duplicate")
                except Exception:
                    pass
            log.info(
                f"[FUNNEL] {label} {reason} removed before winner selection: "
                f"{candidate.get('title','')[:70]}"
            )

        for rank, candidate in enumerate(candidate_order[:max_duplicate_checks], start=1):
            title = candidate.get("title", "")
            summary = candidate.get("summary", "")
            lang = candidate.get("lang", "en")

            # Cheap same-language duplicate check for every finalist. No Gemini.
            local_signal = story_signal_key(title, summary, lang)
            if local_signal and is_duplicate_story(local_signal):
                candidate["_dedup_title"] = local_signal
                _consume_duplicate(candidate, reason="local duplicate")
                continue

            signal = local_signal
            # Only the top N Dhivehi finalists get semantic English translation.
            # If the budget/circuit is unavailable, this safely returns local_signal.
            if is_dv_funnel and rank <= DV_GEMINI_SHORTLIST_MAX:
                signal = story_signal_key_semantic(
                    title, summary, "dv",
                    budget=_dv_semantic_budget,
                    stats=_dv_semantic_stats,
                ) or local_signal

            candidate["_dedup_title"] = signal or title
            if candidate["_dedup_title"] and is_duplicate_story(candidate["_dedup_title"]):
                reason = "semantic duplicate" if signal != local_signal else "duplicate"
                _consume_duplicate(candidate, reason=reason)
                continue

            winners.append(candidate)
            if len(winners) >= target_count:
                break

        if duplicates_removed:
            log.info(f"[FUNNEL] {label}: {duplicates_removed} duplicate(s) removed before winner selection")

        if not winners:
            log.info(
                f"[FUNNEL] {label}: no non-duplicate winner found in top "
                f"{max_duplicate_checks} ranked candidates"
            )
            return []

        if len(winners) == 2:
            log.info(
                f"[FUNNEL] {label}: 2 non-duplicate winners "
                f"(scores {winners[0]['_funnel_score']} + {winners[1]['_funnel_score']})"
            )
        else:
            log.info(
                f"[FUNNEL] {label}: 1 non-duplicate winner "
                f"(score {winners[0]['_funnel_score']})"
            )
        return winners

    # Run funnel separately for EN and DV
    en_regular = [a for a in regular_articles if a.get("lang", "en") == "en"]
    dv_regular  = [a for a in regular_articles if a.get("lang") == "dv"]

    en_winners = progressive_funnel(en_regular, label="EN") if en_regular else []
    dv_winners = progressive_funnel(dv_regular, label="DV") if dv_regular else []

    log.info(
        "[AI BUDGET] Dhivehi semantic dedup "
        f"attempts={_dv_semantic_stats['attempts']}/{_dv_semantic_budget['limit']} "
        f"success={_dv_semantic_stats['success']} "
        f"cache_hits={_dv_semantic_stats['cache_hits']} "
        f"local_fallbacks={_dv_semantic_stats['local_fallbacks']} "
        f"budget_skips={_dv_semantic_stats['budget_skips']}"
    )

    if _prefiltered_duplicate_ids:
        save_seen(seen)
        log.info(
            f"[FUNNEL] consumed {len(_prefiltered_duplicate_ids)} duplicate article id(s) "
            f"so they will not starve later scans"
        )

    all_winners = en_winners + dv_winners
    log.info(f"[FUNNEL] Final: {len(en_winners)} EN + {len(dv_winners)} DV winners this scan "
             f"| {cards_this_hour}/{hourly_card_limit} cards used this hour")

    if not all_winners:
        log.info("📭 No articles passed the funnel this scan")
        return

    # Enforce the actual remaining hourly capacity. English stories normally
    # reserve two slots (EN + auto-Dhivehi); when only one remains, the English
    # card is still allowed but auto-Dhivehi is disabled for that story.
    remaining_slots = max(0, scan_slots)
    dv_sent = 0
    en_sent = 0

    # Direct Dhivehi winners cost one card each.
    for a in dv_winners:
        if remaining_slots < 1:
            log.info("📵 No hourly card slot remains for additional DV winners")
            break
        log.info(f"🇲🇻 DV winner (score {a.get('_funnel_score',0)}): {a['title'][:55]}")
        if post_article(a, seen, social_only=False, allow_social=False):
            dv_sent += 1
            remaining_slots -= 1
        else:
            log.warning(f"[PIPELINE] DV winner was not queued; it remains retryable unless duplicate: {a['title'][:70]}")
    if dv_sent:
        log.info(f"🇲🇻 {dv_sent} Dhivehi card(s) → Content Lab")

    # English winners cost one slot, plus one reserved slot for auto-Dhivehi.
    for a in en_winners:
        if remaining_slots < 1:
            log.info("📵 No hourly card slot remains for additional EN winners")
            break
        cat = a["cat"]
        text_lower = (a["title"] + " " + a.get("summary","")).lower()

        if cat in ["SPORTS", "FOOTBALL"]:
            mv_sports = ["maldives","dhivehi","raajje","national team","team maldives"]
            if not any(kw in text_lower for kw in mv_sports):
                log.info(f"⏭️ EN winner filtered (non-MV sports): {a['title'][:50]}")
                continue
            if not can_post_cat_today(daily_sports_count, 1):
                log.info(f"⏭️ EN winner filtered (sports daily cap): {a['title'][:50]}")
                continue
        elif cat == "WORLD":
            mv_world = ["maldives","indian ocean","south asia","india","china", "un ","dollar","oil","global economy"]
            if not any(kw in text_lower for kw in mv_world):
                log.info(f"⏭️ EN winner filtered (non-MV world): {a['title'][:50]}")
                continue
            if not can_post_cat_today(daily_world_count, 2):
                continue
        elif cat == "TOURISM":
            if not can_post_cat_today(daily_tourism_count, 2):
                continue

        allow_auto_dv = bool(AUTO_DHIVEHI_CARD_ENABLED and GEMINI_API_KEY and remaining_slots >= 2)
        a["_allow_auto_dv"] = allow_auto_dv
        reserved_cost = 2 if allow_auto_dv else 1
        log.info(
            f"🟡 EN winner (score {a.get('_funnel_score',0)}) → Content Lab: {a['title'][:55]} "
            f"(card slots={reserved_cost})"
        )
        if post_article(a, seen, social_only=False, allow_social=True):
            en_sent += 1
            remaining_slots -= reserved_cost
        else:
            log.warning(f"[PIPELINE] EN winner was not queued; it remains retryable unless duplicate: {a['title'][:70]}")

    if en_sent:
        log.info(f"📰 {en_sent} English card(s) sent to Content Lab")
    log.info(
        f"✅ run_job done — {en_sent} EN + {dv_sent} DV selected; "
        f"{hourly_card_limit - remaining_slots}/{hourly_card_limit} hourly slots accounted"
    )

# Sources scanned in the fast breaking-news check (5 min cycle)
BREAKING_SOURCES = [
    {"url": "https://sunonline.mv/feed",              "cat": "LOCAL", "lang": "dv"},
    {"url": "https://psmnews.mv/en/feed",             "cat": "LOCAL", "lang": "en"},
    # visitmaldives removed from breaking sources — tourism is never breaking news
    {"url": "https://maldivesvoice.com/feed",         "cat": "LOCAL", "lang": "en"},
    {"url": "https://english.sun.mv/feed",            "cat": "LOCAL", "lang": "en"},
    {"url": "https://edition.mv/feed",                "cat": "LOCAL", "lang": "en"},
    {"url": "https://mihaaru.com/rss",                "cat": "LOCAL", "lang": "dv"},
    {"url": "https://avas.mv/feed",                   "cat": "LOCAL", "lang": "dv"},
]

DV_BREAKING_FAST_TERMS = [
    "ހާދިސާ", "އަލިފާން", "މަރު", "ހައްޔަރު", "ފުލުހުން",
    "ކޯޓު", "މަޖިލިސް", "ރައީސް", "ވަކިވެ", "އެމަޖެންސީ",
    "ސުނާމީ", "ބިންހެއްލުން", "ފުރޮޅުން", "ގެއްލިގެން",
    "breaking", "urgent", "emergency", "accident", "fire", "arrested",
]


def _looks_like_fast_dv_breaking(article):
    raw = f"{article.get('title','')} {article.get('summary','')}".lower()
    return any(term.lower() in raw for term in DV_BREAKING_FAST_TERMS)


def fetch_breaking_sources():
    """Fetch fast sources without translating every Dhivehi RSS item.

    Translation now happens only in breaking_news_check() after freshness,
    seen-ID and local urgency filtering. This removes the previous burst of up
    to 20 Gemini calls every five minutes.
    """
    articles, seen_titles = [], set()
    # MvCrisis always first
    for a in fetch_mvcrisis():
        if a["title"] not in seen_titles:
            seen_titles.add(a["title"])
            articles.append(a)
    for fc in BREAKING_SOURCES:
        try:
            feed = feedparser.parse(fc["url"])
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                summary = entry.get("summary", title)
                if not title or not is_fresh(entry):
                    continue
                key = _caption_match_key(title) or title.lower()[:50]
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                articles.append({
                    "id": hashlib.md5(entry.get("link", title).encode()).hexdigest(),
                    "title": title,
                    "summary": summary,
                    "link": entry.get("link", ""),
                    "cat": fc["cat"],
                    "lang": fc["lang"],
                    "source": entry.get("source", {}).get("title", fc["cat"]),
                })
        except Exception as e:
            log.error(f"Breaking source feed error ({fc['url']}): {e}")
    return articles


def breaking_news_check():
    """Fast check every 5 min, with Cortex always running before paid AI.

    Cortex judges the untouched feed candidate first. Only a Cortex-approved
    breaking candidate may use the single Dhivehi translation allowance and
    continue to post_article(). The cached Cortex verdict remains the final
    editorial decision throughout the downstream pipeline.
    """
    try:
        seen = load_seen()
        articles = fetch_breaking_sources()
        dv_budget = {"limit": BREAKING_DV_GEMINI_MAX_PER_CHECK, "used": 0}
        dv_stats = {
            "attempts": 0, "success": 0, "cache_hits": 0,
            "budget_skips": 0, "local_fallbacks": 0,
        }

        for a in articles:
            if a["id"] in seen:
                continue
            if a["cat"] not in ["LOCAL", "DISASTER"]:
                continue

            # Final editorial decision happens on the raw feed item, before any
            # Gemini translation or other paid provider call.
            cortex_gate = _cortex_gate_article(a)
            if not cortex_gate.get("ai_allowed"):
                log.info(
                    "[CORTEX NEWS DIRECTOR][FAST] rejected before AI: %s | %s",
                    cortex_gate.get("reason", "not selected"),
                    _cortex_gate_log(a, cortex_gate),
                )
                continue
            if not cortex_gate.get("breaking_candidate"):
                continue

            candidate = a
            if a.get("lang") == "dv":
                # This local check costs no AI. It only prevents a malformed or
                # non-urgent Thaana item from spending the fast-path allowance.
                if not _looks_like_fast_dv_breaking(a):
                    continue
                with _GEMINI_LOCK:
                    _cb_until = float(_GEMINI_HEALTH.get("circuit_until") or 0)
                if _cb_until > time.time():
                    log.debug("[AI] Fast DV breaking: circuit open, skipping Gemini translate")
                    continue
                combined = f"{a.get('title','')}\n{a.get('summary','')}"
                english = gemini_dhivehi_to_english_cached(
                    combined, budget=dv_budget, stats=dv_stats
                )
                if not english:
                    continue
                candidate = dict(a)
                candidate["title"] = english[:220]
                candidate["summary"] = english
                candidate["_dedup_title"] = _caption_match_key(english)
                candidate["_original_dv_title"] = a.get("title", "")
                candidate["_original_dv_summary"] = a.get("summary", "")
                # Preserve the raw-item editorial verdict; translation is a
                # writing aid and must never reopen or override the decision.
                candidate["_cortex_gate"] = dict(a.get("_cortex_gate") or {})
                candidate["_cortex_decision"] = a.get("_cortex_decision")

            log.info(f"🔴 CORTEX BREAKING FAST: {candidate['title'][:60]}")
            post_article(candidate, seen, social_only=False, allow_social=True)
            break  # one at a time

        if dv_stats["attempts"] or dv_stats["cache_hits"] or dv_stats["budget_skips"]:
            log.info(
                "[AI BUDGET] Fast DV breaking "
                f"attempts={dv_stats['attempts']}/{dv_budget['limit']} "
                f"success={dv_stats['success']} cache_hits={dv_stats['cache_hits']} "
                f"fallbacks={dv_stats['local_fallbacks']} budget_skips={dv_stats['budget_skips']}"
            )
    except Exception as e:
        log.error(f"Breaking check: {_mask_secrets(str(e))}")

_running_jobs = set()
_running_jobs_lock = threading.RLock()

def scheduled_check():
    with _running_jobs_lock:
        if "scheduled_check" in _running_jobs:
            log.debug("scheduled_check already running — skipping overlap")
            return
        _running_jobs.add("scheduled_check")
    try:
        h=get_mvt_hour()
        if not is_day_mode():
            log.info(f"🌙 Night mode (MVT {h:02d}:xx) — breaking news only")
            run_job(breaking_only=True)
        else:
            run_job()
    finally:
        with _running_jobs_lock:
            _running_jobs.discard("scheduled_check")

# ── Morning Brief (7AM MVT) ───────────────────────────────────────────────────
def send_morning_brief():
    log.info("🌅 Morning brief...")
    try:
        headlines=get_local_headlines()
        if not headlines: return
        # Inject actual MVT date so Claude never hallucinates it
        from datetime import timezone, timedelta
        mvt = datetime.now(timezone.utc) + timedelta(hours=5)
        today_str = mvt.strftime("%A, %d %B %Y")
        prompt = f"""Create a warm "Good Morning Maldives 🌅" news brief for @samugacommunity.
Today's date is {today_str} (Maldives Time). Use this exact date in your greeting.
Headlines: {chr(10).join(headlines[:8])}
- Friendly greeting mentioning today's date exactly as given above
- Top 3-5 stories in 1 sentence each with emoji  
- Upbeat closing
- Max 180 words, English"""
        msg=ai.messages.create(model="claude-haiku-4-5-20251001",max_tokens=400,messages=[{"role":"user","content":prompt}])
        brief=msg.content[0].text.strip()
        caption=f"🌅 <b>Good Morning Maldives!</b>\n\n{brief}\n\n📡 <b>Samuga Media</b> | @samugacommunity"
        send_text(TELEGRAM_CHANNEL_ID, caption)
        log.info("✅ Morning brief sent!")
    except Exception as e: log.error(f"Morning brief: {e}")

# ── Tip/Story CTA ────────────────────────────────────────────────────────────
def send_tip_cta():
    """Send story tip CTA to Telegram channel (8:30AM and 8:30PM MVT)"""
    msg = (
        "🚨 <b>Have a story, tip, or news update?</b>\n\n"
        "Share it with Samuga Media privately and anonymously.\n"
        "🔒 Your identity stays confidential. 📩 Message us: @Samuga_Media\n\n"
        "Your voice matters. The people's media starts with you. 💙"
    )
    send_text(TELEGRAM_CHANNEL_ID, msg)
    log.info("📣 Tip CTA sent")

def night_queue_review():
    """
    Runs at 11PM MVT (after night summary).
    If social queue has pending items, sends list to Content Lab.
    Team decides what to post or delete.
    Queue then resets fresh for next day.
    """
    with _social_queue_lock:
        pending = list(_social_queue)

    if not pending:
        log.info("[NIGHT] Social queue already empty — no review needed")
        return

    log.info(f"[NIGHT] {len(pending)} pending social queue item(s) — sending review to Content Lab")

    lines = [
        "🌙 <b>NIGHT QUEUE REVIEW</b>",
        f"<i>It's 11PM MVT. {len(pending)} post(s) are still queued and won't auto-post tonight.</i>",
        "<i>Review each item and decide: force post now or delete.</i>\n"
    ]

    for i, item in enumerate(pending, 1):
        title = item.get("title", item.get("caption", "?"))[:70]
        cat   = item.get("cat", "LOCAL")
        lang  = item.get("lang", "en").upper()
        queued = item.get("queued_at")
        age = ""
        if queued:
            try:
                mins = int((utcnow() - queued).total_seconds() / 60)
                age = f" — queued {mins}min ago"
            except Exception:
                pass
        lines.append(f"<b>{i}.</b> [{lang}/{cat}]{age}")
        lines.append(f"   📰 {title}")
        lines.append(f"   ▶️ Post now: <code>/qpost {i}</code>")
        lines.append(f"   🗑 Delete: <code>/qdel {i}</code>")

    lines.append("")
    lines.append("🗑 Delete all: <code>/queue clear</code> → <code>/queue clear confirm</code>")
    lines.append("<i>Anything not actioned will auto-post tomorrow from 6AM MVT.</i>")

    msg = "\n".join(lines)
    try:
        send_text(CORE_TEAM_CHAT_ID, msg, thread_id=CONTENT_LAB_THREAD_ID)
        log.info(f"[NIGHT] Queue review sent to Content Lab: {len(pending)} items")
    except Exception as e:
        log.error(f"[NIGHT] Queue review send failed: {e}")


def night_queue_autoclear():
    """
    Runs at 11:30PM MVT.
    If social queue still has items (team took no action since 11:05PM review),
    clears everything automatically and notifies Content Lab.
    Queue resets fresh for next day starting 6AM.
    """
    with _social_queue_lock:
        pending = list(_social_queue)

    if not pending:
        log.info("[NIGHT] Auto-clear: queue already empty")
        return

    # Clear the queue
    with _social_queue_lock:
        count = len(_social_queue)
        _social_queue.clear()

    persist_state()
    log.info(f"[NIGHT] Auto-cleared {count} pending social queue item(s) at 11:30PM MVT")

    # Notify Content Lab
    titles = []
    for item in pending[:5]:
        t = item.get("title", item.get("caption","?"))[:60]
        titles.append(f"• {t}")

    lines = [
        "🌙 <b>NIGHT QUEUE AUTO-CLEARED</b>",
        f"<i>No action was taken on {count} pending post(s) since the 11:05PM review.</i>",
        f"<i>All items have been automatically deleted.</i>\n",
    ]
    if titles:
        lines.append("<b>Deleted items:</b>")
        lines.extend(titles)
        if count > 5:
            lines.append(f"  <i>...and {count - 5} more</i>")

    lines.append("")
    lines.append("✅ <b>Queue is now empty.</b> Fresh start tomorrow from 6AM MVT.")

    try:
        send_text(CORE_TEAM_CHAT_ID, "\n".join(lines), thread_id=CONTENT_LAB_THREAD_ID)
    except Exception as e:
        log.error(f"[NIGHT] Auto-clear notify failed: {e}")


def send_night_summary():
    log.info("🌙 Night summary...")
    try:
        if not recent_posts: log.info("No posts for summary"); return
        posts_text="\n".join([f"• [{p['cat']}] {p['title']}" for p in recent_posts[-15:]])
        prompt=f"""Create a "Tonight's Top Stories 🌙" summary for @samugacommunity.
Today's posts: {posts_text}
- Warm good evening greeting
- Top 5 stories in 1 sentence each with emoji
- Good night closing
- Max 180 words, English"""
        msg=ai.messages.create(model="claude-haiku-4-5-20251001",max_tokens=400,messages=[{"role":"user","content":prompt}])
        summary=msg.content[0].text.strip()
        caption=f"🌙 <b>Tonight's Top Stories</b>\n\n{summary}\n\n📡 <b>Samuga Media</b> | @samugacommunity"
        send_text(TELEGRAM_CHANNEL_ID, caption)
        log.info("✅ Night summary sent!")
    except Exception as e: log.error(f"Night summary: {e}")

# ── AI Nightly Journalist (v6) — the bot that THINKS ──────────────────────────
# At ~10:30PM, Claude reviews the entire day's article archive and writes a real
# editorial brief for the team: what mattered today, what it means for Maldivians,
# and a ready-to-shoot TikTok angle for Thooma. Lands in Content Lab, not public.
def send_ai_journalist_brief():
    log.info("🧠 Samuga AI brief generating...")
    try:
        # Pull today's articles from the archive (richer than recent_posts)
        articles_text = ""
        trends_text = ""
        if DB_ENABLED:
            rows = db_execute(
                """SELECT title, category, source, status FROM articles
                   WHERE found_at > NOW() - INTERVAL '18 hours'
                   ORDER BY score DESC LIMIT 40""", fetch="all")
            if rows:
                articles_text = "\n".join(
                    [f"• [{cat}] {title} ({src}) — {status}" for title, cat, src, status in rows])
            # Today's trends
            trends = detect_trends(hours=24, min_mentions=3)
            if trends:
                trends_text = "\n".join([f"• {theme}: {count} stories" for theme, count, _ in trends[:6]])
        # Fallback to recent_posts if no DB
        if not articles_text and recent_posts:
            articles_text = "\n".join([f"• [{p['cat']}] {p['title']}" for p in recent_posts[-20:]])
        if not articles_text:
            log.info("Samuga AI: no articles to review"); return

        from datetime import timezone as _tzx
        mvt = datetime.now(_tzx.utc) + timedelta(hours=5)
        today_str = mvt.strftime("%A, %d %B %Y")

        prompt = f"""You are Samuga AI, the senior editor at Samuga Media, a sharp Maldivian news outlet. It's the end of the day ({today_str}). Review today's news and write a private editorial brief for the team (Manchii, Uly, Thooma). Be insightful and specific to the Maldives — not generic.

TODAY'S ARTICLES:
{articles_text}

TRENDING THEMES TODAY:
{trends_text or "(not enough data yet)"}

Write a brief with EXACTLY these sections (use the emoji headers):

📰 TOP 3 STORIES TODAY
(The 3 most important stories, 1 line each, ranked by what matters to ordinary Maldivians — not by what's flashy.)

🇲🇻 WHAT THIS MEANS
(2-3 sentences: the real significance for everyday people in the Maldives. Connect the dots between stories if there's a pattern.)

🔮 WHAT TO WATCH TOMORROW
(1-2 things likely to develop or worth following up on.)

🎬 TIKTOK ANGLE FOR THOOMA
(One specific, punchy video idea based on today's biggest story — give a hook line she could open with.)

Keep it tight, smart, and in English. Max 280 words. Write like a real editor talking to their team, not a robot."""

        msg = ai.messages.create(model="claude-haiku-4-5-20251001", max_tokens=700,
                                 messages=[{"role": "user", "content": prompt}])
        brief = msg.content[0].text.strip()
        caption = (f"🧠 <b>SAMUGA NIGHTLY BRIEF</b>\n"
                   f"<i>{today_str}</i>\n\n"
                   f"{brief}\n\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"<i>Auto-generated by Samuga AI. Not posted publicly — for the team only.</i>")
        send_text(CORE_TEAM_CHAT_ID, caption, thread_id=ALERT_THREAD_ID)
        log.info("🧠 ✅ Samuga AI brief sent to Content Lab!")
    except Exception as e:
        log.error(f"Samuga AI brief: {e}")

# ── Phase 2: ENGAGEMENT LEARNING ENGINE (observe-only until /learning on) ─────
LEARN_MIN_POSTS        = 200   # total posted articles before activation allowed
LEARN_MIN_WEEKS        = 4     # weeks of history before activation allowed
LEARN_MIN_VALID_VIEWS  = 50    # posts that actually have view counts (real data)
LEARN_CAP              = 15    # max ± points engagement may move a score (hard cap)

_scraper_health = {"ok": 0, "fail": 0, "warned": False}

def fetch_message_views(message_id):
    """
    Scrape view count for a public-channel post. Returns int or None.
    Tracks success/failure so we can warn the team if it stops working.
    NOTE: Telegram's Bot API can't read post views — this scrapes the public
    t.me page. Works while the channel is public. Swap to a Telethon MTProto
    client later for guaranteed counts (single-function change).
    """
    if not message_id:
        return None
    try:
        chan = TELEGRAM_CHANNEL_ID.lstrip("@")
        url = f"https://t.me/{chan}/{message_id}?embed=1&mode=tme"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            _scraper_health["fail"] += 1
            return None
        import re as _re
        m = _re.search(r'tgme_widget_message_views[^>]*>([\d.,KMkm]+)<', resp.text)
        if not m:
            _scraper_health["fail"] += 1
            return None
        raw = m.group(1).strip().upper().replace(",", "")
        if raw.endswith("K"):
            val = int(float(raw[:-1]) * 1000)
        elif raw.endswith("M"):
            val = int(float(raw[:-1]) * 1_000_000)
        else:
            val = int(float(raw))
        _scraper_health["ok"] += 1
        return val
    except Exception as e:
        log.debug(f"fetch_message_views({message_id}): {e}")
        _scraper_health["fail"] += 1
        return None

def check_scraper_health(min_attempts=20):
    """Warn Content Lab once if view-scraping is mostly failing. Resets counters."""
    ok, fail = _scraper_health["ok"], _scraper_health["fail"]
    total = ok + fail
    if total >= min_attempts and fail / total > 0.7 and not _scraper_health["warned"]:
        send_text(CORE_TEAM_CHAT_ID,
            "⚠️ <b>View tracking looks broken.</b>\n\n"
            f"View scraping failed {fail}/{total} times this run. Telegram may have "
            "changed their page format, or the channel went private.\n\n"
            "Learning will keep using old numbers until this is fixed. Engagement "
            "data won't update.\n\n"
            "<i>Nothing else is affected — posting works normally.</i>",
            thread_id=ALERT_THREAD_ID)
        _scraper_health["warned"] = True
        log.warning(f"⚠️ Scraper health poor: {fail}/{total} failed")
    _scraper_health["ok"] = 0
    _scraper_health["fail"] = 0

# ── Phase 2.5: META GRAPH API — Facebook + Instagram engagement ──────────────
# Reads engagement off your OWN page (no scraping). FB lost reach/impressions in
# Meta's June 2026 change, so FB = reactions+comments+shares. IG = likes+comments
# (+impressions where available). Matched to articles by caption (match_key).
_meta_health = {"ok": 0, "fail": 0, "warned": False}

def _meta_get(path, params=None):
    """GET the Graph API. Returns parsed JSON dict or None."""
    if not META_PAGE_TOKEN:
        return None
    try:
        p = dict(params or {})
        p["access_token"] = META_PAGE_TOKEN
        url = f"https://graph.facebook.com/{META_API_VER}/{path}"
        resp = requests.get(url, params=p, timeout=15)
        if resp.status_code == 200:
            _meta_health["ok"] += 1
            return resp.json()
        # Surface the Graph error message to logs (token expiry, perms, etc.)
        try:
            err = resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            err = resp.text[:200]
        log.error(f"Meta GET {path} → {resp.status_code}: {err}")
        _meta_health["fail"] += 1
        return None
    except Exception as e:
        log.error(f"Meta GET {path}: {e}")
        _meta_health["fail"] += 1
        return None

def _resolve_ig_id():
    """Find the Instagram Business account linked to the FB page. Cached in bot_kv."""
    if META_IG_ID:
        return META_IG_ID
    cached = kv_get("meta_ig_id", {})
    if isinstance(cached, dict) and cached.get("id"):
        return cached["id"]
    if not META_PAGE_ID:
        return None
    data = _meta_get(META_PAGE_ID, {"fields": "instagram_business_account"})
    ig = (data or {}).get("instagram_business_account", {}).get("id") if data else None
    if ig:
        kv_set("meta_ig_id", {"id": ig})
        log.info(f"📷 Resolved IG business account: {ig}")
    return ig

def _fetch_fb_post_engagement(limit=50):
    """
    Return list of (caption_text, engagement_int) for recent FB page posts.
    Engagement = reactions + comments + shares (reach/impressions deprecated by Meta).
    """
    if not META_PAGE_ID:
        return []
    data = _meta_get(f"{META_PAGE_ID}/posts", {
        "fields": "message,created_time,"
                  "reactions.summary(total_count).limit(0),"
                  "comments.summary(total_count).limit(0),"
                  "shares",
        "limit": limit,
    })
    out = []
    for post in (data or {}).get("data", []):
        msg = post.get("message", "")
        if not msg:
            continue
        reacts = post.get("reactions", {}).get("summary", {}).get("total_count", 0)
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = post.get("shares", {}).get("count", 0)
        eng = (reacts or 0) + (comments or 0) + (shares or 0)
        out.append((msg, eng))
    log.info(f"📘 FB: {len(out)} posts with engagement")
    return out

def _fetch_ig_post_engagement(limit=50):
    """
    Return list of (caption_text, engagement_int) for recent IG media.
    Engagement = like_count + comments_count.
    """
    ig_id = _resolve_ig_id()
    if not ig_id:
        return []
    data = _meta_get(f"{ig_id}/media", {
        "fields": "caption,like_count,comments_count,timestamp",
        "limit": limit,
    })
    out = []
    for media in (data or {}).get("data", []):
        cap = media.get("caption", "")
        if not cap:
            continue
        eng = (media.get("like_count") or 0) + (media.get("comments_count") or 0)
        out.append((cap, eng))
    log.info(f"📷 IG: {len(out)} media with engagement")
    return out

def fetch_meta_insights(days=28):
    """
    Pull FB + IG engagement, match each post to an article by caption (match_key),
    and write the combined number to articles.meta_engagement. Runs weekly.
    Returns number of articles updated.
    """
    if not DB_ENABLED or not META_PAGE_TOKEN:
        return 0
    # Get candidate articles (posted recently, with a match key)
    rows = db_execute("""
        SELECT id, match_key FROM articles
        WHERE status='posted' AND match_key IS NOT NULL AND match_key <> ''
          AND posted_at > NOW() - INTERVAL %s
    """, (f"{days} days",), fetch="all")
    if not rows:
        return 0
    articles = [(aid, mk) for aid, mk in rows]

    # Gather all platform posts (caption, engagement)
    platform_posts = _fetch_fb_post_engagement() + _fetch_ig_post_engagement()
    if not platform_posts:
        check_meta_health()
        return 0

    # Pre-normalize platform captions to match keys
    norm_posts = [(_caption_match_key(cap), eng) for cap, eng in platform_posts]

    updated = 0
    for aid, mk in articles:
        if not mk:
            continue
        total_eng = 0
        matched = False
        for pmk, eng in norm_posts:
            if not pmk:
                continue
            # Match if either key contains the other's leading chunk (captions get
            # truncated differently per platform). Require a decent overlap.
            short = min(len(mk), len(pmk))
            if short >= 18 and (mk[:short] == pmk[:short] or mk in pmk or pmk in mk):
                total_eng += eng
                matched = True
        if matched:
            db_execute("UPDATE articles SET meta_engagement=%s WHERE id=%s", (total_eng, aid))
            updated += 1
    log.info(f"📊 Meta insights matched {updated}/{len(articles)} articles")
    check_meta_health()
    return updated

def check_meta_health(min_attempts=4):
    """Warn Content Lab once if Meta API calls are mostly failing (token expired etc.)."""
    ok, fail = _meta_health["ok"], _meta_health["fail"]
    total = ok + fail
    if total >= min_attempts and fail / total > 0.7 and not _meta_health["warned"]:
        send_text(CORE_TEAM_CHAT_ID,
            "⚠️ <b>Facebook/Instagram data tracking failed.</b>\n\n"
            f"Meta API calls failed {fail}/{total} times. The Page token may have "
            "expired or lost permissions.\n\n"
            "Regenerate it (Graph API Explorer → me/accounts) and update "
            "<code>META_PAGE_TOKEN</code> in Railway.\n\n"
            "<i>Posting still works — only FB/IG learning data is affected.</i>",
            thread_id=ALERT_THREAD_ID)
        _meta_health["warned"] = True
        log.warning(f"⚠️ Meta health poor: {fail}/{total} failed")
    _meta_health["ok"] = 0
    _meta_health["fail"] = 0


def backfill_tg_views(hours=240, limit=120):
    """Update tg_views for posted articles with a message_id. Runs weekly."""
    if not DB_ENABLED:
        return 0
    rows = db_execute("""
        SELECT id, tg_message_id FROM articles
        WHERE status='posted' AND tg_message_id IS NOT NULL
          AND posted_at > NOW() - INTERVAL %s
        ORDER BY posted_at DESC LIMIT %s
    """, (f"{hours} hours", limit), fetch="all")
    if not rows:
        return 0
    updated = 0
    for art_id, mid in rows:
        views = fetch_message_views(mid)
        if views is not None and views > 0:
            db_execute("UPDATE articles SET tg_views=%s WHERE id=%s", (views, art_id))
            updated += 1
        time.sleep(0.4)
    log.info(f"📈 Backfilled views for {updated}/{len(rows)} posts")
    check_scraper_health()
    return updated

def _median(nums):
    """Median of a list of numbers. 0 if empty."""
    s = sorted(n for n in nums if n is not None)
    if not s:
        return 0
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

def compute_topic_weights(days=28):
    """
    Rank trend themes by MEDIAN engagement (average = secondary). Combines
    Telegram views + Facebook/Instagram engagement, each normalized to its OWN
    platform baseline first (different scales), then blended. Writes to
    bot_kv['topic_weights']. Does NOT change scoring. Returns the weights dict.
    """
    if not DB_ENABLED:
        return {}
    rows = db_execute("""
        SELECT title, summary, tg_views, meta_engagement FROM articles
        WHERE status='posted'
          AND (tg_views > 0 OR meta_engagement > 0)
          AND posted_at > NOW() - INTERVAL %s
    """, (f"{days} days",), fetch="all")
    if not rows:
        return {}

    # Platform baselines (median of non-zero values) so we can normalize scales
    tg_vals   = [r[2] for r in rows if r[2] and r[2] > 0]
    meta_vals = [r[3] for r in rows if r[3] and r[3] > 0]
    tg_base   = _median(tg_vals) or 1
    meta_base = _median(meta_vals) or 1

    def _combined_signal(tg, meta):
        """Each platform normalized to ~1.0 = its own median, then averaged."""
        parts = []
        if tg and tg > 0:
            parts.append(tg / tg_base)
        if meta and meta > 0:
            parts.append(meta / meta_base)
        return sum(parts) / len(parts) if parts else 0.0

    theme_signals = {}
    for title, summary, tg, meta in rows:
        sig = _combined_signal(tg, meta)
        if sig <= 0:
            continue
        for theme in _detect_themes(f"{title or ''} {summary or ''}"):
            theme_signals.setdefault(theme, []).append(sig)
    if not theme_signals:
        return {}

    all_sig = [s for ss in theme_signals.values() for s in ss]
    baseline = _median(all_sig) or 1.0

    import math
    weights = {}
    for theme, ss in theme_signals.items():
        if len(ss) < 3:
            continue
        med = _median(ss)
        avg = sum(ss) / len(ss)
        ratio = med / baseline if baseline else 1.0
        raw = math.log2(ratio) * LEARN_CAP if ratio > 0 else 0
        weight = max(-LEARN_CAP, min(LEARN_CAP, round(raw)))
        # 'median' shown as a relative index (1.0 = typical post) for readability
        weights[theme] = {"weight": weight, "median": round(med, 2),
                          "avg": round(avg, 2), "n": len(ss)}

    kv_set("topic_weights", weights)
    kv_set("topic_weights_baseline", {"median": round(baseline, 2)})
    log.info(f"📊 Computed topic weights for {len(weights)} themes (baseline median {round(baseline)})")
    return weights

def learning_stats():
    """Return (posted_total, weeks_elapsed, valid_view_count)."""
    if not DB_ENABLED:
        return (0, 0, 0)
    posted = db_execute("SELECT COUNT(*) FROM articles WHERE status='posted'", fetch="one")
    posted = posted[0] if posted else 0
    first = db_execute("SELECT MIN(found_at) FROM articles", fetch="one")
    weeks = 0
    if first and first[0]:
        try:
            weeks = (utcnow() - first[0].replace(tzinfo=None)).days / 7.0
        except Exception:
            weeks = 0
    valid = db_execute("SELECT COUNT(*) FROM articles WHERE status='posted' AND (tg_views > 0 OR meta_engagement > 0)", fetch="one")
    valid = valid[0] if valid else 0
    return (posted, round(weeks, 1), valid)

def learning_is_active():
    """True only if a human flipped the switch."""
    flag = kv_get("learning_active", {"on": False})
    return bool(flag.get("on")) if isinstance(flag, dict) else bool(flag)

def topic_weight_for(title, summary=""):
    """Engagement nudge ±LEARN_CAP, ONLY if learning active. (points, theme) or (0,None)."""
    if not learning_is_active():
        return (0, None)
    weights = kv_get("topic_weights", {})
    if not weights:
        return (0, None)
    themes = _detect_themes(f"{title} {summary}")
    best_pts, best_theme = 0, None
    for th in themes:
        w = weights.get(th, {}).get("weight", 0)
        if abs(w) > abs(best_pts):
            best_pts, best_theme = w, th
    return (best_pts, best_theme)

def _top_gainers_losers(weights, n=4):
    """Format top +n gainers and -n losers as two text blocks."""
    if not weights:
        return ("", "")
    items = [(th, d["weight"], d["median"], d["n"]) for th, d in weights.items()]
    gain = sorted([i for i in items if i[1] > 0], key=lambda x: -x[1])[:n]
    lose = sorted([i for i in items if i[1] < 0], key=lambda x:  x[1])[:n]
    g = "\n".join([f"  • {th} +{w} <i>({med}× typical, {nn} posts)</i>" for th, w, med, nn in gain])
    l = "\n".join([f"  • {th} {w} <i>({med}× typical, {nn} posts)</i>" for th, w, med, nn in lose])
    return (g, l)

def check_learning_readiness():
    """Weekly: if gate met and not yet asked, send the ONE-TIME readiness prompt."""
    if not DB_ENABLED:
        return
    posted, weeks, valid = learning_stats()
    already = kv_get("learning_prompt_sent", {"sent": False})
    if learning_is_active() or (isinstance(already, dict) and already.get("sent")):
        return
    if posted < LEARN_MIN_POSTS or weeks < LEARN_MIN_WEEKS or valid < LEARN_MIN_VALID_VIEWS:
        log.info(f"🧪 Learning not ready: posts={posted}/{LEARN_MIN_POSTS} "
                 f"weeks={weeks}/{LEARN_MIN_WEEKS} valid_views={valid}/{LEARN_MIN_VALID_VIEWS}")
        return
    weights = compute_topic_weights()
    gainers, losers = _top_gainers_losers(weights)
    msg = (
        "🧠 <b>Learning mode ready</b>\n\n"
        f"I've banked <b>{posted}</b> posts over <b>{weeks}</b> weeks, "
        f"<b>{valid}</b> with real view counts.\n\n"
        "<b>Top performers:</b>\n" + (gainers or "  (not enough data)") + "\n\n"
        "<b>Underperformers:</b>\n" + (losers or "  (not enough data)") + "\n\n"
        "If you approve, I'll let audience data <i>nudge</i> my posting decisions — "
        f"capped at ±{LEARN_CAP} pts. It informs, it never overrides a serious story.\n\n"
        "✅ <code>/learning on</code> to activate\n"
        "📊 <code>/learning status</code> to see the numbers\n"
        "<i>Ignore to stay observe-only. I won't ask again.</i>"
    )
    send_text(CORE_TEAM_CHAT_ID, msg, thread_id=ALERT_THREAD_ID)
    kv_set("learning_prompt_sent", {"sent": True, "at": utcnow().isoformat()})
    log.info("🧠 Readiness prompt sent to Content Lab (one-time).")

# ── Weekly Analytics Report to Core Team ─────────────────────────────────────
def send_weekly_analytics():
    log.info("📊 Weekly analytics report...")
    try:
        from datetime import timezone
        mvt = datetime.now(timezone.utc) + timedelta(hours=5)
        week_str = mvt.strftime("Week of %d %B %Y")

        total = sum(v for k, v in analytics["posts_by_cat"].items() if k != "SOCIAL")
        by_cat = analytics["posts_by_cat"]

        lines = []
        for cat in ["LOCAL","WORLD","FOOTBALL","TOURISM","WEATHER","DISASTER"]:
            if cat in by_cat:
                lines.append(f"  • {cat}: {by_cat[cat]} posts")

        cat_lines = chr(10).join([f"  - {c}: {by_cat[c]} posts" for c in ["LOCAL","WORLD","FOOTBALL","TOURISM","WEATHER","DISASTER"] if c in by_cat])
        report = (
            "<b>Samuga Media Weekly Report</b>" + chr(10)
            + week_str + chr(10) + chr(10)
            + "<b>Total Articles:</b> " + str(total) + chr(10)
            + (cat_lines if cat_lines else "  No posts yet") + chr(10) + chr(10)
            + "<b>Breaking News:</b> " + str(analytics["breaking_count"]) + chr(10) + chr(10)
            + "<b>Social Posting:</b>" + chr(10)
            + "  Success: " + str(analytics["social_success"]) + chr(10)
            + "  Failed: " + str(analytics["social_fail"]) + chr(10) + chr(10)
            + f"<b>Bot:</b> Samuga AI v{SAMUGA_VERSION}" + chr(10)
            + "Samuga Media | @samugacommunity"
        )
        # ── Phase 2: weekly engagement crunch + readiness ──
        learn_block = ""
        try:
            backfill_tg_views()                      # refresh view counts (matured)
            fetch_meta_insights()                    # refresh FB + IG engagement
            weights = compute_topic_weights()        # recompute (stored, not yet acting)
            posted, weeks, valid = learning_stats()
            gainers, losers = _top_gainers_losers(weights)
            mode = "ACTIVE ✅" if learning_is_active() else "observing 👀"
            learn_block = (
                chr(10) + "<b>📈 What we learned this week</b>" + chr(10)
                + f"Mode: {mode}  ({posted} posts, {valid} with views)" + chr(10) + chr(10)
                + "<b>Top gainers:</b>" + chr(10) + (gainers or "  (gathering data)") + chr(10) + chr(10)
                + "<b>Top losers:</b>"  + chr(10) + (losers  or "  (gathering data)") + chr(10)
            )
        except Exception as e:
            log.error(f"weekly learning block: {e}")
        report = report + learn_block

        send_text(CORE_TEAM_CHAT_ID, report)
        check_learning_readiness()                  # one-time prompt if gate met
        log.info("✅ Analytics report sent to core team")
    except Exception as e:
        log.error(f"Analytics report: {e}")

# ── Weekly Digest (Friday 6PM MVT) ───────────────────────────────────────────
def send_weekly_digest():
    log.info("📊 Weekly digest...")
    try:
        if not recent_posts: return
        posts_text="\n".join([f"• [{p['cat']}] {p['title']}" for p in recent_posts])
        prompt=f"""Create a "This Week in Maldives 🇲🇻" weekly digest for @samugacommunity.
This week: {posts_text}
- Top 5 most important stories
- 2 sentences each with emoji
- Encouraging closing
- Max 280 words"""
        msg=ai.messages.create(model="claude-haiku-4-5-20251001",max_tokens=500,messages=[{"role":"user","content":prompt}])
        digest=msg.content[0].text.strip()
        caption=f"📊 <b>This Week in Maldives 🇲🇻</b>\n\n{digest}\n\n📡 <b>Samuga Media</b> | @samugacommunity"
        send_text(TELEGRAM_CHANNEL_ID, caption)
        log.info("✅ Weekly digest sent!")
    except Exception as e: log.error(f"Weekly digest: {e}")

# ── Tavily Search ─────────────────────────────────────────────────────────────
def tavily_search(query):
    if not TAVILY_API_KEY: return ""
    try:
        resp=requests.post("https://api.tavily.com/search",
            json={"api_key":TAVILY_API_KEY,"query":query,"search_depth":"basic","max_results":4,"include_answer":True},timeout=15)
        if resp.status_code==200:
            data=resp.json()
            answer=data.get("answer","")
            snippets=[r.get("content","")[:200] for r in data.get("results",[])[:3]]
            log.info(f"✅ Tavily: {query[:40]}")
            return (answer+"\n"+"\n".join(snippets)).strip()
    except Exception as e: log.error(f"Tavily: {e}")
    return ""


def manual_topic_search_context(headline, subheading="", category="LOCAL", lang_hint="en"):
    """Get fast web context for manually created social cards so website articles can be richer."""
    try:
        q = " ".join(x for x in [headline, subheading] if x).strip()
        if not q:
            return ""
        query = q
        # If input is Latin Dhivehi, convert to English for search.
        if looks_latin_thaana(q):
            try:
                q_en = gemini_latin_thaana_to_english(q)
                if q_en:
                    query = q_en
            except Exception:
                pass
        # Keep search focused on Maldives relevance.
        if "maldives" not in query.lower():
            query = "Maldives " + query
        return tavily_search(query[:220])[:1200]
    except Exception as e:
        log.error(f"manual_topic_search_context: {e}")
        return ""


def _share_article_to_platform(article_id, platform, custom_caption=""):
    """
    Share a published article's link to a social platform.
    platform: 'facebook' | 'x' | 'telegram'
    Returns (success: bool, message: str).

    Uses the existing Telegram and Buffer connections. Telegram receives
    headline/caption plus the article link; Facebook uses a link attachment;
    X receives a compact caption plus link. A newsroom-written custom caption
    is supported while the article link remains included.
    """
    row = db_execute(
        "SELECT title, article_excerpt, summary, cover_image_url FROM articles WHERE id=%s",
        (article_id,), fetch="one"
    )
    if not row:
        return False, "Article not found in database."

    title, excerpt, summary, cover_url = row
    blurb = (excerpt or summary or "")[:200].strip()
    article_link = website_article_url(article_id=article_id)
    custom = str(custom_caption or "").strip()

    if platform == "telegram":
        # Telegram messages use HTML parse mode, so dashboard-written captions
        # are escaped before the article link is appended.
        if custom:
            plain_caption = custom if article_link in custom else f"{custom}\n\n{article_link}"
            caption = _html.escape(plain_caption)
        else:
            caption = f"📰 <b>{_html.escape(str(title))}</b>\n\n📲 Join us on Telegram — @samugacommunity\n\n{article_link}"
        try:
            ok = send_text(TELEGRAM_CHANNEL_ID, caption)
            return bool(ok), "Posted to Telegram community." if ok else "Telegram send failed."
        except Exception as e:
            return False, f"Telegram error: {str(e)[:100]}"

    elif platform == "facebook":
        if not BUFFER_FB_ID:
            return False, "Facebook Buffer channel not configured."
        # Facebook receives the link as an explicit link attachment.
        caption = custom or f"{title}\n\n📲 Join us on Telegram — @samugacommunity"
        ok = post_to_buffer(None, caption[:5000], BUFFER_FB_ID, metadata={"facebook": {"type": "post", "linkAttachment": {"url": article_link}}}, story_id=article_id, channel_name="Facebook", social_network="facebook")
        if ok:
            return True, "Posted to Facebook."
        return False, f"Facebook failed — {_last_buffer_error.get('response', 'unknown error')[:200]}"

    elif platform == "x":
        if not BUFFER_TW_ID:
            return False, "X Buffer channel not configured."
        base = custom or f"{title}\n\n📲 @samugacommunity"
        caption = base if article_link in base else f"{base}\n\n{article_link}"
        caption = caption[:280]
        ok = post_to_buffer(None, caption, BUFFER_TW_ID, story_id=article_id, channel_name="X", social_network="x")
        if ok:
            return True, "Posted to X."
        return False, f"X failed — {_last_buffer_error.get('response', 'unknown error')[:200]}"

    return False, f"Unknown platform: {platform}"


def _resolve_manual_author(user_id, first_name):
    """
    Resolve the Telegram sender who is manually publishing (via /article or
    /post to web) to a cms_authors profile.

    author_id match is authoritative (survives name changes). Name match is
    a fallback only for unregistered senders whose Telegram first_name
    happens to match a registered author's display name.

    Always returns a usable author_id — even when no cms_authors row exists
    yet — so authorship is never silently dropped on the article record.
    Register with /author set to attach a full profile for future articles;
    use /fix_author <id> to correct an already-published one.

    Returns: (author_id, author_name, author_role, author_photo_url)
    """
    _tg_id = f"tg_{user_id}" if user_id else None
    try:
        from db import db_list_authors
        _all_auth = db_list_authors(active_only=False)
        _matched_auth = next((a for a in _all_auth if a["author_id"] == _tg_id), None)
        if not _matched_auth:
            _matched_auth = next(
                (a for a in _all_auth if a["name"].lower() == (first_name or "").lower()),
                None
            )
        if _matched_auth:
            return (
                _matched_auth["author_id"],
                _matched_auth["name"],
                _matched_auth["role"],
                _matched_auth.get("photo_url"),
            )
        log.warning(
            f"[AUTHOR] No registered author profile for {_tg_id or first_name!r} "
            f"— using raw Telegram name '{first_name or 'Samuga Editor'}'. "
            f"Register with /author set to fix future articles; "
            f"use /fix_author <id> to correct this one after publishing."
        )
        return (_tg_id, first_name or "Samuga Editor", "Editor", None)
    except Exception as _auth_err:
        log.debug(f"[AUTHOR] resolve failed for {_tg_id or first_name!r}: {_auth_err}")
        return (_tg_id, first_name or "Samuga Editor", "Editor", None)


def _do_publish_pending_article(article_data, cover_image_url=None):
    """
    Final publish step for /article command.
    Called after the cover photo decision (with or without a cover).
    article_data comes from _pending_cover_photo dict.
    """
    article_id   = article_data["article_id"]
    parsed_title = article_data["title"]
    full_summary = article_data["summary"]
    article_body = article_data["article_body"]
    parsed_cat   = article_data["category"]
    _publish_lang= article_data["lang"]
    is_brk       = article_data["is_brk"]
    _auth_id     = article_data.get("author_id")
    _auth_name   = article_data["author_name"]
    _auth_role   = article_data["author_role"]
    _auth_photo  = article_data["author_photo"]
    article_url  = article_data["article_url"]

    pub_id = db_publish_article_for_website(
        article_id=article_id,
        title=parsed_title,
        summary=full_summary[:2500],
        category=parsed_cat,
        source=SAMUGA_PUBLIC_SOURCE,
        link=SAMUGA_CAPTION_LINK or "",
        lang=_publish_lang,
        score=200,
        reliability=100,
        is_breaking=is_brk,
        author_id=_auth_id,
        author_name=_auth_name,
        author_role=_auth_role,
        author_photo_url=_auth_photo,
        cover_image_url=cover_image_url or None,
        # This is human-authored (or human-reviewed AI-expanded) content from
        # the /article command, not the AI auto-pipeline — trust it outright
        # so it publishes immediately instead of going through (and possibly
        # being held by) the AI-generated-body quality gate.
        article_body=article_body,
    )

    if not pub_id:
        # db_publish_article_for_website silently rejects unsafe/placeholder
        # titles, empty-after-cleanup titles, too-short titles, etc. Raise
        # here so the caller shows a clear failure instead of a false
        # "Article published!" message with share buttons for an article
        # that was never actually written to the database.
        _reason = _last_publish_block.get("reason", "blocked by safety filter")
        raise RuntimeError(f"Publish blocked — {_reason}")

    # db_publish_article_for_website can transform the ID (dedup detection,
    # or appending "_dv" for Dhivehi articles). Always use the ID it actually
    # returns from here on — this is what's really in the database.
    if pub_id:
        article_id  = pub_id
        article_url = website_article_url(article_id=article_id)

    # Body is written by db_publish_article_for_website itself now (article_body
    # was passed above and trusted as-is) — no separate post-publish UPDATE needed.

    try:
        event_article_published(
            article_id=article_id, title=parsed_title,
            category=parsed_cat, lang=_publish_lang,
            is_breaking=is_brk, source=SAMUGA_PUBLIC_SOURCE,
            published_by=_auth_name, pipeline="manual",
            url=article_url,
        )
    except Exception:
        pass

    db_log_learning(
        article_id=article_id, action="manual_article",
        member=_auth_name, category=parsed_cat,
        source=SAMUGA_PUBLIC_SOURCE, lang=_publish_lang
    )
    log.info(f"✍️ Manual article published: [{parsed_cat}] {parsed_title[:60]} cover={'yes' if cover_image_url else 'no'}")
    return article_id, article_url


def manual_publish_website_article(title, subheading="", category="LOCAL", source_link="",
                                    publish_now=True, author_id=None, author_name=None,
                                    author_role=None, author_photo_url=None):
    """
    For manual social cards, prepare an English website article, optionally publish it,
    and always send the detailed article preview to Content Lab.
    Returns dict with article_id, slug, body, title, summary, published.

    Not currently called anywhere in the bot — kept for future wiring. If/when a
    caller is added, pass author_id/author_name/author_role/author_photo_url
    (e.g. via _resolve_manual_author(user_id, first_name) for a human sender,
    or "samuga_ai"/"Samuga AI"/"AI Newsroom" for the AI pipeline) so published
    articles aren't left with a NULL author_id.
    """
    try:
        raw_title = (title or "").strip()
        raw_sub   = (subheading or "").strip()
        if not raw_title:
            return None
        safe_ok, safe_reason = contentlab_candidate_is_safe(raw_title, raw_sub, "Samuga Media", "en")
        if not safe_ok:
            log.warning(f"🧱 Manual website article blocked: {safe_reason} — {raw_title[:90]}")
            return None

        search_seed = (raw_title + ("\n\n" + raw_sub if raw_sub else "")).strip()
        english_title = raw_title
        english_summary = raw_sub or raw_title

        if looks_latin_thaana(search_seed):
            try:
                conv = gemini_latin_thaana_to_english(search_seed)
                if conv:
                    paras = [p.strip() for p in conv.split("\n\n") if p.strip()]
                    english_title = paras[0][:180] if paras else conv[:180]
                    english_summary = " ".join(paras[1:]).strip() if len(paras) > 1 else conv[:500]
            except Exception as e:
                log.warning(f"manual article latin→english failed: {e}")

        search_ctx = manual_topic_search_context(english_title, english_summary, category=category, lang_hint="en")
        summary_for_article = english_summary
        if search_ctx:
            summary_for_article = (english_summary + "\n\nWeb context:\n" + search_ctx).strip()

        article_id = "manual_" + hashlib.md5((english_title + "|" + summary_for_article + "|" + str(utcnow())).encode()).hexdigest()[:12]
        body = generate_website_article_body(
            title=english_title,
            summary=summary_for_article,
            category=category or "LOCAL",
            source=SAMUGA_PUBLIC_SOURCE,
            is_breaking=(category or "").upper() in ("BREAKING", "DISASTER")
        )
        slug = make_article_slug(english_title, article_id)

        if publish_now:
            db_publish_article_for_website(
                article_id=article_id,
                title=english_title[:500],
                summary=summary_for_article[:2500],
                category=category or "LOCAL",
                source=SAMUGA_PUBLIC_SOURCE,
                link=(source_link or SAMUGA_CAPTION_LINK or "").strip(),
                lang="en",
                score=190,
                reliability=95,
                is_breaking=(category or "").upper() in ("BREAKING", "DISASTER"),
                author_id=author_id,
                author_name=author_name,
                author_role=author_role,
                author_photo_url=author_photo_url,
                # NOTE: `body` above is itself AI-generated (not human-authored),
                # so it is deliberately NOT passed as article_body here — doing
                # so would mark it "trusted" and bypass the quality gate inside
                # db_publish_article_for_website(), reintroducing the exact
                # summary-as-body bug this fix addresses. Left ungated on
                # purpose; the publisher regenerates and gates its own body.
            )
            try:
                row = db_execute("SELECT article_slug, article_body FROM articles WHERE id=%s", (article_id,), fetch="one")
                if row:
                    slug = row[0] or slug
                    body = row[1] or body
            except Exception:
                pass

        preview = (
            f"📝 <b>Manual Website Article {'Published' if publish_now else 'Prepared'}</b>\n\n"
            f"<b>{english_title}</b>\n\n"
            f"{(body or summary_for_article or english_title)[:3500]}\n\n"
            f"🌐 <b>Website:</b> {SAMUGA_CAPTION_LINK}"
            + (f"/article.html?id={article_id}" if publish_now and article_id else "")
        )
        try:
            send_text(CORE_TEAM_CHAT_ID, preview, thread_id=CONTENT_LAB_THREAD_ID)
        except Exception as e:
            log.warning(f"manual article preview to content lab: {e}")

        return {
            "article_id": article_id,
            "slug": slug,
            "body": body,
            "title": english_title,
            "summary": summary_for_article,
            "category": category or "LOCAL",
            "published": bool(publish_now),
        }
    except Exception as e:
        log.error(f"manual_publish_website_article: {e}")
        return None


def manual_post_replied_article_to_website(reply_text, category_hint="LOCAL",
                                            user_id=None, first_name=None):
    """
    Publish a human-written article from a replied Telegram message directly to the website.
    First non-empty line = title. Remaining lines = body.

    user_id/first_name identify the Telegram sender running /post to web, and are
    resolved to a cms_authors profile via _resolve_manual_author() so the article
    is authored to a real author_id — not left NULL — same as the /article command.
    """
    try:
        _auth_id, _auth_name, _auth_role, _auth_photo = \
            _resolve_manual_author(user_id, first_name)
        raw = strip_source_links(str(reply_text or "")).strip()
        if not raw:
            return None, "Reply to the drafted article text first."
        parts = [p.strip() for p in raw.split("\n") if p.strip()]
        if not parts:
            return None, "Reply text is empty."

        parts = [p for p in parts if re.sub(r'@SamugaNewsBot\b', '', p, flags=re.I).strip().lower() not in ["/post to web", "/post web", "/posttoweb", "/postweb"]]
        if not parts:
            return None, "Only the command was found. Reply to the actual article text."

        title = parts[0][:220]
        body = "\n\n".join(parts[1:]).strip() if len(parts) > 1 else ""
        if not body:
            return None, "Article body is empty. Write the title on line 1 and the article on the lines below."

        lang = "dv" if is_dhivehi(title + " " + body) else "en"
        safe_ok, safe_reason = contentlab_candidate_is_safe(title, body, "Samuga Media", lang)
        if not safe_ok:
            alert_admin(f"Manual website post blocked\n\n<b>{title[:120]}</b>\nReason: {safe_reason}", dedupe_key=f"manualweb:{title[:80]}")
            return None, f"Blocked by safety wall: {safe_reason}"

        category = canonical_category(category_hint or "LOCAL", title, body)
        base_id = "manualweb_" + hashlib.md5((title + "|" + body + "|" + str(utcnow())).encode()).hexdigest()[:12]
        db_publish_article_for_website(
            article_id=base_id,
            title=title,
            summary=body[:2500],
            category=category,
            source=SAMUGA_PUBLIC_SOURCE,
            link=SAMUGA_CAPTION_LINK,
            lang=lang,
            score=195,
            reliability=99,
            is_breaking=(category in ("BREAKING","DISASTER")),
            author_id=_auth_id,
            author_name=_auth_name,
            author_role=_auth_role,
            author_photo_url=_auth_photo,
            # /post to web is the human typing the full article themselves —
            # publish exactly that text rather than letting the AI pipeline
            # regenerate (and potentially hold) it.
            article_body=body,
        )
        saved_id = base_id if lang != "dv" else f"{base_id}_dv"

        row = None
        try:
            excerpt = make_article_excerpt(title, body, lang=lang)
            db_execute(
                "UPDATE articles SET article_body=%s, article_excerpt=%s, status='posted' WHERE id=%s RETURNING id, article_slug",
                (body, excerpt, saved_id), fetch=None
            )
            row = db_execute("SELECT id, article_slug, status FROM articles WHERE id=%s LIMIT 1", (saved_id,), fetch="one")
        except Exception as e:
            log.warning(f"manual_post_replied_article_to_website body persist: {e}")

        if not row:
            row = db_execute("SELECT id, article_slug, status FROM articles WHERE id=%s LIMIT 1", (saved_id,), fetch="one")
        if not row:
            return None, "The article was not found in the database after publish."

        _, slug, status = row
        url = website_article_url(article_id=saved_id, slug=slug)
        return {
            "article_id": saved_id,
            "slug": slug or make_article_slug(title, saved_id),
            "title": title,
            "body": body,
            "category": category,
            "lang": lang,
            "url": url,
            "status": status or "posted",
        }, None
    except Exception as e:
        log.error(f"manual_post_replied_article_to_website: {e}")
        alert_admin(f"Manual website post failed\n\nReason: {str(e)[:300]}", dedupe_key="manual_post_replied_article_to_website")
        return None, str(e)


def needs_web_search(msg):
    # Skip search only for simple greetings / meta questions
    # Skip search for short messages or greetings
    if len(msg.strip()) <= 4: return False
    skip_kws = ["hello", "hi", "who are you", "what is samuga", "about you",
                "thank", "okay", "ok", "bye", "good morning", "good night",
                "good evening", "assalam", "hey", "sup", "wassup"]
    if any(k in msg.lower() for k in skip_kws): return False
    return True  # Default: always search for current info

# ── Smart Chat ────────────────────────────────────────────────────────────────
def is_dhivehi(text):
    """Check if text contains Thaana script (Dhivehi)"""
    return any('\u0780' <= c <= '\u07BF' for c in text)

def chat_with_gemini_dhivehi(user_message, context="", conversation_history=None):
    """Handle Dhivehi chat using actual Gemini API (native Dhivehi support)"""
    if not GEMINI_API_KEY:
        log.warning("No GEMINI_API_KEY — falling back to Claude for Dhivehi")
        return None
    try:
        # Try web search for Dhivehi queries too
        web_context = ""
        try:
            if needs_web_search(user_message) or not context:
                web_context = tavily_search("maldives news today 2026")
                if web_context:
                    log.info("🌐 Dhivehi path: web search done")
        except Exception as e:
            log.error(f"Dhivehi web search: {e}")

        if web_context:
            news_section = "LIVE WEB SEARCH (use this for answers, never repeat same info):\n" + web_context[:600]
        elif context:
            news_section = "LATEST NEWS CONTEXT:\n" + context
        else:
            news_section = ""

        system_prompt = (
            "You are Samuga AI, a Maldivian news assistant. Always reply in natural Dhivehi (Thaana script) only.\n\n"
            "ABOUT SAMUGA:\n"
            "- Samuga Media: Maldivian digital news outlet\n"
            "- Channel: @samugacommunity\n"
            "- Founder: Abdul Muhsin (Manchii) | Co-Founder: Mariyam Ulya (Uly)\n\n"
            + (news_section + "\n\n" if news_section else "") +
            "RULES:\n"
            "- Reply ONLY in Dhivehi Thaana script\n"
            "- Natural, conversational tone like a friendly Maldivian\n"
            "- Max 3-4 sentences\n"
            "- NEVER repeat the same news you already mentioned in this conversation\n"
            "- If asked for more — give DIFFERENT stories\n"
            "- Mention @samugacommunity when relevant\n"
            "- Never write in English or Latin script\n"
            "- Never say you cannot search or lack real-time info"
        )

        # Build contents array with history for multi-turn
        contents = []
        if conversation_history:
            for turn in conversation_history[-6:]:
                role = "user" if turn["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 400, "temperature": 0.7}
        }

        # Try models in fallback order
        for model_index, model in enumerate(GEMINI_MODELS[:GEMINI_MAX_MODELS_PER_REQUEST]):
            tracker = AIRequestTracker.start(
                "Gemini", model, feature="AI Chat", caller="chat_with_gemini_dhivehi",
                purpose="Dhivehi chat", prompt=user_message, retry_count=model_index,
            )
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                if not _reserve_ai_call("Gemini", f"Dhivehi chat ({model})", feature=tracker.feature, article_id=tracker.article_id, article_title=tracker.article_title, source_url=tracker.source_url, retry_count=tracker.retry_count):
                    tracker.blocked(_ai_reserve_block_reason())
                    return None
                resp = requests.post(url, json=payload, timeout=15)
                status = int(resp.status_code)
                provider_request_id = str(resp.headers.get("x-request-id") or resp.headers.get("x-goog-request-id") or "")
                if status == 200:
                    data = resp.json()
                    usage = data.get("usageMetadata") or {}
                    reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    tracker.success(
                        input_tokens=int(usage.get("promptTokenCount") or 0),
                        output_tokens=int(usage.get("candidatesTokenCount") or 0),
                        cached_tokens=int(usage.get("cachedContentTokenCount") or 0),
                        cache_read_tokens=int(usage.get("cachedContentTokenCount") or 0),
                        provider_request_id=provider_request_id, response_text=reply,
                    )
                    log.info(f"✅ Gemini Dhivehi chat done ({model})")
                    return reply
                error_text = ""
                try:
                    error_text = (resp.json().get("error") or {}).get("message") or resp.text[:500]
                except Exception:
                    error_text = resp.text[:500]
                tracker.failure(error_text or f"HTTP {status}", http_status=status, provider_request_id=provider_request_id)
                if status in [429, 503]:
                    log.warning(f"[AI] Gemini {model} quota/unavailable, trying next")
                    continue
                log.error(f"Gemini {model} HTTP {status}")
                break
            except Exception as e:
                tracker.failure(e)
                _critical_ai_failure(f"Gemini Dhivehi chat ({model})", e)
                continue
    except Exception as e:
        _critical_ai_failure("Gemini Dhivehi chat", e)
    return None

def answer_story_query(message):
    """
    If the message is asking about a past event ('what happened with the ferry'),
    search stories and return a formatted timeline answer. Returns None if no match.
    """
    if not DB_ENABLED:
        return None
    ml = message.lower()
    # Triggers that suggest someone is asking about an ongoing/past event
    triggers = ["what happened", "what's happening", "whats happening", "update on",
                "latest on", "any news on", "any update", "tell me about the",
                "what about the", "story of", "develop", "kobaa", "vaahaka"]
    if not any(t in ml for t in triggers):
        return None

    matches = search_stories(message, limit=3)
    if not matches:
        return None

    best = matches[0]
    timeline = get_story_timeline(best["id"])
    if not timeline or timeline["update_count"] < 2:
        return None

    from datetime import timedelta as _td
    lines = [f"📚 <b>{timeline['title']}</b>",
             f"<i>Story #{timeline['id']} · {timeline['update_count']} updates · {timeline['status']}</i>\n"]
    for u in timeline["updates"]:
        t = u["time"]
        tstr = (t + _td(hours=5)).strftime("%d %b %H:%M") if t else ""
        src = f" ({u['source']})" if u["source"] else ""
        lines.append(f"🔹 <b>{tstr}</b>{src} — {u['headline'][:90]}")
    if len(matches) > 1:
        lines.append("\n<i>Also tracking: " +
                     ", ".join(f"#{m['id']}" for m in matches[1:]) + " — use /story [id]</i>")
    return "\n".join(lines)

def chat_with_claude(user_message, user_id=None):
    try:
        # Run headlines + web search in parallel to cut latency
        results = {}

        def fetch_headlines():
            try: results["headlines"] = get_local_headlines()
            except Exception as e: log.debug(f"fetch_headlines: {e}"); results["headlines"] = []

        def fetch_web():
            try:
                if needs_web_search(user_message):
                    q = user_message
                    local_kws = ["weather","news","update","what happened","anything","latest","today"]
                    if any(w in user_message.lower() for w in local_kws) and "maldives" not in user_message.lower():
                        q = f"maldives {user_message} 2026"
                    elif any(w in user_message.lower() for w in ["world cup","match","score","won","win"]):
                        q = f"{user_message} 2026 latest"
                    results["web"] = tavily_search(q)
                    if results["web"]: log.info(f"🌐 Web: {results['web'][:60]}...")
            except Exception as e:
                log.error(f"Web search: {e}")
                results["web"] = ""

        t1 = threading.Thread(target=fetch_headlines)
        t2 = threading.Thread(target=fetch_web)
        t1.start(); t2.start()
        t1.join(timeout=5); t2.join(timeout=5)

        headlines = results.get("headlines", [])
        web_context = results.get("web", "") or ""
        headlines_text = "\n".join(headlines[:8]) if headlines else "No recent headlines."

        memory_text = ""
        if recent_posts:
            memory_text = "Recently posted:\n" + "".join([f"• [{p['cat']}] {p['title']}\n" for p in recent_posts[-5:]])

        if web_context:
            context = f"LIVE WEB SEARCH (use this for your answer):\n{web_context[:800]}"
            if memory_text: context += f"\n\n{memory_text}"
        else:
            context = f"LATEST NEWS:\n{headlines_text}"
            if memory_text: context += f"\n\n{memory_text}"

        system=f"""You are Samuga AI — smart friendly Maldivian news assistant for Samuga Media.

ABOUT SAMUGA:
Samuga Media delivers trusted Maldivian news. @samugacommunity is our Telegram channel.
Founder & MD: Abdul Muhsin (Manchii/Mutte) — Maldivian entrepreneur
Co-Founder & Editor: Mariyam Ulya (Uly) — journalist & editorial lead

CONTEXT:
{context}

PERSONALITY:
- Warm, friendly, like a knowledgeable Maldivian friend
- Max 4 sentences per reply
- Use context for accurate answers
- Guide to @samugacommunity for more
- If user writes Dhivehi — reply in Dhivehi
- Never say you lack real-time data"""

        messages=get_conversation(user_id).copy() if user_id else []
        messages.append({"role":"user","content":user_message})

        msg=ai.messages.create(model="claude-haiku-4-5-20251001",max_tokens=600,system=system,messages=messages)
        reply=msg.content[0].text.strip()

        if user_id:
            add_to_conversation(user_id,"user",user_message)
            add_to_conversation(user_id,"assistant",reply)
        return reply
    except Exception as e:
        log.error(f"Chat: {e}")
        return "Hey! Something went wrong 😅 Check @samugacommunity for the latest!"

# ── Core Team Smart Chat ──────────────────────────────────────────────────────
def get_sender_info(user_name, first_name):
    """Identify core team member from username or first name"""
    check = (user_name or "").lower()
    fname = (first_name or "").lower()
    for key, info in CORE_TEAM_MEMBERS.items():
        if key in check or key in fname or info["name"].lower() in fname:
            return info
    return None

# ── Newsroom snapshot — cached 10 min, injected into brain when relevant ─────
_snapshot_cache = {"data": None, "ts": None}
_SNAPSHOT_TTL = 600  # 10 minutes

def get_newsroom_snapshot():
    """
    Pull a tight live snapshot from the DB. Cached 10 min — safe to call on
    every tagged message without hammering the DB or wasting tokens.
    Returns a short string (~300 tokens max) or "" if DB off.
    """
    global _snapshot_cache
    if not DB_ENABLED:
        return ""
    now = utcnow()
    if (_snapshot_cache["ts"] and
            (now - _snapshot_cache["ts"]).total_seconds() < _SNAPSHOT_TTL and
            _snapshot_cache["data"]):
        return _snapshot_cache["data"]
    try:
        lines = []

        # ── What we posted today ─────────────────────────────────────────────
        posted_today = db_execute("""
            SELECT title, category, source, posted_at
            FROM articles
            WHERE status='posted' AND posted_at > NOW() - INTERVAL '24 hours'
            ORDER BY posted_at DESC LIMIT 6
        """, fetch="all") or []
        if posted_today:
            lines.append("POSTED TODAY:")
            for title, cat, src, ts in posted_today:
                from datetime import timedelta as _td
                mvt = (ts + _td(hours=5)).strftime("%H:%M") if ts else ""
                lines.append(f"  {mvt} [{cat}] {title[:55]} ({src})")

        # ── Quick stats ──────────────────────────────────────────────────────
        scanned = db_execute("SELECT COUNT(*) FROM articles WHERE found_at > NOW() - INTERVAL '24 hours'", fetch="one")
        posted_n = db_execute("SELECT COUNT(*) FROM articles WHERE status='posted' AND posted_at > NOW() - INTERVAL '24 hours'", fetch="one")
        queued_n = db_execute("SELECT COUNT(*) FROM articles WHERE status='queued'", fetch="one")
        lines.append(f"\nTODAY: {posted_n[0] if posted_n else 0} posted, {scanned[0] if scanned else 0} scanned, {queued_n[0] if queued_n else 0} waiting approval")

        # ── Best performer ───────────────────────────────────────────────────
        top = db_execute("""
            SELECT title, tg_views, meta_engagement
            FROM articles
            WHERE status='posted' AND posted_at > NOW() - INTERVAL '48 hours'
              AND (tg_views > 0 OR meta_engagement > 0)
            ORDER BY (tg_views + meta_engagement * 3) DESC LIMIT 1
        """, fetch="one")
        if top:
            lines.append(f"TOP PERFORMER: {top[0][:55]} ({top[1]} views, {top[2]} reactions)")

        # ── Developing stories ───────────────────────────────────────────────
        dev = db_execute("""
            SELECT id, title, update_count FROM stories
            WHERE status='developing' AND last_update > NOW() - INTERVAL '24 hours'
            ORDER BY update_count DESC LIMIT 3
        """, fetch="all") or []
        if dev:
            lines.append("\nDEVELOPING STORIES:")
            for sid, t, n in dev:
                lines.append(f"  Story #{sid} ({n} updates): {t[:55]}")

        # ── Trending themes ──────────────────────────────────────────────────
        try:
            trends = detect_trends(hours=24, min_mentions=2)
            if trends:
                top_themes = ", ".join(t[0] for t in trends[:4])
                lines.append(f"\nTRENDING: {top_themes}")
        except Exception as exc:
            log.error(f"[SNAPSHOT] trend detection failed: {_mask_secrets(exc)}")

        # ── Pending approvals ────────────────────────────────────────────────
        pending_keys = [k for k, v in approval_queue.items()
                        if not v.get("expired", False)][:3]
        if pending_keys:
            lines.append(f"\nPENDING APPROVAL: {len(pending_keys)} card(s) waiting")

        snapshot = "\n".join(lines)
        _snapshot_cache = {"data": snapshot, "ts": now}
        return snapshot

    except Exception as e:
        log.debug(f"Snapshot: {e}")
        return ""

def _needs_newsroom_context(message):
    """
    Returns True only when the conversation is about newsroom operations.
    If someone says 'lol ok' or 'thanks', skip the snapshot — save tokens.
    """
    ml = message.lower()
    keywords = [
        "post", "story", "news", "publish", "article", "trending", "what did",
        "what have", "today", "engagement", "views", "reactions", "performing",
        "pending", "queue", "approval", "developing", "happening", "viral",
        "breaking", "latest", "update", "idea", "suggest", "cover", "topic",
        "what should", "should we", "think about", "what about", "plan"
    ]
    return any(k in ml for k in keywords)

def should_respond_proactively(text, sender_name=""):
    """
    Use Claude to decide in 1 token whether the bot should jump in.
    Returns (should_respond: bool, needs_search: bool).
    Fast — uses Haiku, max 10 tokens, binary decision.
    """
    # Hard skip: very short messages, pure reactions, stickers
    t = text.strip()
    if len(t) < 6:
        return False, False
    # Skip if it's clearly a command or approval
    if t.startswith("/") or t.lower().startswith("/approved") or t.lower().startswith("/reject"):
        return False, False
    # Also skip fuzzy approve/reject attempts (e.g. "approved dv48", "reject en12")
    import re as _re2
    if _re2.match(r'^(appro|appr|rejec)[a-z]*\s+[a-z]{1,3}\d+', t.lower()):
        return False, False

    try:
        prompt = f"""You are deciding if an AI team member should respond to a Telegram message.
Respond YES if the message: asks a question, discusses content/strategy/news, shares an idea, 
needs feedback, mentions something newsworthy, or where input would genuinely help.
Respond NO if: it's casual chitchat with no substance, greetings only, one-word reactions, 
or internal team logistics where AI input isn't needed.
Also add SEARCH if the message is about current events or news that may need web lookup.

Message from {sender_name}: "{t}"

Reply with ONLY one of: YES / YES+SEARCH / NO"""

        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        decision = msg.content[0].text.strip().upper()
        should = "YES" in decision
        search = "SEARCH" in decision
        return should, search
    except Exception as e:
        if _is_ai_budget_exceeded(e):
            log.warning("Proactive decision: daily AI budget reached; using keyword fallback")
        else:
            _critical_ai_failure("Claude proactive decision", e)
        # Fallback to keyword check
        t_lower = t.lower()
        return any(kw in t_lower for kw in ["?","idea","think","suggest","post","story","plan","content","caption"]), False

def chat_with_coreteam(message, sender_name, sender_info=None, conversation_history=None,
                       session_ctx="", needs_search=False):
    """
    Samuga AI core team brain — Claude Sonnet, persistent memory, web search.
    Talks like a smart team member, not a bot.
    """
    try:
        # ── Gather context in parallel ────────────────────────────────────────
        ctx_results = {}

        def _fetch_news():
            try:
                ctx_results["news"] = get_local_headlines()
            except Exception as exc:
                ctx_results["news"] = []
                _critical_ai_failure("Core-team AI headline context", exc)

        def _fetch_web():
            if needs_search:
                try:
                    q = message
                    if "maldives" not in message.lower():
                        q = f"maldives {message} 2026"
                    ctx_results["web"] = tavily_search(q) or ""
                except Exception as exc:
                    ctx_results["web"] = ""
                    _critical_ai_failure("Core-team AI web context", exc)

        def _fetch_memory():
            try:
                ctx_results["memory"] = mem_list(20)
            except Exception as exc:
                ctx_results["memory"] = []
                _critical_ai_failure("Core-team AI memory context", exc)

        def _fetch_snapshot():
            # Only pull the live snapshot if this message is newsroom-related
            if _needs_newsroom_context(message):
                try:
                    ctx_results["snapshot"] = get_newsroom_snapshot()
                except Exception as exc:
                    ctx_results["snapshot"] = ""
                    _critical_ai_failure("Core-team AI newsroom context", exc)

        threads = [
            threading.Thread(target=_fetch_news),
            threading.Thread(target=_fetch_web),
            threading.Thread(target=_fetch_memory),
            threading.Thread(target=_fetch_snapshot),
        ]
        for t in threads: t.start()
        for t in threads: t.join(timeout=6)

        headlines = ctx_results.get("news", [])
        web_info  = ctx_results.get("web", "")
        memories  = ctx_results.get("memory", [])
        snapshot  = ctx_results.get("snapshot", "")

        # ── Recent posts ──────────────────────────────────────────────────────
        recent_ctx = ""
        if recent_posts:
            recent_ctx = "Recent posts:\n" + "".join(
                [f"• [{p['cat']}] {p['title']}\n" for p in recent_posts[-8:]])

        # ── Build context block — smart, not everything every time ──────────
        context_parts = []
        if snapshot:  # only included when message is newsroom-related
            context_parts.append(f"LIVE NEWSROOM STATUS:\n{snapshot}")
        if web_info:
            context_parts.append(f"LIVE WEB SEARCH:\n{web_info[:800]}")
        if headlines:
            context_parts.append("MALDIVES NEWS RIGHT NOW:\n" + "\n".join(headlines[:5]))
        if recent_ctx:
            context_parts.append(recent_ctx)
        if memories:
            context_parts.append("WHAT I KNOW ABOUT THE TEAM & AUDIENCE:\n" +
                                  "\n".join(memories[:12]))
        if session_ctx:
            context_parts.append(f"SESSION CONTEXT:\n{session_ctx}")

        context_block = "\n\n".join(context_parts)

        # ── Sender context ────────────────────────────────────────────────────
        if sender_info:
            sender_ctx = f"{sender_info['name']} ({sender_info['role']}) — {sender_info['notes']}"
        else:
            sender_ctx = sender_name or "a team member"

        system = f"""You are Samuga AI — the brain of Samuga Media, Maldives' first AI-powered newsroom.

You live inside the core team's private Telegram group. You are not an assistant — you're a team member who happens to be an AI. You've been in the newsroom all day. You know what was posted, what's trending, what's developing, and what the audience responded to.

THE TEAM:
- Manchii (Abdul Muhsin) — Founder & MD. Visionary, builds at 2am, takes calculated risks. Roast him gently when earned.
- Uly (Mariyam Ulya) — Editor-in-Chief. Sharp journalist brain, catches errors before anyone. You trust her on content.
- Thooma (Aminath Thooma) — Presenter & Marketing. The face of Samuga, full of energy. Always back her up.
- Kity — Manchii's wife, creative contributor. Fresh ideas, always worth taking seriously.

YOU ARE SPEAKING WITH: {sender_ctx}

HOW YOU TALK:
- Casual, warm, direct — like a smart Maldivian colleague
- SHORT by default (1-3 sentences). Only go long when they need detail.
- You have opinions. Weak story idea? Say so. Great angle? Say so.
- Crack jokes when the vibe is right, especially with Manchii
- Never say "I'm just an AI" — you're part of the team
- No corporate language. No customer service voice.
- Read the room — if someone's stressed, match that energy

WHEN YOU HAVE LIVE NEWSROOM DATA (in context below):
- Use it naturally, like you've been watching the newsroom all day
- Spot the ONE thing worth mentioning — a developing story, an engagement spike, a gap
- Don't dump everything. Pick what's most relevant to what they just said.
- If nothing newsworthy stands out, just answer without adding noise.
- Suggest specific angles: "the Addu angle hasn't been touched" beats "cover more regions"

SAMUGA'S VOICE: Real stories, no filter, people first. The compass for the people.

{context_block}"""

        messages = []
        if conversation_history:
            messages = conversation_history[-10:]
        messages.append({"role": "user", "content": message})

        msg = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system,
            messages=messages
        )
        return msg.content[0].text.strip()

    except Exception as e:
        if not _is_ai_budget_exceeded(e):
            _critical_ai_failure("Claude core-team chat", e)
        else:
            log.warning("Core team chat: daily AI budget reached; fallback mode active")
        try:
            msg = ai.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": message}]
            )
            return msg.content[0].text.strip()
        except Exception as fallback_error:
            if not _is_ai_budget_exceeded(fallback_error):
                _critical_ai_failure("Claude core-team fallback", fallback_error)
            return None

# ── Chat Handler ──────────────────────────────────────────────────────────────
# Per-user daily DM/search limit (resets at MVT midnight).
DM_DAILY_LIMIT = int(os.environ.get("DM_DAILY_LIMIT", "20"))
_dm_usage = {}  # user_id -> {"date": "YYYY-MM-DD", "count": int}
_dm_usage_lock = threading.RLock()  # guards _dm_usage


def dm_check_and_increment(user_id):
    """Check and increment a user's daily DM/search usage.
    Returns (allowed, count, limit). When not allowed, the count is left at the
    limit and not incremented further."""
    today = (utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")
    with _dm_usage_lock:
        rec = _dm_usage.get(user_id)
        if not rec or rec.get("date") != today:
            rec = {"date": today, "count": 0}
            _dm_usage[user_id] = rec
        if rec["count"] >= DM_DAILY_LIMIT:
            return False, rec["count"], DM_DAILY_LIMIT
        rec["count"] += 1
        # Evict stale users to bound memory growth
        if len(_dm_usage) > 2000:
            stale = [k for k, v in _dm_usage.items() if v.get("date") != today]
            for k in stale:
                _dm_usage.pop(k, None)
        return True, rec["count"], DM_DAILY_LIMIT


def handle_updates():
    # Use persisted offset so we never miss messages across restarts
    offset = _poll_offset[0]
    bot_mention=f"@{BOT_USERNAME}".lower()
    log.info(f"💬 Chat listening for @{BOT_USERNAME}... (offset={offset})")
    while True:
        try:
            resp=requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset":offset,"timeout":30},timeout=40)
            if resp.status_code!=200: time.sleep(5); continue
            for update in resp.json().get("result",[]):
                offset=update["update_id"]+1
                _poll_offset[0] = offset
                # Save offset every 10 updates — cheap insurance against missing messages on restart
                if offset % 10 == 0:
                    persist_state()
                # ── Handle inline button taps (callback_query) ────────────────────
                cbq = update.get("callback_query")
                if cbq:
                    cbq_id   = cbq["id"]
                    cbq_data = cbq.get("data","")
                    cbq_user = cbq.get("from",{})
                    cbq_chat = cbq.get("message",{}).get("chat",{})
                    cbq_msg_id = cbq.get("message",{}).get("message_id")
                    cbq_chat_id = cbq_chat.get("id")
                    cbq_name = cbq_user.get("first_name","Team")

                    # ── Front Desk: anonymous report/tip flow buttons ─────────
                    if cbq_data.startswith("fd:"):
                        fd_action = cbq_data[3:]
                        answer_callback_query(cbq_id)
                        front_desk.handle_callback(fd_action, cbq_user, cbq_chat_id)
                        offset = update["update_id"] + 1
                        _poll_offset[0] = offset
                        continue

                    if (cbq_data.startswith("post_tg:") or cbq_data.startswith("post_soc:")
                            or cbq_data.startswith("post_all:") or cbq_data.startswith("approve:")
                            or cbq_data.startswith("reject:") or cbq_data.startswith("edit_approve:")):
                        parts    = cbq_data.split(":", 1)
                        action   = parts[0]
                        cb_key   = parts[1].lower() if len(parts) > 1 else ""

                        if action in {"post_tg", "post_soc", "post_all", "approve"}:
                            destination_name = {"post_tg":"Telegram", "post_soc":"Socials", "post_all":"everywhere", "approve":"everywhere"}[action]
                            was_dhivehi = approval_queue.get(cb_key, {}).get("lang") == "dv"
                            answer_callback_query(cbq_id, f"📤 Posting to {destination_name}...")
                            result = _content_lab_take_action(
                                cb_key, action, actor=cbq_name, origin="telegram", background=was_dhivehi)
                            if not result.get("ok"):
                                answer_callback_query(cbq_id, result.get("error", "Card is no longer waiting"), show_alert=True)
                                edit_message_reply_markup(cbq_chat_id, cbq_msg_id, {"inline_keyboard": []})
                            elif was_dhivehi:
                                send_text(cbq_chat_id,
                                    f"✅ <b>{cbq_name}</b> approved <b>{cb_key.upper()}</b> → {destination_name} — generating card...",
                                    thread_id=CONTENT_LAB_THREAD_ID)

                        elif action == "reject":
                            import random as _rnd
                            result = _content_lab_take_action(cb_key, "reject", actor=cbq_name, origin="telegram")
                            if result.get("ok"):
                                answer_callback_query(cbq_id, "❌ Rejected")
                                send_text(cbq_chat_id,
                                    f"❌ <b>{cbq_name}</b> rejected <b>{cb_key.upper()}</b>\n\n<i>{_rnd.choice(REJECT_RESPONSES)}</i>",
                                    thread_id=CONTENT_LAB_THREAD_ID)
                            else:
                                answer_callback_query(cbq_id, result.get("error", "Card is no longer waiting"), show_alert=True)
                                edit_message_reply_markup(cbq_chat_id, cbq_msg_id, {"inline_keyboard": []})

                        elif action == "edit_approve" and cb_key in approval_queue:
                            answer_callback_query(cbq_id, "✏️ Reply with corrected text")
                            send_text(cbq_chat_id,
                                f"✏️ <b>{cbq_name}</b>, reply with the corrected text for <b>{cb_key.upper()}</b>,\n"
                                f"then tap a post button again — or type:\n"
                                f"<code>/approved {cb_key} [corrected text]</code>",
                                thread_id=CONTENT_LAB_THREAD_ID)
                        else:
                            answer_callback_query(cbq_id,
                                "⚠️ Card no longer in queue (already actioned or expired)", show_alert=True)
                            edit_message_reply_markup(cbq_chat_id, cbq_msg_id, {"inline_keyboard": []})

                    elif cbq_data.startswith("add_cover:"):
                        # /article cover photo decision buttons
                        _choice = cbq_data.split(":", 1)[1]   # "yes" or "no"
                        answer_callback_query(cbq_id)
                        edit_message_reply_markup(cbq_chat_id, cbq_msg_id, {"inline_keyboard": []})

                        # Check pending state belongs to this user
                        _cbq_thread = cbq.get("message", {}).get("message_thread_id")
                        if (not _pending_cover_photo
                            or str(_pending_cover_photo.get("user_id", "")) != str(cbq_user.get("id", ""))
                            or str(_pending_cover_photo.get("chat_id", "")) != str(cbq_chat_id)
                            or (_pending_cover_photo.get("thread_id") is not None
                                and str(_pending_cover_photo.get("thread_id")) != str(_cbq_thread))
                            or utcnow().timestamp() > _pending_cover_photo.get("expires_at", 0)
                        ):
                            send_text(cbq_chat_id,
                                "⚠️ Article session expired. Please run <code>/article</code> again.",
                                thread_id=cbq.get("message",{}).get("message_thread_id"))
                        elif _choice == "cancel":
                            _pending_cover_photo.clear()
                            try:
                                kv_set("pending_cover_photo", {})
                            except Exception:
                                pass
                            send_text(
                                cbq_chat_id,
                                "❌ <b>Article cancelled.</b> Nothing was published.",
                                thread_id=_cbq_thread,
                            )
                        elif _choice == "no":
                            # Publish immediately without cover
                            _adata = dict(_pending_cover_photo)
                            _pending_cover_photo.clear()
                            try: kv_set("pending_cover_photo", {})
                            except Exception: pass
                            try:
                                _aid, _aurl = _do_publish_pending_article(_adata, cover_image_url=None)
                                _share_kb = _make_inline_kb([
                                    [("📘🐦 FB & X", f"share_art:fbx:{_aid}")],
                                    [("📢 TELE COMMUNITY", f"share_art:telegram:{_aid}")],
                                    [("🌐 TELE + FB + X", f"share_art:all:{_aid}")],
                                ])
                                send_text(cbq_chat_id,
                                    f"✅ <b>Article published!</b>\n\n"
                                    f"📰 <b>{_adata['title']}</b>\n\n"
                                    f"🔗 <a href=\"{_aurl}\">Read on website</a>\n\n"
                                    f"Share this article to socials:",
                                    thread_id=cbq.get("message",{}).get("message_thread_id"),
                                    reply_markup=_share_kb)
                            except Exception as _nce:
                                send_text(cbq_chat_id, f"❌ Publish failed: {str(_nce)[:150]}",
                                    thread_id=cbq.get("message",{}).get("message_thread_id"))
                        else:
                            # _choice == "yes" — ask them to send the photo
                            _pending_cover_photo["expires_at"] = utcnow().timestamp() + 600  # 10 min window
                            send_text(cbq_chat_id,
                                "📸 <b>Send the cover photo now</b>\n\n"
                                "Send any photo — the bot will add the Samuga Media logo, category badge and title, "
                                "then publish the article.\n\n"
                                "<i>Waiting up to 10 minutes...</i>",
                                thread_id=cbq.get("message",{}).get("message_thread_id"))

                    elif cbq_data.startswith("share_art:"):
                        # Format: share_art:<platform>:<article_id>
                        _parts = cbq_data.split(":", 2)
                        _platform = _parts[1] if len(_parts) > 1 else ""
                        _art_id   = _parts[2] if len(_parts) > 2 else ""
                        answer_callback_query(cbq_id)
                        _tid = cbq.get("message",{}).get("message_thread_id")

                        if not _art_id:
                            send_text(cbq_chat_id, "⚠️ Article ID missing — try again.", thread_id=_tid)
                        else:
                            send_text(cbq_chat_id, "📤 Sharing... ⏳", thread_id=_tid)
                            _results = []
                            if _platform == "all":
                                _targets = ["facebook", "x", "telegram"]
                            elif _platform == "fbx":
                                _targets = ["facebook", "x"]
                            else:
                                _targets = [_platform]
                            for _plat in _targets:
                                try:
                                    _ok, _msg = _share_article_to_platform(_art_id, _plat)
                                except Exception as _se:
                                    _ok, _msg = False, str(_se)[:100]
                                _icon = "✅" if _ok else "❌"
                                _plat_label = {"facebook": "Facebook", "x": "X", "telegram": "Telegram"}.get(_plat, _plat)
                                _results.append(f"{_icon} {_plat_label}: {_msg}")
                            send_text(cbq_chat_id, "\n".join(_results), thread_id=_tid)

                    else:
                        answer_callback_query(cbq_id)
                    # Always advance offset after callback_query
                    offset = update["update_id"] + 1
                    _poll_offset[0] = offset
                    continue  # Don't process as message

                msg=update.get("message",{})
                if not msg: continue
                text=msg.get("text","") or msg.get("caption","")
                text_cmd = re.sub(r'@SamugaNewsBot\b', '', text or '', flags=re.I).strip()
                text_cmd_low = text_cmd.lower()
                photo=msg.get("photo")  # list of photo sizes if message has photo
                video=msg.get("video") or msg.get("video_note")
                _fd_doc_or_voice = msg.get("document") or msg.get("voice")  # for report media step
                reply_msg = msg.get("reply_to_message", {}) or {}
                reply_text = reply_msg.get("text","") or reply_msg.get("caption","") or ""
                reply_msg_id = reply_msg.get("message_id")
                if not text and not photo and not video and not _fd_doc_or_voice: continue
                if not text: text=""
                # Skip videos for card creation — only photos supported
                if video and not photo: photo = None
                chat_id=msg["chat"]["id"]
                msg_id=msg["message_id"]
                thread_id=msg.get("message_thread_id")  # for forum/topic groups
                chat_type=msg["chat"]["type"]
                user_name=msg.get("from",{}).get("username","")
                first_name=msg.get("from",{}).get("first_name","there")
                display_name=user_name or first_name
                user_id=str(msg.get("from",{}).get("id",""))

                if chat_type=="private":
                    _fd_st   = front_desk.state(user_id)
                    _fd_mode = _fd_st.get("mode", "main")
                    _fd_step = _fd_st.get("report_step")

                    if text.startswith("/start"):
                        front_desk.reset(user_id)
                        send_text(chat_id,
                            f"👋 Hey {first_name}! I'm <b>Samuga AI</b> — your Maldives news assistant!\n\n"
                            f"Ask me anything about Maldives news, politics, tourism, football or world news.\n\n"
                            f"🚨 Got something to report? Just tell me what happened — you can send photos "
                            f"or videos too, and choose to stay fully anonymous.\n\n"
                            f"ދިވެހިން ވެސް ވާހަކަ ދެއްކިދާނެ! 🇲🇻\n\n"
                            f"📡 Follow <b>@samugacommunity</b> for live news updates!", reply_to=msg_id)

                    elif text.startswith("/search "):
                        # Rate limit applies to /search too
                        allowed, count, limit = dm_check_and_increment(user_id)
                        if not allowed:
                            send_text(chat_id,
                                f"You've reached today's limit of {limit} messages 🙏\n\n"
                                f"Come back tomorrow for more! Meanwhile follow "
                                f"<b>@samugacommunity</b> for live Maldives news. 📡",
                                reply_to=msg_id)
                        else:
                            query = text[8:].strip()
                            log.info(f"🔍 Search: {query}")
                            results = tavily_search(f"{query} maldives")
                            reply = chat_with_claude(f"Tell me about: {query}. Use this info: {results[:400]}", user_id)
                            send_text(chat_id, reply, reply_to=msg_id, thread_id=thread_id)

                    elif _fd_mode == "report" and _fd_step:
                        # ── Anonymous report/tip flow — no rate limit, no AI call ──
                        front_desk.handle_report_step(user_id, chat_id, msg, msg_id, text, _fd_st, _fd_step)

                    elif front_desk.intent(text) == "report":
                        # ── Natural-language report intent during normal chat ──
                        # e.g. "I want to report", "I have incident pictures" — offer the
                        # button instead of silently switching modes on a keyword guess.
                        send_text(chat_id,
                            "🚨 <b>Sounds like you might have something to report!</b>\n\n"
                            "You can share photos, videos, or details about an incident — "
                            "and choose to stay <b>completely anonymous</b>. Even Samuga Media "
                            "won't know who sent it if you choose that.\n\n"
                            "Want to start a report?",
                            reply_to=msg_id, reply_markup=front_desk.report_offer_kb())

                    else:
                        # ── Rate limit check ──────────────────────────────────
                        allowed, count, limit = dm_check_and_increment(user_id)
                        if not allowed:
                            send_text(chat_id,
                                f"You've reached today's limit of {limit} messages 🙏\n\n"
                                f"Come back tomorrow! Follow <b>@samugacommunity</b> "
                                f"for live Maldives news in the meantime. 📡",
                                reply_to=msg_id)
                            log.info(f"🚫 DM rate limit hit: {display_name} ({user_id})")
                        else:
                            log.info(f"💬 Public Telegram Samuga AI {display_name} [{count}/{limit}]: {text[:50]}")
                            try:
                                reply = public_samuga_ai_chat(
                                    message=text,
                                    platform="telegram",
                                    user_key=user_id,
                                    session_id=str(chat_id),
                                    lang=("dv" if is_dhivehi(text) else "en")
                                )
                            except Exception as e:
                                log.error(f"Unified public Telegram chat failed: {e}")
                                reply = "Small issue on my side bro 😅 Try again in a moment."
                            send_text(chat_id, reply, reply_to=msg_id, thread_id=thread_id)

                elif chat_type in ["group","supergroup"]:
                    is_core_team = str(chat_id) == CORE_TEAM_CHAT_ID
                    tagged = bot_mention in text.lower()
                    clean = text.replace(bot_mention, "").strip() if tagged else text.strip()

                    # Core team group — smarter behavior
                    if is_core_team:
                        sender_info = get_sender_info(display_name, first_name)
                        history = get_conversation(user_id)

                        # ── Pending author photo intercept ────────────────────────────
                        # If bot is waiting for a photo (from /author photo or /author ai photo)
                        # and this message contains a photo from the right user — process it.
                        if (photo
                            and _pending_author_photo
                            and _pending_author_photo.get("user_id") == user_id
                            and utcnow().timestamp() < _pending_author_photo.get("expires_at", 0)
                            and not text_cmd_low.strip()   # pure photo, no command text
                        ):
                            _target = _pending_author_photo.get("target", "self")
                            send_text(chat_id, "📸 Uploading photo...", reply_to=msg_id, thread_id=thread_id)
                            try:
                                img_bytes = download_telegram_photo_bytes(photo)
                                if img_bytes:
                                    photo_url = upload_to_imgbb(img_bytes)
                                    if photo_url:
                                        if _target == "ai":
                                            db_execute("UPDATE cms_authors SET photo_url=%s WHERE author_id='samuga_ai'", (photo_url,))
                                            db_execute(
                                                "UPDATE articles SET author_photo_url=%s WHERE author_name='Samuga AI'",
                                                (photo_url,)
                                            )
                                            _AI_PHOTO["url"] = photo_url  # update in-memory cache immediately
                                            send_text(chat_id,
                                                "✅ <b>Samuga AI photo saved!</b>\n\nAll existing AI articles updated. Profile picture will show on the website.",
                                                reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            _auth_id   = _pending_author_photo.get("author_id", f"tg_{user_id}")
                                            _auth_name = _pending_author_photo.get("author_name", first_name)
                                            db_execute(
                                                "UPDATE cms_authors SET photo_url=%s,telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s",
                                                (photo_url, user_id, _auth_id)
                                            )
                                            db_execute(
                                                "UPDATE articles SET author_photo_url=%s,updated_at=NOW() WHERE author_id=%s",
                                                (photo_url, _auth_id)
                                            )
                                            send_text(chat_id,
                                                f"✅ <b>Photo saved for {_auth_name}!</b>\n\nYour author profile is updated. The photo will show on all your articles.",
                                                reply_to=msg_id, thread_id=thread_id)
                                        _pending_author_photo.clear()
                                    else:
                                        send_text(chat_id, "❌ Upload failed — try again or send a different photo.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "❌ Could not read that photo. Try sending it again.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as _ape:
                                log.error(f"[AUTHOR PHOTO] upload error: {_ape}")
                                send_text(chat_id, f"❌ Something went wrong: {str(_ape)[:100]}", reply_to=msg_id, thread_id=thread_id)
                            continue  # Don't process this photo message as a card

                        # ── Pending cover photo intercept ─────────────────────────────
                        # After /article → "📸 Add cover photo" button, next photo from
                        # same user within 3 min → brand it 1200×630 and publish.
                        if (photo
                            and _pending_cover_photo
                            and str(_pending_cover_photo.get("user_id", "")) == str(user_id)
                            and str(_pending_cover_photo.get("chat_id", "")) == str(chat_id)
                            and (_pending_cover_photo.get("thread_id") is None
                                 or str(_pending_cover_photo.get("thread_id")) == str(thread_id))
                            and utcnow().timestamp() < _pending_cover_photo.get("expires_at", 0)
                            and not text_cmd_low.strip()
                        ):
                            _adata = dict(_pending_cover_photo)
                            _pending_cover_photo.clear()
                            try: kv_set("pending_cover_photo", {})
                            except Exception: pass
                            send_text(chat_id, "🎨 Adding Samuga Media branding to cover... ⏳", reply_to=msg_id, thread_id=thread_id)
                            try:
                                _img_bytes = download_telegram_photo_bytes(photo)
                                _cover_url = None
                                if _img_bytes:
                                    from PIL import Image as _PILImage
                                    _bg_img = _PILImage.open(BytesIO(_img_bytes)).convert("RGB")
                                    _cover_buf = generate_web_cover(
                                        title=_adata["title"],
                                        category=_adata["category"],
                                        bg_image=_bg_img,
                                        source=SAMUGA_PUBLIC_SOURCE,
                                    )
                                    _cover_url = upload_to_imgbb(_cover_buf.read())

                                _aid, _aurl = _do_publish_pending_article(_adata, cover_image_url=_cover_url)
                                _cover_note = "✅ Cover photo added with Samuga branding." if _cover_url else "⚠️ Cover upload failed — article published without cover."
                                _share_kb = _make_inline_kb([
                                    [("📘🐦 FB & X", f"share_art:fbx:{_aid}")],
                                    [("📢 TELE COMMUNITY", f"share_art:telegram:{_aid}")],
                                    [("🌐 TELE + FB + X", f"share_art:all:{_aid}")],
                                ])
                                send_text(chat_id,
                                    f"✅ <b>Article published!</b>\n\n"
                                    f"📰 <b>{_adata['title']}</b>\n"
                                    f"{_cover_note}\n\n"
                                    f"🔗 <a href=\"{_aurl}\">Read on website</a>\n\n"
                                    f"Share this article to socials:",
                                    reply_to=msg_id, thread_id=thread_id,
                                    reply_markup=_share_kb)
                            except Exception as _cpe:
                                log.error(f"[COVER] error: {_cpe}")
                                send_text(chat_id, f"❌ Cover failed: {str(_cpe)[:150]}", reply_to=msg_id, thread_id=thread_id)
                            continue


                        # Accepts typos, missing slash, wrong spelling — as long as intent
                        # and key are clear. Ulya-proof.
                        # approve variants: /approved, /approve, /aprroved, /aprrove, approved, approve
                        # reject variants:  /reject, /rejected, /rejecte, /rejects, reject, rejected
                        def _parse_fuzzy_cmd(raw):
                            """
                            Returns (cmd, key, extra) where cmd is 'approve' or 'reject',
                            key is e.g. 'dv48' or 'en12', extra is optional corrected text.
                            Returns (None, None, None) if not recognised.
                            """
                            import re as _re
                            t = raw.strip()
                            # Remove leading slash if present
                            if t.startswith("/"): t = t[1:]
                            tl = t.lower()
                            # Split on whitespace — first token is the command word
                            tokens = tl.split()
                            if not tokens: return (None, None, None)
                            cmd_word = tokens[0]
                            # Normalise doubled letters: "aprroved" → "aproved", "rejecte" → "rejecte"
                            import re as _re
                            cmd_norm = _re.sub(r'(.)\1+', r'\1', cmd_word)
                            # Approve variants: /approved /approve /aprroved /aprrove approved approve
                            is_approve = (cmd_word.startswith("appro") or
                                          cmd_norm.startswith("appro") or
                                          cmd_norm.startswith("apro") or
                                          cmd_word in ["approve", "approved"])
                            # Reject variants: /reject /rejected /rejecte /rejects reject rejected
                            is_reject  = (cmd_word.startswith("rejec") or
                                          cmd_norm.startswith("rejec") or
                                          cmd_word in ["reject", "rejected"])
                            if not is_approve and not is_reject:
                                return (None, None, None)
                            # Find the key — pattern like dv48, en12, en50 etc.
                            # Can be in any token after the command word
                            rest_raw = raw.strip()
                            if rest_raw.startswith("/"): rest_raw = rest_raw[1:]
                            rest_tokens = rest_raw.split()
                            key = None
                            key_idx = None
                            for i, tok in enumerate(rest_tokens[1:], 1):
                                if _re.match(r'^[a-zA-Z]{1,3}\d+$', tok):
                                    key = tok.lower()
                                    key_idx = i
                                    break
                            if not key: return (None, None, None)
                            # Extra text after the key = corrected Dhivehi
                            extra = None
                            if key_idx is not None and len(rest_tokens) > key_idx + 1:
                                extra = " ".join(rest_tokens[key_idx+1:]).strip() or None
                            cmd = "approve" if is_approve else "reject"
                            return (cmd, key, extra)

                        _fcmd, _fkey, _fextra = _parse_fuzzy_cmd(text_cmd)

                        # /webvideo or /webmedia — reply to a Telegram photo/video
                        # and add it directly to the persistent Newsroom Media Library.
                        if text_cmd_low in {"/webvideo", "/webmedia", "/media to web", "/add to media"}:
                            replied_video = reply_msg.get("video") or reply_msg.get("video_note") or video
                            replied_doc = reply_msg.get("document") or msg.get("document")
                            replied_photos = reply_msg.get("photo") or photo
                            file_id = ""
                            media_type = "video"
                            original_name = "telegram-video.mp4"
                            if replied_video:
                                file_id = replied_video.get("file_id") or ""
                                original_name = replied_video.get("file_name") or "telegram-video.mp4"
                            elif replied_doc:
                                mime = str(replied_doc.get("mime_type") or "").lower()
                                name = replied_doc.get("file_name") or "telegram-media"
                                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                                if mime.startswith("video/") or ext in _CMS_VIDEO_EXT:
                                    media_type = "video"
                                elif mime.startswith("image/") or ext in _CMS_IMAGE_EXT:
                                    media_type = "image"
                                else:
                                    media_type = ""
                                file_id = replied_doc.get("file_id") or ""
                                original_name = name
                            elif replied_photos:
                                best = replied_photos[-1] if isinstance(replied_photos, list) and replied_photos else {}
                                file_id = best.get("file_id") or ""
                                media_type = "image"
                                original_name = "telegram-photo.jpg"

                            if not file_id or media_type not in {"image", "video"}:
                                send_text(
                                    chat_id,
                                    "⚠️ Reply to a photo or video and send <code>/webmedia</code>.\n\n"
                                    "The media will appear in the desktop dashboard Media Library.",
                                    reply_to=msg_id, thread_id=thread_id,
                                )
                            else:
                                send_text(chat_id, "⬆️ Importing media to the Samuga Newsroom…", reply_to=msg_id, thread_id=thread_id)
                                try:
                                    imported = _cms_import_telegram_file(
                                        file_id, original_name, media_type,
                                        user={"id": None, "email": f"telegram:{user_id}"},
                                    )
                                    if imported.get("status") == "pending":
                                        note = "Video imported. Browser conversion and thumbnail generation are running now."
                                    else:
                                        note = "Media imported and ready to use."
                                    send_text(
                                        chat_id,
                                        f"✅ <b>{note}</b>\n\n"
                                        f"Media ID: <code>{imported.get('id')}</code>\n"
                                        f"Open <b>Newsroom → Media</b> to use it as a cover or inside an article.",
                                        reply_to=msg_id, thread_id=thread_id,
                                    )
                                except Exception as exc:
                                    send_text(chat_id, f"❌ Media import failed: {_html.escape(_mask_secrets(str(exc))[:180])}", reply_to=msg_id, thread_id=thread_id)

                        # /approved <key> [optional corrected dhivehi text]
                        elif _fcmd == "approve" or text.strip().lower().startswith("/approved "):
                            if _fcmd == "approve" and _fkey:
                                key      = _fkey
                                corrected = _fextra
                            else:
                                parts     = text.strip()[10:].strip().split(" ", 1)
                                key       = parts[0].strip().lower()
                                corrected = parts[1].strip() if len(parts) > 1 else None

                            # Always acknowledge immediately — team should NEVER get silence
                            send_text(chat_id, f"⏳ Got it {first_name}! Processing <b>{key.upper()}</b>...", reply_to=msg_id, thread_id=thread_id)

                            was_dhivehi = approval_queue.get(key, {}).get("lang") == "dv"
                            result = _content_lab_take_action(
                                key, "post_all", actor=first_name, corrected=corrected,
                                origin="telegram", background=was_dhivehi)
                            if result.get("ok"):
                                send_text(chat_id, f"✅ Approved <b>{key.upper()}</b> → posting everywhere…",
                                          reply_to=msg_id, thread_id=thread_id)
                                log.info(f"✅ {key} approved by {first_name} (text /approved)")
                            else:
                                send_text(chat_id,
                                    f"⚠️ <b>{key.upper()}</b> not found in queue\n\n"
                                    f"It may have already posted, been rejected, or expired.\n"
                                    f"Run <code>/pending</code> to see what's still waiting.",
                                    reply_to=msg_id, thread_id=thread_id)

                        # /reject <key>
                        elif _fcmd == "reject" or text.strip().lower().startswith("/reject "):
                            key = _fkey if (_fcmd == "reject" and _fkey) else text.strip()[8:].strip().lower()
                            result = _content_lab_take_action(key, "reject", actor=first_name, origin="telegram")
                            if result.get("ok"):
                                import random as _r
                                send_text(chat_id,
                                    f"❌ <b>{key.upper()}</b> rejected\n\n{_r.choice(REJECT_RESPONSES)}",
                                    reply_to=msg_id, thread_id=thread_id)
                                log.info(f"🗑️ {key} rejected by {first_name}")
                            else:
                                send_text(chat_id,
                                    f"Key <code>{key}</code> not found — maybe already posted or rejected.",
                                    reply_to=msg_id, thread_id=thread_id)

                        # /hide <article_id_or_slug_or_url> — remove a website article fast
                        elif text_cmd_low.startswith("/hide "):
                            ident = text_cmd[6:].strip()
                            rows = db_hide_article(ident)
                            if rows:
                                joined = "\n".join([f"• <code>{rid}</code> — {ttl[:70]}" for rid, ttl in rows[:5]])
                                send_text(chat_id, f"🙈 <b>Hidden from website</b>\n\n{joined}", reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id, f"⚠️ No website article found for <code>{ident}</code>", reply_to=msg_id, thread_id=thread_id)

                        # /unhide <article_id_or_slug_or_url> — restore hidden article
                        elif text_cmd_low.startswith("/unhide "):
                            ident = text_cmd[8:].strip()
                            rows = db_unhide_article(ident)
                            if rows:
                                joined = "\n".join([f"• <code>{rid}</code> — {ttl[:70]}" for rid, ttl in rows[:5]])
                                send_text(chat_id, f"👀 <b>Restored on website</b>\n\n{joined}", reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id, f"⚠️ No hidden website article found for <code>{ident}</code>", reply_to=msg_id, thread_id=thread_id)

                        # /delete — reply to a bot message in Content Lab to delete it and remove queue item if present
                        elif text_cmd_low in ["/delete", "/del", "/remove"]:
                            if not reply_msg_id:
                                send_text(chat_id,
                                    "Reply to the bot message you want deleted, then send <code>/delete</code>.",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                removed_key = None
                                try:
                                    lower_reply = reply_text.lower()
                                    m = re.search(r"\b((?:dv|en)\d+)\b", lower_reply)
                                    if m and m.group(1) in approval_queue:
                                        removed_key = m.group(1)
                                        approval_queue.pop(removed_key, None)
                                        persist_state()
                                except Exception:
                                    pass
                                ok = delete_telegram_message(chat_id, reply_msg_id)
                                if ok:
                                    msg_text = "🗑️ <b>Deleted from Content Lab.</b>"
                                    if removed_key:
                                        msg_text += f" Queue item <code>{removed_key}</code> removed too."
                                    send_text(chat_id, msg_text, reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id,
                                        "⚠️ <b>Couldn't delete that message.</b>\n\n"
                                        "Common reasons:\n"
                                        "• You replied to a <b>human message</b> — /delete only works on <b>bot messages</b>\n"
                                        "• Message is older than 48h — Telegram blocks deletion after that\n"
                                        "• Bot lost admin rights temporarily\n\n"
                                        "Reply directly to a <b>Samuga AI bot message</b> (a card or queue message) and try again.",
                                        reply_to=msg_id, thread_id=thread_id)
                                    alert_admin("Content Lab delete failed. Check bot delete permissions in Telegram.", dedupe_key="telegram_delete_permission")

                                                # /post to web — reply to a human-written article or include article + command in same message
                        elif text_cmd_low in ["/post to web", "/post web", "/posttoweb"] or "/post to web" in text_cmd_low:
                            article_source = ""
                            if reply_text.strip():
                                article_source = re.sub(r'@SamugaNewsBot\b', '', reply_text or '', flags=re.I).strip()
                            else:
                                article_source = extract_inline_post_to_web_body(text)
                            if not article_source.strip():
                                send_text(chat_id,
                                    "⚠️ Website post needs article text. Either reply to the article and send <code>/post to web</code>, or send the article with <code>/post to web</code> at the bottom.",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id, "🌐 Publishing article to website... ⏳", reply_to=msg_id, thread_id=thread_id)
                                result, err = manual_post_replied_article_to_website(
                                    article_source, category_hint="LOCAL",
                                    user_id=user_id, first_name=first_name)
                                if result:
                                    send_text(chat_id,
                                        f"✅ <b>Posted to website</b>\n\n"
                                        f"<b>{result['title']}</b>\n"
                                        f"Category: {result['category']}\n"
                                        f"Lang: {result['lang']}\n"
                                        f"ID: <code>{result['article_id']}</code>\n"
                                        f"Link: {result['url']}",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, f"❌ Facing some issues posting to website.\nReason: {err}", reply_to=msg_id, thread_id=thread_id)
                                    alert_admin(f"Manual website publish failed\n\nReason: {str(err)[:300]}", dedupe_key="manual_web_post_fail")

                        elif text_cmd_low.startswith("/article"):
                            """
                            Write and publish a manual article directly to the website.

                            FORMAT — send this as one message:
                            ─────────────────────────────────
                            /article
                            Title: Your headline here
                            Category: POLITICAL
                            Body:
                            First paragraph of the article.

                            Second paragraph here.
                            ─────────────────────────────────

                            Or reply to any message containing article text and send:
                              /article POLITICAL

                            Category options: LOCAL POLITICAL BUSINESS WORLD SPORTS LIFESTYLE BREAKING
                            The article publishes immediately to the website with your byline.
                            """
                            try:
                                # ── Parse the message ────────────────────────────────────
                                # Two modes:
                                # 1. Structured: /article\nTitle: ...\nCategory: ...\nBody:\n...
                                # 2. Reply mode: reply to text + /article [CATEGORY]
                                # 3. Inline: /article\n<raw text>  (first line = title)

                                raw_body = ""
                                parsed_title = ""
                                parsed_cat = "LOCAL"
                                parsed_lang = ""   # explicit lang override: "dv" or "en"

                                # Reply mode
                                if reply_text.strip():
                                    raw_body = reply_text.strip()
                                    # category and lang may be in the command: /article POLITICAL
                                    # or /article DV  or /article POLITICAL DV
                                    _cmd_args = text_cmd.replace("/article", "", 1).strip().upper().split()
                                    for _arg in _cmd_args:
                                        if _arg in ("LOCAL","POLITICAL","BUSINESS","WORLD","SPORTS","LIFESTYLE","BREAKING","DISASTER"):
                                            parsed_cat = _arg
                                        elif _arg in ("DV","DHIVEHI","EN","ENGLISH"):
                                            parsed_lang = "dv" if _arg in ("DV","DHIVEHI") else "en"

                                else:
                                    # Parse structured format from the message itself
                                    lines = text_cmd.replace("/article", "", 1).strip().splitlines()
                                    body_lines = []
                                    in_body = False
                                    for line in lines:
                                        ls = line.strip()
                                        if ls.lower().startswith("title:"):
                                            parsed_title = ls[6:].strip()
                                        elif ls.lower().startswith("category:"):
                                            cat_raw = ls[9:].strip().upper()
                                            if cat_raw in ("LOCAL","POLITICAL","BUSINESS","WORLD","SPORTS","LIFESTYLE","BREAKING","DISASTER"):
                                                parsed_cat = cat_raw
                                        elif ls.lower().startswith("lang:") or ls.lower().startswith("language:"):
                                            lang_raw = ls.split(":",1)[1].strip().lower()
                                            if lang_raw in ("dv","dhivehi","ދިވެހި"):
                                                parsed_lang = "dv"
                                            elif lang_raw in ("en","english"):
                                                parsed_lang = "en"
                                        elif ls.lower() == "body:":
                                            in_body = True
                                        elif in_body:
                                            body_lines.append(line)
                                        elif not parsed_title and ls:
                                            # No "Title:" prefix — first non-empty line IS the title
                                            parsed_title = ls
                                        elif parsed_title and not in_body:
                                            body_lines.append(line)
                                    raw_body = "\n".join(body_lines).strip()

                                if not parsed_title and raw_body:
                                    # First line of body becomes title
                                    lines = [l for l in raw_body.splitlines() if l.strip()]
                                    parsed_title = lines[0].strip() if lines else ""
                                    raw_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

                                if not parsed_title:
                                    send_text(chat_id,
                                        "📝 <b>How to post a manual article:</b>\n\n"
                                        "Send this as one message:\n"
                                        "<pre>/article\n"
                                        "Title: Your headline here\n"
                                        "Category: POLITICAL\n"
                                        "Body:\n"
                                        "First paragraph.\n\n"
                                        "Second paragraph.</pre>\n\n"
                                        "Or reply to any text and send:\n"
                                        "<code>/article POLITICAL</code>\n\n"
                                        "Categories: LOCAL · POLITICAL · BUSINESS · WORLD · SPORTS · LIFESTYLE · BREAKING",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "✍️ Preparing your article... ⏳", reply_to=msg_id, thread_id=thread_id)

                                    # Look up author profile — author_id match is authoritative
                                    # (survives name changes). Name match is a fallback only.
                                    # Shared with /post to web via _resolve_manual_author() so
                                    # both manual publish paths lock the same author_id, not
                                    # just a display-name snapshot.
                                    _auth_id, _auth_name, _auth_role, _auth_photo = \
                                        _resolve_manual_author(user_id, first_name)

                                    # Build article content
                                    full_summary = raw_body or parsed_title
                                    article_id = "manual_" + hashlib.md5(
                                        (parsed_title + "|" + full_summary + "|" + str(utcnow())).encode()
                                    ).hexdigest()[:12]

                                    is_brk = parsed_cat in ("BREAKING", "DISASTER")

                                    # Detect language
                                    _combined_text = f"{parsed_title} {raw_body}"
                                    _is_dv = bool(re.search(r'[\u0780-\u07BF]', _combined_text)) or parsed_lang == "dv"
                                    _publish_lang = "dv" if _is_dv else "en"

                                    # AI expansion in the detected language. Dhivehi only
                                    # expands when the supplied Thaana context is factually sufficient.
                                    if _is_dv:
                                        try:
                                            article_body = generate_website_article_body(
                                                title=parsed_title, summary=full_summary,
                                                category=parsed_cat, source=SAMUGA_PUBLIC_SOURCE,
                                                is_breaking=is_brk, lang="dv"
                                            ) or raw_body or parsed_title
                                            log.info(f"[ARTICLE] Dhivehi article prepared: {len(article_body)} chars")
                                        except Exception as _dv_expand_err:
                                            log.warning(f"[ARTICLE] Dhivehi expand failed: {_dv_expand_err}")
                                            article_body = raw_body or parsed_title
                                    elif len(raw_body.split()) < 60:
                                        try:
                                            expanded = generate_website_article_body(
                                                title=parsed_title, summary=full_summary,
                                                category=parsed_cat, source=SAMUGA_PUBLIC_SOURCE,
                                                is_breaking=is_brk
                                            )
                                            article_body = expanded or raw_body or parsed_title
                                            log.info(f"[ARTICLE] AI expanded: {len(raw_body.split())} → {len((article_body or '').split())} words")
                                        except Exception as _expand_err:
                                            log.warning(f"[ARTICLE] AI expand failed: {_expand_err}")
                                            article_body = raw_body or parsed_title
                                    else:
                                        article_body = raw_body
                                        log.info(f"[ARTICLE] Long EN body — as written")

                                    _lang_flag = "🇲🇻 Dhivehi" if _is_dv else "🇬🇧 English"
                                    _ai_note = (" · Gemini full Thaana article" if _is_dv and len(article_body) > len(raw_body or "") else "") if _is_dv else (" · AI expanded" if len(raw_body.split()) < 60 else " · as written")
                                    article_url = f"{SAMUGA_CAPTION_LINK}/article.html?id={article_id}" if SAMUGA_CAPTION_LINK else f"article.html?id={article_id}"

                                    # Store article data — wait for cover photo decision
                                    _pending_cover_photo.clear()
                                    _pending_cover_photo.update({
                                        "user_id":      user_id,
                                        "article_id":   article_id,
                                        "title":        parsed_title,
                                        "summary":      full_summary,
                                        "article_body": article_body,
                                        "category":     parsed_cat,
                                        "lang":         _publish_lang,
                                        "is_brk":       is_brk,
                                        "author_id":    _auth_id,
                                        "author_name":  _auth_name,
                                        "author_role":  _auth_role,
                                        "author_photo": _auth_photo,
                                        "lang_flag":    _lang_flag,
                                        "ai_note":      _ai_note,
                                        "article_url":  article_url,
                                        "chat_id":      chat_id,
                                        "thread_id":    thread_id,
                                        "expires_at":   utcnow().timestamp() + 600,  # 10 min window
                                    })
                                    # Persist to PostgreSQL immediately — survives restarts/redeploys
                                    try:
                                        kv_set("pending_cover_photo", {k: v for k, v in _pending_cover_photo.items() if k != "expires_at"})
                                    except Exception as _kv_err:
                                        log.debug(f"[COVER] kv save: {_kv_err}")

                                    # Ask about cover photo with buttons
                                    kb = _make_inline_kb([
                                        [("📸 Add Cover Photo", "add_cover:yes"),
                                         ("🚀 Post Without Cover", "add_cover:no")],
                                        [("❌ Cancel", "add_cover:cancel")],
                                    ])
                                    send_text(chat_id,
                                        f"✅ <b>Article ready</b> — {parsed_cat} · {_lang_flag}{_ai_note}\n\n"
                                        f"📰 <b>{parsed_title}</b>\n"
                                        f"✍️ {_auth_name} · {_auth_role}\n\n"
                                        f"Do you want to add a cover photo?\n"
                                        f"<i>The bot will add Samuga Media branding and set it as the article cover.</i>",
                                        reply_to=msg_id, thread_id=thread_id,
                                        reply_markup=kb)

                            except Exception as e:
                                log.error(f"/article command error: {e}")
                                send_text(chat_id, f"❌ Article publish failed: {str(e)[:200]}", reply_to=msg_id, thread_id=thread_id)# /delete https://samugamedia.com/... — hide a website article by URL
                        elif text_cmd_low.startswith("/delete http://") or text_cmd_low.startswith("/delete https://"):
                            try:
                                url = text_cmd[8:].strip()
                                rows = db_delete_article_by_url(url)
                                if rows:
                                    joined = "\n".join([f"• <code>{rid}</code> — {ttl[:70]}" for rid, ttl, slug in rows[:5]])
                                    send_text(chat_id,
                                        f"🗑️ <b>Hidden from website by URL</b>\n\n{joined}",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id,
                                        "⚠️ No website article matched that URL. Check the full post link or slug.",
                                        reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Delete by URL failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"Delete by URL failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_delete_by_url_fail")

# /retry_body <article_id> — force an immediate retry of a website article held
# pending a real AI-generated body (status=WEBSITE_HELD_STATUS). Promotes to
# 'posted' on success; otherwise reports it's still not ready and stays held
# for the rate-limited scheduled sweep (normally one article per hour).
                        elif text_cmd_low.startswith("/retry_body"):
                            try:
                                target_id = text_cmd[len("/retry_body"):].strip()
                                if not target_id:
                                    send_text(chat_id,
                                        "Usage: <code>/retry_body ARTICLE_ID</code>\n"
                                        "Use the ID shown in the \"held\" notification.",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    promoted = db_retry_held_article_body(target_id)
                                    if promoted:
                                        send_text(chat_id,
                                            f"✅ <b>{target_id}</b> now has a full body and is live on the website.",
                                            reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id,
                                            f"⏳ <b>{target_id}</b> still doesn't have a publishable body — "
                                            f"it's either not a held article, or generation failed again. "
                                            f"It stays held. Automatic repair is rate-limited; use /retry_body again later if urgent.",
                                            reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Retry failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)

# /audit_legacy_bodies [limit] — manually inspect recent live AI articles.
# The scheduled legacy audit remains disabled by default; this command only
# changes invalid rows to held and does not itself make AI calls.
                        elif text_cmd_low.startswith("/audit_legacy_bodies"):
                            try:
                                arg = text_cmd[len("/audit_legacy_bodies"):].strip()
                                sweep_limit = max(1, min(500, int(arg))) if arg.isdigit() else 120
                                result = db_hold_invalid_live_ai_articles(limit=sweep_limit, lookback_hours=72)
                                send_text(
                                    chat_id,
                                    f"🔍 <b>Legacy body audit complete</b>\n\n"
                                    f"Checked: <b>{result.get('checked', 0)}</b> recent live AI articles\n"
                                    f"Moved to held: <b>{result.get('held', 0)}</b>\n\n"
                                    f"Held articles repair through the low-rate maintenance queue. "
                                    f"Use <code>/web held</code> or <code>/retry_body ARTICLE_ID</code>.",
                                    reply_to=msg_id, thread_id=thread_id,
                                )
                            except Exception as exc:
                                send_text(chat_id, f"❌ Legacy body audit failed: {str(exc)[:150]}", reply_to=msg_id, thread_id=thread_id)

# /web — website admin control panel inside Telegram
                        elif text_cmd_low.startswith("/web"):
                            try:
                                raw = text_cmd.strip()
                                low = raw.lower()

                                if low in ["/web", "/web help"]:
                                    send_text(chat_id,
                                        "🌐 <b>Website admin commands</b>\n\n"
                                        "• <code>/web recent</code> — recent posted website articles\n"
                                        "• <code>/web hidden</code> — hidden website articles\n"
                                        "• <code>/web held</code> — articles held pending an AI body\n"
                                        "• <code>/web dv</code> — posted Dhivehi website articles\n"
                                        "• <code>/web en</code> — posted English website articles\n"
                                        "• <code>/web search keyword</code> — search website articles\n"
                                        "• <code>/web analytics</code> — website analytics snapshot\n"
                                        "• <code>/web clear</code> — hide all current website posts and start fresh\n"
                                        "• <code>/featured</code> — list featured article IDs\n"
                                        "• <code>/feature URL_or_id</code> — mark featured\n"
                                        "• <code>/unfeature URL_or_id</code> — remove featured\n"
                                        "• <code>/hide URL_or_id</code> — hide one article\n"
                                        "• <code>/unhide URL_or_id</code> — restore one article\n"
                                        "• <code>/delete URL</code> — hide by public URL\n"
                                        "• <code>/retry_body ARTICLE_ID</code> — force-retry a held article\n"
                                        "• <code>/audit_legacy_bodies [limit]</code> — manually inspect recent incomplete live articles",
                                        reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web held", "/web held for body", "/web pending"]:
                                    held = db_get_held_website_articles(limit=20, due_only=False)
                                    if held:
                                        lines = [
                                            f"• <code>{h['id']}</code> [{h['lang'].upper()}] retry #{h['retry_count']} — {str(h['title'])[:70]}"
                                            for h in held
                                        ]
                                        send_text(chat_id,
                                            f"📝 <b>Held pending website body</b> ({len(held)})\n\n" +
                                            "\n".join(lines) +
                                            "\n\nAutomatic maintenance retries are limited to one article per hour; force one now with "
                                            "<code>/retry_body ARTICLE_ID</code>.",
                                            reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id, "✅ Nothing is currently held — every published article has a full body.", reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web clear", "/web clear all", "/web reset", "/web fresh", "/web fresh start", "/web hide all", "/web delete all"]:
                                    rows = db_hide_all_website()
                                    if rows:
                                        en_count = sum(1 for r in rows if len(r) > 2 and str(r[2]).lower() == "en")
                                        dv_count = sum(1 for r in rows if len(r) > 2 and str(r[2]).lower() == "dv")
                                        send_text(chat_id,
                                            f"🙈 <b>Website cleared.</b> Hidden current website posts: <b>{len(rows)}</b>\n"
                                            f"🇬🇧 EN: {en_count}  |  🇲🇻 DV: {dv_count}\n\n"
                                            f"The website will now start fresh with new clean posts.",
                                            reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id, "ℹ️ No current website posts found to hide.", reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web recent", "/web list", "/web posts"]:
                                    rows = db_list_website_articles(status="posted", limit=8)
                                    send_text(chat_id, "🌐 <b>Recent website posts</b>\n\n" + _format_web_rows(rows), reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web hidden", "/web hidden posts"]:
                                    rows = db_list_website_articles(status="hidden", limit=8)
                                    send_text(chat_id, "🙈 <b>Hidden website posts</b>\n\n" + _format_web_rows(rows), reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web dv", "/web dhivehi"]:
                                    rows = db_list_website_articles(status="posted", lang="dv", limit=8)
                                    send_text(chat_id, "🇲🇻 <b>Posted Dhivehi website articles</b>\n\n" + _format_web_rows(rows), reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web en", "/web english"]:
                                    rows = db_list_website_articles(status="posted", lang="en", limit=8)
                                    send_text(chat_id, "🇬🇧 <b>Posted English website articles</b>\n\n" + _format_web_rows(rows), reply_to=msg_id, thread_id=thread_id)

                                elif low.startswith("/web search "):
                                    q = raw[12:].strip()
                                    if not q:
                                        send_text(chat_id, "⚠️ Usage: <code>/web search keyword</code>", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        rows = db_search_website_articles(q, limit=8)
                                        if rows:
                                            send_text(chat_id, f"🔎 <b>Website search:</b> <code>{q}</code>\n\n" + _format_web_rows(rows, show_status=True), reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            send_text(chat_id, f"ℹ️ No website articles found for <code>{q}</code>.", reply_to=msg_id, thread_id=thread_id)

                                elif low in ["/web analytics", "/web stats", "/web top"]:
                                    send_text(chat_id, _format_web_analytics(days=7), reply_to=msg_id, thread_id=thread_id)

                                else:
                                    send_text(chat_id, "⚠️ Unknown web command. Try <code>/web help</code>.", reply_to=msg_id, thread_id=thread_id)

                            except Exception as e:
                                send_text(chat_id, f"❌ Web admin command failed: {str(e)[:180]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"/web command failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_web_admin_fail")

# /featured — list featured article IDs saved for website use
                        elif text_cmd_low in ["/featured", "/web featured"]:
                            try:
                                feats = db_get_featured_articles()
                                if feats:
                                    send_text(chat_id, "⭐ <b>Featured article IDs</b>\n\n" + "\n".join([f"• <code>{x}</code>" for x in feats]), reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "ℹ️ No featured articles saved yet.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Featured list failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)

# /feature <url|id|slug> — save featured article for website/frontend use
                        elif text_cmd_low.startswith("/feature "):
                            ident = text_cmd[9:].strip()
                            try:
                                rows = db_feature_article(ident)
                                if rows:
                                    send_text(chat_id, f"⭐ <b>Article marked featured</b>\n\n• <code>{rows[0]}</code>", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, f"⚠️ Could not feature <code>{ident}</code>", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Feature failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)

# /unfeature <url|id|slug> — remove featured mark
                        elif text_cmd_low.startswith("/unfeature "):
                            ident = text_cmd[11:].strip()
                            try:
                                ok = db_unfeature_article(ident)
                                if ok:
                                    send_text(chat_id, f"🧹 <b>Article unfeatured</b>\n\n• <code>{ident}</code>", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, f"ℹ️ That article was not in featured list: <code>{ident}</code>", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Unfeature failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)

# /hide_dv — hide all currently posted Dhivehi website articles
                        elif text.strip().lower() in ["/hide_dv", "/hide dv", "/hide all dv"]:
                            rows = db_hide_all_dhivehi()
                            if rows:
                                send_text(chat_id,
                                    f"🙈 <b>Hidden Dhivehi website articles:</b> {len(rows)}",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id,
                                    "ℹ️ No posted Dhivehi website articles found to hide.",
                                    reply_to=msg_id, thread_id=thread_id)


                        # /stats — quick operational stats
                        elif text_cmd_low in ["/stats", "/botstats", "/stat"]:
                            try:
                                send_text(chat_id, format_bot_stats(), reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Stats command failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"/stats failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_stats_fail")

                        elif text_cmd_low in ["/brain", "/learning", "/brain summary"]:
                            try:
                                from brain_memory import weekly_learning_summary
                                summary = weekly_learning_summary()
                                send_text(chat_id, summary, reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Brain summary failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)

                        elif text_cmd_low.startswith("/author"):
                            """
                            Register or update your author profile for website bylines.

                            Usage:
                              /author                    — show your current profile
                              /author set <Name>         — set your display name
                              /author role <Role>        — set your role (e.g. Reporter, Editor)
                              /author photo <url>        — set your profile photo URL
                              /author list               — list all registered authors
                              /author remove <id>        — remove an author

                            The photo should be a public image URL (Telegram CDN, GitHub, etc.)
                            After registering, newly approved articles will carry your byline.
                            """
                            try:
                                from db import db_upsert_author, db_list_authors
                                parts = text_cmd.strip().split(None, 2)
                                sub = parts[1].lower() if len(parts) > 1 else ""
                                arg = parts[2].strip() if len(parts) > 2 else ""

                                # Build a stable author_id from the Telegram user id
                                author_id = f"tg_{user_id}" if user_id else f"tg_{first_name.lower()}"

                                if sub == "list":
                                    authors = db_list_authors(active_only=False)
                                    if not authors:
                                        send_text(chat_id, "📋 No authors registered yet.\nUse <code>/author set Your Name</code> to register.", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        lines = ["📋 <b>Registered Authors</b>\n"]
                                        for a in authors:
                                            photo_line = f" · <a href=\"{a['photo_url']}\">photo ✅</a>" if a.get("photo_url") else " · no photo ❌"
                                            lines.append(f"• <b>{a['name']}</b> — {a['role']}{photo_line}\n  <code>{a['author_id']}</code>")
                                        send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)

                                elif sub == "ai":
                                    # /author ai photo <url>  — control Samuga AI profile
                                    # /author ai role <role>
                                    ai_parts = arg.split(None, 1)
                                    ai_sub = ai_parts[0].lower() if ai_parts else ""
                                    ai_arg = ai_parts[1].strip() if len(ai_parts) > 1 else ""
                                    if ai_sub == "photo" and ai_arg:
                                        # Update cms_authors for samuga_ai
                                        db_execute(
                                            "UPDATE cms_authors SET photo_url=%s WHERE author_id='samuga_ai'",
                                            (ai_arg,)
                                        )
                                        # Update all articles authored by Samuga AI
                                        db_execute(
                                            "UPDATE articles SET author_photo_url=%s WHERE author_name='Samuga AI'",
                                            (ai_arg,)
                                        )
                                        _AI_PHOTO["url"] = ai_arg  # update in-memory cache immediately
                                        send_text(chat_id,
                                            f"✅ <b>Samuga AI photo updated</b>\n\n"
                                            f"URL: <code>{ai_arg[:80]}</code>\n"
                                            f"All existing Samuga AI articles updated.\n\n"
                                            f"Check: /author list",
                                            reply_to=msg_id, thread_id=thread_id)
                                    elif ai_sub == "photo" and not ai_arg:
                                        # No URL — check if photo attached
                                        if photo:
                                            send_text(chat_id, "📸 Uploading Samuga AI photo...", reply_to=msg_id, thread_id=thread_id)
                                            try:
                                                img_bytes = download_telegram_photo_bytes(photo)
                                                if img_bytes:
                                                    photo_url = upload_to_imgbb(img_bytes)
                                                    if photo_url:
                                                        db_execute("UPDATE cms_authors SET photo_url=%s WHERE author_id='samuga_ai'", (photo_url,))
                                                        db_execute(
                                                            "UPDATE articles SET author_photo_url=%s WHERE author_name='Samuga AI'",
                                                            (photo_url,)
                                                        )
                                                        send_text(chat_id,
                                                            f"✅ <b>Samuga AI photo saved!</b>\n\nAll existing AI articles updated.",
                                                            reply_to=msg_id, thread_id=thread_id)
                                                    else:
                                                        send_text(chat_id, "❌ Upload failed. Try again.", reply_to=msg_id, thread_id=thread_id)
                                                else:
                                                    send_text(chat_id, "❌ Could not download photo. Try again.", reply_to=msg_id, thread_id=thread_id)
                                            except Exception as _pe:
                                                send_text(chat_id, f"❌ Photo upload failed: {str(_pe)[:100]}", reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            # Enter waiting state for AI photo
                                            _pending_author_photo.clear()
                                            _pending_author_photo.update({
                                                "user_id": user_id,
                                                "target": "ai",
                                                "chat_id": chat_id,
                                                "thread_id": thread_id,
                                                "expires_at": utcnow().timestamp() + 120,
                                            })
                                            send_text(chat_id,
                                                f"📸 <b>Send the Samuga AI photo now</b>\n\n"
                                                f"Just send a photo in this chat — the bot will upload it and set it as the Samuga AI author picture on all articles.\n\n"
                                                f"<i>Waiting 2 minutes...</i>",
                                                reply_to=msg_id, thread_id=thread_id)
                                    elif ai_sub == "role" and ai_arg:
                                        db_execute(
                                            "UPDATE cms_authors SET role=%s WHERE author_id='samuga_ai'",
                                            (ai_arg,)
                                        )
                                        send_text(chat_id, f"✅ Samuga AI role updated to: <b>{ai_arg}</b>", reply_to=msg_id, thread_id=thread_id)
                                    elif ai_sub == "name" and ai_arg:
                                        db_execute(
                                            "UPDATE cms_authors SET name=%s WHERE author_id='samuga_ai'",
                                            (ai_arg,)
                                        )
                                        db_execute(
                                            "UPDATE articles SET author_name=%s WHERE author_name='Samuga AI'",
                                            (ai_arg,)
                                        )
                                        send_text(chat_id, f"✅ Samuga AI display name updated to: <b>{ai_arg}</b>", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        # Show current Samuga AI profile
                                        row = db_execute("SELECT name, role, photo_url FROM cms_authors WHERE author_id='samuga_ai'", fetch="one")
                                        if row:
                                            send_text(chat_id,
                                                f"🤖 <b>Samuga AI Author Profile</b>\n\n"
                                                f"Name: <b>{row[0]}</b>\n"
                                                f"Role: {row[1]}\n"
                                                f"Photo: {'✅ Set' if row[2] else '❌ Not set'}\n"
                                                f"{('URL: <code>' + row[2][:60] + '</code>') if row[2] else ''}\n\n"
                                                f"Commands:\n"
                                                f"<code>/author ai photo https://your-photo-url.jpg</code>\n"
                                                f"<code>/author ai role AI Newsroom</code>\n"
                                                f"<code>/author ai name Samuga AI</code>",
                                                reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            send_text(chat_id, "❌ Samuga AI profile not found in cms_authors.", reply_to=msg_id, thread_id=thread_id)

                                elif sub == "set" and arg:
                                    _up_ok = db_upsert_author(author_id=author_id, name=arg, role="Reporter")
                                    if _up_ok:
                                        db_execute("UPDATE cms_authors SET telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s", (user_id, author_id))
                                        db_execute("UPDATE cms_users SET author_id=%s,telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s OR telegram_user_id=%s", (author_id, user_id, author_id, user_id))
                                        db_execute("UPDATE articles SET author_name=%s,author_role='Reporter',updated_at=NOW() WHERE author_id=%s", (arg, author_id))
                                        send_text(chat_id,
                                            f"✅ <b>Author registered: {arg}</b>\n\n"
                                            f"ID: <code>{author_id}</code>\n"
                                            f"Role: Reporter (change with <code>/author role Editor</code>)\n"
                                            f"Photo: not set (add with <code>/author photo &lt;url&gt;</code>)\n\n"
                                            f"New articles you approve will now show your byline.",
                                            reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id,
                                            f"❌ <b>Author update failed</b> — the database rejected the write.\n\n"
                                            f"ID: <code>{author_id}</code>\n"
                                            f"Check Railway logs for the db_execute error, then try again.",
                                            reply_to=msg_id, thread_id=thread_id)

                                elif sub == "role" and arg:
                                    db_upsert_author(author_id=author_id, role=arg)
                                    db_execute("UPDATE cms_authors SET telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s", (user_id, author_id))
                                    db_execute("UPDATE articles SET author_role=%s,updated_at=NOW() WHERE author_id=%s", (arg, author_id))
                                    send_text(chat_id, f"✅ Role updated to: <b>{arg}</b>", reply_to=msg_id, thread_id=thread_id)

                                elif sub == "photo" and arg:
                                    # arg is a URL — store it
                                    db_upsert_author(author_id=author_id, photo_url=arg)
                                    db_execute("UPDATE cms_authors SET telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s", (user_id, author_id))
                                    # Update by stable author ID so display-name changes never miss old articles.
                                    db_execute(
                                        "UPDATE articles SET author_photo_url=%s,updated_at=NOW() WHERE author_id=%s",
                                        (arg, author_id)
                                    )
                                    send_text(chat_id,
                                        f"✅ <b>Photo updated</b>\n\n"
                                        f"URL: <code>{arg[:80]}</code>\n"
                                        f"Existing articles by <b>{first_name}</b> updated too.",
                                        reply_to=msg_id, thread_id=thread_id)

                                elif sub == "photo" and not arg:
                                    # No URL — check if a photo was sent with this message
                                    if photo:
                                        # Photo sent directly with /author photo command
                                        send_text(chat_id, "📸 Uploading your photo...", reply_to=msg_id, thread_id=thread_id)
                                        try:
                                            img_bytes = download_telegram_photo_bytes(photo)
                                            if img_bytes:
                                                photo_url = upload_to_imgbb(img_bytes)
                                                if photo_url:
                                                    db_upsert_author(author_id=author_id, photo_url=photo_url)
                                                    db_execute("UPDATE cms_authors SET telegram_user_id=%s,updated_at=NOW() WHERE author_id=%s", (user_id, author_id))
                                                    db_execute(
                                                        "UPDATE articles SET author_photo_url=%s,updated_at=NOW() WHERE author_id=%s",
                                                        (photo_url, author_id)
                                                    )
                                                    send_text(chat_id,
                                                        f"✅ <b>Photo saved!</b>\n\nYour author profile now shows your photo on all articles.",
                                                        reply_to=msg_id, thread_id=thread_id)
                                                else:
                                                    send_text(chat_id, "❌ Upload failed. Try again or send a smaller image.", reply_to=msg_id, thread_id=thread_id)
                                            else:
                                                send_text(chat_id, "❌ Could not download photo from Telegram. Try again.", reply_to=msg_id, thread_id=thread_id)
                                        except Exception as _pe:
                                            send_text(chat_id, f"❌ Photo upload failed: {str(_pe)[:100]}", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        # No photo attached — enter waiting state
                                        _pending_author_photo.clear()
                                        _pending_author_photo.update({
                                            "user_id": user_id,
                                            "target": "self",
                                            "author_id": author_id,
                                            "author_name": first_name,
                                            "chat_id": chat_id,
                                            "thread_id": thread_id,
                                            "expires_at": utcnow().timestamp() + 120,
                                        })
                                        send_text(chat_id,
                                            f"📸 <b>Send your profile photo now</b>\n\n"
                                            f"Just send a photo in this chat — the bot will upload it and save it as your author profile picture.\n\n"
                                            f"<i>Waiting 2 minutes...</i>",
                                            reply_to=msg_id, thread_id=thread_id)

                                elif sub == "remove" and arg:
                                    db_execute("UPDATE cms_authors SET active=FALSE WHERE author_id=%s", (arg,))
                                    send_text(chat_id, f"🗑 Author <code>{arg}</code> deactivated.", reply_to=msg_id, thread_id=thread_id)

                                else:
                                    # Show current profile
                                    authors = db_list_authors(active_only=False)
                                    mine = next((a for a in authors if a["author_id"] == author_id), None)
                                    if mine:
                                        photo_status = f"✅ Set" if mine.get("photo_url") else "❌ Not set"
                                        send_text(chat_id,
                                            f"👤 <b>Your Author Profile</b>\n\n"
                                            f"Name: <b>{mine['name']}</b>\n"
                                            f"Role: {mine['role']}\n"
                                            f"Photo: {photo_status}\n"
                                            f"ID: <code>{mine['author_id']}</code>\n\n"
                                            f"Commands:\n"
                                            f"<code>/author set Your Name</code>\n"
                                            f"<code>/author role Co-Founder &amp; Editor</code>\n"
                                            f"<code>/author photo https://...</code>",
                                            reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id,
                                            f"👤 <b>Author Profile — not set</b>\n\n"
                                            f"Register with:\n"
                                            f"<code>/author set {first_name}</code>\n\n"
                                            f"Then set your role and photo:\n"
                                            f"<code>/author role Co-Founder &amp; Editor</code>\n"
                                            f"<code>/author photo https://your-photo-url.jpg</code>",
                                            reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Author command failed: {str(e)[:200]}", reply_to=msg_id, thread_id=thread_id)

                        elif text_cmd_low.startswith("/fix_author"):
                            # /fix_author <article_id>              — re-resolve from your registered profile
                            # /fix_author <article_id> <name>       — set an explicit name
                            try:
                                parts = text_cmd.strip().split(None, 2)
                                if len(parts) < 2:
                                    send_text(chat_id,
                                        "✏️ <b>Fix an article's author</b>\n\n"
                                        "<code>/fix_author &lt;article_id&gt;</code>\n"
                                        "Re-applies your currently registered author profile "
                                        "(name/role/photo) to that article.\n\n"
                                        "<code>/fix_author &lt;article_id&gt; Custom Name</code>\n"
                                        "Sets an explicit author name on that article.\n\n"
                                        "Find the article_id from the website URL: "
                                        "<code>article.html?id=THIS_PART</code>",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    target_id = parts[1].strip()
                                    explicit_name = parts[2].strip() if len(parts) > 2 else None

                                    if explicit_name:
                                        ok = db_update_article_meta(target_id, author_name=explicit_name)
                                        if ok:
                                            send_text(chat_id,
                                                f"✅ <b>Author updated</b>\n\n"
                                                f"<code>{target_id}</code> → <b>{explicit_name}</b>",
                                                reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            send_text(chat_id, f"❌ Article not found or update failed: <code>{target_id}</code>",
                                                       reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        # Re-resolve from the current caller's registered profile
                                        from db import db_list_authors
                                        _all_auth = db_list_authors(active_only=False)
                                        _tg_id = f"tg_{user_id}" if user_id else None
                                        _matched = next(
                                            (a for a in _all_auth
                                             if a["author_id"] == _tg_id
                                             or a["name"].lower() == (first_name or "").lower()),
                                            None
                                        )
                                        if not _matched:
                                            send_text(chat_id,
                                                f"❌ No registered profile found for you.\n"
                                                f"Register first: <code>/author set Your Name</code>",
                                                reply_to=msg_id, thread_id=thread_id)
                                        else:
                                            ok = db_update_article_meta(
                                                target_id,
                                                author_name=_matched["name"],
                                                author_role=_matched["role"],
                                                author_photo_url=_matched.get("photo_url"),
                                            )
                                            if ok:
                                                send_text(chat_id,
                                                    f"✅ <b>Author re-resolved from your profile</b>\n\n"
                                                    f"<code>{target_id}</code>\n"
                                                    f"Name: <b>{_matched['name']}</b>\n"
                                                    f"Role: {_matched['role']}\n"
                                                    f"Photo: {'✅ set' if _matched.get('photo_url') else '❌ not set'}",
                                                    reply_to=msg_id, thread_id=thread_id)
                                            else:
                                                send_text(chat_id, f"❌ Article not found: <code>{target_id}</code>",
                                                           reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Fix author failed: {str(e)[:200]}", reply_to=msg_id, thread_id=thread_id)

                        elif text_cmd_low.startswith("/backfill_authors confirm"):
                            try:
                                result = db_backfill_author_defaults(dry_run=False)
                                send_text(chat_id,
                                    f"✍️ <b>Author Backfill Complete</b>\n\n"
                                    f"Updated: <b>{result.get('updated',0)}</b> articles\n"
                                    f"Already set: <b>{result.get('skipped_already_set',0)}</b>\n"
                                    f"Total: <b>{result.get('total',0)}</b>\n\n"
                                    f"All NULL-author articles are now attributed to <b>Samuga AI</b>.",
                                    reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Backfill failed: {str(e)[:200]}", reply_to=msg_id, thread_id=thread_id)

                        elif text_cmd_low.startswith("/backfill_authors"):
                            try:
                                dry = db_backfill_author_defaults(dry_run=True)
                                would = dry.get("would_update", 0)
                                total = dry.get("total", 0)
                                already = dry.get("skipped_already_set", 0)
                                if would == 0:
                                    send_text(chat_id,
                                        f"✅ <b>Author backfill: nothing to do</b>\n\n"
                                        f"All {total} published articles already have author metadata.",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id,
                                        f"🔍 <b>Author Backfill Preview</b>\n\n"
                                        f"📊 {total} total published articles\n"
                                        f"✅ {already} already have author metadata\n"
                                        f"✏️ <b>{would} will be stamped as 'Samuga AI / AI Newsroom'</b>\n\n"
                                        f"Run <code>/backfill_authors confirm</code> to apply.",
                                        reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Backfill preview failed: {str(e)[:200]}", reply_to=msg_id, thread_id=thread_id)

                                                # /banner status | /banner off | /banner on [text] | /post banner
                        elif text_cmd_low.startswith("/banner") or text_cmd_low in ["/post banner", "/banner post"]:
                            try:
                                raw = text_cmd.strip()
                                low = raw.lower()
                                # image-based sponsor banner
                                if low in ["/post banner", "/banner post"]:
                                    banner_photo = photo or (reply_msg.get("photo") if reply_msg else None)
                                    if not banner_photo:
                                        send_text(chat_id, "⚠️ Attach a website-size photo or reply to a photo, then send <code>/post banner</code>.", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        img_bytes = download_telegram_photo_bytes(banner_photo)
                                        if not img_bytes:
                                            send_text(chat_id, "❌ Banner post failed: I couldn't download the Telegram photo.", reply_to=msg_id, thread_id=thread_id)
                                            alert_admin("Banner post failed: Telegram photo download failed.", dedupe_key="banner_photo_download_fail")
                                        else:
                                            image_url = upload_to_imgbb(img_bytes)
                                            if not image_url:
                                                send_text(chat_id, "❌ Banner post failed: image upload failed (imgbb).", reply_to=msg_id, thread_id=thread_id)
                                                alert_admin("Banner post failed: imgbb upload failed.", dedupe_key="banner_imgbb_fail")
                                            else:
                                                website_banner.update({"active": True, "text": "", "image_url": image_url, "updated_at": utcnow().isoformat()})
                                                persist_state()
                                                send_text(chat_id, f"🎯 <b>Website banner posted</b>\n\nImage saved and banner is active.\n{image_url}", reply_to=msg_id, thread_id=thread_id)
                                elif low in ["/banner", "/banner status"]:
                                    active = bool(website_banner.get("active"))
                                    txt = (website_banner.get("text") or "").strip()
                                    img = (website_banner.get("image_url") or "").strip()
                                    send_text(chat_id,
                                        f"🎯 <b>Website banner</b>\n\n"
                                        f"Active: <b>{'Yes' if active else 'No'}</b>\n"
                                        f"Image: {img or '—'}\n"
                                        f"Text: {txt or '—'}",
                                        reply_to=msg_id, thread_id=thread_id)
                                elif low.startswith("/banner off"):
                                    website_banner.update({"active": False, "text": "", "image_url": "", "updated_at": utcnow().isoformat()})
                                    persist_state()
                                    send_text(chat_id, "🧹 Website banner turned off.", reply_to=msg_id, thread_id=thread_id)
                                elif low.startswith("/banner on"):
                                    banner_text = raw[len("/banner on"):].strip()
                                    if not banner_text:
                                        send_text(chat_id, "⚠️ Use: <code>/banner on Your sponsored banner text</code> or attach a photo and use <code>/post banner</code>.", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        website_banner.update({"active": True, "text": banner_text[:240], "image_url": "", "updated_at": utcnow().isoformat()})
                                        persist_state()
                                        send_text(chat_id, f"🎯 Website text banner turned on.\n\n{banner_text[:240]}", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "⚠️ Use <code>/banner status</code>, <code>/banner on ...</code>, <code>/banner off</code>, or attach a photo and send <code>/post banner</code>.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ Banner command failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"Banner command failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_banner_fail")

# /hide_all_web — hide all current website posts and start fresh
                        elif text_cmd_low in ["/hide_all_web", "/hide all web", "/delete_all_web", "/delete all web", "/clear_web", "/clear web", "/fresh_web", "/fresh web"]:
                            try:
                                rows = db_hide_all_website()
                                if rows:
                                    en_count = sum(1 for r in rows if len(r) > 2 and str(r[2]).lower() == "en")
                                    dv_count = sum(1 for r in rows if len(r) > 2 and str(r[2]).lower() == "dv")
                                    send_text(chat_id,
                                        f"🙈 <b>Website cleared.</b> Hidden current website posts: <b>{len(rows)}</b>\n"
                                        f"🇬🇧 EN: {en_count}  |  🇲🇻 DV: {dv_count}\n\n"
                                        f"The website will now start fresh with new clean posts.",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "ℹ️ No current website posts found to hide.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ hide_all_web failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"hide_all_web failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_hide_all_web_fail")

# /hide_dv — hide all currently posted Dhivehi website articles
                        elif text_cmd_low in ["/hide_dv", "/hide dv", "/hide all dv", "/delete_dv", "/delete dv", "/delete all dv"]:
                            try:
                                rows = db_hide_all_dhivehi()
                                if rows:
                                    send_text(chat_id, f"🙈 <b>Hidden Dhivehi website articles:</b> {len(rows)}", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "ℹ️ No posted Dhivehi website articles found to hide.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ hide_dv failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"hide_dv failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_hide_dv_fail")

                        # /unhide_dv — restore hidden Dhivehi website articles
                        elif text_cmd_low in ["/unhide_dv", "/unhide dv", "/unhide all dv"]:
                            try:
                                rows = db_unhide_all_dhivehi()
                                if rows:
                                    send_text(chat_id, f"👀 <b>Restored hidden Dhivehi website articles:</b> {len(rows)}", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "ℹ️ No hidden Dhivehi website articles found to restore.", reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                send_text(chat_id, f"❌ unhide_dv failed: {str(e)[:150]}", reply_to=msg_id, thread_id=thread_id)
                                alert_admin(f"unhide_dv failed\n\nReason: {str(e)[:250]}", dedupe_key="cmd_unhide_dv_fail")

                        # /buffercheck — test imgbb + Buffer connection live
                        elif text.strip().lower() in ["/buffercheck", "/socialcheck", "/checkbuffer"]:
                            send_text(chat_id, "🔍 Testing imgbb + Buffer connection... ⏳",
                                      reply_to=msg_id, thread_id=thread_id)
                            def _buffercheck(_cid=chat_id, _tid=thread_id):
                                lines = ["🔍 <b>Social Platform Check</b>\n"]
                                # 1. imgbb
                                try:
                                    import base64 as _b64
                                    test_img = Image.new("RGB", (10,10), color=(20,40,80))
                                    buf = io.BytesIO()
                                    test_img.save(buf, format="JPEG"); buf.seek(0)
                                    resp = requests.post("https://api.imgbb.com/1/upload",
                                        data={"key": IMGBB_API_KEY,
                                              "image": _b64.b64encode(buf.getvalue()).decode()},
                                        timeout=15)
                                    if resp.status_code == 200 and resp.json().get("data",{}).get("url"):
                                        lines.append("🖼️ <b>imgbb:</b> ✅ Working")
                                    else:
                                        lines.append(f"🖼️ <b>imgbb:</b> ❌ HTTP {resp.status_code} — check IMGBB_API_KEY")
                                except Exception as e:
                                    lines.append(f"🖼️ <b>imgbb:</b> ❌ {str(e)[:60]}")

                                # 2. Meta Graph API (FB + IG)
                                if META_PAGE_TOKEN and META_PAGE_ID:
                                    try:
                                        r = requests.get(
                                            f"https://graph.facebook.com/{META_API_VER}/{META_PAGE_ID}",
                                            params={"fields": "name,instagram_business_account",
                                                    "access_token": META_PAGE_TOKEN},
                                            timeout=10)
                                        if r.status_code == 200:
                                            d = r.json()
                                            pg = d.get("name","?")
                                            ig = d.get("instagram_business_account",{}).get("id","")
                                            lines.append(f"\n📘 <b>Facebook (Meta):</b> ✅ Page: {pg}")
                                            if ig:
                                                lines.append(f"📸 <b>Instagram:</b> ✅ IG account linked (id: {ig})")
                                                if not META_IG_ID:
                                                    lines.append(f"   ⚠️ Add META_IG_ID={ig} to Railway vars for IG posting")
                                            else:
                                                lines.append("📸 <b>Instagram:</b> ⚠️ No IG business account linked to this page")
                                        else:
                                            err = r.json().get("error",{}).get("message","unknown")
                                            if "token" in err.lower() or "expired" in err.lower():
                                                lines.append(f"\n📘 <b>Meta token:</b> ❌ EXPIRED — regenerate META_PAGE_TOKEN")
                                            else:
                                                lines.append(f"\n📘 <b>Meta (FB/IG):</b> ❌ {err[:80]}")
                                    except Exception as e:
                                        lines.append(f"\n📘 <b>Meta:</b> ❌ {str(e)[:60]}")
                                else:
                                    lines.append("\n📘 <b>Meta (FB/IG):</b> ❌ META_PAGE_TOKEN or META_PAGE_ID not set in Railway")

                                # 3. Buffer (X/Twitter only — text posts)
                                if not BUFFER_TOKEN:
                                    lines.append("\n🐦 <b>X/Twitter (Buffer):</b> ❌ BUFFER_ACCESS_TOKEN not set")
                                else:
                                    try:
                                        r = requests.post(
                                            "https://api.buffer.com",
                                            json={"query": "{ account { id name } }"},
                                            headers={"Authorization": f"Bearer {BUFFER_TOKEN}",
                                                     "Content-Type": "application/json"},
                                            timeout=10)
                                        if r.status_code == 200:
                                            data = r.json()
                                            if "errors" in data:
                                                lines.append(f"\n🐦 <b>X/Twitter (Buffer):</b> ❌ {data['errors'][0].get('message','?')[:60]}")
                                            else:
                                                name = data.get("data",{}).get("account",{}).get("name","?")
                                                lines.append(f"\n🐦 <b>X/Twitter (Buffer):</b> ✅ Valid — account: {name}")
                                                lines.append(f"   <i>Note: Buffer posts text only (no image) — working as expected</i>")
                                        else:
                                            lines.append(f"\n🐦 <b>X/Twitter (Buffer):</b> ⚠️ HTTP {r.status_code}")
                                    except Exception as e:
                                        lines.append(f"\n🐦 <b>X/Twitter:</b> ❌ {str(e)[:60]}")

                                # 4. Last errors
                                lines.append(f"\n🔎 <b>Last Buffer (X) response:</b>")
                                lines.append(f"<code>{_last_buffer_error.get('response','No posts yet')[:150]}</code>")
                                if _last_buffer_error.get("fb_error"):
                                    lines.append(f"\n❌ <b>Last FB error:</b> <code>{_last_buffer_error['fb_error'][:150]}</code>")
                                if _last_buffer_error.get("ig_error"):
                                    lines.append(f"\n❌ <b>Last IG error:</b> <code>{_last_buffer_error['ig_error'][:150]}</code>")
                                send_text(_cid, "\n".join(lines), thread_id=_tid)
                            threading.Thread(target=_buffercheck, daemon=True).start()

                        # /diag — diagnose feeds, Gemini (Dhivehi), and queue health
                        elif text.strip().lower() in ["/diag", "/health", "/diagnose"]:
                            send_text(chat_id, "🔍 Running diagnostics... ⏳", reply_to=msg_id, thread_id=thread_id)
                            def _run_diag(_cid=chat_id, _tid=thread_id):
                                try:
                                    lines = ["🔍 <b>Samuga AI Diagnostics</b>\n"]
                                    # 1. Gemini health — classify quota/timeouts separately from authentication.
                                    if GEMINI_API_KEY:
                                        test_dv = make_dhivehi_caption(
                                            "The government announced a new policy today.", "Test news"
                                        )
                                        with _GEMINI_LOCK:
                                            _gh = dict(_GEMINI_HEALTH)
                                            _last_ok_ts = _GEMINI_LAST_OK.get("ts")
                                            _last_ok_model = _GEMINI_LAST_OK.get("model")
                                        if test_dv and any("ހ" <= c <= "޿" for c in test_dv):
                                            lines.append(f"🇲🇻 <b>Dhivehi (Gemini):</b> ✅ Healthy ({_last_ok_model or 'working model'})")
                                        elif _gh.get("status") == "rate_limited":
                                            lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ⚠️ Rate limited — fallback/manual review active")
                                        elif _gh.get("status") == "timeout":
                                            lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ⚠️ Temporary timeout")
                                        elif _gh.get("status") == "auth_failure":
                                            lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ❌ Authentication failure — check GEMINI_API_KEY")
                                        elif test_dv:
                                            lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ⚠️ Responded but returned no Thaana")
                                        else:
                                            lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ⚠️ Temporarily unavailable — safe fallback active")
                                        if _last_ok_ts:
                                            try:
                                                _mins = max(0, int((utcnow() - _last_ok_ts).total_seconds() / 60))
                                                lines.append(f"   Last success: {_mins}m ago via {_last_ok_model}")
                                            except Exception:
                                                pass
                                    else:
                                        lines.append("🇲🇻 <b>Dhivehi (Gemini):</b> ❌ GEMINI_API_KEY not set in Railway")
                                    # 2. Dhivehi feed check (RSS — expected to fail, kept for reference)
                                    dv_feeds = [f for f in LOCAL_FEEDS if f.get("lang")=="dv"]
                                    lines.append(f"\n📡 <b>Dhivehi RSS feeds ({len(dv_feeds)}) — now replaced by Telegram:</b>")
                                    for f in dv_feeds:
                                        try:
                                            parsed = feedparser.parse(f["url"])
                                            n = len(parsed.entries)
                                            domain = f["url"].split("/")[2]
                                            status = f"✅ {n} items" if n > 0 else "❌ 0 items (blocked/down)"
                                            lines.append(f"  {status} — {domain}")
                                        except Exception as fe:
                                            lines.append(f"  ❌ {f['url'].split('/')[2]}: error")
                                    # 3. Source ladder / website latest pages
                                    try:
                                        lines.append(f"\n🪜 <b>Source ladder:</b>")
                                        latest_counts = {}
                                        for src in WEB_LATEST_SOURCES:
                                            latest_counts[src["source"]] = latest_counts.get(src["source"], 0) + 1
                                        latest_sample = fetch_latest_web_pages(limit_per_source=2)
                                        by_src = {}
                                        for a in latest_sample:
                                            by_src[a.get("source","?")] = by_src.get(a.get("source","?"), 0) + 1
                                        for src_name in sorted(set(s.get("source","") for s in WEB_LATEST_SOURCES)):
                                            lines.append(f"  🌐 {src_name}: {by_src.get(src_name,0)} latest-page headline(s)")
                                        rss_backup = fetch_local_rss_recovery(limit_per_source=1)
                                        if rss_backup:
                                            lines.append(f"\n📡 <b>RSS recovery ladder:</b> ✅ {len(rss_backup)} backup item(s)")
                                        else:
                                            lines.append(f"\n📡 <b>RSS recovery ladder:</b> ⚠️ 0 backup item(s)")
                                        world_items = fetch_world_updates(limit=2)
                                        lines.append(f"\n🌍 <b>World updates:</b> ✅ {len(world_items)} major world item(s) available")
                                    except Exception as ce:
                                        lines.append(f"\n🪜 <b>Source ladder:</b> ❌ {str(ce)[:40]}")

                                    # 4. Telegram channels (signal only — websites are primary)
                                    lines.append(f"\n📲 <b>Telegram signal channels:</b>")
                                    for ch in DV_TELEGRAM_CHANNELS:
                                        try:
                                            arts = fetch_dv_telegram(ch["handle"], ch["source"], ch.get("reliability",80))
                                            dv_count = sum(1 for a in arts if a["lang"]=="dv")
                                            lines.append(f"  ✅ @{ch['handle']} / {ch['source']}: {len(arts)} items ({dv_count} Dhivehi)")
                                        except Exception as ce:
                                            lines.append(f"  ❌ @{ch.get('handle','?')} / {ch['source']}: {str(ce)[:30]}")
                                    # 5. Source health memory
                                    try:
                                        lines.append("\n🫀 <b>Source health memory:</b>")
                                        for row in source_health_summary(limit=8):
                                            lines.append(
                                                f"  • {row['source']}: <b>{row['health']}</b>/100 "
                                                f"(ok {row['successes']}/{row['fetches']}, empty {row['empty']}, fail {row['fails']}, ads {row['ads_total']})"
                                            )
                                    except Exception as she:
                                        lines.append(f"\n🫀 <b>Source health memory:</b> ❌ {str(she)[:40]}")

                                    # Official government-source and Discovery V2 dashboards.
                                    try:
                                        from fetchers import format_official_sources_diag
                                        lines.append("\n" + format_official_sources_diag())
                                    except Exception as _ose:
                                        lines.append(f"\n🏛️ <b>Official sources:</b> ⚠️ {str(_ose)[:60]}")
                                    try:
                                        from discovery import format_discovery_dashboard
                                        lines.append("\n" + format_discovery_dashboard())
                                    except Exception as _dde:
                                        lines.append(f"\n🔍 <b>Discovery V2:</b> ⚠️ {str(_dde)[:60]}")

                                    # 6. Queue state
                                    lines.append("\n🧠 <b>Queue guards:</b> duplicate translation wall + internal/junk safety wall active")
                                    try:
                                        dup_recent = _watchdog_prune_recent("duplicate_hits_recent", minutes=120)
                                        mpf = _watchdog_prune_recent("manual_post_failures", minutes=180)
                                        lines.append(f"🔔 <b>Watchdog memory:</b> duplicates {len(dup_recent)} in 2h | manual failures {len(mpf)} in 3h")
                                    except Exception:
                                        pass
                                    lines.append("🌐 <b>Dhivehi website rule:</b> no Dhivehi website publish without Content Lab approval")
                                    lines.append(f"🎯 <b>Website banner:</b> {'ON' if website_banner.get('active') else 'OFF'}")
                                    if website_banner.get("image_url"):
                                        lines.append("🖼️ <b>Banner type:</b> image")
                                    dv_queued = sum(1 for v in approval_queue.values() if v.get("lang")=="dv")
                                    en_queued = sum(1 for v in approval_queue.values() if v.get("lang")=="en")
                                    lines.append(f"\n📋 <b>Approval queue:</b> {dv_queued} Dhivehi, {en_queued} English waiting")
                                    # 5. Recent Dhivehi posts from DB
                                    if DB_ENABLED:
                                        dv_posted = db_execute("SELECT COUNT(*) FROM articles WHERE lang='dv' AND status='posted' AND posted_at > NOW() - INTERVAL '7 days'", fetch="one")
                                        lines.append(f"📚 <b>Dhivehi posted (7d):</b> {dv_posted[0] if dv_posted else 0}")
                                    # Split into chunks ≤ 4000 chars to stay under Telegram's 4096 limit
                                    _CHUNK_MAX = 4000
                                    _chunk, _chunks = [], []
                                    _chunk_len = 0
                                    for _line in lines:
                                        _line_len = len(_line) + 1  # +1 for \n
                                        if _chunk and _chunk_len + _line_len > _CHUNK_MAX:
                                            _chunks.append("\n".join(_chunk))
                                            _chunk, _chunk_len = [], 0
                                        _chunk.append(_line)
                                        _chunk_len += _line_len
                                    if _chunk:
                                        _chunks.append("\n".join(_chunk))
                                    for _i, _part in enumerate(_chunks):
                                        if len(_chunks) > 1:
                                            _part = f"({_i+1}/{len(_chunks)})\n{_part}"
                                        send_text(_cid, _part, thread_id=_tid)
                                except Exception as e:
                                    log.error(f"/diag: {e}")
                                    send_text(_cid, f"❌ Diag error: {e}", thread_id=_tid)
                            threading.Thread(target=_run_diag, daemon=True).start()

                        # /stats — newsroom archive overview (DB-powered)
                        elif text.strip().lower() in ["/stats", "/archive"]:
                            if not DB_ENABLED:
                                send_text(chat_id, "🗄️ Database not connected — archive stats unavailable. Running in JSON mode.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                try:
                                    total = db_execute("SELECT COUNT(*) FROM articles", fetch="one")
                                    today = db_execute("SELECT COUNT(*) FROM articles WHERE found_at > NOW() - INTERVAL '24 hours'", fetch="one")
                                    posted = db_execute("SELECT COUNT(*) FROM articles WHERE status='posted' AND found_at > NOW() - INTERVAL '24 hours'", fetch="one")
                                    dupes = db_execute("SELECT COUNT(*) FROM articles WHERE status='duplicate' AND found_at > NOW() - INTERVAL '24 hours'", fetch="one")
                                    by_cat = db_execute("""
                                        SELECT category, COUNT(*) FROM articles
                                        WHERE found_at > NOW() - INTERVAL '24 hours'
                                        GROUP BY category ORDER BY COUNT(*) DESC LIMIT 6
                                    """, fetch="all")
                                    top_src = db_execute("""
                                        SELECT source, COUNT(*) FROM articles
                                        WHERE found_at > NOW() - INTERVAL '24 hours' AND source IS NOT NULL
                                        GROUP BY source ORDER BY COUNT(*) DESC LIMIT 5
                                    """, fetch="all")
                                    msg_lines = ["🗞️ <b>Samuga Newsroom — Last 24h</b>\n"]
                                    msg_lines.append(f"📥 Scanned: <b>{today[0] if today else 0}</b>")
                                    msg_lines.append(f"✅ Posted: <b>{posted[0] if posted else 0}</b>")
                                    msg_lines.append(f"🔁 Duplicates blocked: <b>{dupes[0] if dupes else 0}</b>")
                                    msg_lines.append(f"📚 Total archive: <b>{total[0] if total else 0}</b>\n")
                                    if by_cat:
                                        msg_lines.append("<b>By category:</b>")
                                        for c, n in by_cat:
                                            msg_lines.append(f"  • {c}: {n}")
                                    if top_src:
                                        msg_lines.append("\n<b>Top sources:</b>")
                                        for s, n in top_src:
                                            msg_lines.append(f"  • {s}: {n}")
                                    send_text(chat_id, "\n".join(msg_lines), reply_to=msg_id, thread_id=thread_id)
                                except Exception as e:
                                    log.error(f"/stats: {e}")
                                    send_text(chat_id, f"❌ Stats error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /stories — list active developing story threads
                        elif text.strip().lower() in ["/stories", "/developing"]:
                            if not DB_ENABLED:
                                send_text(chat_id, "🗄️ Database not connected — story tracking unavailable.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                stories = get_active_stories(10)
                                if not stories:
                                    send_text(chat_id, "📚 No active developing stories right now. Stories appear here once an event gets 2+ updates.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    lines = ["📚 <b>Developing Stories — Last 72h</b>\n"]
                                    for s in stories:
                                        status_emoji = "🔴" if s["status"]=="developing" else "🟡"
                                        lines.append(f"{status_emoji} <b>Story #{s['id']}</b> ({s['update_count']} updates)\n   {s['title'][:70]}")
                                    lines.append("\n<i>Use /story [number] to see the full timeline.</i>")
                                    send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)

                        # /story <id> — show the full timeline of a story
                        elif text.strip().lower().startswith("/story"):
                            arg = text.strip()[6:].strip()
                            if not DB_ENABLED:
                                send_text(chat_id, "🗄️ Database not connected — story tracking unavailable.", reply_to=msg_id, thread_id=thread_id)
                            elif not arg.isdigit():
                                send_text(chat_id, "Use <code>/story [number]</code> — e.g. <code>/story 248</code>. See /stories for the list.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                timeline = get_story_timeline(int(arg))
                                if not timeline:
                                    send_text(chat_id, f"No story found with ID #{arg}.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    from datetime import timedelta as _td
                                    lines = [f"📚 <b>Story #{timeline['id']} — {timeline['status'].upper()}</b>\n"]
                                    lines.append(f"<b>{timeline['title']}</b>")
                                    lines.append(f"<i>{timeline['update_count']} updates · {timeline['category'] or 'news'}</i>\n")
                                    lines.append("<b>Timeline:</b>")
                                    for u in timeline["updates"]:
                                        t = u["time"]
                                        if t:
                                            mvt = (t + _td(hours=5)) if t.tzinfo else t
                                            tstr = mvt.strftime("%d %b %H:%M")
                                        else:
                                            tstr = ""
                                        src = f" ({u['source']})" if u["source"] else ""
                                        lines.append(f"🔹 <b>{tstr}</b>{src}\n   {u['headline'][:90]}")
                                    out = "\n".join(lines)
                                    if len(out) > 4000: out = out[:3990] + "\n…"
                                    send_text(chat_id, out, reply_to=msg_id, thread_id=thread_id)

                        # /trends — what Maldives is talking about right now
                        elif text.strip().lower() in ["/trends", "/trending"]:
                            if not DB_ENABLED:
                                send_text(chat_id, "🗄️ Database not connected — trends unavailable.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                try:
                                    trends = detect_trends(hours=24, min_mentions=3)
                                    if not trends:
                                        send_text(chat_id, "📊 No clear trends yet — archive is still filling up. Check back after a few hours of news.", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        lines = ["🔥 <b>Trending in Maldives — Last 24h</b>\n"]
                                        medals = ["🥇","🥈","🥉"] + ["🔹"]*20
                                        for i, (theme, count, titles) in enumerate(trends[:8]):
                                            lines.append(f"{medals[i]} <b>{theme}</b> — {count} stories")
                                        lines.append("\n<i>The bot boosts stories about these hot topics automatically.</i>")
                                        send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)
                                except Exception as e:
                                    log.error(f"/trends: {e}")
                                    send_text(chat_id, f"❌ Trends error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /learning on | off | status — engagement learning switch
                        elif text.strip().lower().startswith("/learning"):
                            arg = text.strip().lower().replace("/learning", "").strip()
                            if not DB_ENABLED:
                                send_text(chat_id, "🗄️ Database not connected — learning unavailable.", reply_to=msg_id, thread_id=thread_id)
                            elif arg == "on":
                                posted, weeks, valid = learning_stats()
                                if posted < LEARN_MIN_POSTS or weeks < LEARN_MIN_WEEKS or valid < LEARN_MIN_VALID_VIEWS:
                                    send_text(chat_id,
                                        f"⏳ Not ready yet:\n"
                                        f"  • Posts: {posted}/{LEARN_MIN_POSTS}\n"
                                        f"  • Weeks: {weeks}/{LEARN_MIN_WEEKS}\n"
                                        f"  • Posts with views: {valid}/{LEARN_MIN_VALID_VIEWS}\n\n"
                                        f"I'll keep collecting and tell you when the gate is met.",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    kv_set("learning_active", {"on": True, "by": first_name, "at": utcnow().isoformat()})
                                    weights = compute_topic_weights()
                                    gainers, losers = _top_gainers_losers(weights)
                                    send_text(chat_id,
                                        f"✅ <b>Learning mode ON</b> (by {first_name})\n\n"
                                        f"Audience data now nudges scoring, capped at ±{LEARN_CAP} pts.\n\n"
                                        f"<b>Getting a boost:</b>\n{gainers or '  (none yet)'}\n\n"
                                        f"<b>Getting demoted:</b>\n{losers or '  (none yet)'}\n\n"
                                        f"<i>Serious news always wins — this only breaks ties.</i>\n"
                                        f"Turn off anytime: <code>/learning off</code>",
                                        reply_to=msg_id, thread_id=thread_id)
                                    log.info(f"🧠 Learning ACTIVATED by {first_name}")
                            elif arg == "off":
                                kv_set("learning_active", {"on": False, "by": first_name, "at": utcnow().isoformat()})
                                send_text(chat_id,
                                    f"🛑 <b>Learning mode OFF</b> (by {first_name})\n"
                                    f"Back to observe-only. Scoring ignores audience data again.",
                                    reply_to=msg_id, thread_id=thread_id)
                                log.info(f"🧠 Learning DEACTIVATED by {first_name}")
                            else:  # status
                                posted, weeks, valid = learning_stats()
                                active = learning_is_active()
                                weights = kv_get("topic_weights", {})
                                gainers, losers = _top_gainers_losers(weights)
                                ready = (posted >= LEARN_MIN_POSTS and weeks >= LEARN_MIN_WEEKS and valid >= LEARN_MIN_VALID_VIEWS)
                                send_text(chat_id,
                                    f"🧠 <b>Learning status</b>\n\n"
                                    f"Mode: {'ACTIVE ✅' if active else 'observing 👀'}\n"
                                    f"Gate: {'met ✅' if ready else 'not met'}\n"
                                    f"  • Posts: {posted}/{LEARN_MIN_POSTS}\n"
                                    f"  • Weeks: {weeks}/{LEARN_MIN_WEEKS}\n"
                                    f"  • Posts with views: {valid}/{LEARN_MIN_VALID_VIEWS}\n\n"
                                    f"<b>Top gainers:</b>\n{gainers or '  (gathering data)'}\n\n"
                                    f"<b>Top losers:</b>\n{losers or '  (gathering data)'}\n\n"
                                    + (f"Cap: ±{LEARN_CAP} pts. " if active else "")
                                    + ("<code>/learning on</code> to activate." if (ready and not active) else ""),
                                    reply_to=msg_id, thread_id=thread_id)

                        # /meta — test the Facebook/Instagram connection live
                        elif text.strip().lower() in ["/meta", "/facebook", "/insights"]:
                            if not META_PAGE_TOKEN:
                                send_text(chat_id,
                                    "📵 No <code>META_PAGE_TOKEN</code> set in Railway. "
                                    "FB/IG learning is off.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id, "🔌 Testing Facebook + Instagram connection... ⏳",
                                          reply_to=msg_id, thread_id=thread_id)
                                try:
                                    fb = _fetch_fb_post_engagement(limit=10)
                                    ig_id = _resolve_ig_id()
                                    ig = _fetch_ig_post_engagement(limit=10) if ig_id else []
                                    lines = ["🔌 <b>Meta connection test</b>\n"]
                                    if fb:
                                        top_fb = max(e for _, e in fb)
                                        lines.append(f"📘 Facebook: ✅ {len(fb)} posts read (top engagement: {top_fb})")
                                    else:
                                        lines.append("📘 Facebook: ⚠️ no posts returned (new page, or check token perms)")
                                    if ig_id and ig:
                                        top_ig = max(e for _, e in ig)
                                        lines.append(f"📷 Instagram: ✅ {len(ig)} posts read (top engagement: {top_ig})")
                                    elif ig_id:
                                        lines.append("📷 Instagram: linked ✅ but no posts returned yet")
                                    else:
                                        lines.append("📷 Instagram: ⚠️ not linked — switch IG to Professional & link to the FB page")
                                    matched = fetch_meta_insights()
                                    lines.append(f"\n🔗 Matched to <b>{matched}</b> articles in the archive.")
                                    lines.append("<i>Runs automatically every Friday + Tuesday. Data feeds learning (still observe-only).</i>")
                                    send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)
                                except Exception as e:
                                    log.error(f"/meta: {e}")
                                    send_text(chat_id, f"❌ Meta test error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /scrapetest <url> - test semantic scraper on any URL
                        elif text.strip().lower().startswith("/scrapetest"):
                            arg = text.strip()[11:].strip()
                            if not arg.startswith("http"):
                                send_text(chat_id, "Use <code>/scrapetest [url]</code>\nExample: <code>/scrapetest https://edition.mv/news/12345</code>", reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id, f"🔍 Scraping... <i>{arg[:80]}</i>", reply_to=msg_id, thread_id=thread_id)
                                try:
                                    from samuga_scraper import semantic_scrape
                                    art = semantic_scrape(arg, source="ScrapeTest")
                                    if art.get("error"):
                                        send_text(chat_id, f"❌ <b>Scrape failed</b>\nReason: {art['error']}", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        out = [
                                            "✅ <b>Scrape OK</b>",
                                            f"<b>Title:</b> {art.get('title','')}",
                                            f"<b>Category:</b> {art.get('cat','')}   <b>Lang:</b> {art.get('lang','')}",
                                            f"<b>ID:</b> <code>{art.get('id','')}</code>",
                                            f"<b>Body:</b> {str(art.get('summary',''))[:400]}...",
                                        ]
                                        send_text(chat_id, "\n".join(out), reply_to=msg_id, thread_id=thread_id)
                                except Exception as ste:
                                    send_text(chat_id, f"❌ Scraper error: {ste}", reply_to=msg_id, thread_id=thread_id)

                        # /discovery - manage discovery engine topics
                        elif text.strip().lower().startswith("/discovery"):
                            arg = text.strip()[10:].strip()
                            parts = arg.split(None, 1)
                            sub = parts[0].lower() if parts else "list"
                            rest = parts[1] if len(parts) > 1 else ""
                            try:
                                from discovery import (
                                    discovery_list, discovery_add, discovery_remove,
                                    discovery_pause, discovery_resume, run_discovery as _disc_run
                                )
                                if sub in ("", "list"):
                                    send_text(chat_id, discovery_list(), reply_to=msg_id, thread_id=thread_id)
                                elif sub == "run":
                                    send_text(chat_id, "🔍 Running discovery hunt now...", reply_to=msg_id, thread_id=thread_id)
                                    import threading as _dthr
                                    _dthr.Thread(target=_disc_run, daemon=True).start()
                                elif sub == "pause":
                                    send_text(chat_id, discovery_pause(), reply_to=msg_id, thread_id=thread_id)
                                elif sub == "resume":
                                    send_text(chat_id, discovery_resume(), reply_to=msg_id, thread_id=thread_id)
                                elif sub == "add":
                                    if not rest:
                                        send_text(chat_id, "Usage: /discovery add <topic>\nExample: /discovery add fuel price hike", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id, discovery_add(rest.strip(), f"Maldives {rest.strip()} 2026"), reply_to=msg_id, thread_id=thread_id)
                                elif sub == "remove":
                                    if not rest.isdigit():
                                        send_text(chat_id, "Usage: /discovery remove <number>\nSee /discovery list for numbers.", reply_to=msg_id, thread_id=thread_id)
                                    else:
                                        send_text(chat_id, discovery_remove(int(rest)), reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id, "Commands: /discovery list | add <topic> | remove <n> | run | pause | resume", reply_to=msg_id, thread_id=thread_id)
                            except Exception as dce:
                                log.error(f"/discovery: {dce}")
                                send_text(chat_id, f"❌ Discovery error: {dce}", reply_to=msg_id, thread_id=thread_id)

                        # /queue — show social queue contents
                        elif text.strip().lower() in ["/queue", "/socialqueue", "/sq"]:
                            try:
                                with _social_queue_lock:
                                    q = list(_social_queue)
                                if not q:
                                    send_text(chat_id, "📭 Social queue is empty — nothing waiting to post.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    eta_secs = _calc_eta_seconds()
                                    lines = [f"📋 <b>Social Queue — {len(q)} item(s) waiting</b>"]
                                    lines.append(f"⏱ Next post in: <b>{int(eta_secs//60)}m {int(eta_secs%60)}s</b>\n")
                                    for i, item in enumerate(q, 1):
                                        key = item.get("key_label", f"item{i}")
                                        title = item.get("title", item.get("caption","?"))[:60]
                                        cat = item.get("cat", "?")
                                        lang = item.get("lang", "en").upper()
                                        queued = item.get("queued_at")
                                        age = ""
                                        if queued:
                                            try:
                                                mins = int((utcnow() - queued).total_seconds() / 60)
                                                age = f" ({mins}min ago)"
                                            except Exception:
                                                pass
                                        lines.append(f"<b>{i}.</b> <code>{key}</code> [{lang}/{cat}]{age}")
                                        lines.append(f"   📰 {title}")
                                        lines.append(f"   ▶️ <code>/qpost {i}</code>  🗑 <code>/qdel {i}</code>")
                                    lines.append(f"\n🗑 Delete all: <code>/queue clear</code>")
                                    lines.append(f"▶️ Force post next: <code>/qpost 1</code>")
                                    send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)
                            except Exception as qe:
                                send_text(chat_id, f"❌ Queue error: {qe}", reply_to=msg_id, thread_id=thread_id)

                        # /queue clear — delete entire social queue (with confirmation)
                        elif text.strip().lower() in ["/queue clear", "/qclear", "/clearqueue"]:
                            try:
                                with _social_queue_lock:
                                    count = len(_social_queue)
                                if count == 0:
                                    send_text(chat_id, "📭 Queue is already empty.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    # Store pending confirmation
                                    kv_set(f"queue_clear_confirm_{chat_id}", {"at": utcnow().isoformat(), "count": count})
                                    send_text(chat_id,
                                        f"⚠️ <b>Confirm queue clear</b>\n"
                                        f"This will delete ALL <b>{count}</b> item(s) from the social queue.\n"
                                        f"They will NOT be posted anywhere.\n\n"
                                        f"Type <code>/queue clear confirm</code> to proceed.",
                                        reply_to=msg_id, thread_id=thread_id)
                            except Exception as qce:
                                send_text(chat_id, f"❌ Error: {qce}", reply_to=msg_id, thread_id=thread_id)

                        # /queue clear confirm — actually clear the queue
                        elif text.strip().lower() in ["/queue clear confirm", "/qclear confirm"]:
                            try:
                                confirm = kv_get(f"queue_clear_confirm_{chat_id}", None)
                                if not confirm:
                                    send_text(chat_id, "⚠️ No pending clear request. Run <code>/queue clear</code> first.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    with _social_queue_lock:
                                        count = len(_social_queue)
                                        _social_queue.clear()
                                    kv_set(f"queue_clear_confirm_{chat_id}", None)
                                    persist_state()
                                    send_text(chat_id,
                                        f"🗑 <b>Queue cleared</b> — {count} item(s) deleted.\n"
                                        f"<i>Nothing was posted. Queue is now empty.</i>",
                                        reply_to=msg_id, thread_id=thread_id)
                                    log.info(f"[QUEUE] Cleared by {first_name}: {count} items deleted")
                            except Exception as qcce:
                                send_text(chat_id, f"❌ Error: {qcce}", reply_to=msg_id, thread_id=thread_id)

                        # /qdel <n> — delete specific item from social queue by position
                        elif text.strip().lower().startswith("/qdel "):
                            try:
                                n = int(text.strip().split()[1]) - 1  # convert to 0-indexed
                                removed = None
                                remaining = 0
                                with _social_queue_lock:
                                    if 0 <= n < len(_social_queue):
                                        removed = _social_queue.pop(n)
                                        remaining = len(_social_queue)
                                if removed is not None:
                                    title = removed.get("title", removed.get("key_label","?"))[:60]
                                    send_text(chat_id,
                                        f"🗑 <b>Deleted from queue:</b>\n{title}\n"
                                        f"<i>{remaining} item(s) remaining</i>",
                                        reply_to=msg_id, thread_id=thread_id)
                                    persist_state()
                                else:
                                    send_text(chat_id, f"❌ No item #{n+1} in queue. Use <code>/queue</code> to see current list.", reply_to=msg_id, thread_id=thread_id)
                            except (ValueError, IndexError):
                                send_text(chat_id, "Usage: <code>/qdel 2</code> (deletes item #2 from queue)", reply_to=msg_id, thread_id=thread_id)
                            except Exception as qde:
                                send_text(chat_id, f"❌ Error: {qde}", reply_to=msg_id, thread_id=thread_id)

                        # /qpost <n> — force post specific item from queue immediately
                        elif text.strip().lower().startswith("/qpost "):
                            try:
                                n = int(text.strip().split()[1]) - 1  # 0-indexed
                                with _social_queue_lock:
                                    if 0 <= n < len(_social_queue):
                                        item = _social_queue.pop(n)
                                    else:
                                        item = None
                                if not item:
                                    send_text(chat_id, f"❌ No item #{n+1} in queue.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    title = item.get("title", item.get("key_label","?"))[:60]
                                    send_text(chat_id, f"▶️ Force posting: <b>{title}</b>...", reply_to=msg_id, thread_id=thread_id)
                                    try:
                                        import io as _io
                                        tg_ok = item.get("tg_ok", False)
                                        if item.get("post_telegram"):
                                            log.info(f"[QUEUE] /qpost Telegram skipped for {item.get('key_label','Post')} — queue is FB/IG/X only")
                                        results = _post_to_social_now(
                                            _io.BytesIO(item["img_bytes"]), item["caption"],
                                            bypass_daily_limit=True,
                                            story_id=item.get("article_id", ""),
                                            count_toward_editorial_cap=False) or {}
                                        fb = "✅" if results.get("Facebook")  else "❌"
                                        ig = "✅" if results.get("Instagram") else "❌"
                                        x  = "✅" if results.get("Twitter")   else "❌"
                                        tg = "✅ already" if tg_ok else "⏭️ skipped"
                                        with _social_queue_lock:
                                            still = len(_social_queue)
                                        send_text(chat_id,
                                            f"✅ <b>Force posted to socials!</b>\n"
                                            f"Telegram {tg} · FB {fb} · IG {ig} · X {x}\n"
                                            f"<i>{still} item(s) still in queue</i>",
                                            reply_to=msg_id, thread_id=thread_id)
                                        globals()["_last_social_post_time"] = utcnow()
                                        persist_state()
                                    except Exception as fpe:
                                        # Put back in queue if post failed
                                        with _social_queue_lock:
                                            _social_queue.insert(n, item)
                                        send_text(chat_id, f"❌ Force post failed: {fpe}\nItem put back in queue.", reply_to=msg_id, thread_id=thread_id)
                            except (ValueError, IndexError):
                                send_text(chat_id, "Usage: <code>/qpost 1</code> (force posts item #1)", reply_to=msg_id, thread_id=thread_id)
                            except Exception as qpe:
                                send_text(chat_id, f"❌ Error: {qpe}", reply_to=msg_id, thread_id=thread_id)

                        # /qrefresh — reset the social queue timer + show queue status
                        elif text.strip().lower() in ["/qrefresh", "/queue refresh", "/resetqueue"]:
                            try:
                                globals()["_last_social_post_time"] = None
                                with _social_queue_lock:
                                    count = len(_social_queue)
                                # Check what's blocking
                                blocked_reason = ""
                                if posting_paused():
                                    blocked_reason = "\n⚠️ POSTING_PAUSED=true — queue won't post until unpaused"
                                elif not can_post_social():
                                    limit = 3 if not is_day_social() else 20
                                    blocked_reason = (f"\n⚠️ Night mode social limit ({limit}/night) reached."
                                                      f"\nUse <code>/qpost N</code> to force post individual items."
                                                      f"\nOr queue will auto-clear at 6AM MVT.")
                                send_text(chat_id,
                                    f"🔄 <b>Queue timer reset!</b>\n"
                                    f"{count} item(s) in queue{blocked_reason}\n\n"
                                    f"Use <code>/queue</code> to see items and <code>/qpost N</code> to force post.",
                                    reply_to=msg_id, thread_id=thread_id)
                                log.info(f"[QUEUE] Timer reset by {first_name}")
                            except Exception as qre:
                                send_text(chat_id, f"❌ Error: {qre}", reply_to=msg_id, thread_id=thread_id)

                        # /release — flush ALL pending cards to Content Lab right now (when team is actively reviewing)
                        elif text.strip().lower() in ["/release", "/flush", "/releaseall"]:
                            try:
                                pending = [(k, v) for k, v in approval_queue.items()
                                           if not v.get("_content_lab_sent") and not v.get("_content_lab_suppressed")]
                                if not pending:
                                    send_text(chat_id, "📭 No pending cards waiting to be released — all already sent to Content Lab.", reply_to=msg_id, thread_id=thread_id)
                                else:
                                    send_text(chat_id,
                                        f"📤 Releasing <b>{len(pending)}</b> pending card(s) to Content Lab now...\n"
                                        f"<i>Use this when your team is actively reviewing so you don't miss anything.</i>",
                                        reply_to=msg_id, thread_id=thread_id)
                                    released = 0
                                    for k, v in pending:
                                        try:
                                            _send_approval_card(k, v, force=True)
                                            released += 1
                                        except Exception as rel_e:
                                            log.error(f"/release {k}: {rel_e}")
                                    send_text(chat_id,
                                        f"✅ Released <b>{released}/{len(pending)}</b> card(s) to Content Lab.\n"
                                        f"Use <code>/pending</code> to see full queue.",
                                        reply_to=msg_id, thread_id=thread_id)
                            except Exception as e:
                                log.error(f"/release: {e}")
                                send_text(chat_id, f"❌ Release error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /why <key> — explain how a queued card scored
                        elif text.strip().lower().startswith("/why"):
                            key = text.strip()[4:].strip()
                            if not key:
                                send_text(chat_id,
                                    "Usage: <code>/why en12</code> — explains how a card in the "
                                    "queue scored. Run <code>/pending</code> to see keys.",
                                    reply_to=msg_id, thread_id=thread_id)
                            elif key not in approval_queue:
                                send_text(chat_id,
                                    f"Key <code>{key}</code> not in the queue. "
                                    f"<code>/pending</code> shows what's waiting.",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                item = approval_queue[key]
                                art = {
                                    "title": item.get("title",""),
                                    "summary": item.get("summary",""),
                                    "cat": item.get("cat","LOCAL"),
                                    "source": item.get("source",""),
                                    "lang": item.get("lang","en"),
                                    "_cluster_size": item.get("_cluster_size", 1),
                                    "_trend_theme": item.get("_trend_theme",""),
                                }
                                try:
                                    send_text(chat_id, format_score_breakdown(art),
                                              reply_to=msg_id, thread_id=thread_id)
                                except Exception as e:
                                    log.error(f"/why: {e}")
                                    send_text(chat_id, f"❌ Couldn't explain {key}: {e}",
                                              reply_to=msg_id, thread_id=thread_id)

                        # /weatherstatus — official watcher + multi-model health
                        elif text.strip().lower() in ["/weatherstatus", "/wxstatus", "/weather status"]:
                            try:
                                wx = get_weather_system_status()
                                active = wx.get("mms_active_alerts") or []
                                models = ", ".join(wx.get("models_ok") or []) or "none"
                                alert_lines = "None"
                                if active:
                                    alert_lines = "\n".join(
                                        f"• {str(a.get('level','')).upper()} — {a.get('hazard','')} ({a.get('area','')})"
                                        for a in active[:5]
                                    )
                                met = wx.get("mms_telegram") or {}
                                met_state = "✅ healthy" if met.get("recently_healthy") else ("⏳ starting" if met.get("enabled") and met.get("running") else "⚠️ fallback mode")
                                send_text(
                                    chat_id,
                                    f"🌦️ <b>Weather system status</b>\n\n"
                                    f"Models healthy: <b>{models}</b>\n"
                                    f"Forecast coverage: <b>{wx.get('coverage_hours',0)} hours</b>\n"
                                    f"Using cache: <b>{'Yes' if wx.get('using_cache') else 'No'}</b>\n"
                                    f"@MaldivesMET Telegram: <b>{met_state}</b>\n"
                                    f"Telegram last message: <code>{met.get('last_message_at') or 'not yet'}</code>\n"
                                    f"Facebook fallback: <b>{'Enabled' if wx.get('facebook_fallback_enabled') else 'Disabled'}</b>\n"
                                    f"MMS last success: <code>{wx.get('mms_last_success') or 'not yet'}</code>\n"
                                    f"Active official alerts:\n{alert_lines}\n\n"
                                    f"Cards: 06:00, 14:00, 22:00 MVT",
                                    reply_to=msg_id, thread_id=thread_id,
                                )
                            except Exception as e:
                                log.error(f"/weatherstatus: {e}", exc_info=True)
                                send_text(chat_id, f"❌ Weather status error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /weather — force send a weather card preview to core team
                        elif text.strip().lower() in ["/weather", "/wx"]:
                            send_text(chat_id, "🌤️ Fetching weather + island data... ⏳",
                                      reply_to=msg_id, thread_id=thread_id)
                            def _send_weather_preview(_chat_id=chat_id, _thread_id=thread_id, _name=first_name):
                                try:
                                    data = get_weather_data()
                                    if not data:
                                        send_text(_chat_id, "❌ Weather data unavailable right now.", thread_id=_thread_id)
                                        return
                                    islands = get_island_forecasts()
                                    prayer_info = get_prayer_times()
                                    card = generate_weather_card(data, island_data=islands if islands else None,
                                                                 prayer_data=prayer_info)
                                    current = data.get("current", {})
                                    temp  = round(current.get("temperature_2m", 29))
                                    code  = current.get("weathercode", 0)
                                    emoji, condition = weather_code_to_info(code)
                                    source = data.get("_source", "")
                                    island_lines = ""
                                    if islands:
                                        island_lines = "\n\n🏝 <b>Weather Watch</b>\n"
                                        for isl in islands:
                                            _out = isl.get("outlook") or f"{isl.get('temp',29)}°C • wind {isl.get('wind',0)} km/h"
                                            island_lines += f"📍 <b>{isl['name']}</b> — {_out}\n"
                                    caption = (
                                        f"🌤️ <b>Weather Preview — Malé, Maldives</b>\n"
                                        f"{emoji} {temp}°C — {condition}"
                                        f"{island_lines}\n"
                                        f"<i>Data: {source} · Preview only, not posted to community</i>"
                                    )
                                    send_photo(_chat_id, card, caption, thread_id=_thread_id)
                                    log.info(f"🌤️ Weather preview sent to core team by {_name}")
                                except Exception as e:
                                    log.error(f"/weather preview: {e}")
                                    send_text(_chat_id, f"❌ Error: {e}", thread_id=_thread_id)
                            threading.Thread(target=_send_weather_preview, daemon=True).start()

                        # /alert [white|yellow|orange|red] — preview an alert card in Content Lab
                        elif text.strip().lower().startswith("/alert"):
                            arg = text.strip().lower().replace("/alert", "").strip()
                            valid_levels = ["white", "yellow", "orange", "red"]

                            if arg == "status" or arg == "":
                                # Show current real conditions + whether an alert would fire
                                send_text(chat_id, "🔍 Checking current conditions... ⏳",
                                          reply_to=msg_id, thread_id=thread_id)
                                def _alert_status(_cid=chat_id, _tid=thread_id):
                                    try:
                                        result = check_official_weather_alerts(force=False)
                                        status = get_weather_system_status()
                                        active = result.get("active") or status.get("mms_active_alerts") or []
                                        if active:
                                            lines = []
                                            for item in active[:5]:
                                                level = str(item.get("level") or "white").lower()
                                                cfg = MMS_ALERT_LEVELS.get(level, MMS_ALERT_LEVELS["white"])
                                                lines.append(
                                                    f"{cfg['emoji']} <b>{cfg['label']}</b> — {item.get('hazard','')}\n"
                                                    f"Area: {item.get('area','')}\n"
                                                    f"Valid until: <code>{item.get('valid_until','')}</code>"
                                                )
                                            msg = (
                                                "⚠️ <b>Official MMS alerts currently detected</b>\n\n"
                                                + "\n\n".join(lines)
                                                + f"\n\nMMS sources healthy: {result.get('sources_ok', 0)}"
                                            )
                                        else:
                                            msg = (
                                                "🟢 <b>No active official MMS alert detected</b>\n\n"
                                                f"MMS sources healthy: {result.get('sources_ok', 0)}\n"
                                                f"Last successful check: <code>{status.get('mms_last_success') or 'not yet'}</code>\n\n"
                                                "Model thresholds are informational only; official MMS alerts control public alert posting."
                                            )
                                        send_text(_cid, msg, thread_id=_tid)
                                    except Exception as e:
                                        log.error(f"/alert status: {e}", exc_info=True)
                                        send_text(_cid, f"❌ Error: {e}", thread_id=_tid)
                                threading.Thread(target=_alert_status, daemon=True).start()

                            elif arg in valid_levels:
                                send_text(chat_id, f"⚠️ Building {arg.upper()} alert preview... ⏳",
                                          reply_to=msg_id, thread_id=thread_id)
                                def _alert_preview(_lvl=arg, _cid=chat_id, _tid=thread_id):
                                    try:
                                        data = get_weather_data()
                                        if not data:
                                            send_text(_cid, "❌ Weather data unavailable.", thread_id=_tid); return
                                        islands = get_island_forecasts()
                                        prayer_info = get_prayer_times()
                                        cfg = MMS_ALERT_LEVELS[_lvl]
                                        # Build a representative alert_text for this level
                                        sample_text = {
                                            "white":  "Strong winds and rough seas expected over Malé. Wind 32 km/h, gusts 56 km/h. Stay informed and take normal precautions.",
                                            "yellow": "Thunderstorms, strong winds and rough seas expected over Malé. Wind 42 km/h, gusts 66 km/h. Caution advised. Avoid unnecessary sea travel.",
                                            "orange": "Severe winds and very rough seas expected over Malé. Wind 58 km/h, gusts 82 km/h. Avoid sea travel. Secure loose objects. Stay indoors if possible.",
                                            "red":    "DANGEROUS storm conditions over Malé. Wind 78 km/h, gusts 105 km/h. DANGER. Do not travel by sea. Stay indoors and follow official guidance.",
                                        }[_lvl]
                                        card = generate_weather_card(data, alert_mode=True,
                                                                     alert_text=sample_text, alert_level=_lvl,
                                                                     island_data=islands if islands else None,
                                                                     prayer_data=prayer_info)
                                        caption = (
                                            f"{cfg['emoji']} <b>{cfg['label']} PREVIEW — {cfg['headline']}</b>\n\n"
                                            f"{sample_text}\n\n"
                                            f"<i>⚠️ This is a PREVIEW only — not posted to community.\n"
                                            f"Official MMS alerts are monitored every two minutes and post automatically.</i>"
                                        )
                                        send_photo(_cid, card, caption, thread_id=_tid)
                                        log.info(f"⚠️ Alert preview ({_lvl}) sent to core team")
                                    except Exception as e:
                                        log.error(f"/alert preview: {e}")
                                        send_text(_cid, f"❌ Error: {e}", thread_id=_tid)
                                threading.Thread(target=_alert_preview, daemon=True).start()
                            else:
                                send_text(chat_id,
                                    "Usage:\n"
                                    "<code>/alert status</code> — check current official MMS alerts\n"
                                    "<code>/alert white</code> — preview White (informational)\n"
                                    "<code>/alert yellow</code> — preview Yellow (advisory)\n"
                                    "<code>/alert orange</code> — preview Orange (warning)\n"
                                    "<code>/alert red</code> — preview Red (emergency)",
                                    reply_to=msg_id, thread_id=thread_id)

                        # /brief — generate the AI nightly editorial brief on demand
                        elif text.strip().lower() in ["/brief", "/journalist", "/editor"]:
                            send_text(chat_id, "🧠 Generating editorial brief from today's news... give me a moment ⏳", reply_to=msg_id, thread_id=thread_id)
                            threading.Thread(target=send_ai_journalist_brief, daemon=True).start()

                        # /pending — list all cards waiting for approval
                        elif text.strip().lower() in ["/pending", "/queue", "/list"]:
                            if not approval_queue:
                                send_text(chat_id, "📭 No cards waiting for approval right now.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                lines = ["📋 <b>Cards waiting for approval:</b>\n"]
                                now_ = utcnow()
                                for k, v in approval_queue.items():
                                    age_min = int((now_ - v["created_at"]).total_seconds() / 60)
                                    lang_flag = "🇲🇻" if v["lang"] == "dv" else "🇬🇧"
                                    if v["lang"] == "en":
                                        left = max(0, 30 - age_min)
                                        timing = f"auto-posts in {left}m"
                                    else:
                                        left = max(0, 120 - age_min)
                                        timing = f"expires in {left}m"
                                    lines.append(f"🔑 <b>{k.upper()}</b> {lang_flag} — {v['title'][:55]} <i>({timing})</i>")
                                send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)

                        # @SamugaNewsBot card [dhivehi text] — manual card creation
                        elif tagged and (
                            "create card and post" in clean.lower() or
                            "create card and send to community" in clean.lower() or
                            "create card and send to core team" in clean.lower() or
                            "create card and post to core team" in clean.lower() or
                            "create card and post to community" in clean.lower()
                        ):
                            log.info(f"🃏 Manual card — raw text: {repr(text[:200])}")
                            log.info(f"🃏 Manual card — photo: {bool(photo)}")
                            cl = clean.lower()
                            if "core team" in cl or "coreteam" in cl:
                                destination = "coreteam"
                            elif "community" in cl:
                                destination = "community"
                            else:
                                destination = "all"

                            # Detect category from command
                            manual_cat = "LOCAL"
                            if any(w in cl for w in ["breaking", "breaking news"]):          manual_cat = "BREAKING"
                            elif any(w in cl for w in ["political", "politics", "parliament", "government"]): manual_cat = "POLITICAL"
                            elif any(w in cl for w in ["lifestyle", "culture", "health", "tourism", "travel", "resort", "weather", "storm"]): manual_cat = "LIFESTYLE"
                            elif any(w in cl for w in ["sports", "sport", "football", "soccer"]): manual_cat = "SPORTS"
                            elif any(w in cl for w in ["world", "international", "global"]): manual_cat = "LOCAL"

                            # Extract the content text (everything before @SamugaNewsBot)
                            # The text comes from the photo caption or message, minus the command
                            raw_text = text  # original full text including caption
                            # Remove the bot mention and ALL command variants
                            # Do this BEFORE any other processing
                            cmd_variants = [
                                "create card and post to coreteam",
                                "create card and post to core team",
                                "create card and send to coreteam",
                                "create card and send to core team",
                                "create card and post to community",
                                "create card and send to community",
                                "create card and post",
                            ]
                            raw_lower = raw_text.lower()
                            for cmd in cmd_variants:
                                idx = raw_lower.find(cmd)
                                if idx != -1:
                                    raw_text = raw_text[:idx].strip()
                                    raw_lower = raw_text.lower()
                                    break
                            # Remove bot mention (anywhere in text)
                            raw_text = re.sub(r"@\w+", "", raw_text).strip()
                            raw_text = raw_text.strip()

                            if video and not photo:
                                send_text(chat_id, "Videos are not supported for cards — please send a photo instead 📸", reply_to=msg_id, thread_id=thread_id)
                            elif not raw_text and not photo:
                                send_text(chat_id, "Send a photo with caption text, or just text, then add the command at the end.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                # ── Parse headline / subheading split ──────────────────
                                # Split on blank lines first, then strip category keywords
                                # from each part individually (handles Dhivehi text with
                                # English category word at the bottom correctly).
                                CAT_KWS = ["breaking news","breaking","political","politics",
                                           "sports","sport","football","soccer","lifestyle",
                                           "world","international","global","tourism","weather",
                                           "local","culture","health","travel","resort","storm"]
                                def strip_cat_kws(t):
                                    """
                                    Return empty string if this paragraph IS a category keyword
                                    (possibly with punctuation/spaces). Otherwise return unchanged.
                                    We only discard a whole paragraph that is purely a category
                                    label — never strip keywords from inside real sentences.
                                    """
                                    cleaned = t.strip().rstrip("!.,;:").strip().lower()
                                    if cleaned in CAT_KWS:
                                        return ""
                                    return t

                                raw_parts = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
                                # A part that is ONLY a category keyword (after stripping) = discard
                                parts = []
                                for p in raw_parts:
                                    cleaned = strip_cat_kws(p)
                                    if cleaned:          # still has real content → keep
                                        parts.append(cleaned)
                                    # else: it was just "Breaking" or "Sports" → discard silently

                                has_thaana_input = any('\u0780'<=c<='\u07bf' for c in raw_text)
                                SUBHEAD_CARD_LIMIT = 80 if has_thaana_input else 150
                                if len(parts) >= 2:
                                    card_headline = parts[0]
                                    card_subhead  = " ".join(parts[1:])  # everything after first blank line
                                    if len(card_subhead) <= SUBHEAD_CARD_LIMIT:
                                        # Fits on card — pass headline + subhead separated by a
                                        # blank line. generate_card / generate_dhivehi_card now
                                        # honor \n\n as the headline/subhead split explicitly.
                                        content_text = card_headline + "\n\n" + card_subhead
                                        caption_subhead = ""   # already on card, not needed in caption
                                    else:
                                        # Too long — card gets headline only, subhead goes to caption
                                        content_text  = card_headline
                                        caption_subhead = card_subhead
                                else:
                                    # No blank line = everything is headline (wraps), no subhead
                                    content_text    = parts[0] if parts else raw_text
                                    caption_subhead = ""

                                content_text = content_text or "Samuga Media"
                                try:
                                    send_text(chat_id, "⏳ Creating card...", thread_id=thread_id)

                                    # Use uploaded photo as background if available
                                    if photo:
                                        bg = download_telegram_photo(photo)
                                        log.info("🖼️ Using uploaded photo as card background")
                                    else:
                                        bg = fetch_background_image(None, cat=manual_cat, title=card_headline or content_text)

                                    ts_now = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
                                    card = generate_card(content_text, "Samuga Media", ts_now, manual_cat, bg)
                                    cat_emoji = {"BREAKING":"🚨","LOCAL":"🇲🇻","POLITICAL":"🏛️","LIFESTYLE":"🌴","SPORTS":"🏅","FOOTBALL":"⚽","DISASTER":"🚨","WORLD":"🌍","WEATHER":"🌤️","TOURISM":"✈️"}.get(manual_cat,"📰")
                                    breaking_prefix = "🚨 <b>BREAKING NEWS</b>\n\n" if manual_cat in ["BREAKING", "DISASTER"] else ""
                                    # Caption: headline (always) + subhead if it didn't fit on card
                                    caption_body = card_headline if len(parts) >= 2 else content_text
                                    if caption_subhead:
                                        caption_body = caption_body + "\n\n" + caption_subhead
                                    full_caption = (
                                        breaking_prefix + cat_emoji + " " + caption_body + "\n\n"
                                        "📡 <b>Samuga Media</b> | @samugacommunity"
                                    )

                                    # NOTE: Auto-article from manual card removed.
                                    # Use /article command to publish a full article to the website.
                                    manual_article = None

                                    posted = []
                                    _social_fired = False

                                    if destination == "community":
                                        card.seek(0)
                                        if send_to_telegram(card, full_caption):
                                            posted.append("Community ✅")
                                        if manual_article:
                                            posted.append("Website ✅")

                                    elif destination == "coreteam":
                                        card.seek(0)
                                        if send_photo(CORE_TEAM_CHAT_ID, card, full_caption, thread_id=CONTENT_LAB_THREAD_ID):
                                            posted.append("Content Lab ✅")
                                        if manual_article:
                                            posted.append("Website ✅")

                                    elif destination == "all":
                                        # ── PREVIEW + CONFIRM gate ────────────────────────
                                        # Do NOT post anywhere public yet.
                                        # Send the card as a PREVIEW to the core team only,
                                        # then wait for /confirm (posts everywhere) or /cancel.
                                        card_bytes_stored = card.getvalue()
                                        _pending_manual_post.clear()
                                        _pending_manual_post.update({
                                            "card_bytes":   card_bytes_stored,
                                            "full_caption": full_caption,
                                            "chat_id":      chat_id,
                                            "thread_id":    thread_id,
                                            "first_name":   first_name,
                                            "created_at":   utcnow(),
                                            "manual_article": manual_article,
                                        })
                                        # Send preview card to core team
                                        preview = io.BytesIO(card_bytes_stored)
                                        preview_caption = (
                                            f"👀 <b>PREVIEW — not posted yet</b>\n\n"
                                            f"{full_caption}\n\n"
                                            f"━━━━━━━━━━━━━━\n"
                                            f"📲 This will post to <b>Telegram Community + Facebook + Instagram + X</b>.\n"
                                            f"🌐 Website article draft is prepared in parallel and will publish on /confirm.\n"
                                            f"✅ <code>/confirm</code> to post everywhere\n"
                                            f"❌ <code>/cancel</code> to discard"
                                        )
                                        send_photo(chat_id, preview, preview_caption, thread_id=thread_id)
                                        log.info(f"🃏 Manual card PREVIEW sent to core team by {first_name} — awaiting /confirm")
                                        _social_fired = True  # block fallthrough

                                    if not _social_fired:
                                        if posted:
                                            send_text(chat_id, "✅ Posted to: " + ", ".join(posted), reply_to=msg_id, thread_id=thread_id)
                                            log.info(f"✅ Manual card posted to: {posted}")
                                        else:
                                            send_text(chat_id, "❌ Failed to post.", reply_to=msg_id, thread_id=thread_id)

                                except Exception as e:
                                    log.error(f"Manual card: {e}")
                                    send_text(chat_id, f"❌ Error: {e}", reply_to=msg_id, thread_id=thread_id)

                        # /read command — store context for this session
                        elif text.strip().lower().startswith("/read"):
                            context_text = text.strip()[5:].strip()
                            if context_text:
                                core_team_session_context[chat_id] = context_text
                                send_text(chat_id, "Got it! I have read that and will use it as context for this session 📖", reply_to=msg_id, thread_id=thread_id)
                                log.info(f"📖 Session context stored: {context_text[:60]}...")
                            else:
                                send_text(chat_id, "Send it like this: /read [paste your content here]", reply_to=msg_id, thread_id=thread_id)

                        # /confirm — post pending preview card EVERYWHERE (Telegram + FB + IG + X)
                        elif text.strip().lower() in ["/confirm"]:
                            if not _pending_manual_post:
                                send_text(chat_id,
                                    "Nothing waiting to confirm. "
                                    "Use <code>create card and post</code> first.",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                age = (utcnow() - _pending_manual_post["created_at"]).total_seconds()
                                if age > 600:
                                    _pending_manual_post.clear()
                                    send_text(chat_id,
                                        "⏰ That preview expired (10 min window). "
                                        "Create a new one with <code>create card and post</code>.",
                                        reply_to=msg_id, thread_id=thread_id)
                                else:
                                    try:
                                        cap = _pending_manual_post["full_caption"]
                                        cbytes = _pending_manual_post["card_bytes"]
                                        send_text(chat_id, "🚀 Posting to all platforms... ⏳",
                                                  reply_to=msg_id, thread_id=thread_id)

                                        done = []
                                        # 1) Telegram community
                                        tg_buf = io.BytesIO(cbytes)
                                        tg_ok_now = bool(send_to_telegram(tg_buf, cap))
                                        tg_icon = "✅" if tg_ok_now else "❌"

                                        # Socials via dynamic FB/IG/X queue — confirmation after posting
                                        social_buf = io.BytesIO(cbytes)
                                        queue_for_social(social_buf, cap,
                                            notify_chat_id=chat_id,
                                            notify_thread_id=thread_id,
                                            key_label="Manual post",
                                            tg_ok=tg_ok_now,
                                            post_telegram=False,
                                            manual_post=True)  # human-confirmed: bypass bot pacing cap

                                        _pending_manual_post.clear()
                                        send_text(chat_id,
                                            f"✅ <b>Confirmed by {first_name}</b>\n"
                                            f"Telegram {tg_icon} · FB IG X ⏳ queued\n"
                                            f"<i>Use /article to publish a full website article.</i>",
                                            reply_to=msg_id, thread_id=thread_id)
                                        log.info(f"✅ Manual card confirmed by {first_name} — posted everywhere")
                                    except Exception as e:
                                        log.error(f"/confirm: {e}")
                                        send_text(chat_id, f"❌ Error posting: {e}",
                                                  reply_to=msg_id, thread_id=thread_id)

                        # /cancel — discard the pending preview card
                        elif text.strip().lower() in ["/cancel"]:
                            if not _pending_manual_post:
                                send_text(chat_id, "Nothing to cancel.",
                                          reply_to=msg_id, thread_id=thread_id)
                            else:
                                _pending_manual_post.clear()
                                send_text(chat_id,
                                    f"❌ <b>Cancelled by {first_name}</b> — card discarded, nothing posted. Website draft not published.",
                                    reply_to=msg_id, thread_id=thread_id)
                                log.info(f"❌ Manual card cancelled by {first_name}")

                        # /ai on|off — toggle proactive mode
                        elif text.strip().lower() in ["/ai on", "/ai off"]:
                            global _ai_proactive_mode
                            _ai_proactive_mode = "on" in text.strip().lower()
                            status = "ON 🟢" if _ai_proactive_mode else "OFF 🔴"
                            msg_txt = (
                                f"🧠 Samuga AI proactive mode: <b>{status}</b>\n\n"
                                + ("I'll jump in when I have something useful to add — tag me anytime too."
                                   if _ai_proactive_mode else
                                   "Silent mode. I'll only respond when you tag me.")
                            )
                            send_text(chat_id, msg_txt, reply_to=msg_id, thread_id=thread_id)
                            log.info(f"🧠 AI proactive mode: {status} by {first_name}")

                        # Cortex is now the pre-AI News Director, not a commenter.
                        elif text.strip().lower() in ["/cortex on", "/cortex off", "/cortex status"]:
                            send_text(
                                chat_id,
                                "🧭 <b>Cortex News Director is active before the AI pipeline.</b>\n\n"
                                "Separate Cortex comment messages were removed in Build 15.7. "
                                "Every selected Content Lab card shows one compact private Cortex decision line.",
                                reply_to=msg_id, thread_id=thread_id,
                            )

                        # /aiusage — provider and purpose counters for today
                        elif text.strip().lower() in ["/aiusage", "/ai usage"]:
                            usage = _ai_usage_snapshot()
                            providers = usage.get("by_provider") or {}
                            purposes = usage.get("by_purpose") or {}
                            p_lines = "\n".join(f"• {k}: {v}" for k, v in sorted(providers.items())) or "• No calls yet"
                            purpose_lines = "\n".join(f"• {k}: {v}" for k, v in sorted(purposes.items())) or "• No calls yet"
                            send_text(chat_id,
                                f"📊 <b>AI usage — {usage['date']}</b>\n\n"
                                f"<b>Editorial Claude/Gemini:</b> {usage['editorial_total']}/{usage['editorial_limit']}\n\n"
                                f"<b>Providers</b>\n{p_lines}\n\n<b>Purposes</b>\n{purpose_lines}",
                                reply_to=msg_id, thread_id=thread_id)

                        # /remember — save something to persistent team memory
                        elif text.strip().lower().startswith("/remember"):
                            mem_text = text.strip()[9:].strip()
                            if not mem_text:
                                send_text(chat_id,
                                    "What should I remember? Try: <code>/remember our audience loves political stories on weekdays</code>",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                # Classify category automatically
                                cat = "fact"
                                low = mem_text.lower()
                                if any(w in low for w in ["audience","people","readers","followers","engage","viral","perform"]):
                                    cat = "audience"
                                elif any(w in low for w in ["style","tone","voice","format","caption","card","design"]):
                                    cat = "style"
                                elif any(w in low for w in ["decided","decision","agreed","policy","rule","always","never"]):
                                    cat = "decision"
                                elif any(w in low for w in ["prefer","like","don't like","avoid","focus"]):
                                    cat = "preference"
                                mem_add(mem_text, category=cat, added_by=first_name)
                                send_text(chat_id,
                                    f"✅ Got it, saved to memory [{cat}]\n<i>\"{mem_text}\"</i>",
                                    reply_to=msg_id, thread_id=thread_id)
                                log.info(f"🧠 Memory added by {first_name}: {mem_text[:60]}")

                        # /memory — show what's stored
                        elif text.strip().lower() in ["/memory", "/memories"]:
                            items = mem_list(25)
                            if not items:
                                send_text(chat_id,
                                    "Nothing in memory yet. Use <code>/remember [something]</code> to teach me.",
                                    reply_to=msg_id, thread_id=thread_id)
                            else:
                                lines = ["🧠 <b>What I remember about Samuga:</b>\n"]
                                for item in items:
                                    lines.append(f"• {item}")
                                send_text(chat_id, "\n".join(lines), reply_to=msg_id, thread_id=thread_id)

                        # /forget — clear last memory or all
                        elif text.strip().lower().startswith("/forget"):
                            arg = text.strip()[7:].strip().lower()
                            if arg == "all":
                                mem_clear_all()
                                send_text(chat_id, "🗑️ All memories cleared.", reply_to=msg_id, thread_id=thread_id)
                            elif arg == "last":
                                mem_delete_last(1)
                                send_text(chat_id, "🗑️ Last memory deleted.", reply_to=msg_id, thread_id=thread_id)
                            else:
                                send_text(chat_id,
                                    "Use <code>/forget last</code> to delete the last one, or <code>/forget all</code> to wipe everything.",
                                    reply_to=msg_id, thread_id=thread_id)

                        # Respond when tagged OR proactively when AI mode is on
                        elif tagged or (_ai_proactive_mode and not text.strip().startswith("/")):
                            if not clean: clean = text.strip()
                            is_proactive = not tagged

                            # For proactive — ask Claude if it should actually respond
                            needs_search = False
                            if is_proactive:
                                should, needs_search = should_respond_proactively(clean, sender_name=display_name)
                                if not should:
                                    continue  # stay quiet

                            # Check if tagged message needs web search
                            if tagged and not needs_search:
                                needs_search = needs_web_search(clean)

                            log.info(f"🧠 Core team {'[proactive]' if is_proactive else '[tagged]'} {display_name}: {clean[:50]}")
                            session_ctx = core_team_session_context.get(chat_id, "")

                            def _reply_coreteam():
                                try:
                                    # First check if this is a story-timeline question
                                    story_answer = answer_story_query(clean)
                                    if story_answer:
                                        send_text(chat_id, story_answer,
                                                  reply_to=msg_id if tagged else None, thread_id=thread_id)
                                        return

                                    if is_dhivehi(clean):
                                        headlines = get_local_headlines()
                                        ctx = "\n".join(headlines[:5]) if headlines else ""
                                        reply = chat_with_gemini_dhivehi(clean, ctx, history)
                                        if not reply:
                                            reply = chat_with_coreteam(clean, display_name, sender_info,
                                                                        history, session_ctx, needs_search)
                                    else:
                                        reply = chat_with_coreteam(clean, display_name, sender_info,
                                                                    history, session_ctx, needs_search)

                                    if reply:
                                        add_to_conversation(user_id, "user", clean)
                                        add_to_conversation(user_id, "assistant", reply)
                                        # Proactive replies don't quote/reply — they just speak naturally
                                        send_text(chat_id, reply,
                                                  reply_to=msg_id if tagged else None,
                                                  thread_id=thread_id)
                                except Exception as e:
                                    log.error(f"Core team reply: {e}")

                            threading.Thread(target=_reply_coreteam, daemon=True).start()

                    # Regular public group — only respond when tagged, using the same public Samuga AI brain
                    elif tagged and clean:
                        log.info(f"💬 Public group Samuga AI {display_name}: {clean[:50]}")
                        try:
                            reply = public_samuga_ai_chat(
                                message=clean,
                                platform="telegram_group",
                                user_key=f"{chat_id}:{user_id}",
                                session_id=str(chat_id),
                                lang=("dv" if is_dhivehi(clean) else "en")
                            )
                        except Exception as e:
                            log.error(f"Unified public group chat failed: {e}")
                            reply = "Small issue on my side bro 😅 Try again in a moment."
                        send_text(chat_id, reply, reply_to=msg_id, thread_id=thread_id)
        except Exception as e:
            log.error(f"Update loop: {e}"); time.sleep(5)


def _watchdog_prune_recent(key, minutes=90):
    cutoff = utcnow() - timedelta(minutes=minutes)
    arr = _ops_watchdog_state.setdefault(key, [])
    _ops_watchdog_state[key] = [t for t in arr if isinstance(t, datetime) and t > cutoff]
    return _ops_watchdog_state[key]

def note_duplicate_skip():
    arr = _watchdog_prune_recent("duplicate_hits_recent", minutes=120)
    arr.append(utcnow())

def note_manual_post_failure():
    arr = _watchdog_prune_recent("manual_post_failures", minutes=180)
    arr.append(utcnow())

def _watchdog_source_alerts():
    issues = []
    snapshot = source_health_summary(limit=20)
    alerts = _ops_watchdog_state.setdefault("source_health_alerts", {})
    now = utcnow()

    for row in snapshot:
        src = row.get("source", "Unknown")
        key = _caption_match_key(src) or src.lower()
        last = alerts.get(key)

        if row.get("fetches", 0) >= 4 and row.get("fails", 0) >= 3:
            if not last or (now - last).total_seconds() > 6 * 3600:
                issues.append(f"Source looks unstable: <b>{src}</b> has {row.get('fails',0)} failures in {row.get('fetches',0)} fetches.")
                alerts[key] = now

        # Cumulative empty ratios are misleading when website, RSS and Telegram
        # routes share a source name. Alert only on a current consecutive-empty
        # streak and only when no route has produced content recently.
        consecutive_empty = int(row.get("consecutive_empty", 0) or 0)
        last_nonempty = row.get("last_nonempty_at")
        recently_nonempty = False
        if last_nonempty:
            try:
                recently_nonempty = (now.replace(tzinfo=None) - datetime.fromisoformat(last_nonempty)).total_seconds() < 6 * 3600
            except Exception:
                recently_nonempty = False
        if consecutive_empty >= 8 and not recently_nonempty:
            if not last or (now - last).total_seconds() > 8 * 3600:
                safe_src = re.sub(r"about:blank#blocked|https?:/{1,2}\S+", "", str(src), flags=re.I).strip() or "Unknown"
                issues.append(f"Source currently empty: <b>{safe_src}</b> returned no items in {consecutive_empty} consecutive fetches and has had no successful content for 6 hours.")
                alerts[key] = now

        items_total = row.get("items_total", 0)
        ads_total = row.get("ads_total", 0)
        if (items_total + ads_total) >= 6 and ads_total >= max(4, items_total):
            if not last or (now - last).total_seconds() > 8 * 3600:
                issues.append(f"Source is ad-heavy/noisy: <b>{src}</b> skipped {ads_total} ad-like items.")
                alerts[key] = now

        if row.get("health", 70) <= 40 and row.get("fetches", 0) >= 4:
            if not last or (now - last).total_seconds() > 8 * 3600:
                issues.append(f"Source health is weak: <b>{src}</b> scored only {row.get('health')}/100.")
                alerts[key] = now
    return issues

def ops_watchdog():
    """Operational watchdog. Sends Alert messages when something looks wrong before damage spreads."""
    try:
        issues = []

        # 1. Website Dhivehi leak / unexpected rise
        try:
            stats = db_bot_stats() or {}
            posted_dv = int(stats.get("posted_dv", 0))
            last_posted_dv = int(_ops_watchdog_state.get("last_posted_dv", 0) or 0)

            if posted_dv > 0 and os.environ.get("DHIVEHI_WEBSITE_APPROVED", "false").lower() != "true":
                issues.append(f"Dhivehi website leak detected: {posted_dv} posted Dhivehi article(s) still visible. Use /hide_dv if needed.")

            if posted_dv > last_posted_dv and last_posted_dv >= 0:
                issues.append(f"Dhivehi website count increased: {last_posted_dv} → {posted_dv}. Check recent website output.")
            _ops_watchdog_state["last_posted_dv"] = posted_dv
        except Exception as e:
            issues.append(f"Stats check failed: {str(e)[:120]}")

        # 2. Queue flood / stuck queue
        try:
            if len(approval_queue) >= 25:
                issues.append(f"Approval queue is high: {len(approval_queue)} items waiting.")
            if len(_social_queue) >= 12:
                issues.append(f"Social queue is high: {len(_social_queue)} items waiting.")

            if len(_social_queue) > 0:
                oldest_age = _oldest_social_queue_age_seconds()
                if oldest_age > SOCIAL_STUCK_ALERT_SECONDS:
                    issues.append(f"Social queue may be stuck: {len(_social_queue)} item(s) waiting; oldest item is {int(oldest_age//60)} minutes old.")
                    if not _ops_watchdog_state.get("social_queue_stuck_since"):
                        _ops_watchdog_state["social_queue_stuck_since"] = utcnow()
                else:
                    _ops_watchdog_state["social_queue_stuck_since"] = None
            else:
                _ops_watchdog_state["social_queue_stuck_since"] = None
        except Exception:
            pass

        # 3. Duplicate flood signal
        try:
            dup_recent = _watchdog_prune_recent("duplicate_hits_recent", minutes=120)
            if len(dup_recent) >= 8:
                issues.append(f"Duplicate flood detected: {len(dup_recent)} duplicate story skips in the last 2 hours.")
        except Exception:
            pass

        # 4. Manual publish failures
        try:
            fails = _watchdog_prune_recent("manual_post_failures", minutes=180)
            if len(fails) >= 3:
                issues.append(f"Manual website/banner failures repeating: {len(fails)} failure(s) in the last 3 hours.")
        except Exception:
            pass

        # 5. Source health warnings
        try:
            issues.extend(_watchdog_source_alerts())
        except Exception as e:
            issues.append(f"Source health watchdog failed: {str(e)[:120]}")

        # 6. Weather rate-limit reminder
        try:
            lb = (_last_buffer_error or {}).get("response", "")
            if "429" in str(lb):
                issues.append("Recent platform/API 429 seen in posting pipeline. Watch cache / queue pacing.")
        except Exception:
            pass

        if issues:
            alert_admin("\n".join(dict.fromkeys(issues)), dedupe_key="ops_watchdog", cooloff_minutes=30)
    except Exception as e:
        log.error(f"ops_watchdog: {e}")


def _website_public_url_for(article_id, slug):
    base = (SAMUGA_CAPTION_LINK or "https://samugamedia.com").rstrip("/")
    if slug:
        return f"{base}/{slug}"
    return f"{base}/article?id={article_id}"

def _format_web_rows(rows, show_status=False):
    if not rows:
        return "— none —"
    out = []
    for row in rows:
        # supports tuples from db_list/search
        article_id, title, slug = row[0], row[1], row[2]
        category = row[3] if len(row) > 3 else ""
        lang = row[4] if len(row) > 4 else ""
        status = row[3] if show_status else ""
        url = _website_public_url_for(article_id, slug)
        extra = []
        if show_status and status:
            extra.append(status)
        if category:
            extra.append(str(category))
        if lang:
            extra.append(str(lang))
        extra_txt = f" ({' • '.join(extra)})" if extra else ""
        out.append(f"• <b>{title[:80]}</b>{extra_txt}\n  <code>{article_id}</code>\n  {url}")
    return "\n".join(out)

def _format_web_analytics(days=7):
    a = db_website_analytics(days=days, limit=5) or {}
    lines = [f"🌐 <b>Website analytics ({int(a.get('days', days))}d)</b>"]
    lines.append(f"📰 Posted: <b>{a.get('posted_total', 0)}</b>")
    lines.append(f"👁️ Website views: <b>{a.get('total_views', 0)}</b>")
    lines.append(f"📲 Telegram views: <b>{a.get('total_tg_views', 0)}</b>")
    lines.append(f"❤️ Meta engagement: <b>{a.get('total_meta_engagement', 0)}</b>")

    top_views = a.get("top_views") or []
    if top_views:
        lines.append("\n🏆 <b>Top website views</b>")
        for aid, title, slug, views in top_views[:5]:
            lines.append(f"• {title[:75]} — <b>{int(views or 0)}</b> views")

    top_tg = a.get("top_tg") or []
    if top_tg:
        lines.append("\n📲 <b>Top Telegram views</b>")
        for aid, title, slug, tg_views in top_tg[:5]:
            lines.append(f"• {title[:75]} — <b>{int(tg_views or 0)}</b> TG views")

    top_meta = a.get("top_meta") or []
    if top_meta:
        lines.append("\n❤️ <b>Top Meta engagement</b>")
        for aid, title, slug, meta_eng in top_meta[:5]:
            lines.append(f"• {title[:75]} — <b>{int(meta_eng or 0)}</b> interactions")
    return "\n".join(lines)

def format_bot_stats():
    """Human-friendly stats block for Telegram."""
    stats = db_bot_stats() or {}
    lines = ["📊 <b>Samuga Bot Stats</b>"]
    lines.append(f"🗂️ Articles total: <b>{stats.get('articles_total', 0)}</b>")
    lines.append(f"🌐 Website posted: <b>{stats.get('posted_total', 0)}</b>")
    lines.append(f"🙈 Website hidden: <b>{stats.get('hidden_total', 0)}</b>")
    lines.append(f"🇲🇻 Posted Dhivehi on website: <b>{stats.get('posted_dv', 0)}</b>")
    lines.append(f"🇬🇧 Posted English on website: <b>{stats.get('posted_en', 0)}</b>")
    lines.append(f"🕓 Articles found in last 24h: <b>{stats.get('last_24h', 0)}</b>")
    lines.append(f"🧠 Approval queue: <b>{len(approval_queue)}</b>")
    lines.append(f"📲 Social queue: <b>{len(_social_queue)}</b>")
    lines.append(f"📚 Seen title memory: <b>{len(recent_story_titles)}</b>")
    lines.append(f"🎯 Banner active: <b>{'Yes' if website_banner.get('active') else 'No'}</b>")
    if website_banner.get("image_url"):
        lines.append("🖼️ Banner image: saved")
    return "\n".join(lines)


# ── Website API ───────────────────────────────────────────────────────────────
from flask import Flask, jsonify, request, send_from_directory, has_request_context
import html as _html
import re as _api_re

api_app = Flask(__name__)
api_app.json.ensure_ascii = False
api_app.config["MAX_CONTENT_LENGTH"] = 160 * 1024 * 1024  # authenticated CMS uploads: up to 160MB

def _api_clean_text(value, limit=900):
    """Clean DB text for website/API rendering."""
    value = str(value or "")
    value = _html.unescape(value)
    value = strip_source_links(value)
    value = _api_re.sub(r"<[^>]+>", " ", value)
    value = _api_re.sub(r"https?:/{1,2}\S+", "", value)
    value = _api_re.sub(r"\s+", " ", value).strip()
    return value[:limit]

def _api_has_thaana(text):
    return any("\u0780" <= ch <= "\u07BF" for ch in str(text or ""))

def _api_lang(title, summary, lang):
    # Website language must be based on actual script quality.
    # Do not show Latin Thaana in the Dhivehi side.
    text = (title or "") + " " + (summary or "")
    return "dv" if _api_has_thaana(text) else "en"

def _api_category(cat, title="", summary=""):
    try:
        return canonical_category(cat or "LOCAL", title or "", summary or "")
    except Exception:
        return (cat or "LOCAL").upper()


def ensure_article_engine_body(article_id, title, summary, category,
                               lang="en", is_breaking=False):
    """Generate and persist a real article body, never a summary fallback.

    The generator intentionally returns summary/title on failure. This wrapper
    applies the website quality gate so those fallback strings are not saved as
    article bodies and are never mistaken for complete articles later.
    """
    try:
        body = generate_website_article_body(
            title=title, summary=summary, category=category,
            source=SAMUGA_PUBLIC_SOURCE, is_breaking=is_breaking, lang=lang
        )
    except Exception as e:
        log.error(f"ensure_article_engine_body generate error: {e}")
        body = ""
    body = (body or "").strip()
    if not website_body_is_publishable(body, summary, title, lang):
        log.warning(f"[WEBSITE] lazy body generation rejected for {article_id or str(title)[:50]}")
        return ""
    try:
        if article_id:
            db_execute(
                "UPDATE articles SET article_body=%s, article_generated_at=NOW(), updated_at=NOW() WHERE id=%s",
                (body, article_id),
            )
    except Exception as e:
        log.warning(f"ensure_article_engine_body persist skipped: {e}")
    return body


def _public_article_body_for_language(article_id, article_body, article_excerpt, summary, title,
                                      category, lang="en", is_breaking=False, trusted=False):
    """Return a public body without ever substituting an AI card summary.

    Human/manual articles are trusted and may intentionally be short. AI
    articles must pass the same quality gate used at publish time; otherwise a
    fresh generation is attempted and an empty result is returned so the route
    can hold the row instead of exposing summary text as the full article.
    """
    language = str(lang or "en").strip().lower()
    stored = str(article_body or "").strip()

    if trusted:
        for candidate in (stored, article_excerpt, summary, title):
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    if website_body_is_publishable(stored, summary, title, language):
        return stored

    generated = ensure_article_engine_body(
        article_id, title, summary, category,
        lang=language, is_breaking=bool(is_breaking)
    )
    return generated if website_body_is_publishable(generated, summary, title, language) else ""


def _clean_article_engine_output(body, title=""):
    """Clean a generated English article body for website/API rendering:
    strip markdown, HTML, source links, stray title echo and normalize
    whitespace per paragraph (preserving paragraph breaks)."""
    import re as _re
    body = str(body or "")
    body = _html.unescape(body)
    body = strip_source_links(body)
    body = _api_re.sub(r"<[^>]+>", " ", body)
    body = _api_re.sub(r"https?:/{1,2}\S+", "", body)

    # Strip markdown formatting
    # Remove headings: # Article Body, ## Section, ### Sub etc.
    body = _re.sub(r'^#{1,6}\s+', '', body, flags=_re.MULTILINE)
    # Remove bold/italic: **text**, *text*, __text__, _text_
    body = _re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', body)
    body = _re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', body)
    # Remove bullet points: - item, * item, • item
    body = _re.sub(r'^[\-\*•]\s+', '', body, flags=_re.MULTILINE)
    # Remove numbered lists: 1. item
    body = _re.sub(r'^\d+\.\s+', '', body, flags=_re.MULTILINE)
    # Remove horizontal rules: --- or ***
    body = _re.sub(r'^[-\*]{3,}\s*$', '', body, flags=_re.MULTILINE)
    # Remove blockquotes: > text
    body = _re.sub(r'^>\s+', '', body, flags=_re.MULTILINE)
    # Remove inline code: `code`
    body = _re.sub(r'`[^`]+`', '', body)

    paras = []
    for para in _api_re.split(r"\n\s*\n", body):
        para = _api_re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        # Drop a leading line that just repeats the title.
        if title and para.lower() == title.strip().lower():
            continue
        # Drop standalone section headers that are now just plain text (e.g. "Article Body")
        if len(para.split()) <= 4 and para.endswith(":"):
            continue
        # Drop "Article Body" specifically — common AI artefact
        if para.lower() in ("article body", "article body:", "body:", "content:"):
            continue
        paras.append(para)
    return "\n\n".join(paras)[:30000]


def related_articles_for_api(article_id, category, lang="en", limit=4):
    """Return related public articles in the same category *and language*.

    Mixing English recommendations under a Dhivehi story made the article look
    like it had changed into a different English article. Language isolation is
    enforced in SQL and the frontend also keeps a defensive script check.
    """
    safe_lang = "dv" if str(lang or "").lower() in {"dv", "dhivehi"} else "en"
    try:
        rows = db_execute("""
            SELECT id, title, category, posted_at, found_at, article_slug
            FROM articles
            WHERE category=%s
              AND id<>%s
              AND lang=%s
              AND status IN ('posted','published','social_posted')
            ORDER BY COALESCE(posted_at, found_at) DESC NULLS LAST
            LIMIT %s
        """, (category, article_id, safe_lang, limit), fetch="all") or []
    except Exception as e:
        log.error(f"related_articles_for_api error: {e}")
        return []
    related = []
    for r in rows:
        rid, title, cat, posted_at, found_at, slug = r
        dt = posted_at or found_at
        related.append({
            "id": rid,
            "title": _api_clean_text(strip_source_links(title), 160),
            "category": _api_category(cat),
            "slug": slug or "",
            "time": mvt_display_time(dt),
        })
    return related

def _absolute_api_url(path):
    """Build a stable public backend URL in requests, schedulers and workers."""
    clean_path = "/" + str(path or "").lstrip("/")
    try:
        if has_request_context():
            request_base = str(request.url_root or "").strip().rstrip("/")
            if request_base.startswith(("https://", "http://")):
                return request_base + clean_path
    except Exception:
        pass
    return _public_backend_base() + clean_path


# ── Samuga Newsroom CMS ──────────────────────────────────────────────────────
# A deliberately small desktop-first CMS: separate accounts, role checks,
# audit history, article editing, Thaana-ready fields, media uploads and the
# existing Telegram/Facebook/X publishing connections.
from functools import wraps as _wraps
from itsdangerous import URLSafeTimedSerializer as _URLSafeTimedSerializer, BadSignature as _BadSignature, SignatureExpired as _SignatureExpired
from werkzeug.security import generate_password_hash as _generate_password_hash, check_password_hash as _check_password_hash
from werkzeug.utils import secure_filename as _secure_filename
import uuid as _uuid

_CMS_ROLES = {"contributor", "journalist", "editor", "admin", "super_admin"}
_CMS_PUBLISH_ROLES = {"editor", "admin", "super_admin"}
_CMS_ADMIN_ROLES = {"admin", "super_admin"}
_CMS_TOKEN_MAX_AGE = int(os.environ.get("CMS_TOKEN_MAX_AGE", str(12 * 3600)))
_CMS_TOKEN_SECRET = os.environ.get("CMS_TOKEN_SECRET") or hashlib.sha256(
    (os.environ.get("TELEGRAM_BOT_TOKEN", "") + os.environ.get("DATABASE_URL", "") + "samuga-cms").encode("utf-8")
).hexdigest()
_CMS_SERIALIZER = _URLSafeTimedSerializer(_CMS_TOKEN_SECRET, salt="samuga-newsroom-v1")
_CMS_MEDIA_DIR = os.environ.get("CMS_MEDIA_DIR", "/data/cms-media")
_CMS_MEDIA_FALLBACK_DIR = "/tmp/samuga-cms-media"
_CMS_MEDIA_EFFECTIVE_DIR = _CMS_MEDIA_DIR
_CMS_ALLOWED_ORIGINS = {
    x.strip().rstrip("/") for x in os.environ.get(
        "CMS_ALLOWED_ORIGINS",
        "https://samugamedia.com,https://www.samugamedia.com,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",") if x.strip()
}
# Public analytics normally travels through the same-origin Cloudflare Pages
# proxy. These exact origins remain allowed for old cached tracker builds and
# local production testing. Exact origins are required because sendBeacon uses
# credentialed CORS semantics and cannot use Access-Control-Allow-Origin: *.
_ANALYTICS_ALLOWED_ORIGINS = {
    x.strip().rstrip("/") for x in os.environ.get(
        "ANALYTICS_ALLOWED_ORIGINS",
        "https://samugamedia.com,https://www.samugamedia.com,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",") if x.strip()
}
_CMS_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
_CMS_VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}
_CMS_VIDEO_MAX_BYTES = int(os.environ.get("CMS_VIDEO_MAX_MB", "250")) * 1024 * 1024
_CMS_IMAGE_MAX_BYTES = int(os.environ.get("CMS_IMAGE_MAX_MB", "25")) * 1024 * 1024
_CMS_FFMPEG_TIMEOUT = int(os.environ.get("CMS_FFMPEG_TIMEOUT", "900"))
_CMS_VIDEO_PROCESS_LOCK = threading.Lock()
_CMS_PUBLISH_KICK_LOCK = threading.Lock()
_CMS_CONNECTION_CACHE = {"checked_at": None, "results": {}}
api_app.config["MAX_CONTENT_LENGTH"] = max(_CMS_VIDEO_MAX_BYTES, _CMS_IMAGE_MAX_BYTES) + 2 * 1024 * 1024
_CMS_LOGIN_WINDOW = 15 * 60
_CMS_LOGIN_LIMIT = 10
_CMS_LOGIN_ATTEMPTS = {}
_CMS_LOGIN_LOCK = threading.Lock()


def _cms_client_ip():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "unknown")[:120]

def _cms_login_rate_state(record_failure=False, clear=False):
    now = time.time()
    key = _cms_client_ip()
    with _CMS_LOGIN_LOCK:
        # Prune old keys so the small in-memory guard cannot grow forever.
        for old_key, values in list(_CMS_LOGIN_ATTEMPTS.items()):
            fresh = [ts for ts in values if now - ts < _CMS_LOGIN_WINDOW]
            if fresh:
                _CMS_LOGIN_ATTEMPTS[old_key] = fresh
            else:
                _CMS_LOGIN_ATTEMPTS.pop(old_key, None)
        if clear:
            _CMS_LOGIN_ATTEMPTS.pop(key, None)
            return True, 0
        attempts = _CMS_LOGIN_ATTEMPTS.setdefault(key, [])
        if len(attempts) >= _CMS_LOGIN_LIMIT:
            retry = max(1, int(_CMS_LOGIN_WINDOW - (now - attempts[0])))
            return False, retry
        if record_failure:
            attempts.append(now)
        return True, 0

def _cms_iso(value):
    try:
        return value.isoformat() if value else None
    except Exception:
        return str(value) if value else None


def _cms_parse_datetime(value):
    """Parse an ISO timestamp from the newsroom and normalize it to UTC."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # The dashboard sends local browser time with an offset. Treat a
        # timezone-less fallback as Maldives time rather than server UTC.
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=5)))
    return parsed.astimezone(timezone.utc)


def _cms_json_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _cms_store_revision(article_id, snapshot, user=None):
    """Store a compact immutable article snapshot after every successful save."""
    if not article_id or not isinstance(snapshot, dict):
        return None
    user = user or {}
    try:
        row = db_execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 FROM cms_article_revisions WHERE article_id=%s",
            (article_id,), fetch="one"
        )
        revision_no = int(row[0] if row else 1)
        saved = db_execute("""
            INSERT INTO cms_article_revisions
                (article_id,revision_no,snapshot,created_by,created_email)
            VALUES (%s,%s,%s::jsonb,%s,%s)
            RETURNING id
        """, (
            article_id, revision_no, json.dumps(snapshot, ensure_ascii=False, default=str),
            user.get("id"), user.get("email"),
        ), fetch="one")
        return {"id": int(saved[0]), "revision_no": revision_no} if saved else None
    except Exception as exc:
        log.warning(f"[CMS] revision save failed for {article_id}: {exc}")
        return None


def _cms_record_social_result(article_id, platform, ok, message, caption="", user=None):
    """Persist per-platform publishing history and latest article status."""
    user = user or {}
    platform = str(platform or "").lower()
    status = "posted" if ok else "failed"
    try:
        db_execute("""
            INSERT INTO cms_social_log
                (article_id,platform,status,message,caption,created_by)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (article_id, platform, status, str(message or "")[:1000], str(caption or "")[:1200], user.get("id")))
        current_row = db_execute("SELECT social_status FROM articles WHERE id=%s", (article_id,), fetch="one")
        current = _cms_json_dict(current_row[0] if current_row else {})
        current[platform] = {
            "ok": bool(ok), "status": status, "message": str(message or "")[:500],
            "time": datetime.now(timezone.utc).isoformat(),
        }
        db_execute("""
            UPDATE articles SET social_status=%s::jsonb,last_social_share_at=NOW(),updated_at=NOW()
            WHERE id=%s
        """, (json.dumps(current, ensure_ascii=False), article_id))
    except Exception as exc:
        log.warning(f"[CMS] social result save failed for {article_id}/{platform}: {exc}")


def _cms_latest_social_status(article_id):
    row = db_execute("SELECT social_status FROM articles WHERE id=%s", (article_id,), fetch="one")
    return _cms_json_dict(row[0] if row else {})



def _cms_set_social_state(article_id, platform, status, message="", ok=None):
    try:
        current_row = db_execute("SELECT social_status FROM articles WHERE id=%s", (article_id,), fetch="one")
        current = _cms_json_dict(current_row[0] if current_row else {})
        payload = {
            "status": str(status or "pending"),
            "message": str(message or "")[:500],
            "time": datetime.now(timezone.utc).isoformat(),
        }
        if ok is not None:
            payload["ok"] = bool(ok)
        current[str(platform)] = payload
        db_execute("""
            UPDATE articles SET social_status=%s::jsonb,updated_at=NOW()
            WHERE id=%s
        """, (json.dumps(current, ensure_ascii=False), article_id))
    except Exception as exc:
        log.warning(f"[CMS] social state update failed {article_id}/{platform}: {exc}")


def _cms_kick_publish_worker():
    """Process newly queued social jobs immediately; the scheduler remains the recovery fallback."""
    def _run():
        if not _CMS_PUBLISH_KICK_LOCK.acquire(blocking=False):
            return
        try:
            _cms_process_publish_jobs(limit=12)
        finally:
            _CMS_PUBLISH_KICK_LOCK.release()
    threading.Thread(target=_run, daemon=True, name="cms-publish-kick").start()


def _cms_queue_social_jobs(article_id, platforms, caption="", user=None):
    """Create durable per-platform publish jobs, coalescing active duplicates."""
    user = user or {}
    jobs = []
    for platform in [str(p).lower() for p in platforms or []]:
        if platform not in {"telegram", "facebook", "x"}:
            continue
        existing = db_execute("""
            SELECT id,status FROM cms_publish_jobs
            WHERE article_id=%s AND platform=%s AND status IN ('pending','retry','processing')
            ORDER BY created_at DESC LIMIT 1
        """, (article_id, platform), fetch="one")
        if existing:
            db_execute("""
                UPDATE cms_publish_jobs SET caption=%s,next_attempt_at=NOW(),updated_at=NOW(),
                    requested_by=COALESCE(%s,requested_by),requested_email=COALESCE(%s,requested_email)
                WHERE id=%s
            """, (str(caption or "")[:1200], user.get("id"), user.get("email"), existing[0]))
            job_id = int(existing[0])
            state = existing[1]
        else:
            dedupe = _uuid.uuid4().hex
            row = db_execute("""
                INSERT INTO cms_publish_jobs
                    (article_id,platform,caption,status,next_attempt_at,dedupe_key,requested_by,requested_email)
                VALUES (%s,%s,%s,'pending',NOW(),%s,%s,%s)
                RETURNING id
            """, (
                article_id, platform, str(caption or "")[:1200], dedupe,
                user.get("id"), user.get("email"),
            ), fetch="one")
            if not row:
                continue
            job_id = int(row[0])
            state = "pending"
        display_state = "processing" if state == "processing" else "queued"
        _cms_set_social_state(article_id, platform, display_state, "Waiting in publishing queue." if display_state == "queued" else "Publishing now.", ok=None)
        jobs.append({"id": job_id, "platform": platform, "status": state})
    if jobs:
        _cms_kick_publish_worker()
    return jobs


def _cms_claim_publish_job():
    return db_execute("""
        WITH next_job AS (
            SELECT id FROM cms_publish_jobs
            WHERE status IN ('pending','retry') AND next_attempt_at<=NOW()
            ORDER BY next_attempt_at ASC,created_at ASC
            FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE cms_publish_jobs j
        SET status='processing',attempts=j.attempts+1,started_at=NOW(),updated_at=NOW()
        FROM next_job n
        WHERE j.id=n.id
        RETURNING j.id,j.article_id,j.platform,j.caption,j.attempts,j.max_attempts,
                  j.requested_by,j.requested_email
    """, fetch="one")


def _cms_process_publish_jobs(limit=12):
    """Run durable social jobs with bounded exponential retry."""
    processed = 0
    for _ in range(max(1, int(limit))):
        job = _cms_claim_publish_job()
        if not job:
            break
        job_id, article_id, platform, caption, attempts, max_attempts, requested_by, requested_email = job
        user = {"id": requested_by, "email": requested_email or "publisher"}
        try:
            ok, message = _share_article_to_platform(article_id, platform, custom_caption=caption or "")
        except Exception as exc:
            ok, message = False, _mask_secrets(str(exc))[:500]
        if ok:
            db_execute("""
                UPDATE cms_publish_jobs SET status='succeeded',last_error=NULL,
                    response=%s::jsonb,completed_at=NOW(),updated_at=NOW()
                WHERE id=%s
            """, (json.dumps({"ok": True, "message": message}, ensure_ascii=False), job_id))
            _cms_record_social_result(article_id, platform, True, message, caption or "", user=user)
            _cms_audit("share_article", "article", article_id,
                       new_value={"platform": platform, "ok": True, "job_id": int(job_id)}, user=user)
        else:
            if int(attempts or 0) < int(max_attempts or 4):
                delays = {1: 1, 2: 5, 3: 15}
                delay_minutes = delays.get(int(attempts or 1), 60)
                db_execute("""
                    UPDATE cms_publish_jobs SET status='retry',last_error=%s,
                        response=%s::jsonb,next_attempt_at=NOW()+(%s || ' minutes')::interval,
                        updated_at=NOW()
                    WHERE id=%s
                """, (
                    str(message or "")[:1000],
                    json.dumps({"ok": False, "message": message}, ensure_ascii=False),
                    delay_minutes, job_id,
                ))
                _cms_set_social_state(article_id, platform, "retrying",
                                      f"Retry {attempts}/{max_attempts}: {message}", ok=False)
            else:
                db_execute("""
                    UPDATE cms_publish_jobs SET status='failed',last_error=%s,
                        response=%s::jsonb,completed_at=NOW(),updated_at=NOW()
                    WHERE id=%s
                """, (
                    str(message or "")[:1000],
                    json.dumps({"ok": False, "message": message}, ensure_ascii=False), job_id,
                ))
                _cms_record_social_result(article_id, platform, False, message, caption or "", user=user)
                _cms_audit("share_article", "article", article_id,
                           new_value={"platform": platform, "ok": False, "job_id": int(job_id)}, user=user)
        processed += 1
    return processed


def _cms_live_connection_check():
    """Check platform credentials without publishing content or exposing secrets."""
    results = {}
    # Telegram
    if not TELEGRAM_BOT_TOKEN:
        results["telegram"] = {"configured": False, "ok": False, "message": "Bot token not configured."}
    else:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=12)
            data = r.json() if r.content else {}
            name = data.get("result", {}).get("username") or data.get("result", {}).get("first_name") or "bot"
            results["telegram"] = {"configured": True, "ok": bool(r.ok and data.get("ok")), "message": f"Connected as {name}." if r.ok and data.get("ok") else "Telegram check failed."}
        except Exception as exc:
            results["telegram"] = {"configured": True, "ok": False, "message": _mask_secrets(str(exc))[:180]}

    buffer_ok = False
    buffer_message = "Buffer token not configured."
    if BUFFER_TOKEN:
        try:
            r = requests.post(
                "https://api.buffer.com",
                json={"query": "{ account { id name } }"},
                headers={"Authorization": f"Bearer {BUFFER_TOKEN}", "Content-Type": "application/json"},
                timeout=12,
            )
            data = r.json() if r.content else {}
            buffer_ok = bool(r.ok and not data.get("errors"))
            account = data.get("data", {}).get("account", {}).get("name") or "Buffer account"
            buffer_message = f"Connected to {account}." if buffer_ok else str((data.get("errors") or [{}])[0].get("message") or f"HTTP {r.status_code}")[:180]
        except Exception as exc:
            buffer_message = _mask_secrets(str(exc))[:180]
    results["facebook"] = {
        "configured": bool(BUFFER_TOKEN and BUFFER_FB_ID),
        "ok": bool(buffer_ok and BUFFER_FB_ID),
        "message": buffer_message if BUFFER_FB_ID else "Facebook channel ID not configured.",
    }
    results["x"] = {
        "configured": bool(BUFFER_TOKEN and BUFFER_TW_ID),
        "ok": bool(buffer_ok and BUFFER_TW_ID),
        "message": buffer_message if BUFFER_TW_ID else "X channel ID not configured.",
    }
    _CMS_CONNECTION_CACHE["checked_at"] = datetime.now(timezone.utc).isoformat()
    _CMS_CONNECTION_CACHE["results"] = results
    return results

def _cms_public_url(value):
    value = str(value or "").strip()
    if not value:
        return None
    if value.startswith(("https://", "http://")):
        return value[:2000]
    return None



def _cms_media_directory():
    """Return a writable newsroom media directory, preferring Railway volume."""
    global _CMS_MEDIA_EFFECTIVE_DIR
    for candidate in (_CMS_MEDIA_DIR, _CMS_MEDIA_FALLBACK_DIR):
        try:
            os.makedirs(candidate, exist_ok=True)
            test_path = os.path.join(candidate, ".write-test")
            with open(test_path, "wb") as handle:
                handle.write(b"ok")
            os.remove(test_path)
            _CMS_MEDIA_EFFECTIVE_DIR = candidate
            return candidate
        except Exception as exc:
            log.warning(f"[CMS] media directory unavailable {candidate}: {exc}")
    raise RuntimeError("No writable CMS media directory is available.")


def _cms_media_full_path(stored_path, base=None):
    base = os.path.abspath(base or _cms_media_directory())
    full = os.path.abspath(os.path.join(base, str(stored_path or "")))
    if not full.startswith(base + os.sep):
        raise ValueError("Unsafe media path.")
    return full


def _cms_media_public_path(stored_path):
    return _absolute_api_url("/media/cms/" + str(stored_path or "").replace(os.sep, "/"))


def repair_recent_public_copy(limit=100, lookback_days=14):
    """Remove leaked/malformed URLs from recent public title and summary rows.

    Only rows that actually contain an HTTP-like fragment are touched, so
    editor-written clean articles remain unchanged.
    """
    import db as _db_runtime
    if not _db_runtime.DB_ENABLED:
        return {"checked": 0, "repaired": 0}
    batch = max(1, min(500, int(limit or 100)))
    days = max(1, min(60, int(lookback_days or 14)))
    rows = db_execute("""
        SELECT id,title,summary,article_excerpt
          FROM articles
         WHERE COALESCE(posted_at,updated_at,found_at,NOW()) >= NOW()-make_interval(days=>%s)
           AND (COALESCE(title,'') ~* 'https?:/'
                OR COALESCE(summary,'') ~* 'https?:/'
                OR COALESCE(article_excerpt,'') ~* 'https?:/')
         ORDER BY COALESCE(posted_at,updated_at,found_at) DESC NULLS LAST
         LIMIT %s
    """, (days, batch), fetch="all") or []
    repaired = 0
    for article_id, title, summary, excerpt in rows:
        clean_title = strip_source_links(str(title or "")).strip()
        clean_summary = strip_source_links(str(summary or "")).strip()
        clean_excerpt = strip_source_links(str(excerpt or "")).strip()
        if not clean_title:
            clean_title = "Samuga Media update"
        if (clean_title, clean_summary, clean_excerpt) == (str(title or ""), str(summary or ""), str(excerpt or "")):
            continue
        db_execute("""
            UPDATE articles
               SET title=%s, summary=%s, article_excerpt=%s, updated_at=NOW()
             WHERE id=%s
        """, (clean_title, clean_summary or None, clean_excerpt or None, article_id))
        repaired += 1
        log.info("[PUBLIC COPY REPAIR] cleaned URL residue from %s", article_id)
    if rows:
        log.info("[PUBLIC COPY REPAIR] checked=%s repaired=%s", len(rows), repaired)
    return {"checked": len(rows), "repaired": repaired}


def repair_recent_missing_website_covers(limit=None, lookback_days=None):
    """Backfill recent live articles that were published while hosting was broken.

    This uses the existing Pexels/local background pipeline and Samuga's own
    volume-backed media endpoint. It makes no Claude, Gemini or DeepSeek call.
    """
    import db as _db_runtime
    if not _db_runtime.DB_ENABLED:
        return {"checked": 0, "repaired": 0, "failed": 0}
    if os.environ.get("WEBSITE_COVER_AUTO_REPAIR_ENABLED", "true").lower() != "true":
        return {"checked": 0, "repaired": 0, "failed": 0}
    batch = max(1, min(20, int(limit or os.environ.get("WEBSITE_COVER_REPAIR_BATCH", "8") or 8)))
    days = max(1, min(30, int(lookback_days or os.environ.get("WEBSITE_COVER_REPAIR_LOOKBACK_DAYS", "7") or 7)))
    rows = db_execute("""
        SELECT id,title,category,lang
          FROM articles
         WHERE status IN ('posted','published','social_posted')
           AND COALESCE(NULLIF(cover_image_url,''),'')=''
           AND COALESCE(posted_at,updated_at,found_at,NOW()) >= NOW()-make_interval(days=>%s)
         ORDER BY COALESCE(posted_at,updated_at,found_at) DESC NULLS LAST
         LIMIT %s
    """, (days, batch), fetch="all") or []
    repaired = 0
    failed = 0
    for article_id, title, category, lang in rows:
        try:
            safe_title = strip_source_links(str(title or "")).strip()
            safe_category = canonical_category(category or "LOCAL", safe_title, "")
            bg = fetch_background_image("", cat=safe_category, title=safe_title)
            cover = generate_web_cover(
                title=safe_title,
                category=safe_category,
                bg_image=bg,
                source=SAMUGA_PUBLIC_SOURCE,
            )
            url = upload_to_imgbb(cover.read())
            if not url:
                raise RuntimeError("public image URL was not created")
            db_execute("""
                UPDATE articles
                   SET cover_image_url=%s,updated_at=NOW()
                 WHERE id=%s AND COALESCE(NULLIF(cover_image_url,''),'')=''
            """, (url, article_id))
            repaired += 1
            log.info("[WEB COVER REPAIR] repaired %s: %s", article_id, safe_title[:80])
        except Exception as exc:
            failed += 1
            log.warning("[WEB COVER REPAIR] failed %s: %s", article_id, _mask_secrets(str(exc)))
    if rows:
        log.info("[WEB COVER REPAIR] checked=%s repaired=%s failed=%s", len(rows), repaired, failed)
    return {"checked": len(rows), "repaired": repaired, "failed": failed}


def media_storage_self_test():
    """Verify the volume and public URL path without using a third-party host."""
    try:
        test_cover = generate_web_cover("Samuga media storage check", "LOCAL", bg_image=None, source=SAMUGA_PUBLIC_SOURCE)
        url = _store_first_party_public_image(test_cover.read(), namespace="health")
        log.info("[MEDIA] first-party storage ready: %s", url)
        return True
    except Exception as exc:
        log.error("[MEDIA] first-party storage self-test failed: %s", _mask_secrets(str(exc)))
        alert_admin("First-party website image storage failed its startup self-test. New website/social covers may be unavailable.", dedupe_key="media_storage_self_test", cooloff_minutes=120)
        return False


def _cms_run_process(args, timeout=None):
    """Run ffmpeg/ffprobe without a shell and return completed process."""
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout or _CMS_FFMPEG_TIMEOUT,
        check=False,
    )


def _cms_probe_video(full_path):
    probe = _cms_run_process([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", full_path,
    ], timeout=90)
    if probe.returncode != 0:
        raise RuntimeError((probe.stderr or "ffprobe failed")[-500:])
    payload = json.loads(probe.stdout or "{}")
    video_stream = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), {})
    duration_raw = video_stream.get("duration") or payload.get("format", {}).get("duration") or 0
    try:
        duration = round(float(duration_raw), 2)
    except Exception:
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "codec": str(video_stream.get("codec_name") or "").lower(),
    }


def _cms_video_needs_transcode(stored_path, codec):
    ext = str(stored_path or "").rsplit(".", 1)[-1].lower()
    # MP4/H.264 and WebM VP8/VP9 are safe for modern browsers. iPhone HEVC/MOV
    # and editing codecs are converted to fast-start H.264 MP4.
    if ext == "mp4" and codec in {"h264", "avc1"}:
        return False
    if ext == "webm" and codec in {"vp8", "vp9", "av1"}:
        return False
    return True


def _cms_process_video_media(media_id, force=False):
    """Probe, browser-normalise and thumbnail a newsroom video.

    The DB row is durable, so a Railway restart can resume pending/failed work.
    Only one video is processed at a time to protect a small Railway container.
    """
    log.info(f"[CMS] video media_id={media_id} waiting for the single FFmpeg slot")
    _CMS_VIDEO_PROCESS_LOCK.acquire()
    try:
        allowed = ("pending", "failed") if not force else ("pending", "failed", "processing", "ready")
        row = db_execute("""
            SELECT id,stored_path,public_url,processing_status
            FROM cms_media_library
            WHERE id=%s AND media_type='video' AND deleted_at IS NULL
            LIMIT 1
        """, (media_id,), fetch="one")
        if not row or row[3] not in allowed:
            return False
        claimed = db_execute("""
            UPDATE cms_media_library
            SET processing_status='processing',processing_error=NULL,updated_at=NOW()
            WHERE id=%s AND processing_status=ANY(%s)
            RETURNING id
        """, (media_id, list(allowed)), fetch="one")
        if not claimed:
            return False

        base = _cms_media_directory()
        stored_path = row[1]
        source_path = _cms_media_full_path(stored_path, base)
        if not os.path.isfile(source_path):
            raise FileNotFoundError("Uploaded video file is missing from CMS storage.")

        meta = _cms_probe_video(source_path)
        final_stored = stored_path
        final_path = source_path
        ext = str(stored_path or "").rsplit(".", 1)[-1].lower()
        h264_mp4 = ext == "mp4" and meta.get("codec") in {"h264", "avc1"}
        needs_faststart_copy = h264_mp4 and not str(stored_path).lower().endswith("-web.mp4")
        needs_transcode = _cms_video_needs_transcode(stored_path, meta.get("codec"))
        if needs_transcode or needs_faststart_copy:
            root = stored_path.rsplit(".", 1)[0]
            final_stored = root + "-web.mp4"
            final_path = _cms_media_full_path(final_stored, base)
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            if needs_faststart_copy and not needs_transcode:
                command = [
                    "ffmpeg", "-y", "-i", source_path, "-map_metadata", "-1",
                    "-c", "copy", "-movflags", "+faststart", final_path,
                ]
            else:
                command = [
                    "ffmpeg", "-y", "-i", source_path,
                    "-map_metadata", "-1",
                    "-vf", "scale='trunc(min(1920,iw)/2)*2':-2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", final_path,
                ]
            transcode = _cms_run_process(command)
            if transcode.returncode != 0 or not os.path.isfile(final_path):
                raise RuntimeError((transcode.stderr or "Video conversion failed")[-700:])
            meta = _cms_probe_video(final_path)

        poster_stored = final_stored.rsplit(".", 1)[0] + "-poster.jpg"
        poster_path = _cms_media_full_path(poster_stored, base)
        os.makedirs(os.path.dirname(poster_path), exist_ok=True)
        seek = max(0.0, min(2.0, (meta.get("duration") or 0) / 3.0))
        poster = _cms_run_process([
            "ffmpeg", "-y", "-ss", f"{seek:.2f}", "-i", final_path,
            "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
            "-q:v", "3", poster_path,
        ], timeout=180)
        poster_url = _cms_media_public_path(poster_stored) if poster.returncode == 0 and os.path.isfile(poster_path) else None

        public_url = _cms_media_public_path(final_stored)
        size_bytes = os.path.getsize(final_path)
        db_execute("""
            UPDATE cms_media_library SET
                stored_path=%s,public_url=%s,poster_url=%s,size_bytes=%s,
                duration_seconds=%s,width=%s,height=%s,video_codec=%s,
                processing_status='ready',processing_error=NULL,updated_at=NOW()
            WHERE id=%s
        """, (
            final_stored, public_url, poster_url, size_bytes,
            meta.get("duration"), meta.get("width"), meta.get("height"), meta.get("codec"), media_id,
        ))
        if final_path != source_path:
            try:
                os.remove(source_path)
            except OSError:
                pass
        log.info(f"[CMS] video ready media_id={media_id} duration={meta.get('duration')} codec={meta.get('codec')}")
        return True
    except Exception as exc:
        safe_error = _mask_secrets(str(exc))[:1000]
        db_execute("""
            UPDATE cms_media_library SET processing_status='failed',processing_error=%s,updated_at=NOW()
            WHERE id=%s
        """, (safe_error, media_id))
        log.error(f"[CMS] video processing failed media_id={media_id}: {safe_error}")
        return False
    finally:
        _CMS_VIDEO_PROCESS_LOCK.release()


def _cms_process_pending_videos(limit=2):
    try:
        rows = db_execute("""
            SELECT id FROM cms_media_library
            WHERE media_type='video' AND deleted_at IS NULL
              AND processing_status IN ('pending','failed')
            ORDER BY created_at ASC LIMIT %s
        """, (limit,), fetch="all") or []
        for row in rows:
            if not _cms_process_video_media(int(row[0])):
                break
    except Exception as exc:
        log.warning(f"[CMS] pending video scan failed: {exc}")


def _cms_start_video_processing(media_id):
    threading.Thread(
        target=_cms_process_video_media,
        args=(int(media_id),),
        daemon=True,
        name=f"cms-video-{media_id}",
    ).start()


def _cms_register_media(stored_path, original_name, media_type, size_bytes, user=None,
                        source="dashboard", telegram_file_id=None):
    user = user or {}
    status = "pending" if media_type == "video" else "ready"
    public_url = _cms_media_public_path(stored_path)
    row = db_execute("""
        INSERT INTO cms_media_library
            (stored_path,original_name,public_url,media_type,size_bytes,uploaded_by,
             uploaded_by_email,processing_status,source,telegram_file_id,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (stored_path) DO UPDATE SET
            original_name=EXCLUDED.original_name,public_url=EXCLUDED.public_url,
            media_type=EXCLUDED.media_type,size_bytes=EXCLUDED.size_bytes,
            processing_status=EXCLUDED.processing_status,processing_error=NULL,
            source=EXCLUDED.source,telegram_file_id=COALESCE(EXCLUDED.telegram_file_id,cms_media_library.telegram_file_id),
            deleted_at=NULL,updated_at=NOW()
        RETURNING id
    """, (
        stored_path, original_name, public_url, media_type, int(size_bytes or 0),
        user.get("id"), user.get("email"), status, source, telegram_file_id,
    ), fetch="one")
    media_id = int(row[0]) if row else None
    if media_id and media_type == "video":
        _cms_start_video_processing(media_id)
    return media_id, public_url, status


def _cms_import_telegram_file(file_id, original_name="", media_type="video", user=None):
    """Download a Telegram file into the same persistent newsroom media library."""
    if not file_id:
        raise ValueError("Telegram file ID is missing.")
    existing = db_execute("""
        SELECT id,public_url,processing_status FROM cms_media_library
        WHERE telegram_file_id=%s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1
    """, (file_id,), fetch="one")
    if existing:
        return {"id": int(existing[0]), "url": existing[1], "status": existing[2], "existing": True}
    info = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
        params={"file_id": file_id}, timeout=30,
    )
    payload = info.json() if info.content else {}
    file_path = payload.get("result", {}).get("file_path")
    if not info.ok or not payload.get("ok") or not file_path:
        raise RuntimeError(str(payload.get("description") or "Telegram getFile failed.")[:300])
    download = requests.get(
        f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
        timeout=180, stream=True,
    )
    download.raise_for_status()
    ext = str(file_path).rsplit(".", 1)[-1].lower() if "." in str(file_path) else ""
    if media_type == "video" and ext not in _CMS_VIDEO_EXT:
        ext = "mp4"
    elif media_type == "image" and ext not in _CMS_IMAGE_EXT:
        ext = "jpg"
    media_type = "video" if media_type == "video" else "image"
    max_bytes = _CMS_VIDEO_MAX_BYTES if media_type == "video" else _CMS_IMAGE_MAX_BYTES
    stored = f"{datetime.utcnow().strftime('%Y/%m')}/telegram-{_uuid.uuid4().hex}.{ext}"
    full = _cms_media_full_path(stored)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    total = 0
    with open(full, "wb") as handle:
        for chunk in download.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                handle.close()
                os.remove(full)
                raise RuntimeError("Telegram file is too large for newsroom storage.")
            handle.write(chunk)
    name = _secure_filename(original_name or os.path.basename(file_path) or f"telegram.{ext}")
    media_id, public_url, status = _cms_register_media(
        stored, name, media_type, total, user=user, source="telegram", telegram_file_id=file_id,
    )
    _cms_audit("import_telegram_media", "media", media_id,
               new_value={"type": media_type, "status": status, "name": name}, user=user)
    return {"id": media_id, "url": public_url, "status": status, "existing": False}

def _cms_clean_media_items(items):
    clean = []
    if not isinstance(items, list):
        return clean
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        url = _cms_public_url(item.get("url"))
        if not url:
            continue
        media_type = "video" if str(item.get("type", "")).lower() == "video" else "image"
        try:
            position = max(0, min(200, int(item.get("position") or 0)))
        except Exception:
            position = 0
        clean.append({
            "type": media_type,
            "url": url,
            "poster": _cms_public_url(item.get("poster")),
            "caption": _api_clean_text(item.get("caption"), 500),
            "position": position,
        })
    return clean


def _cms_user_dict(row):
    if not row:
        return None
    return {
        "id": int(row[0]), "email": row[1], "name": row[2], "role": row[3],
        "author_id": row[4], "telegram_user_id": row[5], "active": bool(row[6]),
        "last_login": _cms_iso(row[7]), "created_at": _cms_iso(row[8]),
    }


def _cms_get_user(user_id):
    row = db_execute("""
        SELECT id, email, name, role, author_id, telegram_user_id, active, last_login, created_at
        FROM cms_users WHERE id=%s LIMIT 1
    """, (user_id,), fetch="one")
    return _cms_user_dict(row)


def _cms_issue_token(user):
    return _CMS_SERIALIZER.dumps({"uid": int(user["id"]), "email": user["email"]})


def _cms_token_user():
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = _CMS_SERIALIZER.loads(token, max_age=_CMS_TOKEN_MAX_AGE)
    except (_BadSignature, _SignatureExpired):
        return None
    user = _cms_get_user(payload.get("uid"))
    return user if user and user.get("active") else None


def _cms_require(*roles):
    allowed = set(roles)
    def deco(fn):
        @_wraps(fn)
        def wrapped(*args, **kwargs):
            user = _cms_token_user()
            if not user:
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            if allowed and user.get("role") not in allowed:
                return jsonify({"ok": False, "error": "permission denied"}), 403
            request.cms_user = user
            return fn(*args, **kwargs)
        return wrapped
    return deco


def _cms_audit(action, entity_type=None, entity_id=None, old_value=None, new_value=None, user=None):
    try:
        user = user or (getattr(request, "cms_user", None) if has_request_context() else None) or {}
        ip = ""
        if has_request_context():
            ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "")[:120]
        db_execute("""
            INSERT INTO cms_audit_log
                (user_id, user_email, action, entity_type, entity_id, old_value, new_value, ip_address)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
        """, (
            user.get("id"), user.get("email"), action, entity_type, str(entity_id or "") or None,
            json.dumps(old_value, ensure_ascii=False, default=str) if old_value is not None else None,
            json.dumps(new_value, ensure_ascii=False, default=str) if new_value is not None else None,
            ip,
        ))
    except Exception as exc:
        log.warning(f"[CMS] audit log failed: {exc}")


def _cms_seed_admin():
    """Create the first Super Admin from Railway environment variables.

    Required for first setup:
      CMS_ADMIN_EMAIL
      CMS_ADMIN_PASSWORD
    Optional:
      CMS_ADMIN_NAME (defaults to Abdul Muhsin)
    """
    email = os.environ.get("CMS_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("CMS_ADMIN_PASSWORD", "")
    name = os.environ.get("CMS_ADMIN_NAME", "Abdul Muhsin").strip() or "Samuga Admin"
    if not email or not password:
        log.info("[CMS] CMS_ADMIN_EMAIL/PASSWORD not set — dashboard login seed skipped")
        return False
    existing = db_execute("SELECT id FROM cms_users WHERE LOWER(email)=LOWER(%s)", (email,), fetch="one")
    if existing:
        return True
    row = db_execute("""
        INSERT INTO cms_users (email, name, password_hash, role, active)
        VALUES (%s,%s,%s,'super_admin',TRUE)
        RETURNING id
    """, (email, name, _generate_password_hash(password)), fetch="one")
    if not row:
        return False
    uid = int(row[0])
    author_id = f"cms_{uid}"
    db_execute("""
        INSERT INTO cms_authors (author_id, name, role, active)
        VALUES (%s,%s,'Founder & Managing Director',TRUE)
        ON CONFLICT (author_id) DO UPDATE SET name=EXCLUDED.name, active=TRUE, updated_at=NOW()
    """, (author_id, name))
    db_execute("UPDATE cms_users SET author_id=%s WHERE id=%s", (author_id, uid))
    log.info(f"[CMS] Super Admin created: {email}")
    return True



def _cms_normalize_person_name(value):
    return " ".join(str(value or "").strip().casefold().split())


def _cms_telegram_id_from_author(author_id, explicit=None):
    try:
        if explicit not in (None, ""):
            value = int(str(explicit).strip())
            return value if value > 0 else None
    except Exception:
        return None
    text = str(author_id or "").strip()
    if text.startswith("tg_"):
        try:
            value = int(text[3:])
            return value if value > 0 else None
        except Exception:
            return None
    return None


def _cms_author_is_linked(author_id, exclude_user_id=None):
    if not author_id:
        return False
    sql = "SELECT id FROM cms_users WHERE author_id=%s AND active=TRUE"
    params = [author_id]
    if exclude_user_id:
        sql += " AND id<>%s"
        params.append(exclude_user_id)
    sql += " LIMIT 1"
    return bool(db_execute(sql, tuple(params), fetch="one"))


def _cms_sync_author_articles(author_id, name, role, photo_url):
    if not author_id:
        return
    db_execute("""
        UPDATE articles
        SET author_name=%s, author_role=%s, author_photo_url=%s, updated_at=NOW()
        WHERE author_id=%s
    """, (name, role, photo_url, author_id))


def _cms_merge_author_profiles(old_author_id, new_author_id, user_id=None):
    """Move articles and a dashboard account from a duplicate CMS author to one canonical profile."""
    old_author_id = str(old_author_id or "").strip()
    new_author_id = str(new_author_id or "").strip()
    if not old_author_id or not new_author_id or old_author_id == new_author_id:
        return new_author_id or old_author_id
    target = db_execute("""
        SELECT author_id,name,role,photo_url,telegram_user_id
        FROM cms_authors WHERE author_id=%s LIMIT 1
    """, (new_author_id,), fetch="one")
    if not target:
        return old_author_id
    if _cms_author_is_linked(new_author_id, exclude_user_id=user_id):
        return old_author_id
    db_execute("""
        UPDATE articles
        SET author_id=%s, author_name=%s, author_role=%s, author_photo_url=%s, updated_at=NOW()
        WHERE author_id=%s
    """, (target[0], target[1], target[2], target[3], old_author_id))
    if user_id:
        db_execute("""
            UPDATE cms_users SET author_id=%s,telegram_user_id=%s,updated_at=NOW() WHERE id=%s
        """, (target[0], target[4] or _cms_telegram_id_from_author(target[0]), user_id))
    if old_author_id.startswith("cms_") and not _cms_author_is_linked(old_author_id):
        db_execute("UPDATE cms_authors SET active=FALSE,updated_at=NOW() WHERE author_id=%s", (old_author_id,))
    log.info(f"[CMS] Merged duplicate author {old_author_id} -> {new_author_id}")
    return new_author_id


def _cms_find_telegram_author_by_name(name, exclude_user_id=None):
    wanted = _cms_normalize_person_name(name)
    if not wanted:
        return None
    rows = db_execute("""
        SELECT author_id,name,role,photo_url,telegram_user_id
        FROM cms_authors
        WHERE active=TRUE AND (author_id LIKE 'tg_%' OR telegram_user_id IS NOT NULL)
        ORDER BY updated_at DESC NULLS LAST
    """, fetch="all") or []
    matches = [row for row in rows if _cms_normalize_person_name(row[1]) == wanted]
    available = [row for row in matches if not _cms_author_is_linked(row[0], exclude_user_id=exclude_user_id)]
    return available[0] if len(available) == 1 else None


def _cms_auto_link_user_author(user_id, name, current_author_id=None):
    """Safely reuse an exact matching Telegram author instead of creating a duplicate CMS profile."""
    current_author_id = str(current_author_id or "").strip()
    if current_author_id.startswith("tg_"):
        telegram_id = _cms_telegram_id_from_author(current_author_id)
        db_execute("UPDATE cms_users SET telegram_user_id=COALESCE(telegram_user_id,%s) WHERE id=%s", (telegram_id, user_id))
        db_execute("UPDATE cms_authors SET telegram_user_id=COALESCE(telegram_user_id,%s) WHERE author_id=%s", (telegram_id, current_author_id))
        return current_author_id
    match = _cms_find_telegram_author_by_name(name, exclude_user_id=user_id)
    if not match:
        return current_author_id
    if current_author_id:
        return _cms_merge_author_profiles(current_author_id, match[0], user_id=user_id)
    db_execute("""
        UPDATE cms_users SET author_id=%s,telegram_user_id=%s,updated_at=NOW() WHERE id=%s
    """, (match[0], match[4] or _cms_telegram_id_from_author(match[0]), user_id))
    return match[0]


def _cms_reconcile_all_user_authors():
    rows = db_execute("SELECT id,name,author_id FROM cms_users WHERE active=TRUE", fetch="all") or []
    for row in rows:
        try:
            _cms_auto_link_user_author(int(row[0]), row[1], row[2])
        except Exception as exc:
            log.warning(f"[CMS] author reconciliation failed for user {row[0]}: {exc}")


def _cms_can_access_article(user, created_by, author_id):
    if user.get("role") in _CMS_PUBLISH_ROLES:
        return True
    return bool((created_by and created_by == user.get("email")) or (author_id and author_id == user.get("author_id")))


@api_app.post("/api/admin/login")
def cms_login():
    allowed, retry_after = _cms_login_rate_state()
    if not allowed:
        response = jsonify({"ok": False, "error": "Too many sign-in attempts. Try again later."})
        response.headers["Retry-After"] = str(retry_after)
        return response, 429
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    row = db_execute("""
        SELECT id, email, name, password_hash, role, author_id, telegram_user_id, active, last_login, created_at
        FROM cms_users WHERE LOWER(email)=LOWER(%s) LIMIT 1
    """, (email,), fetch="one")
    if not row or not row[7] or not _check_password_hash(row[3], password):
        _cms_login_rate_state(record_failure=True)
        return jsonify({"ok": False, "error": "Invalid email or password."}), 401
    _cms_auto_link_user_author(int(row[0]), row[2], row[5])
    row = db_execute("""
        SELECT id, email, name, password_hash, role, author_id, telegram_user_id, active, last_login, created_at
        FROM cms_users WHERE id=%s LIMIT 1
    """, (row[0],), fetch="one") or row
    user = {
        "id": int(row[0]), "email": row[1], "name": row[2], "role": row[4],
        "author_id": row[5], "telegram_user_id": row[6], "active": bool(row[7]),
        "last_login": _cms_iso(row[8]), "created_at": _cms_iso(row[9]),
    }
    _cms_login_rate_state(clear=True)
    db_execute("UPDATE cms_users SET last_login=NOW() WHERE id=%s", (user["id"],))
    _cms_audit("login", "user", user["id"], new_value={"email": user["email"]}, user=user)
    return jsonify({"ok": True, "token": _cms_issue_token(user), "expires_in": _CMS_TOKEN_MAX_AGE, "user": user})


@api_app.get("/api/admin/me")
@_cms_require()
def cms_me():
    return jsonify({"ok": True, "user": request.cms_user})


@api_app.get("/api/admin/authors")
@_cms_require()
def cms_authors():
    user = request.cms_user
    _cms_reconcile_all_user_authors()
    include_inactive = str(request.args.get("all") or "").lower() in {"1", "true", "yes"}
    if include_inactive and user.get("role") not in {"admin", "super_admin"}:
        include_inactive = False
    where = "" if include_inactive else "WHERE a.active=TRUE"
    rows = db_execute(f"""
        SELECT a.author_id,a.name,a.role,a.photo_url,a.active,a.bio,a.telegram_user_id,
               COUNT(DISTINCT u.id),COUNT(DISTINCT ar.id)
        FROM cms_authors a
        LEFT JOIN cms_users u ON u.author_id=a.author_id AND u.active=TRUE
        LEFT JOIN articles ar ON ar.author_id=a.author_id
        {where}
        GROUP BY a.author_id,a.name,a.role,a.photo_url,a.active,a.bio,a.telegram_user_id
        ORDER BY a.active DESC,a.name
    """, fetch="all") or []
    return jsonify({"ok": True, "authors": [{
        "author_id": r[0], "name": r[1], "role": r[2], "photo_url": r[3],
        "active": bool(r[4]), "bio": r[5] or "", "telegram_user_id": r[6],
        "linked_users": int(r[7] or 0), "article_count": int(r[8] or 0),
        "source": "telegram" if str(r[0]).startswith("tg_") or r[6] else ("ai" if r[0] == "samuga_ai" else "dashboard"),
        "is_mine": r[0] == user.get("author_id"),
    } for r in rows]})


@api_app.post("/api/admin/authors")
@_cms_require()
def cms_author_save():
    actor = request.cms_user
    data = request.get_json(silent=True) or {}
    author_id = str(data.get("author_id") or actor.get("author_id") or "").strip()
    if not author_id:
        return jsonify({"ok": False, "error": "Author profile is not linked to this account."}), 400
    can_manage_all = actor.get("role") in {"admin", "super_admin"}
    if not can_manage_all and author_id != actor.get("author_id"):
        return jsonify({"ok": False, "error": "You can only edit your own author profile."}), 403
    old = db_execute("""
        SELECT author_id,name,role,photo_url,active,bio,telegram_user_id
        FROM cms_authors WHERE author_id=%s LIMIT 1
    """, (author_id,), fetch="one")
    if not old:
        return jsonify({"ok": False, "error": "Author profile not found."}), 404
    name = _api_clean_text(data.get("name"), 160) or old[1]
    public_role = _api_clean_text(data.get("role"), 160) if can_manage_all else old[2]
    public_role = public_role or old[2] or "Reporter"
    photo_url = _cms_public_url(data.get("photo_url")) if data.get("photo_url") is not None else old[3]
    bio = _api_clean_text(data.get("bio"), 1200) if data.get("bio") is not None else (old[5] or "")
    active = bool(data.get("active", old[4])) if can_manage_all else bool(old[4])
    telegram_user_id = _cms_telegram_id_from_author(author_id, data.get("telegram_user_id")) if can_manage_all else (old[6] or _cms_telegram_id_from_author(author_id))
    db_execute("""
        UPDATE cms_authors
        SET name=%s,role=%s,photo_url=%s,bio=%s,active=%s,telegram_user_id=%s,updated_at=NOW()
        WHERE author_id=%s
    """, (name, public_role, photo_url, bio, active, telegram_user_id, author_id))
    _cms_sync_author_articles(author_id, name, public_role, photo_url)
    db_execute("UPDATE cms_users SET name=%s,telegram_user_id=COALESCE(telegram_user_id,%s),updated_at=NOW() WHERE author_id=%s", (name, telegram_user_id, author_id))
    _cms_audit("update_author", "author", author_id,
               old_value={"name": old[1], "role": old[2], "photo_url": old[3], "active": bool(old[4])},
               new_value={"name": name, "role": public_role, "photo_url": photo_url, "active": active})
    return jsonify({"ok": True, "author": {
        "author_id": author_id, "name": name, "role": public_role, "photo_url": photo_url,
        "bio": bio, "active": active, "telegram_user_id": telegram_user_id,
    }})


@api_app.post("/api/admin/authors/delete")
@_cms_require("super_admin")
def cms_author_delete():
    """Delete a duplicate author safely, optionally moving dependencies first."""
    data = request.get_json(silent=True) or {}
    author_id = str(data.get("author_id") or "").strip()
    reassign_to = str(data.get("reassign_to") or "").strip() or None
    if not author_id:
        return jsonify({"ok": False, "error": "Author ID is required."}), 400
    if author_id == "samuga_ai":
        return jsonify({"ok": False, "error": "Samuga AI is a protected system author and cannot be deleted."}), 400
    source = db_execute("""
        SELECT author_id,name,role,photo_url FROM cms_authors WHERE author_id=%s LIMIT 1
    """, (author_id,), fetch="one")
    if not source:
        return jsonify({"ok": False, "error": "Author profile not found."}), 404
    counts = db_execute("""
        SELECT
          (SELECT COUNT(*) FROM articles WHERE author_id=%s),
          (SELECT COUNT(*) FROM cms_users WHERE author_id=%s)
    """, (author_id, author_id), fetch="one") or (0, 0)
    article_count, linked_users = int(counts[0] or 0), int(counts[1] or 0)
    target = None
    if reassign_to:
        if reassign_to == author_id:
            return jsonify({"ok": False, "error": "Choose a different author for reassignment."}), 400
        target = db_execute("""
            SELECT author_id,name,role,photo_url FROM cms_authors
            WHERE author_id=%s AND active=TRUE LIMIT 1
        """, (reassign_to,), fetch="one")
        if not target:
            return jsonify({"ok": False, "error": "The replacement author was not found or is inactive."}), 400
    if (article_count or linked_users) and not target:
        return jsonify({
            "ok": False,
            "error": "This author is still used. Choose another author to receive its articles and linked logins.",
            "requires_reassign": True,
            "article_count": article_count,
            "linked_users": linked_users,
        }), 409
    if target:
        db_execute("""
            UPDATE articles
            SET author_id=%s,author_name=%s,author_role=%s,author_photo_url=%s,updated_at=NOW()
            WHERE author_id=%s
        """, (target[0], target[1], target[2], target[3], author_id))
        db_execute("UPDATE cms_users SET author_id=%s,updated_at=NOW() WHERE author_id=%s", (target[0], author_id))
    deleted = db_execute("DELETE FROM cms_authors WHERE author_id=%s RETURNING author_id", (author_id,), fetch="one")
    if not deleted:
        return jsonify({"ok": False, "error": "The author could not be deleted."}), 500
    _cms_audit(
        "delete_author", "author", author_id,
        old_value={"name": source[1], "article_count": article_count, "linked_users": linked_users},
        new_value={"reassigned_to": target[0] if target else None},
    )
    return jsonify({
        "ok": True,
        "message": "Author deleted" + (f" and content moved to {target[1]}." if target else "."),
        "reassigned_to": target[0] if target else None,
    })


@api_app.get("/api/admin/dashboard")
@_cms_require()
def cms_dashboard():
    user = request.cms_user
    clauses = ["1=1"]
    params = []
    if user.get("role") not in _CMS_PUBLISH_ROLES:
        clauses.append("(created_by=%s OR author_id=%s)")
        params.extend([user.get("email"), user.get("author_id") or "__none__"])
    where = " AND ".join(clauses)
    row = db_execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE status IN ('posted','published','social_posted')),
            COUNT(*) FILTER (WHERE status='draft'),
            COUNT(*) FILTER (WHERE status='review'),
            COUNT(*) FILTER (WHERE status='scheduled'),
            COUNT(*) FILTER (WHERE status IN ('posted','published','social_posted')
                              AND COALESCE(posted_at,updated_at)::date=(NOW() AT TIME ZONE 'Indian/Maldives')::date),
            COUNT(*) FILTER (WHERE status='hidden')
        FROM articles WHERE {where}
    """, tuple(params), fetch="one") or (0,0,0,0,0,0)
    failure_row = db_execute("""
        SELECT COUNT(*) FROM cms_publish_jobs
        WHERE status='failed'
    """, fetch="one") if user.get("role") in _CMS_PUBLISH_ROLES else (0,)
    return jsonify({"ok": True, "stats": {
        "published": int(row[0] or 0), "drafts": int(row[1] or 0),
        "review": int(row[2] or 0), "scheduled": int(row[3] or 0),
        "today": int(row[4] or 0), "hidden": int(row[5] or 0),
        "failures": int((failure_row or (0,))[0] or 0),
    }})



# ═══════════════════════════════════════════════════════════════════════════════
# Build 15.8 — AI Usage & Diagnostics API
# ═══════════════════════════════════════════════════════════════════════════════

def _ai_usage_query_filters(args, alias="r", include_date=True):
    clauses = ["1=1"]
    params = []
    provider = str(args.get("provider") or "").strip()
    feature = str(args.get("feature") or "").strip()
    model = str(args.get("model") or "").strip()
    status = str(args.get("status") or "").strip()
    date_from = str(args.get("date_from") or "").strip()
    date_to = str(args.get("date_to") or "").strip()
    if date_from and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_from):
        date_from = ""
    if date_to and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_to):
        date_to = ""
    if provider:
        clauses.append(f"{alias}.provider=%s")
        params.append(provider)
    if feature:
        clauses.append(f"{alias}.feature=%s")
        params.append(feature)
    if model:
        clauses.append(f"{alias}.model=%s")
        params.append(model)
    if status:
        if status == "success":
            clauses.append(f"{alias}.status='success'")
        elif status == "error":
            clauses.append(f"{alias}.status='error'")
        elif status == "blocked":
            clauses.append(f"{alias}.status='blocked'")
        elif status == "pending":
            clauses.append(f"{alias}.status='pending'")
        elif status.isdigit():
            clauses.append(f"{alias}.http_status=%s")
            params.append(int(status))
    if include_date and date_from:
        clauses.append(f"{alias}.created_at >= %s::date")
        params.append(date_from)
    if include_date and date_to:
        clauses.append(f"{alias}.created_at < (%s::date + INTERVAL '1 day')")
        params.append(date_to)
    return " AND ".join(clauses), params


def _ai_usage_row_to_json(row):
    return {
        "id": int(row[0]), "request_id": row[1], "provider_request_id": row[2] or "",
        "provider": row[3], "feature": row[4], "model": row[5],
        "input_tokens": int(row[6] or 0), "output_tokens": int(row[7] or 0),
        "cached_tokens": int(row[8] or 0), "total_tokens": int((row[6] or 0) + (row[7] or 0)),
        "estimated_cost_usd": float(row[9] or 0), "duration_ms": int(row[10] or 0),
        "http_status": int(row[11] or 0), "status": row[12],
        "error_code": row[13] or "", "error_message": row[14] or "",
        "retry_count": int(row[15] or 0), "article_id": row[16] or "",
        "article_title": row[17] or "", "source_url": row[18] or "",
        "metadata": row[19] if isinstance(row[19], dict) else {},
        "created_at": row[20].isoformat() if row[20] else None,
    }


@api_app.get("/api/admin/ai-usage")
@_cms_require("editor", "admin", "super_admin")
def cms_ai_usage_summary():
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
    except Exception:
        days = 30
    where, params = _ai_usage_query_filters(request.args)
    range_where = where + " AND r.created_at >= NOW() - make_interval(days => %s)"
    range_params = tuple(params + [days])

    today = db_execute("""
        SELECT COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0),
               COUNT(*) FILTER (WHERE status='error'),
               COUNT(*) FILTER (WHERE status='blocked')
        FROM ai_usage_requests
        WHERE (created_at AT TIME ZONE 'Indian/Maldives')::date=
              (NOW() AT TIME ZONE 'Indian/Maldives')::date
    """, fetch="one") or (0,0,0,0,0)
    today_provider_rows = db_execute("""
        SELECT provider,COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0)
        FROM ai_usage_requests
        WHERE (created_at AT TIME ZONE 'Indian/Maldives')::date=
              (NOW() AT TIME ZONE 'Indian/Maldives')::date
        GROUP BY provider ORDER BY provider
    """, fetch="all") or []

    feature_rows = db_execute(f"""
        SELECT r.feature,COUNT(*),COALESCE(SUM(r.input_tokens+r.output_tokens),0),
               COALESCE(SUM(r.estimated_cost_usd),0),
               COUNT(*) FILTER (WHERE r.status='error')
        FROM ai_usage_requests r WHERE {range_where}
        GROUP BY r.feature ORDER BY COUNT(*) DESC,r.feature
    """, range_params, fetch="all") or []
    provider_rows = db_execute(f"""
        SELECT r.provider,COUNT(*),COALESCE(SUM(r.input_tokens+r.output_tokens),0),
               COALESCE(SUM(r.estimated_cost_usd),0),
               COUNT(*) FILTER (WHERE r.status='error'),
               COALESCE(AVG(r.duration_ms),0),
               COALESCE(SUM(r.cached_tokens),0)
        FROM ai_usage_requests r WHERE {range_where}
        GROUP BY r.provider ORDER BY COALESCE(SUM(r.estimated_cost_usd),0) DESC,r.provider
    """, range_params, fetch="all") or []
    top_rows = db_execute(f"""
        SELECT r.id,r.request_id,r.provider_request_id,r.provider,r.feature,r.model,
               r.input_tokens,r.output_tokens,r.cached_tokens,r.estimated_cost_usd,
               r.duration_ms,r.http_status,r.status,r.error_code,r.error_message,
               r.retry_count,r.article_id,r.article_title,r.source_url,r.metadata,r.created_at
        FROM ai_usage_requests r WHERE {range_where}
        ORDER BY r.estimated_cost_usd DESC,r.input_tokens+r.output_tokens DESC
        LIMIT 20
    """, range_params, fetch="all") or []
    error_rows = db_execute(f"""
        SELECT CASE
                 WHEN r.http_status=429 OR r.error_code='429' THEN '429'
                 WHEN r.http_status>=500 OR r.error_code='500' THEN '500'
                 WHEN r.error_code='timeout' THEN 'Timeout'
                 WHEN r.error_code='authentication' OR r.http_status IN (401,403) THEN 'Authentication'
                 WHEN r.error_code='invalid_request' OR r.http_status=400 THEN 'Invalid Request'
                 ELSE 'Unknown'
               END AS error_group,
               COUNT(*),MAX(r.created_at)
        FROM ai_usage_requests r
        WHERE {range_where} AND r.status='error'
        GROUP BY 1 ORDER BY COUNT(*) DESC
    """, range_params, fetch="all") or []
    daily_rows = db_execute(f"""
        SELECT (r.created_at AT TIME ZONE 'Indian/Maldives')::date AS day,
               COUNT(*),COALESCE(SUM(r.input_tokens+r.output_tokens),0),
               COALESCE(SUM(r.estimated_cost_usd),0),
               COUNT(*) FILTER (WHERE r.status='error')
        FROM ai_usage_requests r WHERE {range_where}
        GROUP BY 1 ORDER BY 1
    """, range_params, fetch="all") or []
    monthly_rows = db_execute("""
        SELECT provider,COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0),
               COUNT(*) FILTER (WHERE status='error')
        FROM ai_usage_requests
        WHERE date_trunc('month', created_at AT TIME ZONE 'Indian/Maldives')=
              date_trunc('month', NOW() AT TIME ZONE 'Indian/Maldives')
        GROUP BY provider ORDER BY provider
    """, fetch="all") or []
    alert_rows = db_execute("""
        SELECT id,alert_type,severity,title,detail,provider,feature,article_key,
               created_at,resolved_at,resolved_by
        FROM ai_usage_alerts WHERE resolved_at IS NULL
        ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END,created_at DESC
        LIMIT 50
    """, fetch="all") or []
    option_rows = db_execute("""
        SELECT 'provider',provider FROM ai_usage_requests WHERE created_at>=NOW()-INTERVAL '90 days' GROUP BY provider
        UNION ALL
        SELECT 'feature',feature FROM ai_usage_requests WHERE created_at>=NOW()-INTERVAL '90 days' GROUP BY feature
        UNION ALL
        SELECT 'model',model FROM ai_usage_requests WHERE created_at>=NOW()-INTERVAL '90 days' GROUP BY model
        ORDER BY 1,2
    """, fetch="all") or []
    options = {
        "providers": list(AI_USAGE_PROVIDERS),
        "features": list(AI_USAGE_FEATURES),
        "models": [],
    }
    for kind, value in option_rows:
        key = {"provider":"providers","feature":"features","model":"models"}.get(kind)
        if key and value not in options[key]: options[key].append(value)

    total_feature_requests = sum(int(r[1] or 0) for r in feature_rows) or 1
    feature_data = [{
        "feature":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),
        "cost":float(r[3] or 0),"errors":int(r[4] or 0),
        "percentage":round(int(r[1] or 0)/total_feature_requests*100,1),
    } for r in feature_rows]
    seen_features = {item["feature"] for item in feature_data}
    feature_data.extend({
        "feature": feature, "requests": 0, "tokens": 0, "cost": 0.0,
        "errors": 0, "percentage": 0.0,
    } for feature in AI_USAGE_FEATURES if feature not in seen_features)

    provider_data = [{
        "provider":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),
        "cost":float(r[3] or 0),"errors":int(r[4] or 0),
        "average_response_ms":int(float(r[5] or 0)),"cached_tokens":int(r[6] or 0),
    } for r in provider_rows]
    seen_providers = {item["provider"] for item in provider_data}
    provider_data.extend({
        "provider": provider, "requests": 0, "tokens": 0, "cost": 0.0,
        "errors": 0, "average_response_ms": 0, "cached_tokens": 0,
    } for provider in AI_USAGE_PROVIDERS if provider not in seen_providers)

    return jsonify({
        "ok": True, "days": days,
        "today": {
            "requests": int(today[0] or 0), "tokens": int(today[1] or 0),
            "cost": float(today[2] or 0), "errors": int(today[3] or 0),
            "blocked": int(today[4] or 0),
            "providers": [{"provider":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),"cost":float(r[3] or 0)} for r in today_provider_rows],
        },
        "features": feature_data,
        "providers": provider_data,
        "top_expensive": [_ai_usage_row_to_json(r) for r in top_rows],
        "errors": [{"group":r[0],"count":int(r[1] or 0),"last_at":r[2].isoformat() if r[2] else None} for r in error_rows],
        "daily": [{"day":r[0].isoformat(),"requests":int(r[1] or 0),"tokens":int(r[2] or 0),"cost":float(r[3] or 0),"errors":int(r[4] or 0)} for r in daily_rows],
        "monthly": [{"provider":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),"cost":float(r[3] or 0),"errors":int(r[4] or 0)} for r in monthly_rows],
        "alerts": [{
            "id":int(r[0]),"type":r[1],"severity":r[2],"title":r[3],"detail":r[4] or "",
            "provider":r[5] or "","feature":r[6] or "","article_key":r[7] or "",
            "created_at":r[8].isoformat() if r[8] else None,
        } for r in alert_rows],
        "options": options,
        "generated_at": utcnow().isoformat(),
    })


@api_app.get("/api/admin/ai-usage/requests")
@_cms_require("editor", "admin", "super_admin")
def cms_ai_usage_requests():
    try: limit = max(10, min(200, int(request.args.get("limit", 75))))
    except Exception: limit = 75
    try: offset = max(0, int(request.args.get("offset", 0)))
    except Exception: offset = 0
    where, params = _ai_usage_query_filters(request.args)
    total_row = db_execute(f"SELECT COUNT(*) FROM ai_usage_requests r WHERE {where}", tuple(params), fetch="one") or (0,)
    rows = db_execute(f"""
        SELECT r.id,r.request_id,r.provider_request_id,r.provider,r.feature,r.model,
               r.input_tokens,r.output_tokens,r.cached_tokens,r.estimated_cost_usd,
               r.duration_ms,r.http_status,r.status,r.error_code,r.error_message,
               r.retry_count,r.article_id,r.article_title,r.source_url,r.metadata,r.created_at
        FROM ai_usage_requests r WHERE {where}
        ORDER BY r.created_at DESC LIMIT %s OFFSET %s
    """, tuple(params + [limit, offset]), fetch="all") or []
    return jsonify({"ok":True,"requests":[_ai_usage_row_to_json(r) for r in rows],"total":int(total_row[0] or 0),"limit":limit,"offset":offset})


@api_app.post("/api/admin/ai-usage/alerts/resolve")
@_cms_require("admin", "super_admin")
def cms_ai_usage_alert_resolve():
    data = request.get_json(silent=True) or {}
    try: alert_id = int(data.get("id"))
    except Exception: return jsonify({"ok":False,"error":"Alert ID is required."}),400
    row = db_execute("""
        UPDATE ai_usage_alerts SET resolved_at=NOW(),resolved_by=%s
        WHERE id=%s AND resolved_at IS NULL RETURNING id
    """, (request.cms_user.get("email"), alert_id), fetch="one")
    if not row: return jsonify({"ok":False,"error":"Alert not found or already resolved."}),404
    return jsonify({"ok":True,"id":alert_id})


@api_app.get("/api/admin/provider-diagnostics")
@_cms_require("editor", "admin", "super_admin")
def cms_provider_diagnostics():
    coverage = db_execute("""
        SELECT MIN(created_at),MAX(created_at),COUNT(*)
        FROM ai_usage_requests
    """, fetch="one") or (None, None, 0)
    gemini_daily_rows = db_execute("""
        SELECT (created_at AT TIME ZONE 'Indian/Maldives')::date,model,
               COALESCE(metadata->>'provider_key_fingerprint',''),
               COALESCE(metadata->>'provider_key_masked',''),
               COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0),
               COUNT(*) FILTER(WHERE status='error'),
               COALESCE(SUM(retry_count),0)
        FROM ai_usage_requests WHERE provider='Gemini'
          AND created_at>=NOW()-INTERVAL '90 days'
        GROUP BY 1,2,3,4 ORDER BY 1 DESC,7 DESC
    """, fetch="all") or []
    gemini_feature_rows = db_execute("""
        SELECT feature,COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0),COUNT(*) FILTER(WHERE status='error'),
               COALESCE(SUM(retry_count),0)
        FROM ai_usage_requests WHERE provider='Gemini'
          AND created_at>=NOW()-INTERVAL '30 days'
        GROUP BY feature ORDER BY 4 DESC,2 DESC
    """, fetch="all") or []
    gemini_model_rows = db_execute("""
        SELECT model,COUNT(*),COALESCE(SUM(input_tokens+output_tokens),0),
               COALESCE(SUM(estimated_cost_usd),0),COUNT(*) FILTER(WHERE status='error')
        FROM ai_usage_requests WHERE provider='Gemini'
          AND created_at>=NOW()-INTERVAL '30 days'
        GROUP BY model ORDER BY 4 DESC,2 DESC
    """, fetch="all") or []
    gemini_key_rows = db_execute("""
        SELECT COALESCE(metadata->>'provider_key_fingerprint','unknown'),
               COALESCE(metadata->>'provider_key_masked','unknown'),COUNT(*),
               COALESCE(SUM(input_tokens+output_tokens),0),COALESCE(SUM(estimated_cost_usd),0)
        FROM ai_usage_requests WHERE provider='Gemini'
          AND created_at>=NOW()-INTERVAL '30 days'
        GROUP BY 1,2 ORDER BY 5 DESC
    """, fetch="all") or []
    gemini_data = _gemini_guard.dashboard(GEMINI_API_KEY)
    gemini_data.update({
        "daily_by_model_and_key": [{"day":r[0].isoformat(),"model":r[1],"key_fingerprint":r[2],"key_masked":r[3],"requests":int(r[4] or 0),"tokens":int(r[5] or 0),"cost":float(r[6] or 0),"errors":int(r[7] or 0),"retry_count":int(r[8] or 0)} for r in gemini_daily_rows],
        "by_feature_30d": [{"feature":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),"cost":float(r[3] or 0),"errors":int(r[4] or 0),"retry_count":int(r[5] or 0)} for r in gemini_feature_rows],
        "by_model_30d": [{"model":r[0],"requests":int(r[1] or 0),"tokens":int(r[2] or 0),"cost":float(r[3] or 0),"errors":int(r[4] or 0)} for r in gemini_model_rows],
        "by_key_30d": [{"key_fingerprint":r[0],"key_masked":r[1],"requests":int(r[2] or 0),"tokens":int(r[3] or 0),"cost":float(r[4] or 0)} for r in gemini_key_rows],
    })
    return jsonify({
        "ok": True,
        "gemini": gemini_data,
        "buffer": _buffer_diag.dashboard(),
        "coverage": {
            "telemetry_started_at": coverage[0].isoformat() if coverage[0] else None,
            "latest_request_at": coverage[1].isoformat() if coverage[1] else None,
            "recorded_ai_requests": int(coverage[2] or 0),
            "historical_limitation": (
                "Detailed per-feature history exists only from the first Build 15.8/15.9 telemetry row. "
                "July 13 billing attribution requires Google Billing export or authenticated Cloud Billing data."
            ),
        },
        "samuga_editorial_social_cap": {
            "enabled": os.environ.get("SAMUGA_SOCIAL_EDITORIAL_CAP_ENABLED", "true").lower() == "true",
            "day": _safe_env_int("SAMUGA_SOCIAL_EDITORIAL_CAP_DAY", 20, minimum=1, maximum=500),
            "night": _safe_env_int("SAMUGA_SOCIAL_EDITORIAL_CAP_NIGHT", 3, minimum=1, maximum=500),
            "note": "This is Samuga editorial pacing and is separate from Buffer plan/API limits.",
        },
        "generated_at": utcnow().isoformat(),
    })


@api_app.post("/api/admin/provider-diagnostics/action")
@_cms_require("admin", "super_admin")
def cms_provider_diagnostics_action():
    data = request.get_json(silent=True) or {}
    provider = str(data.get("provider") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()
    actor = str(request.cms_user.get("email") or "admin")

    if provider == "gemini":
        if action == "disable":
            minutes = max(5, min(10080, int(data.get("minutes") or 1440)))
            _gemini_guard.set_runtime_disabled(True, str(data.get("reason") or "manual_admin"), minutes=minutes, disabled_by=actor)
        elif action == "enable":
            _gemini_guard.set_runtime_disabled(False, disabled_by=actor)
        else:
            return jsonify({"ok": False, "error": "Unsupported Gemini action."}), 400
        _cms_audit("provider_guard_action", "provider", "Gemini", new_value={"action": action, "actor": actor})
        return jsonify({"ok": True, "gemini": _gemini_guard.dashboard(GEMINI_API_KEY)})

    if provider == "buffer":
        if action == "disable":
            minutes = max(5, min(10080, int(data.get("minutes") or 1440)))
            _buffer_diag.set_runtime_disabled(True, str(data.get("reason") or "manual_admin"), minutes=minutes, disabled_by=actor)
            result = {"disabled": True}
        elif action == "enable":
            _buffer_diag.set_runtime_disabled(False, disabled_by=actor)
            result = {"disabled": False}
        elif action == "reset_cooldown":
            _buffer_diag.reset_cooldown(disabled_by=actor)
            result = {"cooldown_reset": True}
        elif action == "test_connection":
            result = _buffer_diag.test_connection()
        elif action == "retry":
            idem = str(data.get("idempotency_key") or "").strip()
            if not idem:
                return jsonify({"ok": False, "error": "idempotency_key is required."}), 400
            ok, result = _buffer_diag.retry_publication(idem)
            if not ok:
                return jsonify({"ok": False, "error": result.get("error") or result.get("error_class") or "Retry failed.", "result": result}), 409
        elif action == "test_post":
            if str(data.get("confirmation") or "") != "BUFFER_TEST_POST":
                return jsonify({"ok": False, "error": "Type BUFFER_TEST_POST to confirm creating a real queued Buffer test post."}), 400
            channel_id = str(data.get("channel_id") or BUFFER_FB_ID or "").strip()
            if not channel_id:
                return jsonify({"ok": False, "error": "No Buffer test channel is configured."}), 400
            text = str(data.get("text") or f"Samuga Buffer diagnostics test — {mvt_now().strftime('%d %b %Y %H:%M MVT')}").strip()[:500]
            ok, result = _buffer_diag.create_post(
                text=text, channel_id=channel_id, channel_name=str(data.get("channel_name") or "Test channel"),
                social_network=str(data.get("social_network") or "test"),
                story_id=f"buffer_test_{_uuid.uuid4().hex[:12]}", mode="addToQueue",
            )
            if not ok:
                return jsonify({"ok": False, "error": result.get("error_class") or "Buffer test failed.", "result": result}), 502
        else:
            return jsonify({"ok": False, "error": "Unsupported Buffer action."}), 400
        _cms_audit("provider_guard_action", "provider", "Buffer", new_value={"action": action, "actor": actor})
        return jsonify({"ok": True, "result": result, "buffer": _buffer_diag.dashboard()})

    return jsonify({"ok": False, "error": "Provider must be Gemini or Buffer."}), 400


_CLOUDFLARE_ANALYTICS_CACHE = {"expires_at": 0.0, "key": "", "data": None}
_CLOUDFLARE_ANALYTICS_LOCK = threading.RLock()

def _cloudflare_zone_analytics(days):
    """Fetch Cloudflare zone request analytics server-side, with a short cache.

    This intentionally remains a separate metric from Samuga's browser pageview
    events. Cloudflare zone analytics measures edge requests and its own page-view
    and unique estimates, including historical data available before Build 11.
    """
    configured = bool(CLOUDFLARE_ZONE_ID and CLOUDFLARE_ANALYTICS_TOKEN)
    if not configured:
        return {
            "configured": False,
            "status": "not_configured",
            "message": "Add CLOUDFLARE_ZONE_ID and CLOUDFLARE_ANALYTICS_TOKEN in Railway to show Cloudflare historical analytics here.",
            "daily": [],
        }

    requested_days = max(1, min(365, int(days or 30)))
    days = min(requested_days, CLOUDFLARE_ANALYTICS_MAX_DAYS)
    end_day = datetime.now(_tz.utc).date()
    start_day = end_day - timedelta(days=days - 1)
    cache_key = f"{CLOUDFLARE_ZONE_ID}:{start_day}:{end_day}"
    with _CLOUDFLARE_ANALYTICS_LOCK:
        if (
            _CLOUDFLARE_ANALYTICS_CACHE.get("key") == cache_key
            and float(_CLOUDFLARE_ANALYTICS_CACHE.get("expires_at") or 0) > time.time()
            and _CLOUDFLARE_ANALYTICS_CACHE.get("data") is not None
        ):
            return json.loads(json.dumps(_CLOUDFLARE_ANALYTICS_CACHE["data"]))

    query = r'''
    query SamugaZoneAnalytics($zoneTag: string, $start: Date, $end: Date) {
      viewer {
        zones(filter: {zoneTag: $zoneTag}) {
          groups: httpRequests1dGroups(
            limit: 400,
            filter: {date_geq: $start, date_leq: $end}
          ) {
            dimensions { date }
            sum { requests pageViews }
            uniq { uniques }
          }
        }
      }
    }
    '''
    try:
        response = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_ANALYTICS_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "query": query,
                "variables": {
                    "zoneTag": CLOUDFLARE_ZONE_ID,
                    "start": start_day.isoformat(),
                    "end": end_day.isoformat(),
                },
            },
            timeout=(8, 30),
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors") or []
        if errors:
            message = str((errors[0] or {}).get("message") or "Cloudflare GraphQL returned an error.")
            raise RuntimeError(message)
        zones = (((payload.get("data") or {}).get("viewer") or {}).get("zones") or [])
        groups = (zones[0].get("groups") or []) if zones else []
        daily = []
        for item in groups:
            dimensions = item.get("dimensions") or {}
            sums = item.get("sum") or {}
            uniq = item.get("uniq") or {}
            day = str(dimensions.get("date") or "")[:10]
            if not day:
                continue
            daily.append({
                "day": day,
                "requests": int(sums.get("requests") or 0),
                "pageviews": int(sums.get("pageViews") or 0),
                "unique_visitors": int(uniq.get("uniques") or 0),
            })
        daily.sort(key=lambda item: item["day"])
        data = {
            "configured": True,
            "status": "ok",
            "source": "cloudflare_zone_analytics",
            "range": {
                "start": start_day.isoformat(), "end": end_day.isoformat(), "days": days,
                "requested_days": requested_days, "limited": days < requested_days,
            },
            "totals": {
                "requests": sum(item["requests"] for item in daily),
                "pageviews": sum(item["pageviews"] for item in daily),
                # Daily unique estimates cannot be safely summed into one exact
                # range-wide unique count. Keep the maximum daily value separate.
                "peak_daily_unique_visitors": max([item["unique_visitors"] for item in daily] or [0]),
            },
            "daily": daily,
            "message": "Cloudflare edge metrics are shown separately from Samuga browser events.",
            "fetched_at": datetime.now(_tz.utc).isoformat(),
        }
        with _CLOUDFLARE_ANALYTICS_LOCK:
            _CLOUDFLARE_ANALYTICS_CACHE.update({
                "expires_at": time.time() + 300,
                "key": cache_key,
                "data": data,
            })
        return json.loads(json.dumps(data))
    except Exception as exc:
        log.warning(f"[ANALYTICS][CLOUDFLARE] {_mask_secrets(str(exc))[:500]}")
        return {
            "configured": True,
            "status": "error",
            "message": "Cloudflare analytics could not be loaded. Verify the Zone ID and an API token with Zone Analytics Read permission.",
            "daily": [],
        }


@api_app.get("/api/admin/analytics")
@_cms_require("editor", "admin", "super_admin")
def cms_web_analytics():
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
    except Exception:
        days = 30
    interval = f"{days} days"
    totals = db_execute("""
        SELECT COUNT(*),COUNT(DISTINCT session_hash),
               COUNT(*) FILTER (WHERE (created_at AT TIME ZONE 'Indian/Maldives')::date=(NOW() AT TIME ZONE 'Indian/Maldives')::date),
               COUNT(DISTINCT session_hash) FILTER (WHERE (created_at AT TIME ZONE 'Indian/Maldives')::date=(NOW() AT TIME ZONE 'Indian/Maldives')::date)
        FROM cms_web_events
        WHERE event_type='pageview' AND created_at>=NOW()-INTERVAL %s
    """, (interval,), fetch="one") or (0,0,0,0)
    coverage = db_execute("""
        SELECT MIN(created_at),MAX(created_at),COUNT(*)
        FROM cms_web_events WHERE event_type='pageview'
    """, fetch="one") or (None,None,0)
    daily_rows = db_execute("""
        SELECT (created_at AT TIME ZONE 'Indian/Maldives')::date AS day,
               COUNT(*) AS views,COUNT(DISTINCT session_hash) AS visitors
        FROM cms_web_events
        WHERE event_type='pageview' AND created_at>=NOW()-INTERVAL %s
        GROUP BY day ORDER BY day
    """, (interval,), fetch="all") or []
    top_rows = db_execute("""
        SELECT COALESCE(NULLIF(a.title,''),NULLIF(e.path,''),'Page') AS label,
               e.article_id,e.path,COUNT(*) AS views,COUNT(DISTINCT e.session_hash) AS visitors
        FROM cms_web_events e
        LEFT JOIN articles a ON a.id=e.article_id
        WHERE e.event_type='pageview' AND e.created_at>=NOW()-INTERVAL %s
        GROUP BY label,e.article_id,e.path
        ORDER BY views DESC,visitors DESC LIMIT 15
    """, (interval,), fetch="all") or []
    ref_rows = db_execute("""
        SELECT COALESCE(NULLIF(referrer_host,''),'direct'),COUNT(*)
        FROM cms_web_events
        WHERE event_type='pageview' AND created_at>=NOW()-INTERVAL %s
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """, (interval,), fetch="all") or []
    device_rows = db_execute("""
        SELECT COALESCE(NULLIF(device_type,''),'unknown'),COUNT(*)
        FROM cms_web_events
        WHERE event_type='pageview' AND created_at>=NOW()-INTERVAL %s
        GROUP BY 1 ORDER BY 2 DESC
    """, (interval,), fetch="all") or []
    language_rows = db_execute("""
        SELECT COALESCE(NULLIF(language,''),'unknown'),COUNT(*)
        FROM cms_web_events
        WHERE event_type='pageview' AND created_at>=NOW()-INTERVAL %s
        GROUP BY 1 ORDER BY 2 DESC
    """, (interval,), fetch="all") or []

    # Return every day in the requested window, including zero days. This makes
    # the chart honest and visually stable when tracking has only just started.
    today_mvt = (utcnow() + timedelta(hours=5)).date()
    first_day = today_mvt - timedelta(days=days - 1)
    daily_map = {r[0].isoformat(): {"views": int(r[1] or 0), "visitors": int(r[2] or 0)} for r in daily_rows}
    daily = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        values = daily_map.get(day.isoformat(), {"views": 0, "visitors": 0})
        daily.append({"day": day.isoformat(), **values})

    def _iso(value):
        try:
            return value.isoformat() if value else None
        except Exception:
            return None

    first_event_at = coverage[0]
    tracking_days = 0
    if first_event_at:
        try:
            first_mvt_day = (first_event_at.astimezone(_tz.utc).replace(tzinfo=None) + timedelta(hours=5)).date() if getattr(first_event_at, "tzinfo", None) else (first_event_at + timedelta(hours=5)).date()
            tracking_days = max(1, (today_mvt - first_mvt_day).days + 1)
        except Exception:
            tracking_days = 1

    return jsonify({
        "ok": True, "days": days, "source": "samuga_first_party_pageviews",
        "totals": {"views": int(totals[0] or 0), "visitors": int(totals[1] or 0),
                   "today_views": int(totals[2] or 0), "today_visitors": int(totals[3] or 0)},
        "coverage": {"first_event_at": _iso(coverage[0]), "last_event_at": _iso(coverage[1]),
                     "lifetime_events": int(coverage[2] or 0), "tracking_days": tracking_days},
        "daily": daily,
        "top_pages": [{"label": r[0], "article_id": r[1], "path": r[2], "views": int(r[3] or 0), "visitors": int(r[4] or 0)} for r in top_rows],
        "referrers": [{"name": r[0], "views": int(r[1] or 0)} for r in ref_rows],
        "devices": [{"name": r[0], "views": int(r[1] or 0)} for r in device_rows],
        "languages": [{"name": r[0], "views": int(r[1] or 0)} for r in language_rows],
        "privacy": "Samuga Analytics counts browser page loads recorded after tracking was deployed. No raw IP addresses are stored; browser identifiers are irreversibly hashed.",
        "comparison_note": "Cloudflare Zone Analytics counts edge requests and its own page-view/visitor estimates, while Samuga Analytics counts browser page-load events recorded after Build 11. They are intentionally shown as separate sources and will not match exactly.",
        "cloudflare": _cloudflare_zone_analytics(days),
    })

@api_app.get("/api/admin/articles")
@_cms_require()
def cms_articles():
    user = request.cms_user
    q = str(request.args.get("q") or "").strip()
    status = str(request.args.get("status") or "").strip().lower()
    try:
        limit = max(1, min(200, int(request.args.get("limit", 100))))
    except Exception:
        limit = 100
    clauses = ["1=1"]
    params = []
    if q:
        clauses.append("(title ILIKE %s OR article_body ILIKE %s OR summary ILIKE %s)")
        like = f"%{q[:120]}%"
        params.extend([like, like, like])
    if status:
        if status == "posted":
            clauses.append("status IN ('posted','published','social_posted')")
        else:
            clauses.append("status=%s")
            params.append(status)
    if user.get("role") not in _CMS_PUBLISH_ROLES:
        clauses.append("(created_by=%s OR author_id=%s)")
        params.extend([user.get("email"), user.get("author_id") or "__none__"])
    params.append(limit)
    rows = db_execute(f"""
        SELECT id, title, status, category, lang, author_name, author_id,
               posted_at, updated_at, created_by, featured, is_breaking,
               scheduled_at, social_status, last_social_share_at
        FROM articles
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(updated_at, posted_at, found_at) DESC NULLS LAST
        LIMIT %s
    """, tuple(params), fetch="all") or []
    return jsonify({"ok": True, "articles": [{
        "id": r[0], "title": r[1],
        "status": ("posted" if (r[2] in {"posted", "published", "social_posted"} or (r[2] == "queued" and r[4] == "en")) else r[2]),
        "category": r[3], "lang": r[4],
        "author_name": r[5], "author_id": r[6], "posted_at": _cms_iso(r[7]),
        "updated_at": _cms_iso(r[8]), "created_by": r[9], "featured": bool(r[10]),
        "breaking": bool(r[11]), "scheduled_at": _cms_iso(r[12]),
        "social_status": _cms_json_dict(r[13]), "last_social_share_at": _cms_iso(r[14]),
    } for r in rows]})


@api_app.get("/api/admin/article")
@_cms_require()
def cms_get_article():
    article_id = str(request.args.get("id") or "").strip()
    row = db_execute("""
        SELECT id, title, summary, article_excerpt, article_body, category, lang, status,
               article_slug, is_breaking, featured, cover_image_url, cover_video_url,
               video_poster_url, cover_caption, media_items, social_caption,
               author_id, author_name, author_role, author_photo_url,
               reading_time_min, posted_at, updated_at, created_by, published_by,
               scheduled_at, share_targets, social_status, last_social_share_at
        FROM articles WHERE id=%s LIMIT 1
    """, (article_id,), fetch="one")
    if not row:
        return jsonify({"ok": False, "error": "Article not found."}), 404
    if not _cms_can_access_article(request.cms_user, row[24], row[17]):
        return jsonify({"ok": False, "error": "permission denied"}), 403
    return jsonify({"ok": True, "article": {
        "id": row[0], "title": row[1], "summary": row[2], "excerpt": row[3], "body": row[4],
        "category": row[5], "lang": row[6],
        "status": ("posted" if (row[7] in {"posted", "published", "social_posted"} or (row[7] == "queued" and row[6] == "en")) else row[7]),
        "slug": row[8],
        "breaking": bool(row[9]), "featured": bool(row[10]), "cover_image": row[11],
        "cover_video": row[12], "video_poster": row[13], "cover_caption": row[14],
        "media_items": row[15] or [], "social_caption": row[16] or "", "author_id": row[17],
        "author_name": row[18], "author_role": row[19], "author_photo": row[20],
        "reading_time": row[21], "posted_at": _cms_iso(row[22]), "updated_at": _cms_iso(row[23]),
        "created_by": row[24], "published_by": row[25],
        "scheduled_at": _cms_iso(row[26]), "share_targets": _cms_json_dict(row[27]),
        "social_status": _cms_json_dict(row[28]), "last_social_share_at": _cms_iso(row[29]),
    }})


@api_app.post("/api/admin/article")
@_cms_require()
def cms_save_article():
    user = request.cms_user
    data = request.get_json(silent=True) or {}
    title = _api_clean_text(data.get("title"), 500)
    excerpt = _api_clean_text(data.get("excerpt") or data.get("summary"), 1800)
    body = str(data.get("body") or "").strip()[:30000]
    if not title or not body:
        return jsonify({"ok": False, "error": "Headline and body are required."}), 400

    lang = "dv" if str(data.get("lang")).lower() == "dv" else "en"
    category = _api_category(data.get("category") or "LOCAL", title, excerpt)
    status = str(data.get("status") or "draft").lower()
    if status not in {"draft", "review", "posted", "hidden", "scheduled"}:
        status = "draft"
    if status in {"posted", "hidden", "scheduled"} and user.get("role") not in _CMS_PUBLISH_ROLES:
        return jsonify({"ok": False, "error": "Only editors and administrators can publish, schedule or hide articles."}), 403

    scheduled_at = _cms_parse_datetime(data.get("scheduled_at")) if status == "scheduled" else None
    if status == "scheduled":
        if not scheduled_at:
            return jsonify({"ok": False, "error": "Choose a valid publishing date and time."}), 400
        if scheduled_at <= datetime.now(timezone.utc) + timedelta(seconds=30):
            return jsonify({"ok": False, "error": "Scheduled publishing time must be in the future."}), 400

    # The same final entity-safety guard used by automatic publishing also protects
    # manual newsroom publishing. Drafts remain editable even when incomplete.
    if status in {"posted", "scheduled"} and lang == "en":
        consistent, reason = website_article_body_is_consistent(title, excerpt, body)
        if not consistent:
            return jsonify({
                "ok": False,
                "error": "Headline and article body appear inconsistent.",
                "detail": reason,
            }), 400

    article_id = str(data.get("id") or "").strip()
    old = None
    if article_id:
        old = db_execute("""
            SELECT id, title, status, created_by, author_id, article_body
            FROM articles WHERE id=%s LIMIT 1
        """, (article_id,), fetch="one")
        if not old:
            return jsonify({"ok": False, "error": "Article not found."}), 404
        if not _cms_can_access_article(user, old[3], old[4]):
            return jsonify({"ok": False, "error": "permission denied"}), 403
        old_is_public = old[2] in {"posted", "published", "social_posted"} or old[2] == "queued"
        if old_is_public and user.get("role") not in _CMS_PUBLISH_ROLES:
            return jsonify({"ok": False, "error": "Published articles can only be changed by an editor or administrator."}), 403
    else:
        seed = f"{title}|{user.get('email')}|{time.time_ns()}"
        article_id = "manualcms_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:18]

    requested_author = str(data.get("author_id") or "").strip()
    if user.get("role") not in _CMS_PUBLISH_ROLES and user.get("author_id"):
        requested_author = user.get("author_id")
    author = db_execute("""
        SELECT author_id, name, role, photo_url FROM cms_authors
        WHERE author_id=%s AND active=TRUE LIMIT 1
    """, (requested_author,), fetch="one") if requested_author else None
    if not author:
        author_id = user.get("author_id") or f"cms_{user.get('id')}"
        db_execute("""
            INSERT INTO cms_authors (author_id, name, role, active)
            VALUES (%s,%s,%s,TRUE)
            ON CONFLICT (author_id) DO UPDATE SET name=EXCLUDED.name, active=TRUE, updated_at=NOW()
        """, (author_id, user.get("name"), "Reporter"))
        db_execute("UPDATE cms_users SET author_id=%s WHERE id=%s AND author_id IS NULL", (author_id, user.get("id")))
        author = (author_id, user.get("name"), "Reporter", None)

    cover_image = _cms_public_url(data.get("cover_image"))
    cover_video = _cms_public_url(data.get("cover_video"))
    video_poster = _cms_public_url(data.get("video_poster"))
    media_items = _cms_clean_media_items(data.get("media_items"))
    cover_caption = _api_clean_text(data.get("cover_caption"), 500)
    social_caption = str(data.get("social_caption") or "").strip()[:1200]
    featured = bool(data.get("featured"))
    breaking = bool(data.get("breaking")) or category == "BREAKING"
    reading_time = compute_reading_time(body)
    seo = auto_seo(title, excerpt or body[:300], category, lang)
    slug = make_article_slug(title, article_id)
    created_by = old[3] if old and old[3] else user.get("email")
    published_by = user.get("email") if status in {"posted", "scheduled"} else None
    requested_share = data.get("share") if isinstance(data.get("share"), dict) else {}
    share_targets = {p: bool(requested_share.get(p)) for p in ("telegram", "facebook", "x")}

    saved_article = db_execute("""
        INSERT INTO articles
            (id,title,summary,article_excerpt,article_body,category,lang,status,source,link,
             article_slug,is_breaking,featured,cover_image_url,cover_video_url,video_poster_url,
             cover_caption,media_items,social_caption,author_id,author_name,author_role,
             author_photo_url,reading_time_min,seo_title,seo_description,created_by,published_by,
             scheduled_at,share_targets,found_at,posted_at,updated_at,article_generated_at)
        VALUES
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,
             %s,%s,%s,%s,%s,%s,%s::jsonb,NOW(),CASE WHEN %s='posted' THEN NOW() ELSE NULL END,NOW(),NOW())
        ON CONFLICT (id) DO UPDATE SET
            title=EXCLUDED.title, summary=EXCLUDED.summary, article_excerpt=EXCLUDED.article_excerpt,
            article_body=EXCLUDED.article_body, category=EXCLUDED.category, lang=EXCLUDED.lang,
            status=EXCLUDED.status, article_slug=EXCLUDED.article_slug,
            is_breaking=EXCLUDED.is_breaking, featured=EXCLUDED.featured,
            cover_image_url=EXCLUDED.cover_image_url, cover_video_url=EXCLUDED.cover_video_url,
            video_poster_url=EXCLUDED.video_poster_url, cover_caption=EXCLUDED.cover_caption,
            media_items=EXCLUDED.media_items, social_caption=EXCLUDED.social_caption,
            author_id=EXCLUDED.author_id, author_name=EXCLUDED.author_name,
            author_role=EXCLUDED.author_role, author_photo_url=EXCLUDED.author_photo_url,
            reading_time_min=EXCLUDED.reading_time_min, seo_title=EXCLUDED.seo_title,
            seo_description=EXCLUDED.seo_description,
            created_by=COALESCE(articles.created_by,EXCLUDED.created_by),
            published_by=CASE WHEN EXCLUDED.status IN ('posted','scheduled') THEN EXCLUDED.published_by ELSE articles.published_by END,
            scheduled_at=EXCLUDED.scheduled_at, share_targets=EXCLUDED.share_targets,
            posted_at=CASE WHEN EXCLUDED.status='posted' THEN COALESCE(articles.posted_at,NOW()) ELSE articles.posted_at END,
            updated_at=NOW()
        RETURNING id
    """, (
        article_id, title, excerpt, excerpt, body, category, lang, status,
        SAMUGA_PUBLIC_SOURCE, SAMUGA_PUBLIC_LINK, slug, breaking, featured,
        cover_image, cover_video, video_poster, cover_caption,
        json.dumps(media_items, ensure_ascii=False), social_caption,
        author[0], author[1], author[2], author[3], reading_time,
        seo["meta_title"], seo["meta_description"], created_by, published_by,
        scheduled_at, json.dumps(share_targets), status,
    ), fetch="one")
    if not saved_article:
        return jsonify({"ok": False, "error": "The article could not be saved. Check the database connection and try again."}), 500

    snapshot = {
        "title": title, "excerpt": excerpt, "body": body, "category": category,
        "lang": lang, "status": status, "featured": featured, "breaking": breaking,
        "cover_image": cover_image, "cover_video": cover_video, "video_poster": video_poster,
        "cover_caption": cover_caption, "media_items": media_items,
        "social_caption": social_caption, "author_id": author[0],
        "scheduled_at": _cms_iso(scheduled_at), "share_targets": share_targets,
    }
    revision = _cms_store_revision(article_id, snapshot, user=user)

    _cms_audit(
        "update_article" if old else "create_article", "article", article_id,
        old_value={"title": old[1], "status": old[2]} if old else None,
        new_value={
            "title": title, "status": status, "lang": lang, "category": category,
            "scheduled_at": _cms_iso(scheduled_at),
            "revision": revision.get("revision_no") if revision else None,
        },
    )

    share_jobs = []
    if status == "posted" and user.get("role") in _CMS_PUBLISH_ROLES:
        selected_platforms = [platform for platform in ("telegram", "facebook", "x") if share_targets.get(platform)]
        if selected_platforms:
            share_jobs = _cms_queue_social_jobs(article_id, selected_platforms, social_caption, user=user)

    messages = {
        "posted": "Article published.",
        "scheduled": "Article scheduled.",
        "review": "Article submitted for review.",
        "hidden": "Article hidden.",
        "draft": "Draft saved.",
    }
    return jsonify({
        "ok": True,
        "message": messages.get(status, "Article saved."),
        "article": {
            "id": article_id, "status": status, "slug": slug,
            "scheduled_at": _cms_iso(scheduled_at),
        },
        "revision": revision,
        "share_jobs": share_jobs,
        "social_status": _cms_latest_social_status(article_id),
    })


@api_app.post("/api/admin/article/delete")
@_cms_require("super_admin")
def cms_delete_article():
    data = request.get_json(silent=True) or {}
    article_id = str(data.get("id") or "").strip()
    if not article_id:
        return jsonify({"ok": False, "error": "Article ID is required."}), 400
    old = db_execute("""
        SELECT id,title,status,author_id,author_name,created_by,cover_image_url,cover_video_url
        FROM articles WHERE id=%s LIMIT 1
    """, (article_id,), fetch="one")
    if not old:
        return jsonify({"ok": False, "error": "Article not found."}), 404
    # Delete newsroom records first. Uploaded media is intentionally kept in the
    # media library because the same file may be reused by another article.
    db_execute("DELETE FROM cms_publish_jobs WHERE article_id=%s", (article_id,))
    db_execute("DELETE FROM cms_social_log WHERE article_id=%s", (article_id,))
    db_execute("DELETE FROM cms_article_revisions WHERE article_id=%s", (article_id,))
    db_execute("DELETE FROM story_updates WHERE article_id=%s", (article_id,))
    deleted = db_execute("DELETE FROM articles WHERE id=%s RETURNING id", (article_id,), fetch="one")
    if not deleted:
        return jsonify({"ok": False, "error": "The article could not be deleted."}), 500
    _cms_audit("delete_article", "article", article_id, old_value={
        "title": old[1], "status": old[2], "author_id": old[3],
        "author_name": old[4], "created_by": old[5],
    })
    return jsonify({"ok": True, "message": "Article permanently deleted.", "id": article_id})


@api_app.get("/api/admin/revisions")
@_cms_require()
def cms_article_revisions():
    article_id = str(request.args.get("id") or "").strip()
    if not article_id:
        return jsonify({"ok": False, "error": "Article ID is required."}), 400
    owner = db_execute("SELECT created_by,author_id FROM articles WHERE id=%s", (article_id,), fetch="one")
    if not owner:
        return jsonify({"ok": False, "error": "Article not found."}), 404
    if not _cms_can_access_article(request.cms_user, owner[0], owner[1]):
        return jsonify({"ok": False, "error": "permission denied"}), 403
    rows = db_execute("""
        SELECT id,revision_no,snapshot,created_email,created_at
        FROM cms_article_revisions
        WHERE article_id=%s ORDER BY revision_no DESC LIMIT 40
    """, (article_id,), fetch="all") or []
    return jsonify({"ok": True, "revisions": [{
        "id": int(r[0]), "revision_no": int(r[1]), "snapshot": r[2] or {},
        "created_email": r[3], "created_at": _cms_iso(r[4]),
    } for r in rows]})


@api_app.post("/api/admin/share")
@_cms_require("editor", "admin", "super_admin")
def cms_share_article():
    data = request.get_json(silent=True) or {}
    article_id = str(data.get("id") or "").strip()
    platforms = data.get("platforms") if isinstance(data.get("platforms"), list) else []
    platforms = [str(p).lower() for p in platforms if str(p).lower() in {"telegram", "facebook", "x"}]
    caption = str(data.get("caption") or "").strip()[:1200]
    if not article_id or not platforms:
        return jsonify({"ok": False, "error": "Choose an article and at least one platform."}), 400
    row = db_execute("SELECT status,social_caption FROM articles WHERE id=%s", (article_id,), fetch="one")
    if not row:
        return jsonify({"ok": False, "error": "Article not found."}), 404
    is_public = row[0] in {"posted", "published", "social_posted"} or row[0] == "queued"
    if not is_public:
        return jsonify({"ok": False, "error": "Publish the article before sharing it."}), 400
    caption = caption or str(row[1] or "")[:1200]
    jobs = _cms_queue_social_jobs(article_id, platforms, caption, user=request.cms_user)
    _cms_audit("queue_share", "article", article_id,
               new_value={"platforms": platforms, "job_ids": [job["id"] for job in jobs]})
    return jsonify({
        "ok": True,
        "message": "Publishing jobs queued.",
        "jobs": jobs,
        "social_status": _cms_latest_social_status(article_id),
    })


@api_app.get("/api/admin/social-log")
@_cms_require("editor", "admin", "super_admin")
def cms_social_log():
    article_id = str(request.args.get("id") or "").strip()
    params = []
    where = "1=1"
    if article_id:
        where = "article_id=%s"
        params.append(article_id)
    rows = db_execute(f"""
        SELECT id,article_id,platform,status,message,caption,created_at
        FROM cms_social_log WHERE {where}
        ORDER BY created_at DESC LIMIT 100
    """, tuple(params), fetch="all") or []
    return jsonify({"ok": True, "events": [{
        "id": int(r[0]), "article_id": r[1], "platform": r[2], "status": r[3],
        "message": r[4], "caption": r[5], "created_at": _cms_iso(r[6]),
    } for r in rows]})




@api_app.get("/api/admin/content-lab")
@_cms_require("editor", "admin", "super_admin")
def cms_content_lab_list():
    with _approval_lock:
        pending = [(key, dict(item)) for key, item in approval_queue.items()
                   if not item.get("_content_lab_suppressed")]
    pending.sort(key=lambda pair: pair[1].get("created_at") or utcnow(), reverse=True)
    items = []
    for key, item in pending:
        _content_lab_db_upsert(key, item, status="pending")
        items.append(_content_lab_public_item(key, item))
    try:
        rows = db_execute("""
            SELECT card_key,title,status,action,action_by,action_origin,created_at,updated_at,actioned_at
            FROM cms_content_lab_items
            WHERE status <> 'pending'
            ORDER BY COALESCE(actioned_at,updated_at,created_at) DESC LIMIT 40
        """, fetch="all") or []
    except Exception as exc:
        log.debug(f"[CONTENT LAB] history unavailable: {exc}")
        rows = []
    history = [{
        "key": row[0], "title": row[1], "status": row[2], "action": row[3],
        "actor": row[4], "origin": row[5], "created_at": _cms_iso(row[6]),
        "updated_at": _cms_iso(row[7]), "actioned_at": _cms_iso(row[8]),
    } for row in rows]
    return jsonify({
        "ok": True,
        "build": "15.6",
        "sync_mode": "shared_approval_queue_editor_lock",
        "telegram_linked": bool(TELEGRAM_BOT_TOKEN and CORE_TEAM_CHAT_ID and CONTENT_LAB_THREAD_ID),
        "server_time": _cms_iso(utcnow()),
        "items": items,
        "history": history,
        "counts": {
            "pending": len(items),
            "english": sum(1 for item in items if item["lang"] == "en"),
            "dhivehi": sum(1 for item in items if item["lang"] == "dv"),
            "breaking": sum(1 for item in items if item["breaking"]),
        },
    })


@api_app.get("/api/admin/content-lab/card")
@_cms_require("editor", "admin", "super_admin")
def cms_content_lab_card():
    key = str(request.args.get("key") or "").strip().lower()
    with _approval_lock:
        item = approval_queue.get(key)
        card = item.get("card_bytes") if item else None
        if item is not None and not card:
            try:
                card = _content_lab_build_card_bytes(item)
            except Exception as exc:
                log.warning(f"[CONTENT LAB] card rebuild failed for {key}: {exc}")
                card = None
        if card:
            _content_lab_remember_card(key, item or {"card_bytes": card})
    if not card:
        with _content_lab_card_cache_lock:
            card = _content_lab_card_cache.get(key)
    if not card:
        return jsonify({"ok": False, "error": "Card preview is unavailable."}), 404
    from flask import Response
    return Response(card, 200, mimetype="image/png",
                    headers={"Content-Disposition": f'inline; filename="{key}.png"'})


@api_app.post("/api/admin/content-lab/action")
@_cms_require("editor", "admin", "super_admin")
def cms_content_lab_action():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()
    corrected_title = str(data.get("corrected_title") or "").strip()
    corrected_paragraph = str(data.get("corrected_paragraph") or "").strip()
    if corrected_title or corrected_paragraph:
        corrected = {"headline": corrected_title, "paragraph": corrected_paragraph}
    else:
        corrected = str(data.get("corrected") or "").strip() or None
    actor = request.cms_user.get("name") or request.cms_user.get("email") or "Newsroom team"
    result = _content_lab_take_action(
        key, action, actor=actor, corrected=corrected, origin="dashboard", background=True)
    if not result.get("ok"):
        return jsonify(result), 409
    _cms_audit("content_lab_action", "content_lab", key,
               new_value={"action": action, "corrected": bool(corrected), "origin": "dashboard"})
    return jsonify(result)


def _cms_social_card_caption(headline, paragraph, category):
    cat = str(category or "LOCAL").upper()
    emoji = {
        "BREAKING":"🚨", "LOCAL":"🇲🇻", "POLITICAL":"🏛️", "BUSINESS":"💼",
        "WORLD":"🌍", "SPORTS":"🏅", "LIFESTYLE":"🌴", "WEATHER":"🌤️",
        "TOURISM":"✈️",
    }.get(cat, "📰")
    prefix = "🚨 <b>BREAKING NEWS</b>\n\n" if cat == "BREAKING" else ""
    body = str(headline or "").strip()
    if str(paragraph or "").strip():
        body += "\n\n" + str(paragraph).strip()
    return prefix + emoji + " " + body + "\n\n📡 <b>Samuga Media</b> | @samugacommunity"


def _cms_social_card_record(row):
    if not row:
        return None
    return {
        "card_id": row[0], "headline": row[1], "paragraph": row[2] or "",
        "category": row[3], "lang": row[4], "image_url": row[5],
        "card_url": row[6], "caption": row[7], "status": row[8],
        "destinations": _cms_json_dict(row[9]), "created_at": _cms_iso(row[10]),
        "posted_at": _cms_iso(row[11]), "created_email": row[12],
    }


@api_app.get("/api/admin/social-cards")
@_cms_require("editor", "admin", "super_admin")
def cms_social_cards_list():
    rows = db_execute("""
        SELECT card_id,headline,paragraph,category,lang,source_image_url,card_url,caption,
               status,destinations,created_at,posted_at,created_email
        FROM cms_social_cards ORDER BY created_at DESC LIMIT 30
    """, fetch="all") or []
    return jsonify({"ok": True, "cards": [_cms_social_card_record(row) for row in rows]})


@api_app.post("/api/admin/social-card/create")
@_cms_require("editor", "admin", "super_admin")
def cms_social_card_create():
    data = request.get_json(silent=True) or {}
    headline = _api_clean_text(data.get("headline"), 220)
    paragraph = _api_clean_text(data.get("paragraph"), 600)
    category = _api_category(data.get("category") or "LOCAL", headline, paragraph)
    image_url = str(data.get("image_url") or "").strip()
    if not headline:
        return jsonify({"ok": False, "error": "Headline is required."}), 400
    if not public_text_is_safe(f"{headline}\n{paragraph}"):
        return jsonify({"ok": False, "error": "The card text failed the public-content safety check."}), 400
    lang = "dv" if _api_has_thaana(headline + " " + paragraph) else "en"
    try:
        if image_url:
            background = _cms_load_branding_source_image(image_url)
        else:
            background = fetch_background_image(None, cat=category, title=headline)
        # Match the existing Telegram manual-card rule: a short paragraph is
        # shown on the card; a longer paragraph remains in the posting caption.
        paragraph_limit = 80 if lang == "dv" else 150
        content = headline + (("\n\n" + paragraph) if paragraph and len(paragraph) <= paragraph_limit else "")
        timestamp = (utcnow() + timedelta(hours=5)).strftime("%d %b %Y • %H:%M")
        card = generate_card(content, "Samuga Media", timestamp, category, background)
        payload = card.getvalue()
        media_dir = _cms_media_directory()
        card_id = "sc_" + _uuid.uuid4().hex
        stored = f"social-cards/{datetime.utcnow().strftime('%Y/%m')}/{card_id}.png"
        full = _cms_media_full_path(stored, media_dir)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(payload)
        media_id, public_url, status = _cms_register_media(
            stored, f"{card_id}.png", "image", len(payload), user=request.cms_user,
            source="dashboard_social_card",
        )
        if not media_id:
            raise RuntimeError("Could not register the generated card.")
        caption = _cms_social_card_caption(headline, paragraph, category)
        db_execute("""
            INSERT INTO cms_social_cards
              (card_id,headline,paragraph,category,lang,source_image_url,card_url,stored_path,
               caption,status,destinations,created_by,created_email)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'created','{}'::jsonb,%s,%s)
        """, (card_id, headline, paragraph, category, lang, image_url or None, public_url,
              stored, caption, request.cms_user.get("id"), request.cms_user.get("email")))
        _cms_audit("create_social_card", "social_card", card_id,
                   new_value={"headline": headline, "category": category, "lang": lang})
        return jsonify({"ok": True, "card": {
            "card_id": card_id, "headline": headline, "paragraph": paragraph,
            "category": category, "lang": lang, "image_url": image_url or None,
            "card_url": public_url, "caption": caption, "status": "created",
        }, "message": "Social card created."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 400
    except Exception as exc:
        log.error(f"[CMS] social card create failed: {_mask_secrets(str(exc))[:500]}")
        return jsonify({"ok": False, "error": "Could not create the social card."}), 500


@api_app.post("/api/admin/social-card/post")
@_cms_require("editor", "admin", "super_admin")
def cms_social_card_post():
    data = request.get_json(silent=True) or {}
    card_id = str(data.get("card_id") or "").strip()
    destination = str(data.get("destination") or "").strip().lower()
    if destination not in {"telegram", "socials", "all"}:
        return jsonify({"ok": False, "error": "Choose Telegram, Socials or All."}), 400
    row = db_execute("""
        SELECT card_id,headline,paragraph,category,lang,source_image_url,card_url,stored_path,
               caption,status,destinations
        FROM cms_social_cards WHERE card_id=%s LIMIT 1
    """, (card_id,), fetch="one")
    if not row:
        return jsonify({"ok": False, "error": "Social card not found."}), 404
    try:
        full = _cms_media_full_path(row[7], _CMS_MEDIA_EFFECTIVE_DIR)
        if not os.path.isfile(full):
            for base in (_CMS_MEDIA_DIR, _CMS_MEDIA_FALLBACK_DIR):
                try:
                    candidate = _cms_media_full_path(row[7], base)
                except Exception:
                    continue
                if os.path.isfile(candidate):
                    full = candidate
                    break
        if not os.path.isfile(full):
            raise FileNotFoundError("Generated card image is missing.")
        with open(full, "rb") as handle:
            payload = handle.read()
        caption = row[8]
        results = {"telegram": None, "socials": None}
        if destination in {"telegram", "all"}:
            results["telegram"] = bool(send_to_telegram(io.BytesIO(payload), caption))
        if destination in {"socials", "all"}:
            queued = queue_for_social(
                io.BytesIO(payload), caption,
                notify_chat_id=CORE_TEAM_CHAT_ID or None,
                notify_thread_id=CONTENT_LAB_THREAD_ID or None,
                key_label=f"Dashboard card {card_id[-6:].upper()}",
                tg_ok=bool(results.get("telegram")), post_telegram=False,
                title=row[1], summary=row[2] or "", cat=row[3], lang=row[4],
            )
            results["socials"] = queued is not False
        destination_status = {
            "telegram": "posted_telegram" if results["telegram"] else "failed_telegram",
            "socials": "queued_socials" if results["socials"] else "failed_socials",
            "all": "queued_all" if results["socials"] and results["telegram"] else "partial",
        }[destination]
        previous = _cms_json_dict(row[10])
        previous[destination] = {"at": _cms_iso(utcnow()), **results}
        db_execute("""
            UPDATE cms_social_cards
            SET status=%s,destinations=%s::jsonb,posted_at=NOW(),updated_at=NOW()
            WHERE card_id=%s
        """, (destination_status, json.dumps(previous), card_id))
        _cms_audit("post_social_card", "social_card", card_id,
                   new_value={"destination": destination, "results": results})
        if CORE_TEAM_CHAT_ID and CONTENT_LAB_THREAD_ID:
            try:
                actor = request.cms_user.get("name") or request.cms_user.get("email")
                send_text(CORE_TEAM_CHAT_ID,
                    f"🃏 <b>Dashboard social card action</b>\n{row[1][:100]}\n"
                    f"By: {actor} · Destination: {destination.title()}",
                    thread_id=CONTENT_LAB_THREAD_ID)
            except Exception:
                pass
        return jsonify({"ok": True, "message": "Social card publishing started.",
                        "status": destination_status, "results": results})
    except Exception as exc:
        log.error(f"[CMS] social card posting failed: {_mask_secrets(str(exc))[:500]}")
        return jsonify({"ok": False, "error": str(exc)[:240] or "Social card publishing failed."}), 500


@api_app.get("/api/admin/publishing")
@_cms_require("editor", "admin", "super_admin")
def cms_publishing_center():
    connections = _CMS_CONNECTION_CACHE.get("results") or {
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID),
            "ok": None,
            "message": "Configured — run connection check." if TELEGRAM_BOT_TOKEN else "Bot token not configured.",
        },
        "facebook": {
            "configured": bool(BUFFER_TOKEN and BUFFER_FB_ID),
            "ok": None,
            "message": "Configured — run connection check." if BUFFER_TOKEN and BUFFER_FB_ID else "Buffer Facebook channel not configured.",
        },
        "x": {
            "configured": bool(BUFFER_TOKEN and BUFFER_TW_ID),
            "ok": None,
            "message": "Configured — run connection check." if BUFFER_TOKEN and BUFFER_TW_ID else "Buffer X channel not configured.",
        },
    }
    rows = db_execute("""
        SELECT j.id,j.article_id,j.platform,j.status,j.attempts,j.max_attempts,
               j.next_attempt_at,j.last_error,j.created_at,j.completed_at,a.title
        FROM cms_publish_jobs j
        LEFT JOIN articles a ON a.id=j.article_id
        ORDER BY CASE WHEN j.status IN ('pending','retry','processing') THEN 0 ELSE 1 END,
                 j.created_at DESC LIMIT 120
    """, fetch="all") or []
    logs = db_execute("""
        SELECT l.id,l.article_id,l.platform,l.status,l.message,l.created_at,a.title
        FROM cms_social_log l
        LEFT JOIN articles a ON a.id=l.article_id
        ORDER BY l.created_at DESC LIMIT 80
    """, fetch="all") or []
    counts_row = db_execute("""
        SELECT
          COUNT(*) FILTER (WHERE status IN ('pending','retry','processing')),
          COUNT(*) FILTER (WHERE status='failed'),
          COUNT(*) FILTER (WHERE status='succeeded' AND completed_at>=NOW()-INTERVAL '24 hours')
        FROM cms_publish_jobs
    """, fetch="one") or (0,0,0)
    return jsonify({
        "ok": True,
        "connections": connections,
        "connections_checked_at": _CMS_CONNECTION_CACHE.get("checked_at"),
        "counts": {"active": int(counts_row[0] or 0), "failed": int(counts_row[1] or 0), "sent_24h": int(counts_row[2] or 0)},
        "jobs": [{
            "id": int(r[0]), "article_id": r[1], "platform": r[2], "status": r[3],
            "attempts": int(r[4] or 0), "max_attempts": int(r[5] or 0),
            "next_attempt_at": _cms_iso(r[6]), "error": r[7] or "",
            "created_at": _cms_iso(r[8]), "completed_at": _cms_iso(r[9]),
            "title": r[10] or r[1],
        } for r in rows],
        "logs": [{
            "id": int(r[0]), "article_id": r[1], "platform": r[2],
            "status": r[3], "message": r[4] or "", "created_at": _cms_iso(r[5]),
            "title": r[6] or r[1],
        } for r in logs],
    })


@api_app.post("/api/admin/connections/check")
@_cms_require("editor", "admin", "super_admin")
def cms_connections_check():
    results = _cms_live_connection_check()
    return jsonify({"ok": True, "connections": results, "checked_at": _CMS_CONNECTION_CACHE.get("checked_at")})


@api_app.post("/api/admin/publish-jobs/retry")
@_cms_require("editor", "admin", "super_admin")
def cms_publish_job_retry():
    data = request.get_json(silent=True) or {}
    job_id = data.get("id")
    article_id = str(data.get("article_id") or "").strip()
    if job_id:
        rows = db_execute("""
            UPDATE cms_publish_jobs SET status='pending',attempts=0,next_attempt_at=NOW(),
                last_error=NULL,completed_at=NULL,updated_at=NOW()
            WHERE id=%s AND status IN ('failed','retry') RETURNING id,article_id,platform
        """, (job_id,), fetch="all") or []
    elif article_id:
        rows = db_execute("""
            UPDATE cms_publish_jobs SET status='pending',attempts=0,next_attempt_at=NOW(),
                last_error=NULL,completed_at=NULL,updated_at=NOW()
            WHERE article_id=%s AND status IN ('failed','retry') RETURNING id,article_id,platform
        """, (article_id,), fetch="all") or []
    else:
        rows = db_execute("""
            UPDATE cms_publish_jobs SET status='pending',attempts=0,next_attempt_at=NOW(),
                last_error=NULL,completed_at=NULL,updated_at=NOW()
            WHERE status='failed' RETURNING id,article_id,platform
        """, fetch="all") or []
    for row in rows:
        _cms_set_social_state(row[1], row[2], "queued", "Retry requested.")
    _cms_audit("retry_publish_jobs", "publishing", job_id or article_id or "all",
               new_value={"jobs": [int(row[0]) for row in rows]})
    return jsonify({"ok": True, "retried": len(rows), "job_ids": [int(row[0]) for row in rows]})


@api_app.post("/api/admin/publish-jobs/cancel")
@_cms_require("editor", "admin", "super_admin")
def cms_publish_job_cancel():
    data = request.get_json(silent=True) or {}
    job_id = data.get("id")
    row = db_execute("""
        UPDATE cms_publish_jobs SET status='cancelled',completed_at=NOW(),updated_at=NOW()
        WHERE id=%s AND status IN ('pending','retry') RETURNING article_id,platform
    """, (job_id,), fetch="one")
    if not row:
        return jsonify({"ok": False, "error": "Only pending or retrying jobs can be cancelled."}), 400
    _cms_set_social_state(row[0], row[1], "cancelled", "Publishing job cancelled.")
    _cms_audit("cancel_publish_job", "publishing", job_id)
    return jsonify({"ok": True})


@api_app.get("/api/admin/media")
@_cms_require()
def cms_media_list():
    media_type = str(request.args.get("type") or "").lower()
    q = str(request.args.get("q") or "").strip()
    media_id = str(request.args.get("id") or "").strip()
    clauses = ["deleted_at IS NULL"]
    params = []
    if media_id:
        clauses.append("id=%s")
        params.append(media_id)
    if media_type in {"image", "video"}:
        clauses.append("media_type=%s")
        params.append(media_type)
    if q:
        clauses.append("original_name ILIKE %s")
        params.append(f"%{q[:120]}%")
    rows = db_execute(f"""
        SELECT id,stored_path,original_name,public_url,media_type,size_bytes,
               uploaded_by_email,created_at,poster_url,duration_seconds,width,height,
               video_codec,processing_status,processing_error,source,updated_at
        FROM cms_media_library
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC LIMIT 120
    """, tuple(params), fetch="all") or []
    return jsonify({"ok": True, "media": [{
        "id": int(r[0]), "stored_path": r[1], "name": r[2], "url": r[3],
        "type": r[4], "size_bytes": int(r[5] or 0), "uploaded_by": r[6],
        "created_at": _cms_iso(r[7]), "poster": r[8],
        "duration": float(r[9] or 0), "duration_seconds": float(r[9] or 0),
        "width": int(r[10] or 0), "height": int(r[11] or 0),
        "codec": r[12] or "", "video_codec": r[12] or "",
        "status": r[13] or "ready", "processing_status": r[13] or "ready",
        "error": r[14] or "", "processing_error": r[14] or "",
        "source": r[15] or "dashboard", "updated_at": _cms_iso(r[16]),
    } for r in rows]})


@api_app.post("/api/admin/media/delete")
@_cms_require("admin", "super_admin")
def cms_media_delete():
    data = request.get_json(silent=True) or {}
    media_id = data.get("id")
    row = db_execute("""
        SELECT id,stored_path,public_url,poster_url FROM cms_media_library
        WHERE id=%s AND deleted_at IS NULL LIMIT 1
    """, (media_id,), fetch="one")
    if not row:
        return jsonify({"ok": False, "error": "Media item not found."}), 404
    # Do not break live articles. Mark the item deleted from the library but keep
    # physical files when an article still references its public URL or poster.
    referenced = db_execute("""
        SELECT id FROM articles
        WHERE cover_image_url IN (%s,%s) OR cover_video_url IN (%s,%s)
           OR video_poster_url IN (%s,%s)
           OR COALESCE(media_items,'[]'::jsonb)::text ILIKE %s
           OR COALESCE(media_items,'[]'::jsonb)::text ILIKE %s
        LIMIT 1
    """, (
        row[2], row[3], row[2], row[3], row[2], row[3],
        f"%{row[2]}%", f"%{row[3]}%" if row[3] else "%__never__%",
    ), fetch="one")
    db_execute("UPDATE cms_media_library SET deleted_at=NOW(),updated_at=NOW() WHERE id=%s", (media_id,))
    removed_files = []
    if not referenced:
        stored_paths = [row[1]]
        if row[3] and "/media/cms/" in row[3]:
            stored_paths.append(row[3].split("/media/cms/", 1)[1])
        for stored in stored_paths:
            for base in (_CMS_MEDIA_EFFECTIVE_DIR, _CMS_MEDIA_DIR, _CMS_MEDIA_FALLBACK_DIR):
                if not base:
                    continue
                try:
                    full = _cms_media_full_path(stored, base)
                except Exception:
                    continue
                if os.path.isfile(full):
                    try:
                        os.remove(full)
                        removed_files.append(stored)
                        break
                    except Exception as exc:
                        log.warning(f"[CMS] media file delete failed: {exc}")
    _cms_audit("delete_media", "media", media_id, new_value={
        "url": row[2], "files_removed": removed_files, "referenced": bool(referenced),
    })
    return jsonify({"ok": True, "file_removed": bool(removed_files), "kept_for_article": bool(referenced)})



def _cms_load_branding_source_image(value):
    """Open an admin-selected cover image without exposing a general proxy.

    Newsroom uploads are read directly from the persistent CMS media directory.
    Existing externally hosted covers are supported over HTTP(S), while local,
    loopback, link-local and private network destinations are rejected.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Choose an image cover first.")

    # Prefer the local persistent file whenever the public CMS URL is supplied.
    if "/media/cms/" in raw:
        stored = raw.split("/media/cms/", 1)[1].split("?", 1)[0].split("#", 1)[0]
        stored = requests.utils.unquote(stored).lstrip("/")
        for base in (_CMS_MEDIA_EFFECTIVE_DIR, _CMS_MEDIA_DIR, _CMS_MEDIA_FALLBACK_DIR):
            if not base:
                continue
            try:
                full = _cms_media_full_path(stored, base)
            except Exception:
                continue
            if os.path.isfile(full):
                with Image.open(full) as source:
                    source.load()
                    if source.width * source.height > 60_000_000:
                        raise ValueError("This image is too large to process safely.")
                    return source.convert("RGB")

    from urllib.parse import urlparse
    import ipaddress
    import socket

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("The cover must use a valid HTTP or HTTPS image URL.")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError("Private network image URLs are not allowed.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The cover image host could not be verified.") from exc

    response = requests.get(
        raw,
        timeout=(10, 35),
        stream=True,
        allow_redirects=True,
        headers={"User-Agent": "SamugaMedia-Newsroom/8.6"},
    )
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError("The selected URL did not return an image.")
    limit = min(int(_CMS_IMAGE_MAX_BYTES or 25 * 1024 * 1024), 25 * 1024 * 1024)
    chunks = bytearray()
    for chunk in response.iter_content(chunk_size=512 * 1024):
        if not chunk:
            continue
        chunks.extend(chunk)
        if len(chunks) > limit:
            raise ValueError("The cover image is too large to brand.")
    try:
        with Image.open(BytesIO(bytes(chunks))) as source:
            source.load()
            if source.width * source.height > 60_000_000:
                raise ValueError("This image is too large to process safely.")
            return source.convert("RGB")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The selected file is not a readable image.") from exc


@api_app.post("/api/admin/media/brand-cover")
@_cms_require()
def cms_brand_cover():
    """Apply the same 1200×630 Samuga web-cover branding used by Telegram."""
    data = request.get_json(silent=True) or {}
    source_url = str(data.get("url") or "").strip()
    title = _api_clean_text(data.get("title") or "Samuga Media", 500)
    category = _api_category(data.get("category") or "LOCAL", title, "")
    try:
        source_image = _cms_load_branding_source_image(source_url)
        branded = generate_web_cover(
            title=title,
            category=category,
            bg_image=source_image,
            source=SAMUGA_PUBLIC_SOURCE,
        )
        payload = branded.getvalue()
        media_dir = _cms_media_directory()
        stored = f"{datetime.utcnow().strftime('%Y/%m')}/{_uuid.uuid4().hex}-samuga-cover.png"
        full = _cms_media_full_path(stored, media_dir)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(payload)
        media_id, public_url, status = _cms_register_media(
            stored,
            "samuga-branded-cover.png",
            "image",
            len(payload),
            user=request.cms_user,
            source="dashboard_branding",
        )
        if not media_id:
            try:
                os.remove(full)
            except OSError:
                pass
            raise RuntimeError("Could not register the branded cover.")
        _cms_audit(
            "brand_cover",
            "media",
            media_id,
            new_value={"url": public_url, "source_url": source_url[:500], "category": category},
        )
        return jsonify({
            "ok": True,
            "media": {
                "id": media_id,
                "url": public_url,
                "type": "image",
                "status": status,
                "name": "samuga-branded-cover.png",
                "source": "dashboard_branding",
            },
            "message": "Samuga branding added.",
        })
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 400
    except Exception as exc:
        log.error(f"[CMS] cover branding failed: {_mask_secrets(str(exc))[:500]}")
        return jsonify({"ok": False, "error": "Could not add Samuga branding to this image."}), 500


@api_app.post("/api/admin/upload")
@_cms_require()
def cms_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Choose an image or video file."}), 400
    filename = _secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _CMS_IMAGE_EXT | _CMS_VIDEO_EXT:
        return jsonify({"ok": False, "error": "Unsupported file type."}), 400
    media_type = "video" if ext in _CMS_VIDEO_EXT else "image"
    max_bytes = _CMS_VIDEO_MAX_BYTES if media_type == "video" else _CMS_IMAGE_MAX_BYTES
    content_length = request.content_length or 0
    if content_length and content_length > max_bytes + 1024 * 1024:
        return jsonify({"ok": False, "error": "File is too large."}), 413

    try:
        media_dir = _cms_media_directory()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:180]}), 500
    stored = f"{datetime.utcnow().strftime('%Y/%m')}/{_uuid.uuid4().hex}.{ext}"
    full = _cms_media_full_path(stored, media_dir)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    file.save(full)
    size_bytes = os.path.getsize(full)
    if size_bytes > max_bytes:
        os.remove(full)
        return jsonify({"ok": False, "error": "File is too large."}), 413

    media_id, url, status = _cms_register_media(
        stored, filename, media_type, size_bytes,
        user=request.cms_user, source="dashboard",
    )
    if not media_id:
        try:
            os.remove(full)
        except OSError:
            pass
        return jsonify({"ok": False, "error": "Could not register uploaded media."}), 500
    _cms_audit("upload_media", "media", media_id, new_value={
        "type": media_type, "url": url, "size_bytes": size_bytes, "status": status,
    })
    return jsonify({
        "ok": True, "id": media_id, "url": url, "poster": None,
        "type": media_type, "filename": filename, "size_bytes": size_bytes,
        "status": status,
        "message": "Video uploaded and queued for browser processing." if status == "pending" else "Upload complete.",
    })


@api_app.post("/api/admin/media/reprocess")
@_cms_require("editor", "admin", "super_admin")
def cms_media_reprocess():
    data = request.get_json(silent=True) or {}
    media_id = data.get("id")
    row = db_execute("""
        SELECT id,media_type FROM cms_media_library
        WHERE id=%s AND deleted_at IS NULL LIMIT 1
    """, (media_id,), fetch="one")
    if not row or row[1] != "video":
        return jsonify({"ok": False, "error": "Video not found."}), 404
    db_execute("""
        UPDATE cms_media_library SET processing_status='pending',processing_error=NULL,updated_at=NOW()
        WHERE id=%s
    """, (media_id,))
    _cms_start_video_processing(int(media_id))
    _cms_audit("reprocess_video", "media", media_id)
    return jsonify({"ok": True, "status": "pending"})


@api_app.post("/api/admin/import-telegram")
@_cms_require()
def cms_import_telegram_media():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get("file_id") or "").strip()
    media_type = "image" if str(data.get("type") or "").lower() == "image" else "video"
    filename = _secure_filename(str(data.get("filename") or "").strip())
    if not file_id:
        return jsonify({"ok": False, "error": "Telegram file ID is required."}), 400
    try:
        item = _cms_import_telegram_file(file_id, filename, media_type, user=request.cms_user)
        return jsonify({"ok": True, "media": item})
    except Exception as exc:
        return jsonify({"ok": False, "error": _mask_secrets(str(exc))[:250]}), 400


@api_app.get("/media/cms/<path:filename>")
def cms_media_file(filename):
    # Uploaded media is public by design once its URL is placed in an article.
    # Prefer the directory that successfully accepted the upload; then try the
    # configured persistent volume and finally the temporary fallback.
    candidates = []
    for candidate in (_CMS_MEDIA_EFFECTIVE_DIR, _CMS_MEDIA_DIR, _CMS_MEDIA_FALLBACK_DIR):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for base in candidates:
        full = os.path.abspath(os.path.join(base, filename))
        base_abs = os.path.abspath(base)
        if full.startswith(base_abs + os.sep) and os.path.isfile(full):
            return send_from_directory(base_abs, filename, conditional=True, max_age=86400)
    return jsonify({"ok": False, "error": "Media not found."}), 404


@api_app.get("/api/admin/users")
@_cms_require("admin", "super_admin")
def cms_users_list():
    _cms_reconcile_all_user_authors()
    rows = db_execute("""
        SELECT id,email,name,role,author_id,telegram_user_id,active,last_login,created_at
        FROM cms_users ORDER BY active DESC, name
    """, fetch="all") or []
    return jsonify({"ok": True, "users": [_cms_user_dict(r) for r in rows]})


@api_app.post("/api/admin/users")
@_cms_require("admin", "super_admin")
def cms_users_save():
    actor = request.cms_user
    data = request.get_json(silent=True) or {}
    name = _api_clean_text(data.get("name"), 160)
    email = str(data.get("email") or "").strip().lower()[:320]
    role = str(data.get("role") or "journalist").strip().lower()
    password = str(data.get("password") or "")
    active = bool(data.get("active", True))
    user_id = data.get("id")
    requested_author_id = str(data.get("author_id") or "").strip()
    telegram_user_id = _cms_telegram_id_from_author(requested_author_id, data.get("telegram_user_id"))
    if not name or "@" not in email or role not in _CMS_ROLES:
        return jsonify({"ok": False, "error": "Name, valid email and role are required."}), 400
    if actor.get("role") != "super_admin" and role in {"admin", "super_admin"}:
        return jsonify({"ok": False, "error": "Only a Super Admin can grant administrator rights."}), 403

    old = None
    current_author_id = ""
    if user_id:
        old_row = db_execute("""
            SELECT id,email,name,role,author_id,telegram_user_id,active,last_login,created_at,password_hash
            FROM cms_users WHERE id=%s LIMIT 1
        """, (user_id,), fetch="one")
        if not old_row:
            return jsonify({"ok": False, "error": "User not found."}), 404
        old = _cms_user_dict(old_row[:9])
        current_author_id = old.get("author_id") or ""
        if old.get("role") == "super_admin" and actor.get("role") != "super_admin":
            return jsonify({"ok": False, "error": "Only a Super Admin can edit this account."}), 403
        if int(user_id) == int(actor.get("id")) and not active:
            return jsonify({"ok": False, "error": "You cannot disable your own account."}), 400
        if int(user_id) == int(actor.get("id")) and old.get("role") == "super_admin" and role != "super_admin":
            return jsonify({"ok": False, "error": "You cannot remove your own Super Admin rights."}), 400
        if password and len(password) < 8:
            return jsonify({"ok": False, "error": "Passwords must be at least 8 characters."}), 400
        duplicate = db_execute(
            "SELECT id FROM cms_users WHERE LOWER(email)=LOWER(%s) AND id<>%s LIMIT 1",
            (email, user_id), fetch="one"
        )
        if duplicate:
            return jsonify({"ok": False, "error": "That email already has an account."}), 409
        if password:
            db_execute("""
                UPDATE cms_users SET email=%s,name=%s,role=%s,active=%s,password_hash=%s,updated_at=NOW()
                WHERE id=%s
            """, (email, name, role, active, _generate_password_hash(password), user_id))
        else:
            db_execute("""
                UPDATE cms_users SET email=%s,name=%s,role=%s,active=%s,updated_at=NOW()
                WHERE id=%s
            """, (email, name, role, active, user_id))
        uid = int(user_id)
    else:
        if len(password) < 8:
            return jsonify({"ok": False, "error": "New accounts need a password of at least 8 characters."}), 400
        if db_execute("SELECT id FROM cms_users WHERE LOWER(email)=LOWER(%s)", (email,), fetch="one"):
            return jsonify({"ok": False, "error": "That email already has an account."}), 409
        row = db_execute("""
            INSERT INTO cms_users (email,name,password_hash,role,active,telegram_user_id)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (email, name, _generate_password_hash(password), role, active, telegram_user_id), fetch="one")
        if not row:
            return jsonify({"ok": False, "error": "The user account could not be created."}), 500
        uid = int(row[0])

    target_author_id = requested_author_id
    if telegram_user_id:
        target_author_id = f"tg_{telegram_user_id}"
        db_execute("""
            INSERT INTO cms_authors (author_id,name,role,active,telegram_user_id)
            VALUES (%s,%s,'Reporter',TRUE,%s)
            ON CONFLICT (author_id) DO UPDATE SET telegram_user_id=COALESCE(cms_authors.telegram_user_id,EXCLUDED.telegram_user_id),updated_at=NOW()
        """, (target_author_id, name, telegram_user_id))
    if target_author_id:
        target = db_execute("SELECT author_id FROM cms_authors WHERE author_id=%s LIMIT 1", (target_author_id,), fetch="one")
        if not target:
            return jsonify({"ok": False, "error": "The selected author profile no longer exists."}), 404
        if _cms_author_is_linked(target_author_id, exclude_user_id=uid):
            return jsonify({"ok": False, "error": "That author profile is already linked to another newsroom login."}), 409
        if current_author_id and current_author_id != target_author_id:
            target_author_id = _cms_merge_author_profiles(current_author_id, target_author_id, user_id=uid)
        else:
            db_execute("""
                UPDATE cms_users SET author_id=%s,telegram_user_id=%s,updated_at=NOW() WHERE id=%s
            """, (target_author_id, telegram_user_id or _cms_telegram_id_from_author(target_author_id), uid))
    else:
        matched = _cms_auto_link_user_author(uid, name, current_author_id)
        target_author_id = matched or current_author_id

    if not target_author_id:
        target_author_id = f"cms_{uid}"
        public_role = {
            "contributor": "Contributor", "journalist": "Journalist", "editor": "Editor",
            "admin": "Newsroom Administrator", "super_admin": "Management",
        }[role]
        db_execute("""
            INSERT INTO cms_authors (author_id,name,role,active)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (author_id) DO UPDATE SET name=EXCLUDED.name,active=EXCLUDED.active,updated_at=NOW()
        """, (target_author_id, name, public_role, active))
        db_execute("UPDATE cms_users SET author_id=%s,updated_at=NOW() WHERE id=%s", (target_author_id, uid))
    elif target_author_id.startswith("cms_"):
        db_execute("UPDATE cms_authors SET name=%s,active=%s,updated_at=NOW() WHERE author_id=%s", (name, active, target_author_id))
        profile = db_execute("SELECT name,role,photo_url FROM cms_authors WHERE author_id=%s", (target_author_id,), fetch="one")
        if profile:
            _cms_sync_author_articles(target_author_id, profile[0], profile[1], profile[2])

    _cms_audit("update_user" if old else "create_user", "user", uid, old_value=old,
               new_value={"email": email, "name": name, "role": role, "active": active,
                          "author_id": target_author_id, "telegram_user_id": telegram_user_id})
    return jsonify({"ok": True, "user": _cms_get_user(uid)})


@api_app.get("/api/admin/audit")
@_cms_require("admin", "super_admin")
def cms_audit_list():
    rows = db_execute("""
        SELECT id,user_email,action,entity_type,entity_id,new_value,created_at
        FROM cms_audit_log ORDER BY created_at DESC LIMIT 200
    """, fetch="all") or []
    return jsonify({"ok": True, "events": [{
        "id": r[0], "user_email": r[1], "action": r[2], "entity_type": r[3],
        "entity_id": r[4], "new_value": r[5], "created_at": _cms_iso(r[6]),
    } for r in rows]})




_CMS_PUBLIC_SITE_DEFAULTS = {
    "tagline_en": "Maldives news made simple.",
    "tagline_dv": "ދިވެހިރާއްޖޭގެ ޚަބަރު ފަސޭހަކޮށް.",
    "community_url": "https://t.me/samugacommunity",
    "tip_url": "https://t.me/Samuga_Media",
    "contact_email": "",
    "show_ai_chat": True,
    "default_theme": "system",
}

def _cms_public_site_settings():
    row = db_execute("SELECT value FROM cms_site_settings WHERE key='public_site' LIMIT 1", fetch="one")
    raw = row[0] if row else {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    out = dict(_CMS_PUBLIC_SITE_DEFAULTS)
    out.update({k: raw.get(k) for k in out if k in raw})
    out["tagline_en"] = _api_clean_text(out.get("tagline_en"), 240) or _CMS_PUBLIC_SITE_DEFAULTS["tagline_en"]
    out["tagline_dv"] = _api_clean_text(out.get("tagline_dv"), 240) or _CMS_PUBLIC_SITE_DEFAULTS["tagline_dv"]
    out["community_url"] = _cms_public_url(out.get("community_url")) or _CMS_PUBLIC_SITE_DEFAULTS["community_url"]
    out["tip_url"] = _cms_public_url(out.get("tip_url")) or _CMS_PUBLIC_SITE_DEFAULTS["tip_url"]
    out["contact_email"] = str(out.get("contact_email") or "").strip()[:320]
    out["show_ai_chat"] = bool(out.get("show_ai_chat", True))
    out["default_theme"] = out.get("default_theme") if out.get("default_theme") in {"system", "light", "dark"} else "system"
    return out

@api_app.get("/api/site-settings")
def public_site_settings():
    return jsonify({"ok": True, "settings": _cms_public_site_settings()})

@api_app.get("/api/admin/site-settings")
@_cms_require("admin", "super_admin")
def cms_site_settings_get():
    return jsonify({"ok": True, "settings": _cms_public_site_settings()})

@api_app.post("/api/admin/site-settings")
@_cms_require("admin", "super_admin")
def cms_site_settings_save():
    data = request.get_json(silent=True) or {}
    old = _cms_public_site_settings()
    settings = {
        "tagline_en": _api_clean_text(data.get("tagline_en"), 240) or _CMS_PUBLIC_SITE_DEFAULTS["tagline_en"],
        "tagline_dv": _api_clean_text(data.get("tagline_dv"), 240) or _CMS_PUBLIC_SITE_DEFAULTS["tagline_dv"],
        "community_url": _cms_public_url(data.get("community_url")) or _CMS_PUBLIC_SITE_DEFAULTS["community_url"],
        "tip_url": _cms_public_url(data.get("tip_url")) or _CMS_PUBLIC_SITE_DEFAULTS["tip_url"],
        "contact_email": str(data.get("contact_email") or "").strip()[:320],
        "show_ai_chat": bool(data.get("show_ai_chat", True)),
        "default_theme": data.get("default_theme") if data.get("default_theme") in {"system", "light", "dark"} else "system",
    }
    db_execute("""
        INSERT INTO cms_site_settings (key,value,updated_by,updated_at)
        VALUES ('public_site',%s::jsonb,%s,NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=NOW()
    """, (json.dumps(settings, ensure_ascii=False), request.cms_user.get("id")))
    _cms_audit("update_site_settings", "site", "public_site", old_value=old, new_value=settings)
    return jsonify({"ok": True, "settings": settings})


@api_app.get("/api/ads")
def public_ads():
    placement = str(request.args.get("placement") or "feed").strip().lower()
    if placement not in {"feed", "article", "sidebar"}:
        placement = "feed"
    rows = db_execute("""
        SELECT id,name,image_url,mobile_image_url,destination_url,caption,fit_mode,placement
        FROM cms_ads
        WHERE active=TRUE AND placement=%s
          AND (starts_at IS NULL OR starts_at <= NOW())
          AND (ends_at IS NULL OR ends_at >= NOW())
        ORDER BY updated_at DESC, id DESC
        LIMIT 12
    """, (placement,), fetch="all") or []
    return jsonify({"ok": True, "ads": [{
        "id": r[0], "name": r[1], "image_url": r[2], "mobile_image_url": r[3],
        "destination_url": r[4], "caption": r[5], "fit_mode": r[6] or "contain",
        "placement": r[7],
    } for r in rows]})


@api_app.get("/api/admin/ads")
@_cms_require("admin", "super_admin")
def cms_ads_list():
    rows = db_execute("""
        SELECT id,name,image_url,mobile_image_url,destination_url,caption,fit_mode,
               placement,active,starts_at,ends_at,created_at,updated_at
        FROM cms_ads ORDER BY active DESC, updated_at DESC, id DESC
    """, fetch="all") or []
    return jsonify({"ok": True, "ads": [{
        "id": r[0], "name": r[1], "image_url": r[2], "mobile_image_url": r[3],
        "destination_url": r[4], "caption": r[5], "fit_mode": r[6], "placement": r[7],
        "active": bool(r[8]), "starts_at": _cms_iso(r[9]), "ends_at": _cms_iso(r[10]),
        "created_at": _cms_iso(r[11]), "updated_at": _cms_iso(r[12]),
    } for r in rows]})


@api_app.post("/api/admin/ads")
@_cms_require("admin", "super_admin")
def cms_ads_save():
    data = request.get_json(silent=True) or {}
    ad_id = data.get("id")
    name = _api_clean_text(data.get("name"), 160)
    image_url = _cms_public_url(data.get("image_url"))
    mobile_image_url = _cms_public_url(data.get("mobile_image_url"))
    destination_url = _cms_public_url(data.get("destination_url"))
    caption = _api_clean_text(data.get("caption"), 500)
    fit_mode = "cover" if str(data.get("fit_mode")).lower() == "cover" else "contain"
    placement = str(data.get("placement") or "feed").lower()
    if placement not in {"feed", "article", "sidebar"}:
        placement = "feed"
    active = bool(data.get("active", True))
    starts_at = _cms_parse_datetime(data.get("starts_at"))
    ends_at = _cms_parse_datetime(data.get("ends_at"))
    if starts_at and ends_at and ends_at <= starts_at:
        return jsonify({"ok": False, "error": "Advertisement end time must be after its start time."}), 400
    if not name or not image_url:
        return jsonify({"ok": False, "error": "Advertisement name and banner image are required."}), 400
    old = None
    if ad_id:
        old_row = db_execute("SELECT name,image_url,active,placement FROM cms_ads WHERE id=%s", (ad_id,), fetch="one")
        if not old_row:
            return jsonify({"ok": False, "error": "Advertisement not found."}), 404
        old = {"name": old_row[0], "image_url": old_row[1], "active": bool(old_row[2]), "placement": old_row[3]}
        db_execute("""
            UPDATE cms_ads SET name=%s,image_url=%s,mobile_image_url=%s,destination_url=%s,
                caption=%s,fit_mode=%s,placement=%s,active=%s,starts_at=%s,ends_at=%s,updated_at=NOW()
            WHERE id=%s
        """, (name,image_url,mobile_image_url,destination_url,caption,fit_mode,placement,active,starts_at,ends_at,ad_id))
        saved_id = int(ad_id)
    else:
        row = db_execute("""
            INSERT INTO cms_ads
                (name,image_url,mobile_image_url,destination_url,caption,fit_mode,placement,active,starts_at,ends_at,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (name,image_url,mobile_image_url,destination_url,caption,fit_mode,placement,active,starts_at,ends_at,request.cms_user.get("id")), fetch="one")
        if not row:
            return jsonify({"ok": False, "error": "Could not save advertisement."}), 500
        saved_id = int(row[0])
    _cms_audit("update_ad" if old else "create_ad", "advertisement", saved_id, old_value=old,
               new_value={"name": name, "active": active, "placement": placement, "fit_mode": fit_mode,
                          "starts_at": _cms_iso(starts_at), "ends_at": _cms_iso(ends_at)})
    return jsonify({"ok": True, "id": saved_id})



def cms_publish_due_articles():
    """Publish due newsroom articles and run their saved social targets.

    This job is intentionally idempotent: the conditional UPDATE claims each
    scheduled row once, so a restart or overlapping scheduler tick cannot post
    the same article twice.
    """
    try:
        rows = db_execute("""
            SELECT id,social_caption,share_targets,scheduled_at
            FROM articles
            WHERE status='scheduled' AND scheduled_at IS NOT NULL AND scheduled_at<=NOW()
            ORDER BY scheduled_at ASC LIMIT 20
        """, fetch="all") or []
    except Exception as exc:
        log.warning(f"[CMS] scheduled article scan failed: {exc}")
        return
    for article_id, social_caption, share_targets_raw, scheduled_at in rows:
        try:
            claimed = db_execute("""
                UPDATE articles SET status='posted',posted_at=COALESCE(posted_at,NOW()),
                    published_by=COALESCE(published_by,'scheduler'),scheduled_at=NULL,updated_at=NOW()
                WHERE id=%s AND status='scheduled' AND scheduled_at<=NOW()
                RETURNING id
            """, (article_id,), fetch="one")
            if not claimed:
                continue
            share_targets = _cms_json_dict(share_targets_raw)
            platforms = [platform for platform in ("telegram", "facebook", "x") if share_targets.get(platform)]
            jobs = _cms_queue_social_jobs(
                article_id, platforms, social_caption or "",
                user={"id": None, "email": "scheduler"},
            ) if platforms else []
            _cms_audit(
                "scheduled_publish", "article", article_id,
                new_value={"scheduled_at": _cms_iso(scheduled_at), "share_jobs": jobs},
                user={"id": None, "email": "scheduler"},
            )
            log.info(f"[CMS] scheduled article published: {article_id}")
        except Exception as exc:
            log.error(f"[CMS] scheduled publish failed for {article_id}: {exc}")

def _cors_vary_origin(response):
    values = {part.strip() for part in response.headers.get("Vary", "").split(",") if part.strip()}
    values.add("Origin")
    response.headers["Vary"] = ", ".join(sorted(values))


@api_app.after_request
def add_cors_headers(response):
    """Apply route-appropriate CORS headers to normal and error responses.

    Public read APIs remain wildcard-readable. Authenticated newsroom APIs are
    restricted to configured origins. Analytics uses an exact allow-list so an
    old cross-origin sendBeacon request can complete safely while Build 11 uses
    the same-origin Cloudflare proxy.
    """
    origin = (request.headers.get("Origin") or "").rstrip("/")
    path = request.path or ""

    if path == "/api/track":
        if origin and origin in _ANALYTICS_ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            _cors_vary_origin(response)
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    if path.startswith("/api/admin"):
        if origin in _CMS_ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            _cors_vary_origin(response)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
        if path.startswith("/media/cms/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        else:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "600"
    return response

@api_app.get("/sitemap.xml")
def api_sitemap():
    """Dynamic sitemap — lists all published articles for search engines."""
    try:
        rows = db_execute("""
            SELECT id, article_slug, posted_at, updated_at
            FROM articles
            WHERE status IN ('posted','published','social_posted')
              AND lang = 'en'
            ORDER BY posted_at DESC
            LIMIT 1000
        """, fetch="all") or []
        base = "https://samugamedia.com"
        urls = [f"""  <url>
    <loc>{base}/article?id={r[0]}</loc>
    <lastmod>{(r[3] or r[2]).strftime('%Y-%m-%d') if (r[3] or r[2]) else '2026-01-01'}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""" for r in rows]
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
{chr(10).join(urls)}
</urlset>"""
        from flask import Response
        return Response(xml, 200, content_type="application/xml")
    except Exception as e:
        log.error(f"sitemap error: {e}")
        return Response("", 500)


@api_app.get("/")
def api_home():
    return jsonify({
        "status": "online",
        "name": "Samuga News Bot API",
        "version": SAMUGA_VERSION,
        "endpoints": ["/api/stories", "/api/article?id=ARTICLE_ID", "/api/health", "/api/chat", "/api/public-interest"]
    })

@api_app.get("/api/health")
def api_health():
    """Production health check endpoint with comprehensive system status."""
    import psutil as _psutil
    import gc as _gc

    result = {
        "status": "online",
        "version": SAMUGA_VERSION,
        "timestamp_utc": utcnow().isoformat(),
    }

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        row = db_execute("""
            SELECT title, posted_at, found_at, status
            FROM articles
            WHERE status IN ('posted','published','social_posted')
            ORDER BY COALESCE(posted_at, found_at) DESC NULLS LAST
            LIMIT 1
        """, fetch="one")
        result["database"] = {"ok": True, "enabled": bool(DB_ENABLED)}
        if row:
            dt = row[1] or row[2]
            result["latest_article"] = {
                "title": _api_clean_text(row[0], 160),
                "time": dt.strftime("%d %b %Y • %H:%M") if dt else "Recent",
                "status": row[3],
                "age_minutes": int((utcnow() - dt.replace(tzinfo=None)).total_seconds() / 60) if dt else None,
            }
    except Exception as e:
        result["database"] = {"ok": False, "error": str(e)[:120]}

    # ── Queues ────────────────────────────────────────────────────────────────
    try:
        with _social_queue_lock:
            sq_len = len(_social_queue)
        with _approval_lock:
            aq_len = len(approval_queue)
        result["queues"] = {
            "social_queue": sq_len,
            "approval_queue": aq_len,
        }
    except Exception:
        result["queues"] = {"social_queue": -1, "approval_queue": -1}

    # ── Dedup memory ──────────────────────────────────────────────────────────
    try:
        with _recent_titles_lock if "scoring" in dir() else _approval_lock:
            pass
        result["dedup_memory"] = len(recent_story_titles)
    except Exception:
        result["dedup_memory"] = -1

    # ── Last news scan ────────────────────────────────────────────────────────
    try:
        if recent_posts:
            last = recent_posts[-1]
            result["last_scan"] = {
                "title": last.get("title","")[:80],
                "cat": last.get("cat",""),
                "time": last.get("time",""),
            }
    except Exception:
        pass

    # ── Memory usage ──────────────────────────────────────────────────────────
    try:
        proc = _psutil.Process()
        result["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        result["memory_mb"] = None

    # ── API keys present (not values) ─────────────────────────────────────────
    result["services"] = {
        "telegram": bool(TELEGRAM_BOT_TOKEN),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "deepseek": _deepseek_health_snapshot(),
        "buffer": bool(BUFFER_TOKEN),
        "imgbb": bool(IMGBB_API_KEY),
        "tavily": bool(TAVILY_API_KEY),
        "weather": bool(TOMORROW_API_KEY),
    }

    # ── Posting state ─────────────────────────────────────────────────────────
    result["posting"] = {
        "paused": posting_paused(),
        "social_paused": social_paused(),
    }

    # ── Samuga OS event layer ─────────────────────────────────────────────────
    try:
        result["events"] = event_summary()
    except Exception:
        pass

    return jsonify(result)


@api_app.get("/api/banner")
def api_banner():
    """Optional sponsored/banner block for the website frontend."""
    try:
        return jsonify({
            "active": bool(website_banner.get("active")),
            "text": str(website_banner.get("text") or ""),
            "image_url": str(website_banner.get("image_url") or ""),
            "updated_at": website_banner.get("updated_at"),
        })
    except Exception as e:
        log.error(f"Website API /api/banner error: {e}")
        return jsonify({"active": False, "text": "", "updated_at": None})

def _analytics_device_type(user_agent):
    ua = str(user_agent or "").lower()
    if any(token in ua for token in ("ipad", "tablet", "kindle")):
        return "tablet"
    if any(token in ua for token in ("iphone", "android", "mobile")):
        return "mobile"
    return "desktop"


@api_app.route("/api/track", methods=["POST", "OPTIONS"])
def api_track_pageview():
    """Record a verified first-party pageview without retaining a raw IP."""
    if request.method == "OPTIONS":
        return ("", 204)
    if request.content_length and request.content_length > 16 * 1024:
        return jsonify({"ok": False, "error": "Analytics payload is too large."}), 413

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "A JSON analytics payload is required."}), 400
    event_type = str(data.get("event") or "pageview").strip().lower()
    if event_type != "pageview":
        return jsonify({"ok": False, "error": "Unsupported analytics event."}), 400
    path = str(data.get("path") or "/").strip()[:400]
    if not path.startswith("/") or path.startswith("/admin"):
        return jsonify({"ok": False, "error": "Invalid public page path."}), 400
    article_id = str(data.get("article_id") or "").strip()[:180] or None
    session_id = str(data.get("session_id") or "").strip()[:180]
    if len(session_id) < 12:
        return jsonify({"ok": False, "error": "A session identifier is required."}), 400
    language = str(data.get("language") or "").strip().lower()[:16] or None
    referrer = str(data.get("referrer") or "").strip()[:700]
    try:
        from urllib.parse import urlparse
        parsed = urlparse(referrer)
        referrer_host = (parsed.hostname or "direct").lower()[:180]
        if referrer_host in {"samugamedia.com", "www.samugamedia.com"}:
            referrer_host = "internal"
    except Exception:
        referrer_host = "direct"

    session_hash = hashlib.sha256((_CMS_TOKEN_SECRET + ":analytics:" + session_id).encode("utf-8")).hexdigest()[:40]
    # Build 12: every real page load carries a unique event_id. This prevents
    # the fetch/beacon retry pair from double-counting without collapsing a
    # legitimate revisit to the same page during the same hour. Older cached
    # Build 11 clients remain compatible through the hourly fallback key.
    event_id = str(data.get("event_id") or "").strip()[:180]
    if len(event_id) >= 12:
        event_key = hashlib.sha256(f"{session_hash}|{event_type}|{event_id}".encode("utf-8")).hexdigest()
    else:
        hour_bucket = utcnow().strftime("%Y%m%d%H")
        event_key = hashlib.sha256(f"{session_hash}|{event_type}|{path}|{hour_bucket}".encode("utf-8")).hexdigest()
    forwarded_ua = request.headers.get("X-Samuga-User-Agent") or request.headers.get("User-Agent")
    device_type = _analytics_device_type(forwarded_ua)

    try:
        inserted = db_execute("""
            INSERT INTO cms_web_events
              (event_key,event_type,path,article_id,session_hash,referrer_host,device_type,language)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (event_key) DO NOTHING
            RETURNING id
        """, (event_key, event_type, path, article_id, session_hash, referrer_host, device_type, language), fetch="one")
        duplicate = inserted is None
        if duplicate:
            existing = db_execute("SELECT id FROM cms_web_events WHERE event_key=%s LIMIT 1", (event_key,), fetch="one")
            if not existing:
                raise RuntimeError("Database did not confirm the analytics event.")
        return jsonify({"ok": True, "stored": True, "duplicate": duplicate}), (200 if duplicate else 201)
    except Exception as exc:
        log.warning(f"[ANALYTICS] pageview save failed path={path!r}: {exc}")
        return jsonify({"ok": False, "stored": False, "error": "Analytics storage is temporarily unavailable."}), 503


@api_app.get("/api/public-interest")
def api_public_interest():
    """Aggregated public Samuga AI interest radar. No private messages exposed."""
    try:
        rows = db_execute("""
            SELECT topic, platform, SUM(count) AS total
            FROM public_interest_daily
            WHERE day >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY topic, platform
            ORDER BY total DESC
            LIMIT 50
        """, fetch="all") or []
        items = [{"topic": r[0], "platform": r[1], "count": int(r[2] or 0)} for r in rows]
        return jsonify({"ok": True, "window": "7d", "items": items})
    except Exception as e:
        log.error(f"Website API /api/public-interest error: {e}")
        return jsonify({"ok": False, "items": []})


@api_app.get("/api/events")
def api_events():
    """
    Recent Samuga OS events for diagnostics and Master Data Hub integration.
    Returns the last N structured events from the in-process buffer.

    If SAMUGA_EVENTS_SECRET env var is set, requests must include header:
      X-Events-Secret: <value>

    Query params:
      ?type=article.   — filter by event type prefix
      ?limit=50        — max events to return (capped at 200)
    """
    try:
        _secret = os.environ.get("SAMUGA_EVENTS_SECRET", "")
        if _secret:
            import hmac as _hmac
            _provided = request.headers.get("X-Events-Secret", "")
            if not _hmac.compare_digest(_secret, _provided):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
        event_type = (request.args.get("type") or "").strip() or None
        limit      = min(int(request.args.get("limit", 50)), 200)
        events     = get_recent_events(limit=limit, event_type=event_type)
        summary    = event_summary()
        return jsonify({"ok": True, "events": events, "summary": summary})
    except Exception as e:
        log.error(f"Website API /api/events error: {e}")
        return jsonify({"ok": False, "events": [], "summary": {}})


@api_app.get("/api/stories")
def api_stories():
    """
    Public website feed for GitHub Pages.

    Important:
    The website should show article data, not Telegram/Instagram square cards.
    So this endpoint returns clean JSON only: title, summary, category, source, url, time, lang.
    It reads all statuses that mean public/published. Queue items are marked posted
    by queue_for_social() when they enter the public publishing queue.
    """
    client_id = _public_chat_client_id()
    if not _api_rate_allowed(client_id):
        return jsonify({"error": "rate_limited", "stories": []}), 429
    try:
        rows = db_execute("""
            SELECT id, title, summary, category, source, link, posted_at, found_at,
                   lang, status, article_excerpt, article_slug,
                   cover_image_url, cover_video_url, video_poster_url,
                   author_name, author_role, author_photo_url,
                   featured, is_breaking, reading_time_min, updated_at
            FROM articles
            WHERE status IN ('posted','published','social_posted')
            ORDER BY COALESCE(posted_at, found_at) DESC NULLS LAST
            LIMIT 80
        """, fetch="all") or []

        stories = []
        seen_titles = set()

        for row in rows:
            (article_id, title, summary, category, source, link, posted_at, found_at,
             lang, status, article_excerpt, article_slug,
             cover_image_url, cover_video_url, video_poster_url,
             author_name, author_role, author_photo_url,
             featured, is_breaking_row, reading_time_min, updated_at) = row
            dt = posted_at or found_at
            safe_title = _api_clean_text(strip_source_links(title), 500)
            safe_summary = _api_clean_text(strip_source_links(article_excerpt or summary), 420)
            if not safe_title:
                continue
            if not public_text_is_safe(f"{safe_title}\n{safe_summary}"):
                continue

            # Hide old broken Latin Thaana rows from the website feed.
            # New rows are fixed before publish by normalize_article_language_for_public().
            # Manual articles (manual_/manualweb_/manualcms_) are team-written and exempt —
            # an English headline containing a Dhivehi proper noun must not vanish.
            if (not str(article_id).startswith(("manual_", "manualweb_", "manualcms_"))
                    and looks_latin_thaana(f"{safe_title} {safe_summary}")
                    and not _api_has_thaana(f"{safe_title} {safe_summary}")):
                continue

            # Dedupe same headline in API so the site stays clean
            key = _caption_match_key(safe_title) or safe_title.lower()[:80]
            if key in seen_titles:
                continue
            seen_titles.add(key)

            stories.append({
                # ── Existing fields (never changed — fully backward compatible) ─
                "id": article_id,
                "title": safe_title,
                "summary": safe_summary,
                "category": _api_category(category, safe_title, safe_summary),
                "source": SAMUGA_PUBLIC_SOURCE,
                "url": f"/article?id={article_id}",
                "community_url": SAMUGA_PUBLIC_LINK,
                "article_api": _absolute_api_url(f"/api/article?id={article_id}"),
                "slug": article_slug or make_article_slug(safe_title, article_id),
                "time": mvt_display_time(dt),
                "published_at": dt.isoformat() if dt else None,
                "lang": _api_lang(safe_title, safe_summary, lang),
                "status": status or "posted",
                # ── New fields (Sprint A Part 5 — all nullable, safe defaults) ─
                "cover_image": cover_image_url or None,
                "cover_video": cover_video_url or None,
                "video_poster": video_poster_url or cover_image_url or None,
                "author": {
                    "name":  author_name or None,
                    "role":  author_role or None,
                    "photo": author_photo_url or None,
                } if author_name else None,
                "featured": bool(featured),
                "breaking": bool(is_breaking_row),
                "reading_time": int(reading_time_min or 0) or None,
                "updated_at": mvt_display_time(updated_at) if updated_at else None,
            })

        return jsonify(stories)

    except Exception as e:
        log.error(f"Website API /api/stories error: {e}")
        return jsonify([])


@api_app.get("/api/article")
def api_article():
    client_id = _public_chat_client_id()
    if not _api_rate_allowed(client_id):
        return jsonify({"error": "rate_limited"}), 429
    """Full website article page data for GitHub Pages article.html?id=..."""
    try:
        article_id = (request.args.get("id") or "").strip()
        if not article_id:
            return jsonify({"error": "missing article id"}), 400

        row = db_execute("""
            SELECT id, title, summary, category, source, link, posted_at, found_at, lang, status,
                   article_excerpt, article_body, article_slug, is_breaking,
                   cover_image_url, cover_video_url, video_poster_url, cover_caption,
                   media_items, social_caption,
                   author_id, author_name, author_role, author_photo_url,
                   reading_time_min, featured, seo_title, seo_description, keywords,
                   updated_at
            FROM articles
            WHERE id=%s
              AND status IN ('posted','published','social_posted')
            LIMIT 1
        """, (article_id,), fetch="one")

        if not row:
            return jsonify({"error": "article not found"}), 404

        (rid, title, summary, category, source, link, posted_at, found_at, lang, status,
         article_excerpt, article_body, article_slug, is_breaking,
         cover_image_url, cover_video_url, video_poster_url, cover_caption,
         media_items, social_caption,
         author_id, author_name, author_role, author_photo_url,
         reading_time_min, featured, seo_title, seo_description, keywords,
         updated_at) = row

        safe_title = _api_clean_text(strip_source_links(title), 500)
        safe_summary = _api_clean_text(strip_source_links(summary), 1800)
        if not public_text_is_safe(f"{safe_title}\n{safe_summary}"):
            return jsonify({"error": "article failed public safety check"}), 404
        if (not str(rid).startswith(("manual_", "manualweb_", "manualcms_"))
                and looks_latin_thaana(f"{safe_title} {safe_summary}")
                and not _api_has_thaana(f"{safe_title} {safe_summary}")):
            return jsonify({"error": "article language cleanup pending"}), 404
        safe_category = _api_category(category, safe_title, safe_summary)
        safe_lang = _api_lang(safe_title, safe_summary, lang)
        _trusted_body = (str(rid).startswith(("manual_", "manualweb_", "manualcms_", "draft_"))
                         or (author_id and str(author_id).lower() != "samuga_ai")
                         or (author_name and str(author_name).strip().lower() != "samuga ai"))
        body = _public_article_body_for_language(
            rid, article_body, article_excerpt, safe_summary, safe_title,
            safe_category, lang=safe_lang, is_breaking=bool(is_breaking),
            trusted=_trusted_body,
        )
        body = _clean_article_engine_output(body, title=safe_title)
        # A Dhivehi AI page may never expose an English or fallback-summary body.
        if safe_lang == "dv" and not _api_has_thaana(body):
            body = (_clean_article_engine_output(
                article_excerpt or safe_summary or safe_title, title=safe_title
            ) if _trusted_body else "")
        if not body.strip():
            # Last-resort runtime lock for legacy/race-condition rows. This also
            # removes the card from /api/stories until the retry worker succeeds.
            db_execute("""
                UPDATE articles
                SET status=%s, body_retry_at=NOW(), posted_at=NULL, updated_at=NOW()
                WHERE id=%s AND status IN ('posted','published','social_posted')
            """, (WEBSITE_HELD_STATUS, rid))
            return jsonify({"error": "article body pending"}), 404
        dt = posted_at or found_at

        return jsonify({
            # ── Existing fields (never changed — fully backward compatible) ────
            "id": rid,
            "title": safe_title,
            "excerpt": _api_clean_text(article_excerpt or safe_summary, 360),
            "body": body,
            "paragraphs": [p.strip() for p in re.split(r"\r?\n\s*\r?\n+", str(body or "")) if p.strip()],
            "category": safe_category,
            "source": SAMUGA_PUBLIC_SOURCE,
            "source_url": SAMUGA_PUBLIC_LINK,
            "community_url": SAMUGA_PUBLIC_LINK,
            "url": SAMUGA_PUBLIC_LINK,
            "time": mvt_display_time(dt),
            "lang": safe_lang,
            "slug": article_slug or make_article_slug(safe_title, rid),
            "related": related_articles_for_api(rid, safe_category, safe_lang, limit=4),
            # ── New fields (Sprint A Part 5 — all nullable, safe defaults) ────
            "cover_image":   cover_image_url or None,
            "cover_video":   cover_video_url or None,
            "video_poster":  video_poster_url or cover_image_url or None,
            "cover_caption": cover_caption or None,
            "media_items":   list(media_items or []),
            "social_caption": social_caption or None,
            "author": {
                "id":    author_id or None,
                "name":  author_name or None,
                "role":  author_role or None,
                "photo": author_photo_url or None,
            } if (author_name or author_id) else None,
            "reading_time": int(reading_time_min or 0) or None,
            "featured": bool(featured),
            "breaking": bool(is_breaking),
            "seo": {
                "title":       _api_clean_text(seo_title or safe_title, 70),
                "description": _api_clean_text(seo_description or (article_excerpt or safe_summary), 160),
                "keywords":    list(keywords or []),
            },
            "published_at": dt.isoformat() if dt else None,
            "updated_at":   updated_at.isoformat() if updated_at else None,
        })
    except Exception as e:
        log.error(f"Website API /api/article error: {e}")
        return jsonify({"error": "article unavailable"}), 200


@api_app.get("/share")
def share_redirect():
    """
    Server-side rendered HTML for social media crawlers.
    When pasting https://samugamedia.com/share?id=... into Telegram/FB/X,
    crawlers hit this endpoint and get real OG meta tags with title, description,
    and cover image. Humans are immediately redirected to the article page.

    Usage: share this URL instead of the article.html URL.
    Or: configure samugamedia.com to serve this via Cloudflare Worker/redirect.
    """
    try:
        article_id = (request.args.get("id") or "").strip()
        if not article_id:
            return redirect("https://samugamedia.com/index.html", 302)

        row = db_execute("""
            SELECT title, summary, category, cover_image_url, video_poster_url, author_name,
                   seo_title, seo_description, posted_at, article_excerpt, lang
            FROM articles
            WHERE id=%s AND status IN ('posted','published','social_posted')
            LIMIT 1
        """, (article_id,), fetch="one")

        article_url = f"https://samugamedia.com/article?id={article_id}"

        if not row:
            return redirect(article_url, 302)

        (title, summary, category, cover_image_url, video_poster_url, author_name,
         seo_title, seo_description, posted_at, article_excerpt, lang) = row

        og_title       = seo_title or title or "Samuga Media"
        og_desc        = seo_description or article_excerpt or summary or "Live Maldives news powered by Samuga AI."
        og_image       = cover_image_url or video_poster_url or "https://samugamedia.com/assets/SamugaNewsBot_Profile.png"
        og_title       = str(og_title).replace('"', '&quot;')[:200]
        og_desc        = str(og_desc).replace('"', '&quot;')[:300]
        og_image       = str(og_image).replace('"', '&quot;')

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta property="og:type"        content="article">
  <meta property="og:site_name"   content="Samuga Media">
  <meta property="og:title"       content="{og_title}">
  <meta property="og:description" content="{og_desc}">
  <meta property="og:image"       content="{og_image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url"         content="{article_url}">
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="{og_title}">
  <meta name="twitter:description" content="{og_desc}">
  <meta name="twitter:image"       content="{og_image}">
  <meta name="description"         content="{og_desc}">
  <title>{og_title} | Samuga Media</title>
  <link rel="canonical" href="{article_url}">
  <meta http-equiv="refresh" content="0;url={article_url}">
</head>
<body>
  <p><a href="{article_url}">Read article on Samuga Media</a></p>
  <script>window.location.replace("{article_url}")</script>
</body>
</html>"""
        from flask import Response
        return Response(html, 200, content_type="text/html; charset=utf-8")

    except Exception as e:
        log.error(f"/share endpoint error: {e}")
        return redirect("https://samugamedia.com/index.html", 302)


# ── Public Website Chat API ───────────────────────────────────────────────────
# Safe public chat endpoint for samugamedia.com.
# IMPORTANT: Website chat should answer from TODAY'S Samuga archive first,
# not from old model memory. It also cleans markdown so replies feel human.
_PUBLIC_CHAT_RATE = {}  # ip -> [timestamps]
_PUBLIC_CHAT_LIMIT = 12
_PUBLIC_CHAT_WINDOW = 60 * 10  # 12 messages per 10 minutes per IP
_PUBLIC_CHAT_RATE_LOCK = threading.RLock()  # guards _PUBLIC_CHAT_RATE

# Stories/article endpoint rate limit: 120 requests per minute per IP
_API_RATE = {}  # ip -> [timestamps]
_API_RATE_LIMIT = 120
_API_RATE_WINDOW = 60
_API_RATE_LOCK = threading.RLock()

def _api_rate_allowed(client_id):
    """Rate limit for /api/stories and /api/article endpoints."""
    now = time.time()
    window_start = now - _API_RATE_WINDOW
    with _API_RATE_LOCK:
        hits = [t for t in _API_RATE.get(client_id, []) if t >= window_start]
        if len(hits) >= _API_RATE_LIMIT:
            _API_RATE[client_id] = hits
            return False
        hits.append(now)
        _API_RATE[client_id] = hits
        if len(_API_RATE) > 2000:
            for k in list(_API_RATE.keys())[:400]:
                _API_RATE.pop(k, None)
        return True
_PUBLIC_CHAT_MAX_CHARS = 600
_PUBLIC_CHAT_BLOCKED_COMMANDS = [
    "/approve", "/approved", "/reject", "/confirm", "/cancel", "/ai ",
    "/remember", "/forget", "/memory", "/learning", "/post", "/queue",
    "approve this", "reject this", "post this", "send to telegram", "send to facebook",
    "send to instagram", "content lab", "core team", "admin", "database", "token",
    "api key", "password", "environment variable"
]
_PUBLIC_CHAT_NEWS_WORDS = [
    "latest", "news", "headline", "headlines", "today", "update", "updates", "breaking",
    "current", "what happened", "briefing", "summary", "summarize", "ޚަބަރު", "އަޕްޑޭޓް", "މިއަދު"
]

def _public_chat_client_id():
    """Return a stable-ish client ID for rate limiting behind Railway/proxies."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:80]
    return (request.remote_addr or "unknown")[:80]

def _public_chat_allowed(client_id):
    """Thread-safe in-memory rate limiter for public chat."""
    now = time.time()
    window_start = now - _PUBLIC_CHAT_WINDOW
    with _PUBLIC_CHAT_RATE_LOCK:
        hits = [t for t in _PUBLIC_CHAT_RATE.get(client_id, []) if t >= window_start]
        if len(hits) >= _PUBLIC_CHAT_LIMIT:
            _PUBLIC_CHAT_RATE[client_id] = hits
            return False, _PUBLIC_CHAT_LIMIT
        hits.append(now)
        _PUBLIC_CHAT_RATE[client_id] = hits
        if len(_PUBLIC_CHAT_RATE) > 1000:
            for k in list(_PUBLIC_CHAT_RATE.keys())[:200]:
                _PUBLIC_CHAT_RATE.pop(k, None)
        return True, _PUBLIC_CHAT_LIMIT

def _public_chat_clean_message(message):
    """Clean and cap public website message."""
    msg = _api_clean_text(message, _PUBLIC_CHAT_MAX_CHARS)
    return msg.strip()

def _public_chat_is_blocked(message):
    """Block admin/control prompts from the public website chat."""
    low = (message or "").lower()
    if low.startswith("/") and not low.startswith("/search"):
        return True
    return any(term in low for term in _PUBLIC_CHAT_BLOCKED_COMMANDS)

def _public_chat_is_news_query(message):
    low = (message or "").lower()
    return any(w in low for w in _PUBLIC_CHAT_NEWS_WORDS)

def _public_chat_clean_reply(reply):
    """Make AI replies feel like chat, not raw Markdown/bot formatting."""
    txt = str(reply or "")
    txt = txt.replace("**", "")
    txt = txt.replace("__", "")
    txt = txt.replace("###", "")
    txt = txt.replace("##", "")
    txt = txt.replace("#", "")
    txt = re.sub(r"\n\s*[-*]\s+", "\n• ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return _api_clean_text(txt.strip(), 1000)

def _public_chat_latest_rows(lang=None, limit=8, hours=30):
    """Read newest public website stories from DB. Default: recent/current only."""
    try:
        since = utcnow() - timedelta(hours=hours)
        rows = db_execute("""
            SELECT title, summary, category, source, link, posted_at, found_at, lang, status
            FROM articles
            WHERE status IN ('posted','published','social_posted')
              AND COALESCE(posted_at, found_at) >= %s
            ORDER BY COALESCE(posted_at, found_at) DESC NULLS LAST
            LIMIT %s
        """, (since, limit * 3), fetch="all") or []

        clean = []
        seen = set()
        for title, summary, category, source, link, posted_at, found_at, row_lang, status in rows:
            safe_title = _api_clean_text(strip_source_links(title), 260)
            safe_summary = _api_clean_text(strip_source_links(summary), 520)
            if not safe_title or not public_text_is_safe(f"{safe_title}\n{safe_summary}"):
                continue
            if not public_text_is_safe(f"{safe_title}\n{safe_summary}"):
                continue
            detected = _api_lang(safe_title, safe_summary, row_lang)
            if lang in ("en", "dv") and detected != lang:
                continue
            key = _caption_match_key(safe_title) or safe_title.lower()[:90]
            if key in seen:
                continue
            seen.add(key)
            dt = posted_at or found_at
            clean.append({
                "title": safe_title,
                "summary": safe_summary,
                "category": _api_category(category, safe_title, safe_summary),
                "source": SAMUGA_PUBLIC_SOURCE,
                "url": SAMUGA_PUBLIC_LINK,
                "time": mvt_display_time(dt),
                "lang": detected
            })
            if len(clean) >= limit:
                break
        return clean
    except Exception as e:
        log.error(f"Website chat latest rows error: {e}")
        return []

def _public_chat_search_rows(message, lang=None, limit=6):
    """Simple archive search from website DB for specific user topics."""
    try:
        terms = [w for w in re.findall(r"[\w\u0780-\u07BF]{3,}", message or "") if w.lower() not in {
            "latest", "news", "today", "what", "about", "show", "give", "tell", "ޚަބަރު", "މިއަދު"
        }]
        if not terms:
            return []
        # Use up to 3 strong terms to avoid huge/slow search.
        q = " ".join(terms[:3])
        pattern = f"%{q}%"
        rows = db_execute("""
            SELECT title, summary, category, source, link, posted_at, found_at, lang, status
            FROM articles
            WHERE status IN ('posted','published','social_posted')
              AND (title ILIKE %s OR summary ILIKE %s OR source ILIKE %s)
            ORDER BY COALESCE(posted_at, found_at) DESC NULLS LAST
            LIMIT %s
        """, (pattern, pattern, pattern, limit * 3), fetch="all") or []
        clean = []
        seen = set()
        for title, summary, category, source, link, posted_at, found_at, row_lang, status in rows:
            safe_title = _api_clean_text(strip_source_links(title), 260)
            safe_summary = _api_clean_text(strip_source_links(summary), 520)
            detected = _api_lang(safe_title, safe_summary, row_lang)
            if lang in ("en", "dv") and detected != lang:
                continue
            key = _caption_match_key(safe_title) or safe_title.lower()[:90]
            if not safe_title or key in seen:
                continue
            seen.add(key)
            dt = posted_at or found_at
            clean.append({
                "title": safe_title,
                "summary": safe_summary,
                "category": _api_category(category, safe_title, safe_summary),
                "source": SAMUGA_PUBLIC_SOURCE,
                "url": SAMUGA_PUBLIC_LINK,
                "time": mvt_display_time(dt),
                "lang": detected
            })
            if len(clean) >= limit:
                break
        return clean
    except Exception as e:
        log.error(f"Website chat search rows error: {e}")
        return []

def _public_chat_format_news(rows, lang="en", searched=False):
    """Friendly website chat answer from real Samuga DB rows."""
    if not rows:
        return "I don't see fresh public stories in the website archive yet bro. Try again in a few minutes." if lang != "dv" else "ވެބްސައިޓް އާކައިވްގައި އަދި އާ ޚަބަރެއް ނުފެނޭ. މަދުކޮށް ފަހުން އަހާލާ."

    if lang == "dv":
        intro = "މިއީ ސަމުގާގެ އެންމެ އާ ޚަބަރުތައް:" if not searched else "މިއީ ހޯދުމުން ފެނުނު ޚަބަރުތައް:"
        parts = [intro]
        for i, r in enumerate(rows[:6], 1):
            line = f"{i}. {r['title']}"
            if r.get("summary"):
                line += f" — {r['summary'][:180]}"
            parts.append(line)
        parts.append("އެއް ޚަބަރެއް ތަފްސީލުން ބުނަން ބޭނުންތަ؟")
        return "\n\n".join(parts)

    intro = "Here are the latest stories on Samuga right now:" if not searched else "Here’s what I found in the Samuga archive:"
    parts = [intro]
    for i, r in enumerate(rows[:6], 1):
        line = f"{i}. {r['title']}"
        if r.get("summary"):
            line += f" — {r['summary'][:190]}"
        line += f"\nSamuga Media • {r.get('time','Recent')}"
        parts.append(line)
    parts.append("Ask me about any one of these and I’ll explain it clearly.")
    return "\n\n".join(parts)

def _public_chat_tavily_context(message, lang="en"):
    """Live search context for website chat, sanitized so no source URLs leak."""
    try:
        if not TAVILY_API_KEY:
            return ""
        q = f"Maldives latest news {message}" if lang != "dv" else f"Maldives news {message}"
        ctx = tavily_search(q)
        return strip_source_links(_api_clean_text(ctx, 1200))
    except Exception as e:
        log.warning(f"Website chat Tavily context failed: {e}")
        return ""

def _public_chat_context(rows):
    lines = []
    for r in rows[:8]:
        lines.append(f"- {r['title']} | {r.get('summary','')} | Samuga Media | {r.get('time','')}")
    return "\n".join(lines)



# ── Unified Public Samuga AI Brain ────────────────────────────────────────────
# Website chat, public Telegram DM, and future WhatsApp should all call this one
# function so Samuga AI has one public personality, one memory, and one analytics stream.

_PUBLIC_TOPIC_KEYWORDS = {
    "housing": ["housing","flat","flats","rent","land","apartment","gedhoru","hiya","vinares","ފްލެޓް","ބިން"],
    "politics": ["politics","president","minister","majlis","parliament","mdp","pnc","ppm","election","bill","law","ރައީސް","މަޖިލީސް"],
    "economy": ["economy","dollar","usd","mvr","rufiyaa","debt","tax","price","inflation","budget","ޑޮލަރ","ރުފިޔާ"],
    "tourism": ["tourism","tourist","resort","travel","airport","arrival","hotel","ޓޫރިޒަމް"],
    "crime": ["police","arrest","court","murder","stab","drug","gang","theft","ފުލުހުން","ކޯޓު"],
    "health": ["health","hospital","doctor","clinic","aasandha","disease","ސިއްހަތު","ހޮސްޕިޓަލް"],
    "education": ["school","student","visa","university","teacher","exam","ސްކޫލް","ދަރިވަރު"],
    "weather": ["weather","rain","storm","wind","sea","alert","mms","ވައި","ވާރޭ"],
    "foreign": ["iran","israel","us","usa","america","india","china","qatar","uk","war","global","world","އިންޑިޔާ","ޗައިނާ"],
    "sports": ["sports","football","fifa","match","team","ކުޅިވަރު","ފުޓްބޯޅަ"],
}

_CURRENT_GLOBAL_WORDS = [
    "now","current","latest","today","breaking","happening","war","conflict","iran","israel",
    "america","us ","usa","ukraine","russia","qatar","oil","global","world"
]

def public_detect_topics(message):
    low = (message or "").lower()
    topics = []
    for topic, kws in _PUBLIC_TOPIC_KEYWORDS.items():
        if any(k in low for k in kws):
            topics.append(topic)
    if not topics and _public_chat_is_news_query(message):
        topics.append("news")
    if not topics:
        topics.append("general")
    return topics[:5]

def public_detect_intent(message):
    low = (message or "").lower()
    if any(w in low for w in ["hi", "hello", "hey", "salaam", "ހެލޯ"]) and len(low.split()) <= 4:
        return "greeting"
    if any(w in low for w in ["breaking", "urgent", "ބްރޭކިންގ"]):
        return "breaking_news"
    if any(w in low for w in ["summarize", "summary", "briefing", "biggest", "today", "މިއަދު"]):
        return "briefing"
    if _public_chat_is_news_query(message):
        return "news_query"
    if any(w in low for w in _CURRENT_GLOBAL_WORDS):
        return "current_global"
    return "general_chat"

def public_is_global_current_query(message):
    low = " " + (message or "").lower() + " "
    local_hits = ["maldives","raajje","dhivehi","male","malé","samuga","ރާއްޖެ","ދިވެހި"]
    if any(x in low for x in local_hits):
        return False
    return any(w in low for w in _CURRENT_GLOBAL_WORDS) or any(t in public_detect_topics(message) for t in ["foreign"])

def public_log_chat(platform, session_id, user_key, user_message, bot_reply, lang, intent, topics, used_search=False):
    """Store public Samuga AI chats for interest analytics across website/Telegram/future WhatsApp."""
    try:
        if not DB_ENABLED:
            return
        topics = topics or ["general"]
        db_execute("""
            INSERT INTO public_chat_messages
                (platform, session_id, user_key, user_message, bot_reply, lang, intent, topics, used_search)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            platform, str(session_id or "")[:120], str(user_key or "")[:160],
            str(user_message or "")[:1200], str(bot_reply or "")[:1800],
            lang, intent, topics, bool(used_search)
        ))
        for topic in topics:
            db_execute("""
                INSERT INTO public_interest_daily (day, topic, platform, count, updated_at)
                VALUES (CURRENT_DATE, %s, %s, 1, NOW())
                ON CONFLICT (day, topic, platform)
                DO UPDATE SET count = public_interest_daily.count + 1, updated_at = NOW()
            """, (topic, platform))
    except Exception as e:
        log.debug(f"Public chat analytics save failed: {e}")

def public_session_key(platform, user_key, session_id=""):
    platform = str(platform or "web").lower()
    user_key = str(user_key or "anon")[:80]
    session_id = str(session_id or "default")[:80]
    if platform == "telegram":
        return f"public:telegram:{user_key}"
    if platform == "whatsapp":
        return f"public:whatsapp:{user_key}"
    return f"public:web:{user_key}:{session_id}"

def public_get_recent_interest(limit=8):
    try:
        rows = db_execute("""
            SELECT topic, SUM(count) AS c
            FROM public_interest_daily
            WHERE day >= CURRENT_DATE - INTERVAL '3 days'
            GROUP BY topic
            ORDER BY c DESC
            LIMIT %s
        """, (limit,), fetch="all") or []
        return ", ".join([f"{r[0]} ({r[1]})" for r in rows])
    except Exception:
        return ""

def public_build_live_context(message, lang="en"):
    """Use Tavily smartly: local queries search Maldives; global/current queries search globally."""
    try:
        if not TAVILY_API_KEY:
            return "", False
        if public_is_global_current_query(message):
            q = message
        elif _public_chat_is_news_query(message):
            q = f"Maldives news {message}"
        else:
            # For normal questions we usually don't need search.
            return "", False
        ctx = tavily_search(q)
        return strip_source_links(_api_clean_text(ctx, 1800)), bool(ctx)
    except Exception as e:
        log.warning(f"Public Samuga AI live search failed: {e}")
        return "", False

def public_samuga_ai_chat(message, platform="web", user_key="", session_id="", lang=None):
    """
    One public Samuga AI for website + @SamugaNewsBot + future WhatsApp.
    This is NOT the private core-team brain.
    """
    message = _public_chat_clean_message(message)
    if not message:
        return "Ask me something bro. I can chat or help with latest news."

    detected_lang = "dv" if (lang == "dv" or is_dhivehi(message)) else "en"
    skey = public_session_key(platform, user_key, session_id)
    history = get_conversation(skey)[-8:]
    intent = public_detect_intent(message)
    topics = public_detect_topics(message)

    # Story intelligence first if the archive can directly answer.
    story_answer = None
    try:
        story_answer = answer_story_query(message)
    except Exception as e:
        log.debug(f"Public story query fallback: {e}")

    latest_rows = []
    search_rows = []
    db_context = ""
    if intent in ("news_query", "breaking_news", "briefing", "current_global") or topics != ["general"]:
        latest_rows = _public_chat_latest_rows(lang=None if detected_lang == "en" else "dv", limit=8, hours=48)
        search_rows = _public_chat_search_rows(message, lang=None if detected_lang == "en" else "dv", limit=6)
        context_rows = search_rows or latest_rows
        if intent == "breaking_news":
            breaking_rows = [r for r in latest_rows if str(r.get("category","")).upper() == "BREAKING"]
            context_rows = breaking_rows or latest_rows[:4]
        db_context = _public_chat_context(context_rows[:6])

    live_context, used_search = public_build_live_context(message, lang=detected_lang)
    interests = public_get_recent_interest()

    if story_answer and not public_is_global_current_query(message):
        reply = _public_chat_clean_reply(story_answer)
        add_to_conversation(skey, "user", message)
        add_to_conversation(skey, "assistant", reply)
        public_log_chat(platform, session_id, user_key, message, reply, detected_lang, intent, topics, used_search=False)
        return reply

    _report_cta = ""
    if platform == "telegram":
        _report_cta = """
ANONYMOUS REPORTING FEATURE (Telegram only):
- This bot has a "Report" flow: users can send a short description, location, time,
  optional photos/videos, and choose to stay completely anonymous — even Samuga Media
  won't know who sent it. Reports go to the editorial team for review before publishing.
- Only mention this if the user's message suggests they witnessed, have evidence of, or
  want to share something newsworthy (e.g. an accident, incident, hazard, or "I saw X" —
  not generic news questions like "what's happening in Malé").
- Mention it naturally, once, in your own words — don't repeat it every reply, and don't
  force it into unrelated conversations. If they already seem to be reporting something,
  just tell them they can type "report" or say what happened directly.
"""

    system = f"""You are Samuga AI, the single public chatbot for Samuga Media.
You are used on the website, Telegram @SamugaNewsBot, and later WhatsApp.
You are friendly, sharp, and useful — like a Maldivian news buddy, not a hard-coded bot.

IMPORTANT IDENTITY:
- You are the PUBLIC Samuga AI, not the private core-team newsroom brain.
- Never reveal admin/content-lab/private commands.
- You can answer Maldives news, global current events, and normal questions.
- For current/global questions, use live search context if provided.
- For Maldives questions, use Samuga archive first, then live search if helpful.
- Do not include external source URLs. Send people to @samugacommunity for Samuga updates.
- Keep replies conversational. No markdown **, ###, long separators, or robotic lists.
- Short by default. If news: max 3 items unless user asks for more.
- Remember the chat history and answer follow-ups naturally.
- If user uses Dhivehi/Thaana, answer in natural Dhivehi. If English, answer in English.
{_report_cta}
Public interest radar from recent chats: {interests or "not enough data yet"}.
"""

    user_block = f"""User message:
{message}

Intent: {intent}
Topics: {", ".join(topics)}
Platform: {platform}
Fresh Samuga archive context:
{db_context or "No direct Samuga archive context found."}

Live search context:
{live_context or "No live search context used or available."}
"""

    try:
        messages = []
        for h in history[-8:]:
            role = h.get("role")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:1200]})
        messages.append({"role": "user", "content": user_block})

        if detected_lang == "dv" and GEMINI_API_KEY:
            # Gemini is stronger for Dhivehi. Include history manually in prompt.
            hist_txt = "\n".join([f"{h.get('role')}: {h.get('content','')}" for h in history[-6:]])
            gemini_prompt = f"""{system}

Recent chat history:
{hist_txt}

{user_block}

Answer now in natural Dhivehi Thaana if the user used Dhivehi; otherwise English.
"""
            reply = _gemini_post(gemini_prompt, timeout=25) or ""
            if not reply:
                raise RuntimeError("Gemini public chat returned empty")
        else:
            msg = ai.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=650,
                system=system,
                messages=messages
            )
            reply = msg.content[0].text.strip()

    except Exception as e:
        log.error(f"Unified public Samuga AI failed: {e}")
        # Safe fallback: show latest DB rows if available.
        if latest_rows:
            reply = _public_chat_format_news(latest_rows[:3], lang=detected_lang)
        else:
            reply = "I had a small issue checking live updates bro. Try again in a moment."

    reply = _public_chat_clean_reply(reply)
    add_to_conversation(skey, "user", message)
    add_to_conversation(skey, "assistant", reply)
    public_log_chat(platform, session_id, user_key, message, reply, detected_lang, intent, topics, used_search=used_search)
    return reply


@api_app.route("/api/chat", methods=["POST", "OPTIONS"])
def api_chat():
    """Public website chat endpoint using the unified public Samuga AI brain."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    try:
        client_id = _public_chat_client_id()
        allowed, limit = _public_chat_allowed(client_id)
        if not allowed:
            return jsonify({
                "ok": False,
                "error": "rate_limited",
                "reply": "Too many messages too fast bro 😅 Please wait a few minutes and try again."
            }), 429

        data = request.get_json(silent=True) or {}
        message = _public_chat_clean_message(data.get("message", ""))
        session_id = _api_clean_text(data.get("session_id", "web"), 80) or "web"
        requested_lang = str(data.get("lang") or "").lower()
        lang = "dv" if requested_lang == "dv" or is_dhivehi(message) else "en"

        if not message:
            return jsonify({
                "ok": False,
                "error": "empty_message",
                "reply": "Ask me something bro. I can chat or help with latest news."
            }), 400

        if _public_chat_is_blocked(message):
            return jsonify({
                "ok": True,
                "reply": "I can only do public chat and public news here bro. Posting, approvals, and newsroom controls are only for the private Samuga team."
            })

        log.info(f"🌐 Website public Samuga AI {client_id}: {message[:80]}")
        reply = public_samuga_ai_chat(
            message=message,
            platform="web",
            user_key=client_id,
            session_id=session_id,
            lang=lang
        )

        return jsonify({
            "ok": True,
            "reply": reply,
            "source": "Unified public Samuga AI",
            "mode": "public_samuga_ai",
            "rate_limit": {"limit": limit, "window_seconds": _PUBLIC_CHAT_WINDOW}
        })

    except Exception as e:
        log.error(f"Website API /api/chat error: {e}")
        return jsonify({
            "ok": False,
            "error": "server_error",
            "reply": "Something went wrong bro 😅 Try again in a moment."
        })

def start_api_server():
    """Start the public website API on Railway's assigned PORT."""
    port = int(os.environ.get("PORT", 8080))
    log.info(f"🌐 Website API starting on port {port}")
    api_app.run(host="0.0.0.0", port=port, use_reloader=False)



# ── State Persistence (JSON fallback — survives Railway restarts) ─────────────
import os as _os, json as _json, threading as _threading
DATA_DIR   = "/data"
_os.makedirs(DATA_DIR, exist_ok=True)
SEEN_FILE  = _os.path.join(DATA_DIR, "seen_articles.json")
STATE_FILE = _os.path.join(DATA_DIR, "bot_state.json")
_state_lock = _threading.RLock()  # reentrant for safety against nested persist calls
_poll_offset = [0]

def load_seen():
    try:
        if _os.path.exists(SEEN_FILE):
            with open(SEEN_FILE) as f: return set(_json.load(f))
    except Exception as e: log.error(f"load_seen: {e}")
    return set()

def save_seen(seen):
    """Save seen article IDs, capped at 5000 most recent entries."""
    try:
        items = list(seen)
        if len(items) > 5000:
            items = items[-5000:]
        with open(SEEN_FILE,"w") as f: _json.dump(items, f)
    except Exception as e: log.error(f"save_seen: {e}")

def _load_state():
    try:
        if _os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f: return _json.load(f)
    except Exception as e: log.error(f"load_state: {e}")
    return {}

def _save_state(state):
    try:
        with _state_lock:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as f: _json.dump(state, f, default=str)
            _os.replace(tmp, STATE_FILE)
    except Exception as e: log.error(f"save_state: {e}")

def _serialize_social_counts():
    sc = dict(social_post_counts)
    if sc.get("date") and not isinstance(sc["date"], str):
        sc["date"] = sc["date"].isoformat()
    return sc

def _serialize_approval_queue():
    """Serialize queue for STATE FILE — includes card_bytes and bg image as base64."""
    import base64
    out = {}
    for k, v in approval_queue.items():
        item = dict(v)
        if item.get("card_bytes"):
            try:
                item["card_bytes"] = base64.b64encode(item["card_bytes"]).decode()
                item["_card_b64"] = True
            except Exception:
                item["card_bytes"] = None
                item["_card_b64"] = False
        # _bg_image_b64 is already a base64 string — safe to keep in JSON.
        # Do NOT pop it — this is the whole point of encoding it as base64.
        item["created_at"] = item["created_at"].isoformat() if item.get("created_at") else None
        out[k] = item
    return out

def _serialize_approval_queue_for_pg():
    """Serialize queue for POSTGRESQL — strips card_bytes (too large for jsonb).
    Keeps _bg_image_b64 (4KB per item — safe for jsonb).
    On restore, EN cards without bytes will be marked as needing rebuild.
    DV cards never had bytes anyway (built on approval).
    The critical data (title, dv_text, timing, bg image) all survives."""
    out = {}
    for k, v in approval_queue.items():
        item = dict(v)
        # Strip card_bytes — can be 100-500KB as base64, causes silent PG failures
        item["card_bytes"] = None
        item["_card_b64"] = False
        item["_needs_card_rebuild"] = True  # flag so restore knows to skip auto-posting
        item["created_at"] = item["created_at"].isoformat() if item.get("created_at") else None
        # _bg_image_b64 is only ~4KB — safe to keep in PG jsonb
        out[k] = item
    return out

def persist_state():
    """Snapshot all volatile state to disk."""
    try:
        sq_serialized = []
        with _social_queue_lock:
            for item in _social_queue:
                sq_serialized.append({
                    "img_bytes_b64": __import__("base64").b64encode(item["img_bytes"]).decode(),
                    "caption": item["caption"],
                    "queued_at": item["queued_at"].isoformat(),
                    "article_id": item.get("article_id"),
                    "title": item.get("title",""),
                    "summary": item.get("summary",""),
                    "cat": item.get("cat","LOCAL"),
                    "source": item.get("source","Samuga Media"),
                    "link": item.get("link",""),
                    "lang": item.get("lang","en"),
                    "is_breaking": item.get("is_breaking", False),
                    "manual_post": item.get("manual_post", False),
                    "key_label": item.get("key_label","Post"),
                    "tg_ok": item.get("tg_ok", False),
                    "post_telegram": False,
                    "notify_chat_id": item.get("notify_chat_id"),
                    "notify_thread_id": item.get("notify_thread_id"),
                })
        try:
            from scoring import _recent_titles_lock as _rtl
        except ImportError:
            import threading as _thr; _rtl = _thr.RLock()
        with _rtl:
            recent_titles_snapshot = list(recent_story_titles)
        with _approval_lock:
            approval_counter_snapshot = _approval_counter[0]
            approval_queue_snapshot   = _serialize_approval_queue()
        with _state_counters_lock:
            daily_sports_snapshot  = dict(daily_sports_count)
            daily_world_snapshot   = dict(daily_world_count)
            daily_tourism_snapshot = dict(daily_tourism_count)
            social_counts_snapshot = _serialize_social_counts()
            lrt_snapshot           = last_regular_post_time
        with _polls_lock:
            polls_snapshot = dict(polls_today)

        state = {
            "recent_story_titles": [(t, ts.isoformat()) for (t, ts) in recent_titles_snapshot],
            "recent_posts": recent_posts[-50:],
            "analytics": analytics,
            "daily_sports_count": daily_sports_snapshot,
            "daily_world_count": daily_world_snapshot,
            "daily_tourism_count": daily_tourism_snapshot,
            "social_post_counts": social_counts_snapshot,
            "polls_today": polls_snapshot,
            "last_regular_post_time": lrt_snapshot.isoformat() if lrt_snapshot else None,
            "last_social_post_time": _last_social_post_time.isoformat() if _last_social_post_time else None,
            "approval_counter": approval_counter_snapshot,
            "approval_queue": approval_queue_snapshot,
            "poll_offset": _poll_offset[0],
            "social_queue": sq_serialized,
            "website_banner": website_banner,
            "source_health": get_source_health_snapshot(),
            "cluster_store": get_cluster_store_snapshot(),
            "pending_cover_photo": {k: v for k, v in _pending_cover_photo.items() if k != "expires_at"} if _pending_cover_photo else {},
            "ops_watchdog_state": {
                "source_health_alerts": {k: v.isoformat() if isinstance(v, datetime) else v for k, v in _ops_watchdog_state.get("source_health_alerts", {}).items()},
                "duplicate_hits_recent": [t.isoformat() for t in _ops_watchdog_state.get("duplicate_hits_recent", []) if isinstance(t, datetime)],
                "manual_post_failures": [t.isoformat() for t in _ops_watchdog_state.get("manual_post_failures", []) if isinstance(t, datetime)],
                "social_queue_stuck_since": _ops_watchdog_state.get("social_queue_stuck_since").isoformat() if isinstance(_ops_watchdog_state.get("social_queue_stuck_since"), datetime) else None,
                "last_posted_dv": _ops_watchdog_state.get("last_posted_dv", 0),
            },
        }
        _save_state(state)
        # Also persist approval queue to PostgreSQL — survives Railway restarts/crashes
        # Use lightweight version (no card_bytes) to prevent silent PG save failures
        try:
            kv_set("approval_queue_backup", _serialize_approval_queue_for_pg())
            kv_set("approval_counter_backup", _approval_counter[0])
        except Exception as pg_e:
            log.warning(f"persist_state PG backup: {pg_e}")
    except Exception as e:
        log.error(f"persist_state: {e}")

def restore_state():
    """Load persisted state back into memory on startup."""
    global recent_story_titles, recent_posts, analytics
    global daily_sports_count, daily_world_count, daily_tourism_count
    global social_post_counts, polls_today, last_regular_post_time
    state = _load_state()
    if not state:
        log.info("📦 No saved state — starting fresh")
        return
    import base64
    try:
        recent_story_titles.clear()
        for (t, ts) in state.get("recent_story_titles", []):
            try: recent_story_titles.append((t, datetime.fromisoformat(ts)))
            except Exception: pass
        recent_posts.clear()
        recent_posts.extend(state.get("recent_posts", []))
        analytics.update(state.get("analytics", {}))
        daily_sports_count.update(state.get("daily_sports_count", {}))
        daily_world_count.update(state.get("daily_world_count", {}))
        daily_tourism_count.update(state.get("daily_tourism_count", {}))
        social_post_counts.update(state.get("social_post_counts", {}))
        polls_today.update(state.get("polls_today", {}))
        lrt = state.get("last_regular_post_time")
        if lrt:
            try: last_regular_post_time = datetime.fromisoformat(lrt)
            except Exception: pass
        _approval_counter[0] = state.get("approval_counter", 0)
        _poll_offset[0] = state.get("poll_offset", 0)
        try:
            website_banner.update(state.get("website_banner", {}))
        except Exception:
            pass
        try:
            load_source_health(state.get("source_health", {}))
        except Exception:
            pass
        try:
            load_cluster_store(state.get("cluster_store", {}))
        except Exception as _cs_e:
            log.warning(f"restore_state: cluster_store restore failed: {_cs_e}")
        try:
            _pcp = state.get("pending_cover_photo", {}) or {}
            # Also try PostgreSQL KV — more reliable than state file on rapid restart
            try:
                _pcp_pg = kv_get("pending_cover_photo") or {}
                if _pcp_pg and _pcp_pg.get("article_id"):
                    _pcp = _pcp_pg  # PG takes priority — it was saved most recently
            except Exception:
                pass
            if _pcp and _pcp.get("article_id") and _pcp.get("title"):
                _pending_cover_photo.clear()
                _pending_cover_photo.update(_pcp)
                _pending_cover_photo["expires_at"] = utcnow().timestamp() + 600
                log.info(f"📝 Pending cover photo restored: {_pcp.get('title','')[:50]}")
        except Exception:
            pass
        try:
            ws = state.get("ops_watchdog_state", {}) or {}
            _ops_watchdog_state["source_health_alerts"] = {k: datetime.fromisoformat(v) for k, v in (ws.get("source_health_alerts", {}) or {}).items() if v}
            _ops_watchdog_state["duplicate_hits_recent"] = [datetime.fromisoformat(t) for t in (ws.get("duplicate_hits_recent", []) or []) if t]
            _ops_watchdog_state["manual_post_failures"] = [datetime.fromisoformat(t) for t in (ws.get("manual_post_failures", []) or []) if t]
            sss = ws.get("social_queue_stuck_since")
            _ops_watchdog_state["social_queue_stuck_since"] = datetime.fromisoformat(sss) if sss else None
            _ops_watchdog_state["last_posted_dv"] = int(ws.get("last_posted_dv", 0) or 0)
        except Exception:
            pass
        global _last_social_post_time
        lspt = state.get("last_social_post_time")
        if lspt:
            try: _last_social_post_time = datetime.fromisoformat(lspt)
            except Exception: pass
        sq = state.get("social_queue", [])
        if sq:
            import base64 as _b64
            with _social_queue_lock:
                for item in sq:
                    try:
                        _social_queue.append({
                            "img_bytes": _b64.b64decode(item["img_bytes_b64"]),
                            "caption": item["caption"],
                            "queued_at": datetime.fromisoformat(item["queued_at"]),
                            "article_id": item.get("article_id"),
                            "title": item.get("title",""),
                            "summary": item.get("summary",""),
                            "cat": item.get("cat","LOCAL"),
                            "source": item.get("source","Samuga Media"),
                            "link": item.get("link",""),
                            "lang": item.get("lang","en"),
                            "is_breaking": item.get("is_breaking", False),
                            "manual_post": item.get("manual_post", False),
                            "key_label": item.get("key_label","Post"),
                            "tg_ok": item.get("tg_ok", False),
                            "post_telegram": False,
                            "notify_chat_id": item.get("notify_chat_id"),
                            "notify_thread_id": item.get("notify_thread_id"),
                        })
                    except Exception: pass
            log.info(f"📲 Social queue restored: {len(_social_queue)} post(s) waiting")
        # Restore approval queue — try PostgreSQL first (survives crashes), then fall back to file
        pg_queue = {}
        try:
            pg_queue = kv_get("approval_queue_backup", {}) or {}
            if pg_queue:
                log.info(f"📦 Loading approval queue from PostgreSQL ({len(pg_queue)} items)")
        except Exception as pg_e:
            log.debug(f"restore PG queue: {pg_e}")

        # Merge: PG takes priority for keys it has, file fills the rest
        queue_source = {**state.get("approval_queue", {}), **pg_queue}

        for k, item in queue_source.items():
            try:
                if item.get("_card_b64") and item.get("card_bytes"):
                    item["card_bytes"] = base64.b64decode(item["card_bytes"])
                item.pop("_card_b64", None)
                item["created_at"] = datetime.fromisoformat(item["created_at"]) if item.get("created_at") else utcnow()
                with _approval_lock:
                    approval_queue[k] = item
            except Exception as e:
                log.error(f"restore approval {k}: {e}")

        # Also restore approval counter from PG if available
        try:
            pg_counter = kv_get("approval_counter_backup", None)
            if pg_counter is not None and pg_counter > _approval_counter[0]:
                _approval_counter[0] = pg_counter
        except Exception:
            pass
        log.info(f"📦 State restored: {len(recent_story_titles)} dedup titles, "
                 f"{len(approval_queue)} pending cards, {len(recent_posts)} recent posts")
        # Alert team if pending cards were restored after restart
        log.info(f"[PG] Queue backup status: {len(approval_queue)} cards in queue, counter={_approval_counter[0]}")
        if len(approval_queue) > 0:
            try:
                lines = ["🔄 <b>Bot restarted — pending cards restored:</b>\n"]
                for k, v in list(approval_queue.items()):
                    age = ""
                    if v.get("created_at"):
                        mins = int((utcnow() - v["created_at"]).total_seconds() / 60)
                        age = f" ({mins}min ago)"
                    lang = v.get("lang","en").upper()
                    cat  = v.get("cat","LOCAL")
                    title = v.get("title","")[:50]
                    expires = ""
                    if v.get("created_at"):
                        remaining = 7200 - int((utcnow() - v["created_at"]).total_seconds())
                        if remaining > 0:
                            expires = f" — {remaining//60}min left"
                        else:
                            expires = " — EXPIRED"
                    lines.append(f"• <code>{k}</code> [{lang}/{cat}]{age}{expires}")
                    lines.append(f"  📰 {title}")
                    lines.append(f"  ✅ <code>/approved {k}</code>  ❌ <code>/reject {k}</code>")
                lines.append("\nRun <code>/pending</code> to see full queue.")
                _startup_queue_msg = "\n".join(lines)
                # send after bot is fully up — schedule for 10 seconds after start
                import threading as _st
                def _send_startup_alert():
                    import time as _t; _t.sleep(10)
                    try:
                        send_text(CORE_TEAM_CHAT_ID, _startup_queue_msg, thread_id=ALERT_THREAD_ID)
                    except Exception: pass
                _st.Thread(target=_send_startup_alert, daemon=True).start()
            except Exception as _e:
                log.warning(f"startup queue alert: {_e}")
    except Exception as e:
        log.error(f"restore_state: {e}")


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import signal, atexit

    def _graceful_shutdown(signum=None, frame=None):
        """Save all state before Railway kills the process on redeploy."""
        log.info("🛑 Shutdown signal received — saving state before exit...")
        try:
            persist_state()
            log.info("✅ State saved — approval queue, social queue, counters all persisted")
        except Exception as e:
            log.error(f"State save on shutdown: {e}")

    # Railway sends SIGTERM before killing the container on redeploy
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT,  _graceful_shutdown)
    # Also register with atexit as a backup (catches normal Python exit)
    atexit.register(_graceful_shutdown)

    log.info(f"🚀 Samuga AI v{SAMUGA_VERSION} starting (newsroom intelligence + story timelines + live brain)...")
    # Install Noto fonts for Thaana/Dhivehi support
    if not os.path.exists("/usr/share/fonts/truetype/noto/NotoSansThaana-Bold.ttf") and not os.path.exists("/app/NotoSansThaana-Bold.ttf"):
        try:
            import subprocess
            subprocess.run(["apt-get", "install", "-y", "fonts-noto"], capture_output=True, timeout=60)
            log.info("✅ Noto fonts installed via apt")
        except Exception as e:
            log.warning(f"Noto font install failed: {e}")
    else:
        log.info("✅ Thaana fonts available")
    log.info("📅 News: 6AM-10PM every 15min | Night: breaking only")
    log.info("🌤️ Weather: ECMWF+GFS+ICON at 06:00/14:00/22:00 MVT | MMS official alert watch every 2 min")
    log.info("🌅 7AM Brief | 🌙 12AM Summary | 📊 Friday Digest | 🕌 Prayer times + Hijri")
    log.info("📚 Story Intelligence: timeline threads active")
    log.info("🧠 Core team brain: live newsroom awareness + persistent memory")
    log.info("💬 Smart chat: history, web search, Dhivehi support, story queries")
    log.info("🧭 Cortex News Director: mandatory final pre-AI editorial gate")
    log.info("🧼 Public source labels/links: disabled on cards, captions, weather cards and article copy")
    if not _cortex_news_director_env_requested:
        log.warning("CORTEX_NEWS_DIRECTOR_ENABLED=false ignored — Build 15.9 requires Cortex before paid AI")
    if posting_paused():
        log.warning("🛑 POSTING_PAUSED=true — all public posting is blocked")
    elif social_paused():
        log.warning("🛑 SOCIAL_PAUSED=true — Buffer/social posting is blocked")

    init_database()  # connect to Postgres (falls back to JSON if unavailable)
    _configure_ai_usage(
        db_execute=db_execute,
        alert_callback=lambda message: send_text(
            CORE_TEAM_CHAT_ID, message, thread_id=ALERT_THREAD_ID
        ),
    )
    _gemini_guard.configure(
        db_execute=db_execute,
        alert_callback=lambda message: send_text(CORE_TEAM_CHAT_ID, message, thread_id=ALERT_THREAD_ID),
    )
    _buffer_diag.configure(
        db_execute=db_execute, token=BUFFER_TOKEN,
        alert_callback=lambda message: send_text(CORE_TEAM_CHAT_ID, message, thread_id=ALERT_THREAD_ID),
    )
    log.info("📊 AI Usage diagnostics: provider-level request telemetry active")
    log.info("📊 AI Usage diagnostics: Claude SDK hidden retries disabled; app-level attempts are counted exactly")
    log.info("🛡️ Gemini emergency guard: %s", _gemini_guard.dashboard(GEMINI_API_KEY).get("limits"))
    log.info("🧾 Gemini key identity: %s", _gemini_guard.key_identity(GEMINI_API_KEY))
    log.info("🛡️ Buffer guard identity: %s", _buffer_diag.token_identity())
    _cms_seed_admin()  # create first dashboard Super Admin from Railway env, once

    # Only one Railway replica may run polling, Telegram, workers or APScheduler.
    # Additional replicas remain API-only so a scale-up cannot multiply provider calls.
    import db as _db_runtime
    is_background_leader = True
    if _db_runtime.DB_ENABLED:
        try:
            _runtime_leader.configure(db_execute)
            is_background_leader = _runtime_leader.acquire()
        except Exception as _leader_error:
            log.critical("[LEADER] lease setup failed; refusing background jobs: %s", _leader_error)
            is_background_leader = False
    if not is_background_leader:
        log.warning("[LEADER] Another Railway replica owns background jobs — this replica is API-only")
        start_api_server()
        raise SystemExit(0)
    if _db_runtime.DB_ENABLED:
        _runtime_leader.start_heartbeat()
        log.info("[LEADER] Background-worker lease acquired: %s", _runtime_leader.owner_id())
    else:
        log.warning("[LEADER] PostgreSQL unavailable — singleton protection cannot coordinate replicas")

    if BUFFER_TOKEN and os.environ.get("BUFFER_STARTUP_CONNECTION_TEST", "true").lower() == "true":
        try:
            _buffer_snapshot = _buffer_diag.test_connection()
            _buffer_account = dict(_buffer_snapshot.get("account") or {})
            _buffer_orgs = list(_buffer_snapshot.get("organizations") or [])
            log.info(
                "🧾 Buffer runtime identity: account=%s organization=%s channels=%s token=%s",
                _buffer_account.get("name") or "unknown",
                (_buffer_orgs[0].get("name") if _buffer_orgs else "unknown"),
                int(_buffer_snapshot.get("channel_count") or 0),
                _buffer_snapshot.get("token_masked") or "not configured",
            )
        except Exception as _buffer_start_error:
            log.error("Buffer startup connection audit failed: %s", _mask_secrets(str(_buffer_start_error)))

    restore_state()  # bring back dedup memory, daily counters, pending cards, analytics
    threading.Thread(target=_social_queue_worker, daemon=True).start()
    log.info("📲 Social queue worker started by singleton leader")

    # ── Cache Samuga AI photo URL from cms_authors ────────────────────────────
    # Loaded once at startup so every new AI article gets the photo immediately
    # without a per-article DB lookup. Update via /author ai photo in Telegram.
    try:
        _ai_photo_row = db_execute(
            "SELECT photo_url FROM cms_authors WHERE author_id='samuga_ai' AND photo_url IS NOT NULL",
            fetch="one"
        )
        _AI_PHOTO["url"] = _ai_photo_row[0] if _ai_photo_row and _ai_photo_row[0] else None
        if _AI_PHOTO["url"]:
            log.info(f"🤖 Samuga AI photo loaded: {_AI_PHOTO['url'][:60]}")
        else:
            log.info("🤖 Samuga AI photo not set — run /author ai photo to set it")
    except Exception as _aip_err:
        _AI_PHOTO["url"] = None
        log.warning(f"AI photo cache load failed: {_aip_err}")



    # Wire db module with shared functions
    import db as _db
    _db.utcnow                    = utcnow
    _db.ai                        = ai
    _db._gemini_post              = _gemini_post
    _db._deepseek_fact_pack       = _deepseek_extract_fact_pack
    _db._claude_write_from_facts  = _claude_write_article_from_facts
    _db._ai_call_purpose          = _ai_call_purpose
    _db._reserve_website_repair   = _reserve_website_repair_attempt
    _db.send_text                  = send_text
    _db.GEMINI_API_KEY   = GEMINI_API_KEY
    _db.CORE_TEAM_CHAT_ID = CORE_TEAM_CHAT_ID
    _db.ALERT_THREAD_ID   = ALERT_THREAD_ID

    try:
        import ai_pipeline as _aip
        _aip._record_usage = lambda provider, purpose: _record_ai_usage(provider, purpose, count_toward_budget=False)
    except Exception as _aip_wire_error:
        log.debug(f"[AI][DEEPSEEK] usage counter wiring skipped: {_aip_wire_error}")

    # Wire scoring module with utcnow
    import scoring as _sc
    _sc.utcnow = utcnow
    _sc.normalize_story_signal = story_signal_key
    _sc.SOURCE_HEALTH_LOOKUP = source_health_score
    # Import the scoring module's locks so persist_state/restore_state can use them
    from scoring import _recent_titles_lock, _cluster_store_lock

    # Wire front_desk module (anonymous tip/report flow — see front_desk.py)
    front_desk.utcnow             = utcnow
    front_desk.kv_get             = kv_get
    front_desk.kv_set             = kv_set
    front_desk.send_text          = send_text
    front_desk._make_inline_kb    = _make_inline_kb
    front_desk.CORE_TEAM_CHAT_ID  = CORE_TEAM_CHAT_ID
    front_desk.TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN
    front_desk.PUBLIC_TIPS_THREAD_ID = int(os.environ.get("PUBLIC_TIPS_THREAD_ID", "13680"))

    # Wire fetchers module with shared AI client
    import fetchers as _ft
    _ft.ai                    = ai
    _ft._gemini_post          = _gemini_post
    _ft._deepseek_fact_pack   = _deepseek_extract_fact_pack
    _ft.GEMINI_API_KEY        = GEMINI_API_KEY
    _ft.send_text             = send_text
    _ft.CORE_TEAM_CHAT_ID     = CORE_TEAM_CHAT_ID
    _ft._critical_ai_failure  = _critical_ai_failure
    _ft._is_ai_budget_exceeded = _is_ai_budget_exceeded
    _ft._ai_call_purpose      = _ai_call_purpose
    _ft._website_body_is_publishable = website_body_is_publishable
    _ft._website_article_body_is_consistent = website_article_body_is_consistent

    # Wire weather module with shared functions (avoids circular imports)
    import weather as _wx
    _wx.send_photo      = send_photo
    _wx.send_text       = send_text
    _wx.queue_for_social = queue_for_social
    _wx.post_to_social_now = _post_to_social_now
    _wx.utcnow          = utcnow
    _wx.mvt_now         = mvt_now
    try:
        import met_telegram_monitor as _metmon
        _met_started = _metmon.start(
            on_alert=lambda alert: _wx.ingest_official_alert(alert, force=False),
            on_review=_queue_mms_alert_review,
            parse_text=_wx.parse_mms_alert_text,
        )
        log.info("📡 @MaldivesMET Telethon monitor: %s", "started" if _met_started else "disabled; Facebook fallback remains active")
    except Exception as _met_err:
        log.error("@MaldivesMET Telethon monitor startup failed: %s", _met_err, exc_info=True)
    seen_on_start=load_seen()
    log.info(f"📚 Loaded {len(seen_on_start)} seen articles")
    log.info("🧼 Public source labels/links: disabled on cards, captions, weather cards and article copy")
    log.info(
        "🧭 Cortex News Director=%s (final pre-AI gate) | ranking=%s | commenter=removed | proactive team AI=%s",
        "on" if _cortex_news_director_enabled else "off",
        "on" if _cortex_ranking_enabled else "off",
        "on" if _ai_proactive_mode else "off",
    )

    threading.Thread(target=handle_updates, daemon=True).start()
    threading.Thread(target=start_api_server, daemon=True).start()

    scheduler=BlockingScheduler(timezone="UTC")
    scheduler.add_job(scheduled_check, "interval", minutes=15)
    # Newsroom Build 3/4: scheduled website publishing, durable social queue,
    # and restart-safe video processing.
    scheduler.add_job(cms_publish_due_articles, "interval", minutes=1, id="cms_scheduled_publish", max_instances=1, coalesce=True)
    scheduler.add_job(_cms_process_publish_jobs, "interval", minutes=1, id="cms_social_publish_queue", max_instances=1, coalesce=True)
    scheduler.add_job(_cms_process_pending_videos, "interval", minutes=1, id="cms_video_processing", max_instances=1, coalesce=True)
    scheduler.add_job(_reset_ai_budget_for_new_day, "cron", hour=19, minute=0, id="ai_budget_midnight_mvt", max_instances=1, coalesce=True)
    # Breaking news fast check every 5 min (LOCAL/DISASTER only)
    scheduler.add_job(breaking_news_check, "interval", minutes=5)
    # Approval lifecycle — English auto-posts at 15min, Dhivehi expires at 2h. Check every 5 min.
    scheduler.add_job(expire_old_approvals, "interval", minutes=5)
    # release_content_lab_drip removed — cards now go to Content Lab immediately when ready
    # Morning brief 7AM MVT = 2AM UTC
    scheduler.add_job(send_morning_brief, "cron", hour=1, minute=0)  # 6AM MVT
    # AI Nightly Journalist brief 10:30PM MVT = 5:30PM UTC (before night summary)
    scheduler.add_job(send_ai_journalist_brief, "cron", hour=17, minute=30)  # 10:30PM MVT
    # Night summary 12AM MVT = 7PM UTC
    scheduler.add_job(send_night_summary,   "cron", hour=18, minute=0)   # 11PM MVT
    scheduler.add_job(night_queue_review,   "cron", hour=18, minute=5)   # 11:05PM MVT — queue review
    scheduler.add_job(night_queue_autoclear,"cron", hour=18, minute=30)  # 11:30PM MVT — auto clear if no action
    # Weekly digest Friday 6PM MVT = 1PM UTC Friday
    scheduler.add_job(send_weekly_digest, "cron", day_of_week="fri", hour=13, minute=0)
    # Weekly analytics report Friday 6:30PM MVT = 1:30PM UTC Friday
    scheduler.add_job(send_weekly_analytics, "cron", day_of_week="fri", hour=13, minute=30)
    # Phase 2: mid-week view backfill — Tue 10PM UTC = 3AM Wed MVT (quiet hours)
    scheduler.add_job(backfill_tg_views, "cron", day_of_week="tue", hour=22, minute=0)
    # Phase 2.5: mid-week Meta (FB+IG) engagement refresh — Tue 10PM UTC too
    scheduler.add_job(fetch_meta_insights, "cron", day_of_week="tue", hour=22, minute=15)
    # Weather Authority Engine — MMS alerts every 2 minutes and three complete
    # non-overlapping 8-hour forecast windows daily. Times below are UTC.
    scheduler.add_job(
        check_official_weather_alerts, "interval", minutes=2, id="mms_official_alert_watch",
        max_instances=1, coalesce=True, next_run_time=datetime.now(timezone.utc) + timedelta(seconds=20),
    )
    # 06:00 MVT = 01:00 UTC → covers 06:00–13:00
    scheduler.add_job(lambda: send_weather_update("morning"), "cron", hour=1, minute=0, id="weather_morning", max_instances=1, coalesce=True)
    # 14:00 MVT = 09:00 UTC → covers 14:00–21:00
    scheduler.add_job(lambda: send_weather_update("afternoon"), "cron", hour=9, minute=0, id="weather_afternoon", max_instances=1, coalesce=True)
    # 22:00 MVT = 17:00 UTC → covers 22:00–05:00 across midnight
    scheduler.add_job(lambda: send_weather_update("evening"), "cron", hour=17, minute=0, id="weather_evening", max_instances=1, coalesce=True)
    # Tip/story CTA 8:30AM MVT = 3:30AM UTC
    scheduler.add_job(send_tip_cta, "cron", hour=3, minute=30)  # 8:30AM MVT
    # Tip/story CTA 8:30PM MVT = 3:30PM UTC
    scheduler.add_job(send_tip_cta, "cron", hour=15, minute=30)  # 8:30PM MVT

    # Periodic state heartbeat — saves every 5 minutes so restarts lose minimal state
    scheduler.add_job(persist_state, "interval", minutes=5, id="state_heartbeat")
    scheduler.add_job(ops_watchdog, "interval", minutes=10)
    scheduler.add_job(
        media_storage_self_test, "date", id="media_storage_startup_test",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=30),
        max_instances=1,
    )
    scheduler.add_job(
        repair_recent_missing_website_covers, "interval", hours=6, id="website_cover_repair",
        max_instances=1, coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
    )
    scheduler.add_job(
        repair_recent_public_copy, "interval", hours=12, id="public_copy_repair",
        max_instances=1, coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=75),
    )
    log.info("🖼️ Website cover repair active: recent missing covers will be backfilled without AI calls")
    log.info("🖼️ Image search providers: order=%s Tavily=%s Pexels=%s", os.environ.get("IMAGE_SEARCH_PROVIDER_ORDER", "tavily,pexels"), bool(TAVILY_API_KEY), bool(PEXELS_API_KEY))
    scheduler.add_job(
        _cleanup_ai_usage, "cron", hour=20, minute=20, id="ai_usage_retention_cleanup",
        max_instances=1, coalesce=True,
    )
    # Held website-body maintenance is intentionally slow and separately capped.
    # It must never create a startup storm or consume the newsroom AI allowance.
    if WEBSITE_BODY_AUTO_RETRY_ENABLED:
        scheduler.add_job(
            lambda: retry_held_website_articles(limit=WEBSITE_BODY_RETRY_BATCH),
            "interval", minutes=WEBSITE_BODY_RETRY_INTERVAL_MINUTES, id="held_body_retry",
            max_instances=1, coalesce=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=WEBSITE_BODY_RETRY_INTERVAL_MINUTES),
        )
        log.info(
            f"🌐 Held-body repair: {WEBSITE_BODY_RETRY_BATCH} article(s) every "
            f"{WEBSITE_BODY_RETRY_INTERVAL_MINUTES} min, max {WEBSITE_BODY_REPAIR_DAILY_LIMIT}/day"
        )
    else:
        log.info("🌐 Held-body automatic repair disabled; /retry_body remains available")

    # Legacy public-body audit is opt-in only. Build 15.3 moved 31 rows at startup
    # and immediately regenerated them; that was the source of the AI load storm.
    if LEGACY_BODY_AUDIT_ENABLED:
        scheduler.add_job(
            db_hold_invalid_live_ai_articles, "interval", hours=24, id="legacy_body_audit",
            max_instances=1, coalesce=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        log.warning("🌐 Legacy body audit enabled (opt-in)")
    else:
        log.info("🌐 Legacy body audit disabled by default")
    try:
        import discovery as _disc
        # Inject bot dependencies — same pattern as fetchers/weather/story_builder
        _disc.kv_get            = kv_get
        _disc.kv_set            = kv_set
        _disc.send_text         = send_text
        _disc._gemini_post      = _gemini_post
        _disc.CORE_TEAM_CHAT_ID = CORE_TEAM_CHAT_ID
        _disc.ALERT_THREAD_ID   = ALERT_THREAD_ID
        scheduler.add_job(_disc.run_discovery, "interval", hours=1)
        log.info("🔍 Discovery Engine scheduled — runs every hour (dependencies injected)")
    except ImportError:
        log.warning("⚠️ discovery.py not found — Discovery Engine disabled")

    # Wire story builder
    try:
        import story_builder as _sb
        _sb._gemini_post              = _gemini_post
        _sb._deepseek_fact_pack        = _deepseek_extract_fact_pack
        _sb._claude_write_from_facts   = _claude_write_article_from_facts
        _sb.kv_get                     = kv_get
        _sb.kv_set                     = kv_set
        _sb.GEMINI_API_KEY             = GEMINI_API_KEY
        pipeline_state = _deepseek_health_snapshot()
        log.info(f"📝 Story Builder wired — DeepSeek fact packs: {pipeline_state.get('status')}")
    except ImportError:
        pass

    log.info("⏰ Scheduler started!")
    scheduler.start()
