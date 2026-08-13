#!/usr/bin/env python3
"""
Duplicate-topic gate.

A daily publishing loop drifts towards repetition on its own: the same beats get
checked each morning, the same stories are the most findable, and "the KOSPI
fell again" is always available. Two articles about the same thing is the single
most damaging pattern for a young site — Google reads it as scaled content, the
pages cannibalise each other's rankings, and neither one wins.

So this is enforced rather than advised. `validate.py` calls it, and a
sufficiently similar pair fails the build.

How similarity is measured
--------------------------
Three signals, because each alone gives false positives on a single-country site
where every article shares vocabulary like "Korea", "won" and "2026":

* **Title overlap** — Jaccard on meaningful title words.
* **Subject overlap** — Jaccard on tags plus `about` entities.
* **Body overlap** — Jaccard on word 5-grams (shingles). This is the one that
  catches a genuine rewrite, because reworded prose still shares long runs of
  phrasing with its source.

A pair fails when body shingles alone are damning, or when two weaker signals
agree. Thresholds are deliberately loose enough that legitimate follow-ups —
"the KOSPI crash" and later "what the crash did to pensions" — pass.

Legitimate updates
------------------
To deliberately revisit a topic, either update the existing article in place
(what `updated:` is for — better for SEO than a near-duplicate), or set
`supersedes: <slug>` in the new post's front matter, which exempts the pair and
emits a canonical pointer from old to new.

Run standalone: python3 scripts/dedupe.py
"""
from __future__ import annotations

import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "content", "posts")

SHINGLE = 5
BODY_FAIL = 0.22            # word-5-gram overlap that alone means "same article"
BODY_WARN = 0.12
TITLE_FAIL = 0.60
SUBJECT_FAIL = 0.70

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "what", "how", "why",
    "korea", "korean", "south", "2026", "2025", "explained", "guide", "you",
    "are", "was", "were", "has", "have", "not", "but", "its", "it's", "into",
    "than", "then", "which", "their", "there", "about", "will", "would", "can",
}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(w) > 2 and w not in STOP]


def _shingles(text: str, n: int = SHINGLE) -> set[str]:
    w = _words(text)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(POSTS, "*.md"))):
        raw = open(path, encoding="utf-8").read()
        if not raw.startswith("---"):
            continue
        _, fm, body = raw.split("---", 2)
        try:
            meta = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            continue
        if meta.get("draft"):
            continue
        subject = {str(t).lower() for t in (meta.get("tags") or [])}
        subject |= {str(t).lower() for t in (meta.get("about") or [])}
        out.append({
            "file": os.path.basename(path),
            "slug": meta.get("slug", ""),
            "title": meta.get("title", ""),
            "date": str(meta.get("date", "")),
            "supersedes": meta.get("supersedes"),
            "title_words": set(_words(meta.get("title", ""))),
            "subject": subject,
            "body": _shingles(body),
        })
    return out


def compare(a: dict, b: dict) -> tuple[float, float, float]:
    return (_jaccard(a["body"], b["body"]),
            _jaccard(a["title_words"], b["title_words"]),
            _jaccard(a["subject"], b["subject"]))


def check() -> tuple[list[str], list[str]]:
    posts = load()
    errors: list[str] = []
    warnings: list[str] = []

    for i, a in enumerate(posts):
        for b in posts[i + 1:]:
            # an explicit replacement is not a duplicate
            if a.get("supersedes") == b["slug"] or b.get("supersedes") == a["slug"]:
                continue

            body, title, subject = compare(a, b)
            reasons = []
            if body >= BODY_FAIL:
                reasons.append(f"{body:.0%} of phrasing shared")
            if title >= TITLE_FAIL:
                reasons.append(f"{title:.0%} of headline words shared")
            if subject >= SUBJECT_FAIL and body >= BODY_WARN:
                reasons.append(f"{subject:.0%} of tags shared with {body:.0%} phrasing overlap")

            if reasons:
                errors.append(
                    f"{a['file']} and {b['file']} look like the same article "
                    f"({'; '.join(reasons)}). Update the earlier one in place, or "
                    f"set `supersedes: {b['slug']}` if this deliberately replaces it.")
            elif body >= BODY_WARN or (subject >= SUBJECT_FAIL):
                warnings.append(
                    f"{a['file']} and {b['file']} are close "
                    f"(phrasing {body:.0%}, tags {subject:.0%}) — make sure this one "
                    "says something the other did not.")
    return errors, warnings


def topic_index() -> str:
    """A compact list of what has already been published, for the writer to read."""
    lines = ["# Topics already published", "",
             "Read this before choosing today's story. Do not re-cover any of these;",
             "either write something new or update the existing article in place.", ""]
    for p in sorted(load(), key=lambda x: x["date"], reverse=True):
        tags = ", ".join(sorted(p["subject"])[:6])
        lines.append(f"- **{p['date']}** — {p['title']}  \n  `{p['slug']}` · {tags}")
    return "\n".join(lines) + "\n"


def main() -> int:
    errors, warnings = check()
    posts = load()
    print(f"dedupe: compared {len(posts)} post(s), "
          f"{len(posts) * (len(posts) - 1) // 2} pair(s)")
    for w in warnings:
        print(f"  warn: {w}")
    if errors:
        print(f"\n✗ {len(errors)} duplicate topic(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("✓ no duplicate topics")
    return 0


if __name__ == "__main__":
    if "--index" in sys.argv:
        print(topic_index())
        sys.exit(0)
    sys.exit(main())
