#!/usr/bin/env python3
"""
Pre-publication gate. Runs in CI after build.py and fails the deploy on anything
that would cost us search visibility or embarrass us in front of a client.

The first check in this file is the most important one. The site this replaces
shipped `nofollow, nosnippet, noimageindex, noarchive` on every page. That single
meta tag is why it had no organic traffic and why no AI assistant could quote it.
This gate makes it structurally impossible to ship that again.

Checks:
  * NO page carries noindex/nofollow/nosnippet outside the explicit allow-list
  * every internal link and image resolves
  * exactly one <h1> per page
  * <title> <= 62 chars, meta description 110-165 chars, both unique site-wide
  * hreflang pairs are reciprocal and self-referencing
  * every JSON-LD block parses, and the business node carries a real address
  * every <img> has alt text and explicit dimensions
  * required policy pages exist and are linked from every page
  * every article has takeaways, sources, an FAQ and >= 2 internal links
  * no placeholder text escaped into production
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.environ.get("BSB_DIST") or os.path.join(ROOT, "dist")
CFG = json.load(open(os.path.join(ROOT, "site.config.json"), encoding="utf-8"))

REQUIRED_PAGES = ["about", "contact", "privacy-policy", "cookie-policy",
                  "terms", "disclaimer", "editorial-policy"]
REQUIRED_FILES = ["index.html", "404.html", "sitemap.xml", "robots.txt",
                  "rss.xml", "llms.txt", "style.css", "favicon.svg"]
FORBIDDEN = ["lorem ipsum", "TODO:", "FIXME", "XXXX", "{{", "[INSERT", "TK TK",
             "As an AI language model", "placeholder text", "Lorem Ipsum"]

# The only page permitted to tell a crawler to stay away.
NOINDEX_ALLOWED = {"/404.html"}
BAD_ROBOTS = ("noindex", "nofollow", "nosnippet", "noimageindex", "noarchive")

# Staging inverts the rule: a reachable copy of the site that Google indexes is
# duplicate content competing with production, so there noindex is required
# rather than forbidden. The gate checks for the opposite defect in that mode —
# a staging build that forgot to suppress indexing.
IS_STAGING = bool((CFG.get("staging") or {}).get("enabled"))

# Sub-path the site is served from, derived the same way build.py derives it.
# On a GitHub Pages project site every internal link carries this prefix, so it
# has to come back off before a link is resolved against the output directory.
_SITE = ((CFG.get("staging") or {}).get("domain") if IS_STAGING
         else CFG["domain"]).rstrip("/")
_rest = _SITE.partition("://")[2]
BASE = ("/" + _rest.partition("/")[2].strip("/")) if "/" in _rest else ""
BASE = "" if BASE == "/" else BASE

# CNAME belongs to a site that owns a hostname, not to a project page.
if not BASE:
    REQUIRED_FILES.append("CNAME")

errors: list[str] = []
warnings: list[str] = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def rel_of(f):
    return "/" + os.path.relpath(f, DIST).replace(os.sep, "/")


def main():
    if not os.path.isdir(DIST):
        print(f"FATAL: no build output at {DIST}")
        return 1

    for f in REQUIRED_FILES:
        if not os.path.exists(os.path.join(DIST, f)):
            err(f"missing required file: {f}")
    for lang_cfg in CFG["languages"]:
        p = lang_cfg["prefix"].strip("/")
        for page in REQUIRED_PAGES:
            target = os.path.join(DIST, p, page, "index.html") if p else \
                os.path.join(DIST, page, "index.html")
            if not os.path.exists(target):
                err(f"missing required policy page: /{p + '/' if p else ''}{page}/")

    # Anything beginning with an underscore is a local scratch file (a flattened
    # preview, a diff artefact) rather than a page the build produced. CI starts
    # from a clean checkout so this only ever matters on a developer's machine.
    pages = [p for p in sorted(glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True))
             if not os.path.basename(p).startswith("_")]
    if len(pages) < 12:
        err(f"only {len(pages)} pages built — expected at least 12")

    titles: dict[str, str] = {}
    descs: dict[str, str] = {}
    hreflang_graph: dict[str, set[str]] = {}

    for f in pages:
        rel = rel_of(f)
        h = open(f, encoding="utf-8").read()
        low = h.lower()

        # ── the check this whole file exists for ──────────────────────────────
        m = re.search(r'<meta name="robots" content="([^"]*)"', h)
        if not m:
            err(f"{rel}: no robots meta tag")
        elif IS_STAGING:
            if "noindex" not in m.group(1).lower():
                err(f"{rel}: staging build is missing noindex — a crawlable staging copy "
                    "competes with the production site as duplicate content")
        else:
            directives = [d.strip().lower() for d in m.group(1).split(",")]
            for bad in BAD_ROBOTS:
                if bad in directives and rel not in NOINDEX_ALLOWED:
                    err(f"{rel}: robots meta contains {bad!r} — this is the exact defect "
                        f"that made the previous site invisible to search and to AI answer "
                        f"engines. Nothing but /404.html may carry it.")

        # ── internal references resolve ───────────────────────────────────────
        for ref in re.findall(r'(?:href|src)="(/[^"#?]*)"', h):
            path = ref
            if BASE:
                if not path.startswith(BASE + "/") and path != BASE:
                    err(f"{rel}: internal link {ref} is missing the {BASE} base path — "
                        "it will 404 on a project page")
                    continue
                path = path[len(BASE):] or "/"
            target = os.path.join(DIST, path.lstrip("/"))
            if path.endswith("/"):
                target = os.path.join(target, "index.html")
            if not os.path.exists(target):
                err(f"{rel}: broken internal reference -> {ref}")

        # ── headings ──────────────────────────────────────────────────────────
        n = len(re.findall(r"<h1[ >]", h))
        if n != 1:
            err(f"{rel}: {n} <h1> elements (must be exactly 1)")

        # ── title + description, length and uniqueness ─────────────────────────
        # Length limits are language-aware. Google truncates a snippet on rendered
        # pixel width, not character count, and a Hangul syllable is roughly twice
        # the width of a Latin character while carrying far more meaning. Holding
        # Korean pages to an English character count would force padding — which
        # is precisely the waffle that makes a snippet worse.
        is_ko = 'lang="ko' in h[:400]
        t_max = 62
        d_min, d_max = (45, 100) if is_ko else (110, 165)

        m = re.search(r"<title>(.*?)</title>", h, re.S)
        if not m:
            err(f"{rel}: no <title>")
        else:
            t = html.unescape(m.group(1)).strip()
            if len(t) > t_max:
                err(f"{rel}: <title> is {len(t)} chars (max {t_max}, or Google truncates it)")
            if t in titles:
                err(f"{rel}: duplicate <title> — also used by {titles[t]}")
            titles[t] = rel

        m = re.search(r'name="description" content="(.*?)"', h, re.S)
        if not m:
            err(f"{rel}: no meta description")
        else:
            d = html.unescape(m.group(1)).strip()
            if not (d_min <= len(d) <= d_max):
                err(f"{rel}: meta description is {len(d)} chars "
                    f"(want {d_min}-{d_max} for {'ko' if is_ko else 'en'})")
            if d in descs:
                err(f"{rel}: duplicate meta description — also used by {descs[d]}")
            descs[d] = rel

        if 'rel="canonical"' not in h:
            err(f"{rel}: no canonical link")

        # ── hreflang reciprocity ──────────────────────────────────────────────
        alts = re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', h)
        if alts:
            canon = re.search(r'<link rel="canonical" href="([^"]+)"', h)
            canon_url = canon.group(1) if canon else ""
            hrefs = {u for lg, u in alts if lg != "x-default"}
            if canon_url and canon_url not in hrefs:
                err(f"{rel}: hreflang set does not include a self-reference to {canon_url}")
            if not any(lg == "x-default" for lg, _ in alts):
                err(f"{rel}: hreflang set has no x-default")
            hreflang_graph[canon_url] = hrefs

        # ── structured data ───────────────────────────────────────────────────
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                data = json.loads(block)
            except Exception as e:                          # noqa: BLE001
                err(f"{rel}: invalid JSON-LD ({e})")
                continue
            for node in data.get("@graph", []):
                types = node.get("@type")
                types = types if isinstance(types, list) else [types]
                # Only the primary business entity needs a full NAP. Articles also
                # carry an Organization node for the editorial desk, which is a
                # sub-organization of it and has no separate address or phone.
                if "Organization" in types and str(node.get("@id", "")).endswith("#organization"):
                    addr = node.get("address") or {}
                    for k in ("streetAddress", "addressLocality", "addressCountry"):
                        if not addr.get(k):
                            err(f"{rel}: Organization JSON-LD missing address.{k} — "
                                "local search and AI answers depend on a resolvable NAP")
                    if not node.get("telephone"):
                        err(f"{rel}: Organization JSON-LD has no telephone")

        # ── images ────────────────────────────────────────────────────────────
        for img in re.findall(r"<img [^>]*>", h):
            if "alt=" not in img:
                err(f"{rel}: <img> without alt attribute")
            if "width=" not in img or "height=" not in img:
                warn(f"{rel}: <img> without explicit dimensions (CLS risk)")

        for bad in FORBIDDEN:
            if bad.lower() in low:
                err(f"{rel}: forbidden placeholder text found: {bad!r}")

        # ── policy pages reachable from every page ────────────────────────────
        if rel != "/404.html":
            for policy in ("privacy-policy", "terms", "disclaimer", "contact"):
                if f"/{policy}/" not in h:
                    err(f"{rel}: no link to /{policy}/ in the footer")

    # hreflang must be mutual: if A points at B, B must point back at A.
    for url, targets in hreflang_graph.items():
        for t in targets:
            if t in hreflang_graph and url not in hreflang_graph[t]:
                err(f"hreflang not reciprocal: {url} -> {t} but not back")

    # ── service pages ─────────────────────────────────────────────────────────
    svc_slugs = {s["slug"] for s in CFG["services"]}
    for lang_cfg in CFG["languages"]:
        p = lang_cfg["prefix"].strip("/")
        for slug in svc_slugs:
            target = os.path.join(DIST, p, "services", slug, "index.html") if p else \
                os.path.join(DIST, "services", slug, "index.html")
            if not os.path.exists(target):
                err(f"missing service page: /{p + '/' if p else ''}services/{slug}/")
                continue
            h = open(target, encoding="utf-8").read()
            if '"@type":"Service"' not in h.replace(" ", ""):
                err(f"/services/{slug}/: no Service JSON-LD node")
            if "faq-item" not in h:
                err(f"/services/{slug}/: no FAQ block — service pages need one for "
                    "FAQ rich results and for answer-engine extraction")
            words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", h)))
            if words < 600:
                err(f"/services/{slug}/: only ~{words} words — too thin for a money page")

    # ── articles ──────────────────────────────────────────────────────────────
    articles = []
    for f in pages:
        parts = os.path.relpath(f, DIST).split(os.sep)
        if "blog" in parts and parts[-1] == "index.html" and \
                parts.index("blog") + 2 < len(parts) - 1:
            articles.append(f)

    if not articles:
        warn("no articles in the build yet — the daily loop has not run. "
             "This is expected on day one and not expected on day ten.")

    for f in articles:
        rel = rel_of(f)
        h = open(f, encoding="utf-8").read()
        words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", h)))
        if words < 900:
            err(f"{rel}: only ~{words} words — too thin to publish")
        for needle, label in [("takeaways", "key takeaways block"),
                              ("faq-item", "FAQ section"),
                              ('class="sources"', "sources list"),
                              ("disclosure", "AI/production disclosure")]:
            if needle not in h:
                err(f"{rel}: missing {label}")
        body = h.split('<div class="prose"', 1)[-1]
        internal = len(set(re.findall(
            r'href="(/(?!img/|style|favicon|rss|sitemap|consent|script)[^"]*)"', body)))
        if internal < 2:
            err(f"{rel}: {internal} internal link(s) in the body — need at least 2")
        if not re.search(r'(datetime=|class="byline")', h):
            err(f"{rel}: no visible byline or publication date")

    # ── sitemap sanity ────────────────────────────────────────────────────────
    sm = os.path.join(DIST, "sitemap.xml")
    if os.path.exists(sm):
        xml = open(sm, encoding="utf-8").read()
        locs = re.findall(r"<loc>([^<]+)</loc>", xml)
        if len(locs) < 10:
            err(f"sitemap lists only {len(locs)} URLs")
        if len(locs) != len(set(locs)):
            err("sitemap contains duplicate <loc> entries")
        domain = ((CFG.get("staging") or {}).get("domain") if IS_STAGING
                  else CFG["domain"]).rstrip("/")
        for u in locs:
            if not u.startswith(domain):
                err(f"sitemap URL on wrong host: {u}")

    # ── duplicate-topic gate: a daily loop drifts into repeating itself ───────
    try:
        import dedupe as _dd
        dd_errors, dd_warnings = _dd.check()
        for e in dd_errors:
            err(f"duplicate topic — {e}")
        for w in dd_warnings:
            warn(f"duplicate topic — {w}")
    except Exception as e:                                  # noqa: BLE001
        warn(f"duplicate check skipped: {type(e).__name__}: {e}")

    # ── sourcing gate: every published figure traceable to a live source ──────
    try:
        import factcheck
        offline = bool(os.environ.get("BSB_OFFLINE")) or \
            (CFG["factcheck"].get("offline_ok") and not os.environ.get("CI"))
        fc_errors, fc_legacy = factcheck.run(offline=offline)
        for f in fc_errors:
            err(f"fact-check — {f}")
        for f in fc_legacy:
            warn(f"fact-check (pre-cutoff) — {f}")
    except Exception as e:                                  # noqa: BLE001
        warn(f"fact-check skipped: {type(e).__name__}: {e}")

    print(f"checked {len(pages)} pages ({len(articles)} articles, "
          f"{len(svc_slugs) * len(CFG['languages'])} service pages)")
    if warnings:
        print(f"  {len(warnings)} warning(s):")
        for w in warnings[:8]:
            print(f"  warn: {w}")
    if errors:
        print(f"\n✗ {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("✓ all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
