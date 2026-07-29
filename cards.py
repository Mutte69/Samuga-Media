"""
cards.py — Samuga AI Card Generation Module
Extracted from bot.py v7.0

Contains:
  - generate_card()          PIL-based news card (English + Thaana fallback)
  - generate_dhivehi_card()  Pango/Cairo Thaana card (proper RTL shaping)
  - fetch_background_image() Pexels background image fetcher
  - _safe_bg_keyword()       Smart keyword extractor for backgrounds
  - draw_weather_icon()      Vector weather icon renderer

Import in bot.py:
  from cards import generate_card, generate_dhivehi_card, fetch_background_image
"""

import os, io, logging, re, requests, threading, time, hashlib
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

log = logging.getLogger(__name__)

# ── These come from bot.py config — passed in or read from env ────────────────
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

_IMAGE_CACHE = {}
_IMAGE_CACHE_LOCK = threading.Lock()
_TAVILY_CALL_TIMES = []
_TAVILY_FAILURES = 0
_TAVILY_CIRCUIT_UNTIL = 0.0


# Public-card text must never contain original publisher/source links. This
# renderer-level guard is the final safety net: even if a fetcher, AI response,
# manual correction, or future call site forgets to sanitize, the pixels that
# reach Telegram/socials remain clean.
_CARD_URL_RE = re.compile(r"(?:https?:/{1,2}|www\.)[^\s<>\"']+", re.I)
_CARD_BARE_DOMAIN_RE = re.compile(
    r"(?<!@)\b(?:[a-z0-9-]+\.)+(?:com|net|org|mv|io|co|me|app|news|media|info)(?:/[^\s<>\"']*)?",
    re.I,
)
_CARD_SOURCE_LINE_RE = re.compile(
    r"(?im)^\s*(?:[🔗🌐📰📎]\s*)?(?:source(?:s)?|via|read more|full story|original(?: story)?|story link|link|website|from)\s*(?::|[-–—])\s*.*$"
)
_CARD_OUTLET_PATTERN = (
    r"Edition|Sun(?: Online)?|Mihaaru|Avas|Raajje|PSM(?: News)?|ThePress|"
    r"VoiceMV|Maldives Voice|OneOnline|Adhadhu|VNews|MV\+|MvCrisis(?:Plus)?|"
    r"Bithufangi|Vamundhaagoi|Dhuvas"
)
_CARD_MEDIA_ATTRIBUTION_RE = re.compile(
    rf"(?i)\b(?:according to|as reported by|reported by|via|from)\s+(?:the\s+)?(?:{_CARD_OUTLET_PATTERN})\b(?:\s*[,;:–—-]\s*)?"
)
_CARD_MEDIA_REPORTING_PREFIX_RE = re.compile(
    rf"(?i)\b(?:{_CARD_OUTLET_PATTERN})\s+(?:reports?|reported|says?|said|writes?|published|posted)(?:\s+that)?\s*[,;:–—-]?\s*"
)
_CARD_MEDIA_LABEL_PREFIX_RE = re.compile(
    rf"(?im)^\s*(?:{_CARD_OUTLET_PATTERN})\s*[:|–—-]\s*"
)
_CARD_MEDIA_ONLY_LINE_RE = re.compile(
    rf"(?im)^\s*(?:source\s*[:–—-]?\s*)?(?:{_CARD_OUTLET_PATTERN})\s*$"
)

