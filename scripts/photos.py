#!/usr/bin/env python3
"""
Photographic hero sourcing for Bluestones BPO.

Fetches a licensed landscape photograph per article from Pexels, caches it in the
repository, and records the photographer for attribution. The build composites it
behind the headline (see imagegen.photo_cover).

Design decisions worth knowing:

* **Cached and committed.** A photo is fetched once, written to assets/photos/,
  and its credit recorded in content/_data/photos.json. Later builds reuse the
  file. That keeps builds reproducible, keeps the article's image stable over
  time (readers and social previews hate images that silently change), and means
  CI does not depend on a third-party API being up.
* **Degrades to nothing.** No API key, no network, or no acceptable match and the
  function returns None — the caller then falls back to the typographic cover.
  A missing key is never an error.
* **Attribution is mandatory, not optional.** Pexels' licence requires crediting
  the photographer. The credit is stored alongside the file and rendered under
  the hero; a photo without a recorded credit is discarded rather than used.

Set PEXELS_API_KEY in the environment. In GitHub Actions, add it as a repository
secret and expose it to the build step.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "assets", "photos")
INDEX = os.path.join(ROOT, "content", "_data", "photos.json")
API = "https://api.pexels.com/v1/search"
TIMEOUT = 20
UA = "bluestonesbpo-build/1.0 (+https://www.bluestonesbpo.co.kr/)"

# Fallback search terms per category. Deliberately concrete and Korea-anchored:
# generic "business" stock photography is what makes a site look like a template.
#
# These are this site's categories. They previously listed markets/technology/
# living/society/policy/kcontent — the categories of a different site — so every
# Bluestones post missed the lookup, fell through to `_default`, and searched the
# same string. That, not the ranking, is why photo heroes repeated.
CATEGORY_TERMS = {
    "accounting": "accountant ledger financial statements desk",
    "payroll":    "payroll calculator salary documents desk",
    "tax":        "tax forms paperwork calculator desk",
    "entity":     "Seoul business district office buildings",
    "compliance": "filing cabinet documents government office",
    "operations": "modern office workspace team meeting",
    "_default":   "Seoul business district office",
}

# Subject → a scene that actually exists in a stock library.
#
# This is the crux of the relevance problem. An article's own vocabulary is
# abstract — "간이지급명세서", "two-of-four audit test", "limited tax rate" — and no
# photographer has ever tagged an image with those words. Searching them returns
# whatever the engine falls back to, which is how you end up with a picture of
# nothing in particular. So we translate the subject into something photographable
# first, and search for that.
#
# Ordered most specific first, because the first match wins and this site's
# vocabulary overlaps heavily — nearly every payroll article carries a "korean
# payroll" tag, and statute names drag in words the article is not about. Two
# patterns are deliberately narrow for that reason: `severance` does not include
# "retirement benefit" (it appears in the Guarantee of Employees' Retirement
# Benefits Act, cited by articles that are not about severance), and the VAT rule
# does not include "hometax" (every tax article mentions the portal).
CONCEPT_MAP: list[tuple[str, str]] = [
    (r"\b(maternity|parental|spousal|childcare|miscarriage|childbirth)",
     "parent newborn baby family home"),
    (r"\b(penalt|fine|criminal|prosecut|court|offence|arrears)",
     "courthouse law justice columns"),
    (r"\b(rules of employment|employment contract|termination|dismissal|disciplinary)",
     "signing contract documents desk"),
    (r"\b(filing calendar|compliance calendar|filing deadline|filing schedule|tax calendar)",
     "desk calendar deadline planner"),
    (r"\b(severance|퇴직금)",
     "retirement savings planning documents"),
    (r"\b(entertainment expense|promotion expense|corporate card|business meal)",
     "restaurant dinner bill receipt"),
    (r"\b(foreign parent|dividend|royalt|tax treaty|beneficial owner|repatriat)",
     "international money transfer finance"),
    # Above the entity rule: "subsidiary" appears in the title of articles that
    # are about something else happening to one. Below the two rules above it,
    # because "tax audit" is a common tag on articles that are not about audits.
    (r"\b(audit|k-ifrs|k-gaap|bookkeep|month-end|financial statement)",
     "auditor reviewing financial statements"),
    (r"\b(fdi|subsidiary|branch office|liaison office|company registration|incorporat)",
     "Seoul business district office towers"),
    (r"\b(visa|immigration|e-7|d-8|residence permit|hikorea|passport)",
     "passport immigration documents desk"),
    (r"\b(annual leave|chuseok|seollal|substitute holiday|public holiday)",
     "wall calendar planner dates"),
    (r"\b(52-hour|working hour|overtime|night work|shift)",
     "office clock late working desk"),
    (r"\b(vat|tax invoice|input tax|부가가치세)",
     "invoice receipts bookkeeping desk"),
    (r"\b(withholding|corporate tax|income tax|interim payment|tax treaty"
     r"|transfer pricing|flat tax|entertainment expense|promotion expense)",
     "tax forms calculator accounting desk"),
    (r"\b(pension|health insurance|four major insurance|4대보험|nhis|comwel)",
     "insurance policy documents signing"),
    (r"\b(minimum wage|payroll|payslip|salary|wage|연말정산|year-end settlement)",
     "payroll calculator salary paperwork"),
    (r"\b(bank|signator|foreign exchange|remittance)",
     "bank building finance counter"),
    (r"\b(employment|hiring|worker|staff|headcount|employee)",
     "office workers team meeting"),
]

STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "what", "how",
             "why", "korea", "korean", "2026", "explained", "guide", "compared"}

# A candidate must share at least this many meaningful words with the search
# concept, judged against Pexels' own description of the photo. Below it we
# publish a typographic cover instead — an honest abstract card beats a
# confidently irrelevant photograph.
MIN_RELEVANCE = 1


def _load_index() -> dict:
    try:
        return json.load(open(INDEX, encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return {}


def _save_index(data: dict) -> None:
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    json.dump(data, open(INDEX, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def query_for(post: dict) -> str:
    """
    Decide what to photograph, in descending order of reliability:

    1. `photo_query` in front matter — the writer naming a concrete scene.
       Always the best answer, because only the writer knows the piece's image.
    2. A concept mapped from the title and tags — jargon translated into
       something a photographer would actually have shot.
    3. The category default.

    Note what this deliberately does *not* do any more: paste the article's own
    tags into the search box. "KOSPI Korean stocks Samsung Electronics" is not a
    photograph of anything, and asking a stock library for it returns noise.
    """
    if post.get("photo_query"):
        return str(post["photo_query"])

    # Title and tags only. `about:` holds statute and institution names — every
    # payroll article cites the Labor Standards Act and half of them name the
    # National Tax Service — so feeding it in here matched articles to whatever
    # law they happened to quote rather than what they are about.
    haystack = " ".join([
        str(post.get("title", "")),
        " ".join(str(t) for t in (post.get("tags") or [])),
    ]).lower()

    for pattern, concept in CONCEPT_MAP:
        if re.search(pattern, haystack):
            return concept

    return CATEGORY_TERMS.get(post.get("category", "_default"), CATEGORY_TERMS["_default"])


def _claimed(index: dict, slug: str) -> set[str]:
    """Photo ids already used by some *other* post.

    Without this, two posts that resolve to the same query take the same
    top-ranked result and the archive shows the same photograph twice. Keyed on
    the Pexels id rather than the URL because the API returns several size
    variants of one image under different URLs.
    """
    used = set()
    for other, rec in index.items():
        if other == slug:
            continue                                  # a post may keep its own
        pid = rec.get("photo_id")
        if pid:
            used.add(str(pid))
        elif rec.get("source_url"):                   # records written before ids
            # .../photo/two-people-signing-a-form-31415926/ → 31415926
            m = re.search(r"(\d+)/?$", rec["source_url"])
            if m:
                used.add(m.group(1))
    return used


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower())
            if len(w) > 3 and w not in STOPWORDS}


def relevance(photo: dict, query: str) -> int:
    """How well does this candidate match what we asked for?

    Scored against Pexels' own description of the image rather than its filename
    or tags, because the description is what a human would write if asked what
    the picture shows.
    """
    return len(_terms(photo.get("alt", "")) & _terms(query))


def fetch(post: dict, *, offline: bool = False) -> dict | None:
    """
    Return {'path', 'credit', 'credit_url', 'query'} for this post's photo, or None.

    Cached results are returned without touching the network.
    """
    slug = post["slug"]
    index = _load_index()
    hit = index.get(slug)
    if hit and os.path.exists(os.path.join(ROOT, hit.get("path", ""))):
        return {**hit, "path": os.path.join(ROOT, hit["path"])}

    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if offline or not key:
        return None

    q = query_for(post)
    # 30 rather than 15: candidates already used by another post are skipped, so
    # the pool has to be deep enough to still hold a relevant unused one.
    url = f"{API}?{urllib.parse.urlencode({'query': q, 'orientation': 'landscape', 'per_page': 30, 'size': 'large'})}"
    try:
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        print(f"  photos: search failed for {slug} ({type(e).__name__}) — falling back to cover")
        return None

    # Rank by how well each candidate actually depicts the concept, rather than
    # trusting the API's own ordering. Ties keep the API's order.
    candidates = [p for p in data.get("photos", []) if p.get("alt")]
    ranked = sorted(candidates, key=lambda p: -relevance(p, q))

    best = relevance(ranked[0], q) if ranked else 0
    if best < MIN_RELEVANCE:
        print(f"  photos: no relevant match for {slug} (“{q}”, best score {best}) "
              "— using typographic cover instead")
        return None

    claimed = _claimed(index, slug)
    skipped = 0
    for photo in ranked:
        if relevance(photo, q) < MIN_RELEVANCE:
            break
        if str(photo.get("id", "")) in claimed:
            skipped += 1
            continue                                       # already another post's
        src = (photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")
        credit = (photo.get("photographer") or "").strip()
        if not src or not credit:
            continue                                       # no credit, no use
        try:
            os.makedirs(PHOTO_DIR, exist_ok=True)
            dest = os.path.join(PHOTO_DIR, f"{slug}.jpg")
            req = urllib.request.Request(src, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(dest, "wb") as f:
                f.write(r.read())
        except Exception as e:                             # noqa: BLE001
            print(f"  photos: download failed for {slug} ({type(e).__name__})")
            return None

        rec = {
            "path": os.path.relpath(dest, ROOT).replace("\\", "/"),
            "photo_id": str(photo.get("id", "")),
            # Pexels supplies its own description of the photo. Using it keeps the
            # alt text truthful once a post's artwork changes from generated art
            # to a photograph — otherwise the old alt silently describes an image
            # that is no longer there, which is worse than no alt at all.
            "alt": (photo.get("alt") or "").strip(),
            "credit": credit,
            "credit_url": photo.get("photographer_url") or photo.get("url") or "",
            "source_url": photo.get("url", ""),
            "provider": "Pexels",
            "query": q,
        }
        index[slug] = rec
        _save_index(index)
        note = f" ({skipped} already used)" if skipped else ""
        print(f"  photos: {slug} ← “{q}” by {credit}{note}")
        return {**rec, "path": dest}

    print(f"  photos: no unused relevant result for {slug} (“{q}”, "
          f"{skipped} candidates already used) — falling back to cover")
    return None


def credit_html(rec: dict | None) -> str:
    if not rec or not rec.get("credit"):
        return ""
    who = rec["credit"]
    href = rec.get("credit_url") or rec.get("source_url") or ""
    name = (f'<a href="{href}" rel="nofollow noopener" target="_blank">{who}</a>'
            if href else who)
    return (f'<p class="photo-credit muted small">Photograph by {name} '
            f'on {rec.get("provider", "Pexels")}.</p>')
