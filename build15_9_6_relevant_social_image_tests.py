from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent
checks = 0

def check(condition, message):
    global checks
    if not condition:
        raise AssertionError(message)
    checks += 1

bot_text = (ROOT / "bot.py").read_text()
cards_text = (ROOT / "cards.py").read_text()

check('SAMUGA_VERSION = "15.9.6"' in bot_text, "backend version")
check("MALDIVES_SCENIC_FALLBACKS" in cards_text, "Maldives fallback pool")
check("selected real/relevant Tavily photo for social + website" in cards_text, "shared social/website image routing")
check("Tavily exact image unavailable — Maldives scenic fallback" in cards_text, "fallback logging")
check("TAVILY_IMAGE_RELEVANCE_MIN_SCORE" in cards_text, "relevance threshold")
check("force_query=True" in cards_text, "forced Maldives Pexels query")
check("must not trip the provider circuit" in cards_text, "no-match circuit safety")

import cards

class FakeResponse:
    status_code = 200
    text = ""
    def __init__(self, images):
        self._images = images
    def json(self):
        return {"request_id": "req-1596", "images": self._images, "results": []}

os.environ["TAVILY_IMAGE_SEARCH_ENABLED"] = "true"
os.environ["TAVILY_IMAGE_MAX_REQUESTS_PER_HOUR"] = "30"
os.environ["TAVILY_IMAGE_RELEVANCE_MIN_SCORE"] = "2.0"
cards.TAVILY_API_KEY = "tvly-test"
cards.PEXELS_API_KEY = "pexels-test"
cards._TAVILY_CALL_TIMES[:] = []
cards._TAVILY_FAILURES = 0
cards._TAVILY_CIRCUIT_UNTIL = 0.0
cards._IMAGE_CACHE.clear()

# Tavily must prefer the actual named person even when a generic photo is first.
images = [
    {"url": "https://example.test/parliament-building.jpg", "description": "Parliament building in Maldives"},
    {"url": "https://presidency.gov.mv/president-muizzu.jpg", "description": "President Mohamed Muizzu of Maldives"},
]
downloaded = []
def fake_download(url, provider="web"):
    downloaded.append(url)
    return Image.new("RGB", (1200, 800))

with patch.object(cards.requests, "post", return_value=FakeResponse(images)), \
     patch.object(cards, "_download_image_candidate", side_effect=fake_download):
    result = cards._tavily_image_search(
        "President Muizzu",
        cat="POLITICAL",
        title="President Muizzu meets Parliament leaders",
    )
check(result is not None, "Tavily exact result")
check(downloaded and "president-muizzu" in downloaded[0], "named person ranked before generic building")

# A healthy no-match result must not count as a Tavily provider failure.
cards._TAVILY_CALL_TIMES[:] = []
cards._TAVILY_FAILURES = 0
cards._IMAGE_CACHE.clear()
with patch.object(cards.requests, "post", return_value=FakeResponse([
    {"url": "https://example.test/random-beach.jpg", "description": "Generic tropical beach"},
])), patch.object(cards, "_download_image_candidate", return_value=Image.new("RGB", (1200, 800))):
    result = cards._tavily_image_search(
        "Hussain Ziyad",
        cat="POLITICAL",
        title="MP Hussain Ziyad submits emergency motion",
    )
check(result is None, "misleading named-person image rejected")
check(cards._TAVILY_FAILURES == 0, "normal no-match does not open circuit")

# The complete public-card route must use Tavily first and a Maldives scene second.
scenic_calls = []
def fake_pexels(keyword, **kwargs):
    scenic_calls.append((keyword, kwargs))
    return Image.new("RGB", (1400, 900))

with patch.object(cards, "_tavily_image_search", return_value=None) as tavily_mock, \
     patch.object(cards, "_pexels_image_search", side_effect=fake_pexels) as pexels_mock, \
     patch.object(cards, "_local_bg_for_cat", return_value=None):
    os.environ["IMAGE_SEARCH_PROVIDER_ORDER"] = "tavily,pexels"
    result = cards.fetch_background_image(
        "transport",
        cat="LOCAL",
        title="Speedboat service resumes between the islands",
    )
check(result is not None, "Maldives scenic result")
check(tavily_mock.called, "Tavily tried first")
check(pexels_mock.called, "Pexels scenic fallback tried")
check("Maldives" in scenic_calls[0][0], "fallback query is explicitly Maldivian")
check(scenic_calls[0][1].get("force_query") is True, "fallback does not get rewritten to unrelated stock")

# Stable selection: the same story must keep the same fallback across retries.
q1 = cards._maldives_scenic_query("Local transport update", "LOCAL")
q2 = cards._maldives_scenic_query("Local transport update", "LOCAL")
check(q1 == q2, "stable story fallback")
check(any(word in q1.lower() for word in ("maldives", "male")), "fallback remains Maldives-specific")

# Dhivehi headlines should use the supplied English visual keyword for Tavily.
query = cards._clean_image_query("Maldives parliament members", "މަޖިލީހުގެ މެންބަރުން", "POLITICAL")
check(query.lower().startswith("maldives parliament members"), "Dhivehi title uses English image keyword")

print(f"Build 15.9.6 relevant social image tests: {checks} checks passed")