def sanitize_card_text(text):
    """Return display-safe card text with all external source residue removed."""
    value = str(text or "")
    value = re.sub(r"\[([^\]\n]+)\]\((?:https?:/{1,2}|www\.)[^)\n]+\)", r"\1", value, flags=re.I)
    value = re.sub(r"<a\s+[^>]*href=[\"'][^\"']+[\"'][^>]*>(.*?)</a>", r"\1", value, flags=re.I|re.S)
    value = _CARD_SOURCE_LINE_RE.sub("", value)
    value = _CARD_MEDIA_ONLY_LINE_RE.sub("", value)
    value = _CARD_MEDIA_ATTRIBUTION_RE.sub("", value)
    value = _CARD_MEDIA_REPORTING_PREFIX_RE.sub("", value)
    value = _CARD_MEDIA_LABEL_PREFIX_RE.sub("", value)
    value = re.sub(r"(?i)(?:\s+|[|•·]\s*)(?:source(?:s)?|via|read more|full story|story link|link|website)\s*:\s*(?:https?:/{1,2}\S+|www\.\S+|(?:[a-z0-9-]+\.)+(?:com|net|org|mv|io|co|me|app|news|media|info)(?:/\S*)?|@[a-z0-9_]{3,}|[^\n]{1,120})\s*$", "", value)
    value = re.sub(r"(?im)^\s*(?:forwarded from|originally posted by|shared from|join|follow)\s+@?[a-z0-9_./-]+\s*$", "", value)
    value = re.sub(r"(?im)^\s*(?:[🔗🌐📎]\s*)?(?:https?:/{1,2}\S+|www\.\S+|(?:[a-z0-9-]+\.)+(?:com|net|org|mv|io|co|me|app|news|media|info)(?:/\S*)?|@[a-z0-9_]{3,})\s*$", "", value)
    value = _CARD_URL_RE.sub("", value)
    value = _CARD_BARE_DOMAIN_RE.sub("", value)
    value = re.sub(r"(?<!\w)@[A-Za-z0-9_]{3,}", "", value)
    value = re.sub(r"(?im)^\s*(?:source(?:s)?|via|read more|full story|story link|link|website)\s*[:\-–—]?\s*$", "", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value or "Samuga Media is following this developing story."

def sanitize_source_label(source):
    """Compatibility shim: public Samuga cards never render a source label.

    Original publisher/outlet data remains private metadata in the newsroom
    database for verification and deduplication. It is intentionally blank in
    every public image.
    """
    return ""


# ── Card color constants ───────────────────────────────────────────────────────
WHITE      = (255, 255, 255)
LIGHT_GRAY = (200, 215, 230)
BG_TOP     = (10, 40, 75)
BG_BOTTOM  = (5, 20, 45)

# ── Category config (colors + labels) ─────────────────────────────────────────
CAT_CONFIG = {
    "BREAKING":  {"label": "🚨  BREAKING NEWS", "color": (220, 50, 50)},
    "LOCAL":     {"label": "🇲🇻  LOCAL NEWS",    "color": (41, 171, 226)},
    "POLITICAL": {"label": "🏛️  POLITICAL",      "color": (180, 140, 40)},
    "LIFESTYLE": {"label": "🌴  LIFESTYLE",      "color": (160, 80, 220)},
    "SPORTS":    {"label": "🏅  SPORTS",         "color": (34, 180, 80)},
    "DISASTER":  {"label": "🚨  BREAKING NEWS",  "color": (220, 50, 50)},
    "WORLD":     {"label": "🌍  WORLD NEWS",     "color": (220, 80, 60)},
    "WEATHER":   {"label": "🌴  LIFESTYLE",      "color": (160, 80, 220)},
    "TOURISM":   {"label": "🌴  LIFESTYLE",      "color": (160, 80, 220)},
    "FOOTBALL":  {"label": "🏅  SPORTS",         "color": (34, 180, 80)},
}

# ── Dhivehi category labels (shared by social card + web cover) ─────────────
DV_CAT = {
    "BREAKING":  {"label": "ބްރޭކިން ނިއުސް", "color": (220, 50, 50)},
    "LOCAL":     {"label": "ލޯކަލް ނިއުސް",   "color": (0, 180, 255)},
    "POLITICAL": {"label": "ސިޔާސީ",          "color": (180, 140, 40)},
    "LIFESTYLE": {"label": "ލައިފްސްޓައިލް",  "color": (160, 80, 220)},
    "SPORTS":    {"label": "ކުޅިވަރު",        "color": (34, 180, 80)},
    "DISASTER":  {"label": "ބްރޭކިން ނިއުސް", "color": (220, 50, 50)},
    "WORLD":     {"label": "ދުނިޔެ",          "color": (50, 180, 100)},
    "FOOTBALL":  {"label": "ކުޅިވަރު",        "color": (34, 180, 80)},
    "TOURISM":   {"label": "ލައިފްސްޓައިލް",  "color": (160, 80, 220)},
    "WEATHER":   {"label": "ލައިފްސްޓައިލް",  "color": (160, 80, 220)},
}

def _to_arabic_nums(t):
    """Convert Western digits to Arabic-Indic digits for Thaana/RTL display."""
    return t.translate(str.maketrans("0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"))



# ── Background keyword maps ───────────────────────────────────────────────────
CAT_BG_KEYWORDS = {
    "BREAKING":  ["emergency lights night", "police lights dark", "crisis dark dramatic", "rescue operation dark"],
    "LOCAL":     ["maldives aerial ocean", "male city maldives", "maldives island drone", "maldives lagoon blue"],
    "POLITICAL": ["parliament building architecture", "government building dark", "official hall columns"],
    "LIFESTYLE": ["tropical beach sunset", "maldives lagoon aerial", "resort pool tropical", "island sunrise"],
    "SPORTS":    ["football stadium lights night", "soccer field green aerial", "sport arena lights"],
    "DISASTER":  ["emergency lights night", "rescue operation dark", "crisis scene dramatic", "disaster response"],
    "WORLD":     ["world globe dark", "city skyline night", "international airport", "global city lights"],
    "TOURISM":   ["maldives resort luxury", "tropical beach aerial", "maldives overwater villa", "island paradise blue"],
    "WEATHER":   ["storm clouds dramatic", "tropical rain dark", "monsoon ocean waves", "dark clouds sea"],
    "FOOTBALL":  ["football stadium lights night", "soccer field green aerial", "football match crowd"],
}
DEFAULT_BG_KEYWORDS = [
    "maldives ocean aerial", "island blue lagoon",
    "tropical dark dramatic", "maldives night city", "ocean waves dark"
]


# When an exact/relevant Tavily photo is unavailable, Samuga should still look
# unmistakably Maldivian instead of falling back to unrelated generic stock.
# The choice is deterministic per story so the social card and website cover
# keep the same visual identity across retries and worker restarts.
MALDIVES_SCENIC_FALLBACKS = {
    "POLITICAL": [
        "Male city Maldives aerial waterfront",
        "Maldives capital Male skyline drone",
        "Male city harbour Maldives aerial",
    ],
    "BREAKING": [
        "Male city Maldives night aerial",
        "Maldives speedboat ocean drone",
        "Maldives island harbour aerial",
    ],
    "DISASTER": [
        "Maldives ocean waves aerial",
        "Maldives island coastline drone",
        "Male city waterfront Maldives",
    ],
    "TOURISM": [
        "Maldives island lagoon aerial",
        "Maldives coral reef drone view",
        "Maldives resort island aerial",
    ],
    "LIFESTYLE": [
        "Maldives local island aerial",
        "Maldives coral reef drone view",
        "Maldives beach lagoon aerial",
    ],
    "WEATHER": [
        "Maldives ocean clouds aerial",
        "Maldives island coastline drone",
        "Maldives sea waves aerial",
    ],
    "WORLD": [
        "Maldives airport island aerial",
        "Male city Maldives skyline",
        "Maldives speedboat ocean aerial",
    ],
    "SPORTS": [
        "Male city Maldives aerial",
        "Maldives island football field aerial",
        "Maldives harbour drone view",
    ],
    "FOOTBALL": [
        "Maldives island football field aerial",
        "Male city Maldives aerial",
        "Maldives local island drone",
    ],
    "LOCAL": [
        "Male city Maldives aerial waterfront",
        "Maldives local island drone view",
        "Maldives coral reef aerial",
        "Maldives speedboat ocean drone view",
        "Maldives island harbour aerial",
        "Maldives turquoise lagoon aerial",
    ],
    "DEFAULT": [
        "Male city Maldives aerial waterfront",
        "Maldives island lagoon aerial",
        "Maldives coral reef drone view",
        "Maldives speedboat ocean aerial",
        "Maldives local island harbour drone",
    ],
}

_IMAGE_RELEVANCE_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "over", "after", "before",
    "amid", "against", "this", "that", "have", "has", "had", "will", "new",
    "says", "said", "news", "photo", "maldives", "maldivian", "media", "update",
    "breaking", "story", "latest", "today", "their", "about", "more", "under",
    "president", "minister", "parliament", "majlis", "government", "political",
    "member", "managing", "director", "commissioner", "ambassador", "court",
    "police", "chief", "prime", "dr", "mr", "ms", "mrs", "hon",
}

def _story_signal_terms(title):
    """Extract distinctive English entity/topic terms for image relevance."""
    raw = sanitize_card_text(str(title or ""))
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", raw)
    terms = []
    for token in tokens:
        low = token.lower().strip("-' ")
        if not low or low in _IMAGE_RELEVANCE_STOPWORDS or len(low) < 3:
            continue
        # Preserve distinctive names, institutions, places and topic nouns.
        if low not in terms:
            terms.append(low)
    return terms[:18]

def _requires_identity_relevance(title, cat):
    """Return True when a named person/institution must match before using it."""
    text = str(title or "")
    lowered = text.lower()
    sensitive = (
        "president", "vice president", "minister", "mp ", "member of parliament",
        "parliament", "majlis", "ambassador", "judge", "chief justice", "mayor",
        "commissioner", "managing director", "ceo", "chairperson", "candidate",
    )
    if not (str(cat or "").upper() == "POLITICAL" or any(term in f" {lowered} " for term in sensitive)):
        return False
    # Generic political stories may safely use a parliament/Malé scene. Be strict
    # only when the headline contains at least one distinctive name/place token.
    return bool(_story_signal_terms(text))

