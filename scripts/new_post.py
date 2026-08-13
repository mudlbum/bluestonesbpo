#!/usr/bin/env python3
"""
Scaffold a correctly-shaped post.

    python3 scripts/new_post.py "Do you pay severance if an employee resigns?" \
        --category payroll --services payroll-outsourcing

Writes content/posts/YYYY-MM-DD-slug.md with front matter the build and the
validation gate both expect. Pass --ko to also scaffold the Korean counterpart
with the same basename, which is what pairs them for hreflang.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "site.config.json"), encoding="utf-8"))
CATS = [c["slug"] for c in CFG["categories"]]
SVCS = [s["slug"] for s in CFG["services"]]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:70].strip("-")


TEMPLATE = """---
title: "{title}"
slug: {slug}
seo_title: "TK — under 45 chars, primary keyword first"
meta: "TK — {dmin}-{dmax} chars. Primary keyword plus a reason to click. No ellipsis."
category: {category}
date: {date}
updated: {date}
description: "TK — the on-page standfirst. One or two sentences, plain."
image_alt: "TK — describe the generated artwork for a screen reader"
tags: [tk, tk, tk, tk, tk]
about: ["TK — authorities, statutes or institutions named in the article"]
services: [{services}]

# 4-6 items. Each MUST contain a bolded figure and cite a source index.
# These are what an AI answer engine quotes verbatim — write them to stand alone.
key_takeaways:
  - text: "TK — lead with the number. **Bold the figure.** State the period."
    source: 1

faq:
  - q: "TK — a question someone would actually type"
    a: "TK — a complete answer in 2-5 sentences."
  - q: "TK"
    a: "TK"
  - q: "TK"
    a: "TK"
  - q: "TK"
    a: "TK"
  - q: "TK"
    a: "TK"

resources:
  - title: "TK — portal name"
    url: "https://"
    note: "TK — what it is and why you would open it"

# At least 3 sources, at least 1 primary. Every URL is fetched in CI.
sources:
  - title: "TK"
    url: "https://"
    publisher: "TK"
    accessed: {date}
    primary: true
---

## TK — an H2 that is a question or a claim, not a label

Lead with the answer. Not with context, not with "Korea is a dynamic market". State the
answer in the first two sentences, then explain the mechanism, then say what to do.

> [!KEY] TK — the number that matters, with its period

## TK

Use a table for anything comparative. Tables win featured snippets and are clearer.

| TK | TK |
| --- | --- |
| TK | TK |

> [!DEADLINE] TK — a date the reader must not miss

## TK

Link to the relevant service page in context with descriptive anchor text — for example,
[payroll outsourcing](/services/payroll-outsourcing/) — and to one or two related articles.

> [!ACTION] TK — a checklist the reader can act on
> - TK
> - TK

*Figures current as at {pretty}. Korean rates and thresholds are revised regularly — each is
linked to the authority it was read from above.*
"""

KO_TEMPLATE = """---
title: "TK — 한국어 제목 (번역이 아니라 한국어로 새로 작성)"
slug: {slug}-ko
seo_title: "TK — 45자 이내"
meta: "TK — 45-100자. 핵심 키워드와 클릭할 이유."
category: {category}
date: {date}
updated: {date}
description: "TK — 한 두 문장의 요약."
image_alt: "TK"
tags: [tk, tk, tk]
about: ["TK"]
services: [{services}]
key_takeaways:
  - text: "TK — 숫자를 앞세우고 **굵게** 표시하며 기준 시점을 밝힙니다."
    source: 1
faq:
  - q: "TK"
    a: "TK"
sources:
  - title: "TK"
    url: "https://"
    publisher: "TK"
    accessed: {date}
    primary: true
---

## TK

한국어 판본은 번역이 아니라 한국어로 작성합니다. 한국 실무자가 실제로 쓰는 용어를
사용하십시오 — 기장, 원천징수, 4대보험, 연말정산.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("--category", default="payroll", choices=CATS)
    ap.add_argument("--services", default="", help="comma-separated service slugs")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--ko", action="store_true", help="also scaffold the Korean counterpart")
    a = ap.parse_args()

    services = [s.strip() for s in a.services.split(",") if s.strip()]
    for s in services:
        if s not in SVCS:
            print(f"unknown service {s!r}; known: {', '.join(SVCS)}")
            return 1

    slug = slugify(a.title)
    base = f"{a.date}-{slug}"
    d = dt.date.fromisoformat(a.date)
    body = TEMPLATE.format(
        title=a.title.replace('"', "'"), slug=slug, category=a.category, date=a.date,
        services=", ".join(services), dmin=110, dmax=165,
        pretty=d.strftime("%d %B %Y").lstrip("0"))

    path = os.path.join(ROOT, "content", "posts", base + ".md")
    if os.path.exists(path):
        print(f"already exists: {path}")
        return 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(body)
    print(f"→ {os.path.relpath(path, ROOT)}")

    if a.ko:
        kpath = os.path.join(ROOT, "content", "posts", "ko", base + ".md")
        os.makedirs(os.path.dirname(kpath), exist_ok=True)
        open(kpath, "w", encoding="utf-8").write(KO_TEMPLATE.format(
            slug=slug, category=a.category, date=a.date, services=", ".join(services)))
        print(f"→ {os.path.relpath(kpath, ROOT)}  (same basename = paired for hreflang)")

    print("\nEvery TK must be replaced. validate.py fails on placeholder text,")
    print("on an unsourced figure, and on a takeaway without a bolded number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