def _image_candidate_score(candidate, title, query):
    """Score Tavily image metadata against the real story, not only the category."""
    if isinstance(candidate, dict):
        url = str(candidate.get("url") or "")
        description = str(candidate.get("description") or candidate.get("alt") or "")
    else:
        url = str(candidate or "")
        description = ""
    haystack = f"{description} {url}".lower()
    title_terms = _story_signal_terms(title)
    query_terms = _story_signal_terms(query)
    score = 0.0
    matched_title = 0
    for term in title_terms:
        if term in haystack:
            matched_title += 1
            score += 2.2 if len(term) >= 6 else 1.4
    for term in query_terms:
        if term in haystack:
            score += 0.35
    if "maldives" in haystack or ".mv/" in haystack or ".gov.mv" in haystack:
        score += 1.25
    if any(domain in haystack for domain in ("presidency.gov.mv", "majlis.gov.mv", "police.gov.mv", "mndf.gov.mv")):
        score += 2.0
    if any(term in haystack for term in ("logo", "icon", "clipart", "vector", "advertisement", "screenshot", "poster")):
        score -= 8.0
    return score, matched_title

def _maldives_scenic_query(title, cat):
    """Choose a stable Maldivian fallback scene suitable for the story context."""
    category = str(cat or "LOCAL").upper()
    text = str(title or "").lower()
    if any(term in text for term in ("boat", "ferry", "ship", "vessel", "harbour", "harbor", "sea", "ocean")):
        options = [
            "Maldives speedboat ocean drone view",
            "Maldives island harbour aerial",
            "Maldives ferry lagoon aerial",
        ]
    elif any(term in text for term in ("reef", "coral", "environment", "marine", "tourism", "resort")):
        options = [
            "Maldives coral reef drone view",
            "Maldives island lagoon aerial",
            "Maldives turquoise ocean aerial",
        ]
    elif any(term in text for term in ("male", "parliament", "majlis", "government", "court", "police", "traffic", "road")):
        options = [
            "Male city Maldives aerial waterfront",
            "Maldives capital Male skyline drone",
            "Male city harbour Maldives aerial",
        ]
    else:
        options = MALDIVES_SCENIC_FALLBACKS.get(category, MALDIVES_SCENIC_FALLBACKS["DEFAULT"])
    seed = hashlib.sha256(f"{title}|{category}".encode("utf-8", "ignore")).digest()
    return options[int.from_bytes(seed[:4], "big") % len(options)]


# ═══════════════════════════════════════════════════════════════════════════════
# Background image helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_bg_keyword(title, cat):
    """
    Extract a safe, visually appropriate Pexels search keyword from the article title.
    Never shows wrong flags, wrong faces, or misleading visuals.
    """
    import random as _r
    t = title.lower()

    if any(k in t for k in ["maldives", "male", "hulhumale", "addu", "atoll",
                             "mndf", "mps", "police", "coast guard"]):
        return _r.choice(["maldives aerial ocean", "male city maldives", "maldives island drone",
                          "maldives lagoon blue", "tropical island aerial"])
    if any(k in t for k in ["parliament", "majlis", "government", "minister",
                             "president", "cabinet", "policy", "law", "bill"]):
        return _r.choice(["parliament building architecture", "government building dark",
                          "official hall columns", "legislative building aerial"])
    if any(k in t for k in ["court", "judge", "verdict", "sentence", "criminal", "trial"]):
        return _r.choice(["court building architecture", "justice scales dark",
                          "legal building exterior", "court hall dramatic"])
    if any(k in t for k in ["fire", "blaze", "burned", "flames"]):
        return _r.choice(["fire night dark dramatic", "emergency lights night",
                          "fire rescue dark", "flames dark dramatic"])
    if any(k in t for k in ["accident", "crash", "collision", "vehicle"]):
        return _r.choice(["emergency lights night", "accident scene dark",
                          "road night dramatic", "rescue operation night"])
    if any(k in t for k in ["boat", "ferry", "ship", "vessel", "sea", "ocean", "coast"]):
        return _r.choice(["boat ocean maldives", "sea vessel dramatic", "ocean dark waves",
                          "maldives boat lagoon", "ferry ocean dark"])
    if any(k in t for k in ["hospital", "health", "medical", "disease", "drug", "dengue"]):
        return _r.choice(["hospital building exterior", "medical blue dark",
                          "healthcare building", "medical technology dark"])
    if any(k in t for k in ["school", "education", "student", "university", "exam"]):
        return _r.choice(["school building exterior", "education building",
                          "university campus aerial", "classroom empty dramatic"])
    if any(k in t for k in ["economy", "finance", "bank", "budget", "mvr", "usd", "money"]):
        return _r.choice(["finance building city", "economy dark dramatic",
                          "bank building architecture", "business district night"])
    if any(k in t for k in ["weather", "storm", "rain", "flood", "wind"]):
        return _r.choice(["storm clouds ocean", "dark rain dramatic",
                          "monsoon waves tropical", "storm lightning sea"])
    if any(k in t for k in ["football", "soccer", "sport", "game", "match", "tournament"]):
        return _r.choice(["football stadium night", "soccer pitch aerial",
                          "sport arena lights", "football match crowd"])
    if any(k in t for k in ["tourism", "resort", "tourist", "hotel", "visit"]):
        return _r.choice(["maldives resort luxury", "overwater villa tropical",
                          "maldives beach sunset", "tropical resort aerial"])
    if any(k in t for k in ["arrest", "murder", "kill", "crime", "robbery", "theft"]):
        return _r.choice(["police lights night", "crime scene dark dramatic",
                          "investigation dark city", "night city dramatic dark"])
    if any(k in t for k in ["earthquake", "tsunami", "disaster", "emergency"]):
        return _r.choice(["disaster rescue dramatic", "emergency response night",
                          "crisis dark dramatic", "emergency lights dark"])

    fallbacks = CAT_BG_KEYWORDS.get(cat, DEFAULT_BG_KEYWORDS)
    return _r.choice(fallbacks)


def _local_bg_for_cat(cat):
    """
    Pick a random background image from the local library in the repo.
    Returns a PIL Image or None if the folder is empty / missing.

    Folder structure (relative to where bot.py runs, i.e. repo root):
        assets/backgrounds/politics/    → parliament, govt buildings
        assets/backgrounds/business/    → finance, economy, office
        assets/backgrounds/sports/      → stadium, pitch, athletes
        assets/backgrounds/breaking/    → dramatic dark scenes
        assets/backgrounds/local/       → Malé skyline, islands
        assets/backgrounds/world/       → globe, international
        assets/backgrounds/lifestyle/   → beach, tourism, nature
        assets/backgrounds/weather/     → clouds, rain, ocean sky
        assets/backgrounds/default/     → generic fallback images

    Category → folder mapping:
        POLITICAL / POLITICAL_KEYWORD → politics
        BUSINESS / WORLD              → business or world
        SPORTS / FOOTBALL             → sports
        BREAKING / DISASTER           → breaking
        LOCAL                         → local
        LIFESTYLE / TOURISM / WEATHER → lifestyle or weather
    """
    import random as _r

    CAT_FOLDER = {
        "BREAKING":  "breaking",
        "DISASTER":  "breaking",
        "LOCAL":     "local",
        "POLITICAL": "politics",
        "BUSINESS":  "business",
        "WORLD":     "world",
        "SPORTS":    "sports",
        "FOOTBALL":  "sports",
        "LIFESTYLE": "lifestyle",
        "TOURISM":   "lifestyle",
        "WEATHER":   "weather",
    }
    folder_name = CAT_FOLDER.get(cat, "default")
    base = os.path.join("assets", "backgrounds")
    folder = os.path.join(base, folder_name)

    # If category folder is empty/missing, try default
    def _pick_from(folder_path):
        if not os.path.isdir(folder_path):
            return None
        files = [f for f in os.listdir(folder_path)
                 if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        if not files:
            return None
        chosen = _r.choice(files)
        try:
            img = Image.open(os.path.join(folder_path, chosen)).convert("RGB")
            log.info(f"🖼️ Local bg: {folder_name}/{chosen}")
            return img
        except Exception as e:
            log.warning(f"Local bg load failed ({chosen}): {e}")
            return None

    img = _pick_from(folder)
    if img is None and folder_name != "default":
        img = _pick_from(os.path.join(base, "default"))
    return img


def _image_cache_get(key):
    now = time.time()
    with _IMAGE_CACHE_LOCK:
        entry = _IMAGE_CACHE.get(key)
        if not entry:
            return None
        created_at, payload = entry
        ttl = max(300, int(os.environ.get("IMAGE_SEARCH_CACHE_SECONDS", "21600") or 21600))
        if now - created_at > ttl:
            _IMAGE_CACHE.pop(key, None)
            return None
    try:
        return Image.open(BytesIO(payload)).convert("RGB")
    except Exception:
        return None


def _image_cache_put(key, image):
    try:
        buf = BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
        payload = buf.getvalue()
        with _IMAGE_CACHE_LOCK:
            _IMAGE_CACHE[key] = (time.time(), payload)
            if len(_IMAGE_CACHE) > 100:
                oldest = sorted(_IMAGE_CACHE.items(), key=lambda item: item[1][0])[:20]
                for old_key, _ in oldest:
                    _IMAGE_CACHE.pop(old_key, None)
    except Exception:
        pass


def _download_image_candidate(url, *, provider="web"):
    """Download and validate one external image candidate."""
    raw_url = str(url or "").strip()
    if not raw_url.startswith(("https://", "http://")):
        return None
    if raw_url.lower().endswith((".svg", ".gif")):
        return None
    try:
        response = requests.get(
            raw_url,
            timeout=(8, 22),
            stream=True,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 SamugaMedia/15.9.6",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        if response.status_code != 200:
            return None
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            return None
        limit = max(1_000_000, min(20_000_000, int(os.environ.get("IMAGE_SEARCH_MAX_BYTES", "12000000") or 12000000)))
        payload = bytearray()
        for chunk in response.iter_content(256 * 1024):
            if not chunk:
                continue
            payload.extend(chunk)
            if len(payload) > limit:
                return None
        with Image.open(BytesIO(bytes(payload))) as source:
            source.load()
            width, height = source.size
            if width < 480 or height < 270:
                return None
            ratio = width / max(1, height)
            if ratio < 0.45 or ratio > 3.2:
                return None
            image = source.convert("RGB")
        log.info("✅ %s image downloaded: %sx%s", provider, width, height)
        return image
    except Exception as exc:
        log.debug("%s image candidate failed: %s", provider, exc)
        return None


def _clean_image_query(keyword, title, cat):
    title_value = sanitize_card_text(str(title or "")).strip()
    keyword_value = sanitize_card_text(str(keyword or "")).strip()
    # Dhivehi headlines search better when the writer already supplied an English
    # visual keyword. English headlines keep the full real headline for accuracy.
    latin_title_words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", title_value)
    if keyword_value and len(latin_title_words) < 3:
        value = keyword_value
    else:
        value = title_value or keyword_value
    value = re.sub(r"\s+", " ", value).strip()
    if not value or value == "Samuga Media is following this developing story.":
        value = _safe_bg_keyword(str(title or ""), str(cat or "LOCAL"))
    suffix = "Maldives news photo" if str(cat or "").upper() in {"LOCAL", "POLITICAL", "BUSINESS", "WEATHER", "TOURISM"} else "news photo"
    return (value[:170] + " " + suffix).strip()


def _tavily_image_search(keyword, *, cat=None, title=None):
    """Return a validated Tavily image, with cache, rate cap and circuit break."""
    global _TAVILY_FAILURES, _TAVILY_CIRCUIT_UNTIL
    if not TAVILY_API_KEY or os.environ.get("TAVILY_IMAGE_SEARCH_ENABLED", "true").lower() != "true":
        return None
    now = time.time()
    if now < _TAVILY_CIRCUIT_UNTIL:
        return None
    max_per_hour = max(1, int(os.environ.get("TAVILY_IMAGE_MAX_REQUESTS_PER_HOUR", "30") or 30))
    with _IMAGE_CACHE_LOCK:
        _TAVILY_CALL_TIMES[:] = [stamp for stamp in _TAVILY_CALL_TIMES if now - stamp < 3600]
        if len(_TAVILY_CALL_TIMES) >= max_per_hour:
            log.warning("[IMAGE] Tavily image hourly cap reached: %s/%s", len(_TAVILY_CALL_TIMES), max_per_hour)
            return None
        _TAVILY_CALL_TIMES.append(now)

    query = _clean_image_query(keyword, title, cat)
    cache_key = "tavily:" + query.lower()
    cached = _image_cache_get(cache_key)
    if cached is not None:
        log.info("✅ Tavily image cache: '%s'", query[:70])
        return cached

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "topic": "general",
                "search_depth": "basic",
                "max_results": max(3, min(10, int(os.environ.get("TAVILY_IMAGE_MAX_RESULTS", "6") or 6))),
                "include_answer": False,
                "include_raw_content": False,
                "include_images": True,
                "include_image_descriptions": True,
            },
            timeout=25,
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:180]}")
        data = response.json() or {}
        candidates = list(data.get("images") or [])
        for result in data.get("results") or []:
            candidates.extend(result.get("images") or [])

        ranked = []
        seen = set()
        for index, candidate in enumerate(candidates):
            if isinstance(candidate, dict):
                url = str(candidate.get("url") or "").strip()
                description = str(candidate.get("description") or candidate.get("alt") or "").lower()
            else:
                url = str(candidate or "").strip()
                description = ""
            if not url or url in seen:
                continue
            seen.add(url)
            if any(term in description for term in ("logo", "icon", "clipart", "vector", "advertisement", "screenshot", "poster")):
                continue
            score, matched_title = _image_candidate_score(candidate, title or keyword, query)
            # Tavily ordering remains a useful tiebreaker, but an exact named
            # person/institution match is preferred over the first generic image.
            ranked.append((score, matched_title, -index, url, candidate))

        ranked.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
        exact_required = _requires_identity_relevance(title or keyword, cat)
        minimum_score = float(os.environ.get("TAVILY_IMAGE_RELEVANCE_MIN_SCORE", "2.0") or 2.0)
        for score, matched_title, _order, url, candidate in ranked:
            if exact_required and (matched_title < 1 or score < minimum_score):
                continue
            image = _download_image_candidate(url, provider="Tavily")
            if image is not None:
                _TAVILY_FAILURES = 0
                _image_cache_put(cache_key, image)
                match_kind = "exact/relevant" if exact_required else "relevant"
                log.info(
                    "✅ Tavily %s bg: '%s' score=%.2f matched=%s request_id=%s",
                    match_kind, query[:70], score, matched_title, str(data.get("request_id") or "")[:40],
                )
                return image
        if exact_required:
            raise RuntimeError("No sufficiently relevant named-person/institution image returned")
        raise RuntimeError("No usable image candidate returned")
    except Exception as exc:
        message = str(exc)
        no_match = message.startswith("No usable image candidate") or message.startswith("No sufficiently relevant")
        if no_match:
            # A healthy Tavily response with no trustworthy picture is normal; it
            # must not trip the provider circuit or suppress later real-photo hits.
            log.info("[IMAGE] Tavily had no trustworthy exact image; using Maldives fallback")
            return None
        _TAVILY_FAILURES += 1
        log.warning("[IMAGE] Tavily image search failed: %s", message[:260])
        if _TAVILY_FAILURES >= 3:
            cooldown = max(60, int(os.environ.get("TAVILY_IMAGE_CIRCUIT_MINUTES", "15") or 15) * 60)
            _TAVILY_CIRCUIT_UNTIL = time.time() + cooldown
            log.warning("[IMAGE] Tavily image circuit opened for %s minutes", cooldown // 60)
        return None


def _pexels_image_search(keyword, *, cat=None, title=None, force_query=False):
    if not PEXELS_API_KEY:
        return None
    import random as _rand
    resolved_cat = cat or "LOCAL"
    try:
        if force_query and str(keyword or "").strip():
            search_kw = str(keyword).strip()
        elif title:
            search_kw = _safe_bg_keyword(title, resolved_cat)
        elif cat and cat in CAT_BG_KEYWORDS:
            search_kw = _rand.choice(CAT_BG_KEYWORDS[cat])
        elif not keyword or keyword in ["maldives news", "news", "local"]:
            search_kw = _rand.choice(DEFAULT_BG_KEYWORDS)
        else:
            dangerous = ["president", "minister", "india", "china", "pakistan",
                         "israel", "america", "flag", "person", "man", "woman"]
            search_kw = _rand.choice(DEFAULT_BG_KEYWORDS) if any(d in str(keyword).lower() for d in dangerous) else str(keyword)
        cache_key = "pexels:" + search_kw.lower()
        cached = _image_cache_get(cache_key)
        if cached is not None:
            log.info("✅ Pexels image cache: '%s'", search_kw)
            return cached
        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": search_kw, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        )
        if response.status_code != 200:
            log.warning("[IMAGE] Pexels HTTP %s: %s", response.status_code, response.text[:180])
            return None
        photos = response.json().get("photos", [])
        _rand.shuffle(photos)
        for photo in photos:
            src = photo.get("src") or {}
            url = src.get("large2x") or src.get("large") or src.get("original")
            image = _download_image_candidate(url, provider="Pexels")
            if image is not None:
                _image_cache_put(cache_key, image)
                log.info("✅ Pexels bg: '%s'", search_kw)
                return image
    except Exception as exc:
        log.warning("[IMAGE] Pexels search failed: %s", str(exc)[:260])
    return None


def fetch_background_image(keyword, cat=None, title=None):
    """Choose one image for both the social card and website cover.

    Priority:
      1. Exact/relevant Tavily news photo (real people, institutions and events).
      2. A safe Maldivian scenic image from Pexels.
      3. A local curated Maldives/category image if one is packaged.
      4. Branded Samuga fallback.

    This deliberately avoids letting a generic local/stock image override a real
    Tavily photo. The same returned PIL image is reused by the caller for social
    and website artwork.
    """
    resolved_cat = str(cat or "LOCAL").upper()
    order = [item.strip().lower() for item in os.environ.get(
        "IMAGE_SEARCH_PROVIDER_ORDER", "tavily,pexels"
    ).split(",") if item.strip()]

    # Real related image first. This is what allows President, MP, Parliament,
    # court and event stories to use the actual relevant photo when Tavily has it.
    if "tavily" in order:
        image = _tavily_image_search(keyword, cat=resolved_cat, title=title)
        if image is not None:
            log.info("[IMAGE] selected real/relevant Tavily photo for social + website")
            return image

    # No trustworthy exact image: keep the visual unmistakably Maldivian rather
    # than using a misleading face or unrelated foreign stock image.
    scenic_query = _maldives_scenic_query(title or keyword or "", resolved_cat)
    if "pexels" in order:
        image = _pexels_image_search(
            scenic_query, cat="LOCAL", title=None, force_query=True
        )
        if image is not None:
            log.info("[IMAGE] Tavily exact image unavailable — Maldives scenic fallback: '%s'", scenic_query)
            return image

    local = _local_bg_for_cat(resolved_cat) or _local_bg_for_cat("LOCAL")
    if local is not None:
        log.info("[IMAGE] external image unavailable — local Maldives fallback selected")
        return local

    log.warning("[IMAGE] no relevant or Maldives scenic background available; using branded card fallback")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Dhivehi card — Pango/Cairo (proper Thaana RTL shaping)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_dhivehi_card(text, source, timestamp, cat, bg_image=None):
    """Generate a card with proper Thaana shaping using Pango/Cairo."""
    text = sanitize_card_text(text)
    source = ""  # private metadata must never be rendered on public cards
    try:
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
        import cairo
    except Exception as e:
        log.error(f"Pango not available (falling back to PIL): {e}")
        return generate_card(text, source, timestamp, cat, bg_image, _skip_dhivehi=True)

    import numpy as np

    W, H = 1080, 1080
    cfg    = DV_CAT.get(cat, DV_CAT["LOCAL"])
    accent = cfg["color"]
    label_dv = cfg["label"]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx     = cairo.Context(surface)

    # Background
    if bg_image:
        try:
            bg  = bg_image.copy().convert("RGB")
            r   = bg.width / bg.height
            nh, nw = (H, int(H * r)) if r > 1 else (int(W / r), W)
            bg  = bg.resize((nw, nh), Image.LANCZOS)
            bg  = bg.crop(((nw - W) // 2, (nh - H) // 2,
                           (nw - W) // 2 + W, (nh - H) // 2 + H))
            bg  = ImageEnhance.Brightness(bg).enhance(0.32)
            navy = Image.new("RGB", (W, H), (8, 30, 65))
            bg  = Image.blend(bg, navy, 0.45).convert("RGBA")
            bg_arr  = np.array(bg)
            bg_bgra = np.ascontiguousarray(bg_arr[:, :, [2, 1, 0, 3]])
            bg_surf = cairo.ImageSurface.create_for_data(bg_bgra, cairo.FORMAT_ARGB32, W, H)
            ctx.set_source_surface(bg_surf, 0, 0)
            ctx.paint()
        except Exception as e:
            log.error(f"DV card BG paste: {e}")
            ctx.set_source_rgb(0.008, 0.047, 0.107)
            ctx.paint()
    else:
        ctx.set_source_rgb(0.008, 0.047, 0.107)
        ctx.paint()

    # Bottom gradient
    grad = cairo.LinearGradient(0, H // 2, 0, H)
    grad.add_color_stop_rgba(0, 0.02, 0.08, 0.2, 0)
    grad.add_color_stop_rgba(1, 0.02, 0.08, 0.2, 0.85)
    ctx.set_source(grad); ctx.rectangle(0, 0, W, H); ctx.fill()

    # Top gradient
    grad2 = cairo.LinearGradient(0, 0, 0, 170)
    grad2.add_color_stop_rgba(0, 0.02, 0.08, 0.2, 0.75)
    grad2.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(grad2); ctx.rectangle(0, 0, W, H); ctx.fill()

    # Accent bar
    ctx.set_source_rgb(accent[0] / 255, accent[1] / 255, accent[2] / 255)
    ctx.rectangle(0, 0, W, 5); ctx.fill()

    # PIL overlay for logo + footer text
    from PIL import ImageDraw as _ID, ImageFont as _IF
    ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od  = _ID.Draw(ov)
    try:
        logo = Image.open("logo.png").convert("RGBA")
        lh   = 72; lw = int(logo.width * lh / logo.height)
        logo = logo.resize((lw, lh), Image.LANCZOS)
        ov.paste(logo, (50, 38), logo)
    except Exception as e:
        log.debug(f"DV logo overlay: {e}")
    try:
        f_sm = _IF.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
        od.text((W - 310, 50), "t.me/samugacommunity", font=f_sm, fill=(200, 230, 255, 220))
        tw = od.textlength(timestamp, font=f_sm)
        od.text((W - 50 - int(tw), H - 52), timestamp, font=f_sm, fill=(180, 200, 220, 220))
        od.line([(0, H - 65), (W, H - 65)], fill=(255, 255, 255, 50), width=1)
    except Exception as e:
        log.debug(f"DV footer draw: {e}")

    ov_arr  = np.array(ov)
    ov_bgra = np.ascontiguousarray(ov_arr[:, :, [2, 1, 0, 3]])
    ov_surf = cairo.ImageSurface.create_for_data(ov_bgra, cairo.FORMAT_ARGB32, W, H)
    ctx.set_source_surface(ov_surf, 0, 0); ctx.paint()

    # Category label (Dhivehi Pango)
    tag_y  = 580
    cat_lo = PangoCairo.create_layout(ctx)
    cat_lo.set_text(label_dv, -1)
    cat_lo.set_font_description(Pango.FontDescription("Noto Sans Thaana Bold 20"))
    tw, _ = cat_lo.get_pixel_size()
    ctx.set_source_rgb(accent[0] / 255, accent[1] / 255, accent[2] / 255)
    ctx.rectangle(50, tag_y, tw + 26, 36); ctx.fill()
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(63, tag_y + 6); PangoCairo.show_layout(ctx, cat_lo)

    # Headline + body
    # Rule: an explicit blank line (\n\n) is an intentional headline/subhead
    # separator and is ALWAYS honored. Part 1 = headline, the rest = subhead.
    # If there is NO blank line, the whole text stays as headline and simply
    # wraps to more lines — UNLESS it is very long (no blank line, >160 chars),
    # in which case we fall back to the old 80-char auto-split so auto-generated
    # cards still look balanced.
    _blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(_blocks) >= 2:
        headline = _blocks[0].replace("\n", " ").strip()
        body     = " ".join(b.replace("\n", " ") for b in _blocks[1:]).strip()
    else:
        single = (_blocks[0] if _blocks else text).replace("\n", " ").strip()
        if len(single) <= 160:
            headline = single
            body     = ""
        else:
            words = single.split()
            hw, bw, cc = [], [], 0
            for i, w in enumerate(words):
                if cc < 80:
                    hw.append(w); cc += len(w) + 1
                else:
                    bw = words[i:]; break
            headline = " ".join(hw)
            body     = " ".join(bw)

    def to_arabic_nums(t):
        return _to_arabic_nums(t)

    h_lo = PangoCairo.create_layout(ctx)
    h_lo.set_width(980 * Pango.SCALE)
    h_lo.set_alignment(Pango.Alignment.RIGHT)
    h_fd = Pango.FontDescription("Noto Sans Thaana 50")
    h_fd.set_weight(Pango.Weight.ULTRABOLD)
    h_lo.set_font_description(h_fd)
    h_lo.set_text(to_arabic_nums(headline), -1)
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(50, tag_y + 44); PangoCairo.show_layout(ctx, h_lo)

    if body:
        _, hh = h_lo.get_pixel_size()
        b_lo  = PangoCairo.create_layout(ctx)
        b_lo.set_width(980 * Pango.SCALE)
        b_lo.set_alignment(Pango.Alignment.RIGHT)
        b_lo.set_font_description(Pango.FontDescription("Noto Sans Thaana 26"))
        b_lo.set_text(to_arabic_nums(body), -1)
        ctx.set_source_rgba(0.78, 0.86, 1, 0.85)
        ctx.move_to(50, tag_y + 44 + hh + 8); PangoCairo.show_layout(ctx, b_lo)

    png_buf = io.BytesIO()
    surface.write_to_png(png_buf)
    png_buf.seek(0)
    return png_buf


# ═══════════════════════════════════════════════════════════════════════════════
# English card — PIL/Pillow
# ═══════════════════════════════════════════════════════════════════════════════

def generate_card(text, source, timestamp, cat, bg_image=None, morning=False, _skip_dhivehi=False):
    """
    Generate a 1080x1080 news card.
    - Dhivehi text (Thaana chars) → routed to generate_dhivehi_card() automatically
    - morning=True → golden accent + morning brief style
    - _skip_dhivehi=True → force PIL path (used as Pango fallback)
    """
    text = sanitize_card_text(text)
    source = ""  # private metadata must never be rendered on public cards
    # Route Dhivehi text to Pango-based card generator
    if not morning and not _skip_dhivehi and any('\u0780' <= ch <= '\u07BF' for ch in text):
        return generate_dhivehi_card(text, source, timestamp, cat, bg_image)

    W, H   = 1080, 1080
    accent = (255, 180, 0) if morning else CAT_CONFIG.get(cat, CAT_CONFIG["LOCAL"])["color"]
    label  = "🌅  MORNING BRIEF" if morning else CAT_CONFIG.get(cat, CAT_CONFIG["LOCAL"])["label"]

    img = Image.new("RGB", (W, H), BG_TOP)
    if bg_image:
        bg  = bg_image.copy()
        r   = bg.width / bg.height
        nh, nw = (H, int(H * r)) if r > 1 else (int(W / r), W)
        bg  = bg.resize((nw, nh), Image.LANCZOS).crop(
            ((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))
        bg  = ImageEnhance.Brightness(bg).enhance(0.32)
        img = Image.blend(bg, Image.new("RGB", (W, H), (8, 30, 65)), 0.45)
    else:
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)], fill=(
                int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
                int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
                int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t),
            ))

    # Bottom dark vignette
    ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od  = ImageDraw.Draw(ov)
    for y in range(H // 2, H):
        t = (y - H // 2) / (H // 2)
        od.line([(0, y), (W, y)], fill=(5, 20, 50, int(185 * t)))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    # Top dark vignette
    ov2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od2 = ImageDraw.Draw(ov2)
    for y in range(0, 170):
        t = 1 - y / 170
        od2.line([(0, y), (W, y)], fill=(5, 20, 50, int(190 * t)))
    img = Image.alpha_composite(img.convert("RGBA"), ov2).convert("RGB")

    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W, 5)], fill=accent)

    # Logo
    try:
        logo = Image.open("logo.png").convert("RGBA")
        lh   = 72; lw = int(logo.width * lh / logo.height)
        logo = logo.resize((lw, lh), Image.LANCZOS)
        img.paste(logo, (50, 38), logo)
    except Exception as e:
        log.debug(f"logo paste: {e}")

    # Font loading — Thaana or DejaVu
    has_thaana = any('\u0780' <= ch <= '\u07BF' for ch in text)

    def find_thaana_font(name):
        for path in [f"/app/{name}", f"/data/{name}",
                     f"/usr/share/fonts/truetype/noto/{name}"]:
            if os.path.exists(path): return path
        return None

    THAANA_BOLD = find_thaana_font("NotoSansThaana-Bold.ttf")
    THAANA_REG  = find_thaana_font("NotoSansThaana-Regular.ttf")

    try:
        if has_thaana and THAANA_BOLD:
            f_tag   = ImageFont.truetype(THAANA_BOLD, 22)
            f_title = ImageFont.truetype(THAANA_BOLD, 46)
            f_body  = ImageFont.truetype(THAANA_REG or THAANA_BOLD, 27)
            f_sm    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
        else:
            f_tag   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
            f_body  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 27)
            f_sm    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
    except Exception as e:
        log.debug(f"font load fallback: {e}")
        f_tag = f_title = f_body = f_sm = ImageFont.load_default()

    draw.text((W - 310, 50), "t.me/samugacommunity", font=f_sm, fill=(200, 230, 255))

    # Category tag
    tag_label = {
        "BREAKING": "BREAKING NEWS", "LOCAL": "LOCAL NEWS", "POLITICAL": "POLITICAL",
        "LIFESTYLE": "LIFESTYLE", "SPORTS": "SPORTS", "DISASTER": "BREAKING NEWS",
        "WORLD": "WORLD NEWS", "WEATHER": "LIFESTYLE", "TOURISM": "LIFESTYLE",
        "FOOTBALL": "SPORTS"
    }.get(cat, cat) if has_thaana else label

    f_tag_en = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    tag_y    = 590
    tw       = draw.textbbox((0, 0), tag_label, font=f_tag_en)[2] + 26
    draw.rectangle([(50, tag_y), (50 + tw, tag_y + 34)], fill=accent)
    draw.text((63, tag_y + 6), tag_label, font=f_tag_en,
              fill=WHITE if not morning else (0, 0, 0))

    # Text wrap helper
    def wrap(t, f, mw):
        words = t.split(); lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textbbox((0, 0), test, font=f)[2] <= mw:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines

    # Convert digits for Thaana RTL
    if has_thaana:
        text = text.translate(str.maketrans(
            "0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"))

    # Split headline vs body
    # Rule: explicit blank line (\n\n) = intentional headline/subhead separator,
    # always honored. No blank line = whole text stays headline (wraps), unless
    # very long, where we fall back to the original auto-split behaviour.
    _blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(_blocks) >= 2:
        headline = _blocks[0].replace("\n", " ").strip()
        body     = " ".join(b.replace("\n", " ") for b in _blocks[1:]).strip()
    elif has_thaana:
        single = (_blocks[0] if _blocks else text).replace("\n", " ").strip()
        if len(single) <= 160:
            headline = single; body = ""
        else:
            words = single.split(); hw, bw, cc = [], [], 0
            for i, w in enumerate(words):
                if cc < 80: hw.append(w); cc += len(w) + 1
                else:       bw = words[i:]; break
            headline = " ".join(hw)
            body     = " ".join(bw)
    else:
        single = (_blocks[0] if _blocks else text).replace("\n", " ").strip()
        if len(single) <= 120 and ". " not in single:
            headline = single; body = ""
        else:
            sentences = single.split(". ")
            headline  = sentences[0] + ("." if len(sentences) > 1 else "")
            body      = ". ".join(sentences[1:]) if len(sentences) > 1 else ""

    y = tag_y + 48
    for line in wrap(headline, f_title, W - 100)[:4]:
        draw.text((50, y), line, font=f_title, fill=WHITE); y += 56
    if body:
        y += 4
        for line in wrap(body, f_body, W - 100)[:3]:
            draw.text((50, y), line, font=f_body, fill=LIGHT_GRAY); y += 36

    # Footer
    draw.rectangle([(0, H - 78), (W, H)], fill=(3, 12, 30))
    draw.rectangle([(0, H - 78), (W, H - 75)], fill=accent)
    draw.text((W - 260, H - 53), timestamp, font=f_sm, fill=LIGHT_GRAY)

    buf = BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════════════════════
# Weather icon renderer (vector, scales at any size)
# ═══════════════════════════════════════════════════════════════════════════════

def draw_weather_icon(draw, code, x, y, size=40):
    """Draw a vector weather icon. Scales cleanly at any size."""
    import math
    cx, cy = x, y
    s  = size
    lw = max(2, s // 18)

    if code == 0:  # Sun
        draw.ellipse([cx - s // 3, cy - s // 3, cx + s // 3, cy + s // 3],
                     fill=(255, 210, 40, 255))
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            x1  = cx + int((s // 3 + s // 12) * math.cos(rad))
            y1  = cy + int((s // 3 + s // 12) * math.sin(rad))
            x2  = cx + int((s // 2 + s // 10) * math.cos(rad))
            y2  = cy + int((s // 2 + s // 10) * math.sin(rad))
            draw.line([x1, y1, x2, y2], fill=(255, 210, 40, 230), width=lw)

    elif code in [1, 2]:  # Partly cloudy
        draw.ellipse([cx - s // 6, cy - s // 2, cx + s // 2, cy + s // 8],
                     fill=(255, 210, 40, 235))
        draw.ellipse([cx - s // 2, cy - s // 8, cx + s // 6, cy + s // 2],
                     fill=(225, 235, 250, 255))
        draw.ellipse([cx - s // 8, cy - s // 5, cx + s // 2, cy + s // 3],
                     fill=(225, 235, 250, 255))
        draw.ellipse([cx - s // 2, cy, cx + s // 4, cy + s // 2],
                     fill=(225, 235, 250, 255))

    elif code == 3:  # Cloud
        draw.ellipse([cx - s // 2, cy - s // 8, cx + s // 2, cy + s // 2],
                     fill=(210, 220, 245, 255))
        draw.ellipse([cx - s // 3, cy - s // 3, cx + s // 6, cy + s // 4],
                     fill=(210, 220, 245, 255))
        draw.ellipse([cx - s // 12, cy - s // 4, cx + s // 2, cy + s // 3],
                     fill=(210, 220, 245, 255))

    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:  # Rain
        draw.ellipse([cx - s // 2, cy - s // 5, cx + s // 2, cy + s // 3],
                     fill=(175, 190, 225, 255))
        draw.ellipse([cx - s // 3, cy - s // 3, cx + s // 6, cy + s // 5],
                     fill=(175, 190, 225, 255))
        draw.ellipse([cx - s // 12, cy - s // 4, cx + s // 2, cy + s // 4],
                     fill=(175, 190, 225, 255))
        for rx in [-s // 3, 0, s // 3]:
            draw.line([cx + rx, cy + s // 3, cx + rx - s // 12, cy + s // 2 + s // 8],
                      fill=(90, 160, 255, 235), width=lw)

    elif code in [95, 96, 99]:  # Thunderstorm
        draw.ellipse([cx - s // 2, cy - s // 5, cx + s // 2, cy + s // 3],
                     fill=(90, 90, 115, 255))
        draw.ellipse([cx - s // 3, cy - s // 3, cx + s // 6, cy + s // 5],
                     fill=(90, 90, 115, 255))
        draw.ellipse([cx - s // 12, cy - s // 4, cx + s // 2, cy + s // 4],
                     fill=(90, 90, 115, 255))
        bolt = [cx + s // 12, cy + s // 4, cx - s // 12, cy + s // 4,
                cx, cy + s // 2, cx - s // 6, cy + s // 2, cx + s // 5, cy + s * 3 // 4]
        draw.line(bolt, fill=(255, 215, 0, 255), width=lw + 1)

    else:  # Default cloud
        draw.ellipse([cx - s // 2, cy - s // 8, cx + s // 2, cy + s // 2],
                     fill=(190, 200, 230, 255))
        draw.ellipse([cx - s // 3, cy - s // 3, cx + s // 6, cy + s // 4],
                     fill=(190, 200, 230, 255))


# ═══════════════════════════════════════════════════════════════════════════════
# Web article cover — 1200×630 branded image
# ═══════════════════════════════════════════════════════════════════════════════

def generate_web_cover(title, category="LOCAL", bg_image=None, source="Samuga Media"):
    """
    Generate a 1200x630 branded article cover image for the website.

    Pure branding — no headline text is drawn on the image at all.
    Just the background photo (or a dark gradient if none is supplied),
    the Samuga Media logo top-left, a category pill top-right, and a
    footer strip with samugamedia.com only.

    Because there is no text to shape, this single function works
    identically for English AND Dhivehi articles — no Thaana font
    handling is needed here at all, since the headline itself is never
    rendered into the image (the website page renders the real headline
    as normal HTML/CSS text, which already handles Thaana correctly).

    `title` is accepted for backward compatibility with existing call
    sites but is intentionally unused.

    Returns BytesIO PNG.
    """
    W, H = 1200, 630
    PAD = 56
    accent = CAT_CONFIG.get(category, CAT_CONFIG["LOCAL"])["color"]
    label  = CAT_CONFIG.get(category, CAT_CONFIG["LOCAL"])["label"]

    img = Image.new("RGB", (W, H), (4, 14, 32))
    if bg_image:
        bg = bg_image.copy()
        r  = bg.width / bg.height
        if r > W / H:
            nh = H; nw = int(H * r)
        else:
            nw = W; nh = int(W / r)
        bg = bg.resize((nw, nh), Image.LANCZOS)
        x0 = (nw - W) // 2; y0 = (nh - H) // 2
        bg = bg.crop((x0, y0, x0 + W, y0 + H))
        bg = ImageEnhance.Brightness(bg).enhance(0.55)
        img = Image.blend(bg, Image.new("RGB", (W, H), (8, 28, 60)), 0.28)

    # Subtle bottom gradient so the footer strip always reads cleanly
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for y in range(H - 220, H):
        t = (y - (H - 220)) / 220
        od.line([(0, y), (W, y)], fill=(3, 10, 28, int(160 * t)))
    # Subtle top vignette so the logo/pill always read cleanly
    for y in range(0, 130):
        t = 1 - y / 130
        od.line([(0, y), (W, y)], fill=(3, 10, 28, int(130 * t)))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W, 5)], fill=accent)

    # Logo — top left
    try:
        logo = Image.open("logo.png").convert("RGBA")
        lh = 56; lw = int(logo.width * lh / logo.height)
        logo = logo.resize((lw, lh), Image.LANCZOS)
        img.paste(logo, (PAD, 28), logo)
    except Exception as e:
        log.debug(f"web cover logo: {e}")

    # Fonts
    try:
        f_cat = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)
        f_sm  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        f_cat = f_sm = ImageFont.load_default()

    # Category pill — top right
    tag_text = label.upper()
    tw = draw.textbbox((0, 0), tag_text, font=f_cat)[2] + 28
    tag_x = W - tw - PAD
    draw.rectangle([(tag_x, 26), (tag_x + tw, 26 + 34)], fill=accent)
    draw.text((tag_x + 14, 32), tag_text, font=f_cat,
              fill=(0, 0, 0) if sum(accent) > 400 else (255, 255, 255))

    # Footer strip
    draw.rectangle([(0, H - 62), (W, H)], fill=(3, 12, 30))
    draw.rectangle([(0, H - 62), (W, H - 59)], fill=accent)
    tw2 = draw.textlength("samugamedia.com", font=f_sm)
    draw.text((W - PAD - int(tw2), H - 42), "samugamedia.com", font=f_sm, fill=(120, 160, 210))

    buf = BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf
