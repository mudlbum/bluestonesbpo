#!/usr/bin/env python3
"""
Fact-check gate for Bluestones BPO.

Every quotable statistic must be traceable to a named primary source that was
alive when the post was built. This module is the machine-readable half of the
editorial standard described in CLAUDE.md — validate.py calls it, and a failure
here fails the deploy.

Schema
------
sources:                      # >= MIN_SOURCES entries, ordered; cited by 1-based index
  - title: "..."              # required
    url: "https://..."        # required, absolute http(s)
    publisher: "..."          # required — who published it, not where you found it
    accessed: 2026-08-12      # required — the date the figure was read off the source
    primary: true             # optional; see MIN_PRIMARY below

key_takeaways:                # each item a mapping (legacy plain strings are rejected)
  - text: "The KOSPI rose **92%** in H1 2026."
    source: 2                 # int, or list of ints, indexing `sources`

Rules enforced
--------------
1.  Every takeaway carries at least one source index, and every index resolves.
2.  Most takeaways state a figure — a **bolded** span containing a number, in
    digits or words. Not every one: some key facts are genuinely qualitative
    ("Samsung has no US-listed ADR"), and forcing a number into those would mean
    inventing one. MIN_QUANTIFIED sets the required share.
3.  Every source has title, url, publisher and an `accessed` date that is not in
    the future and not older than MAX_SOURCE_AGE_DAYS relative to the post date.
4.  At least MIN_PRIMARY sources are marked `primary: true` — a government
    statistics office, central bank, exchange, regulator or company filing.
    News coverage corroborates; it does not substitute.
5.  Source URLs resolve (network check; see check_urls). WARNING only — see the
    note in check_urls for why an unreachable third-party URL does not fail a build.

Run standalone for a report:  python3 scripts/factcheck.py [--offline]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import glob
import os
import re
import sys
import urllib.error
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "content", "posts")

MIN_SOURCES = 3
MIN_PRIMARY = 1
MAX_SOURCE_AGE_DAYS = 400
MIN_QUANTIFIED = 0.6   # share of takeaways that must carry a figure
URL_TIMEOUT = 12
USER_AGENT = "bluestonesbpo-linkcheck/1.0 (+https://www.bluestonesbpo.co.kr/)"

# Seoul time, not the machine's time.
#
# The publication operates on KST and dates its figures in KST. CI runners are on
# UTC, which is nine hours behind — so for the first nine hours of every Korean
# day, a post written today looks like it was accessed "in the future" to a UTC
# runner and the build fails. The daily publishing task runs at 09:00 KST, which
# lands squarely inside that window, so this would have broken every single
# scheduled post rather than being an occasional edge case.
KST = dt.timezone(dt.timedelta(hours=9))


def today() -> dt.date:
    """The current date in the publication's own timezone."""
    return dt.datetime.now(KST).date()

# A "figure" is a bolded span containing a digit, or a bolded span containing a
# number written as a word. Both are quantitative claims; only the typography differs.
NUMBER_WORDS = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                r"dozen|half|third|quarter|double|triple|record|first|second|no\b")
FIGURE = re.compile(r"\*\*[^*]*(?:\d|" + NUMBER_WORDS + r")[^*]*\*\*", re.I)
ABSOLUTE = re.compile(r"^https?://", re.I)


class Finding:
    __slots__ = ("post", "message", "fatal")

    def __init__(self, post: str, message: str, fatal: bool = True):
        self.post, self.message, self.fatal = post, message, fatal

    def __str__(self) -> str:
        return f"{self.post}: {self.message}"


def load_posts() -> list[tuple[str, dict]]:
    """Return (filename, front-matter) for every non-draft post."""
    out = []
    for path in sorted(glob.glob(os.path.join(POSTS, "*.md"))):
        raw = open(path, encoding="utf-8").read()
        if not raw.startswith("---"):
            continue
        _, fm, _ = raw.split("---", 2)
        try:
            meta = yaml.safe_load(fm) or {}
        except yaml.YAMLError as e:
            out.append((os.path.basename(path), {"__yaml_error__": str(e)}))
            continue
        if meta.get("draft"):
            continue
        out.append((os.path.basename(path), meta))
    return out


def _as_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def check_structure(name: str, meta: dict) -> list[Finding]:
    """Everything checkable without touching the network."""
    f: list[Finding] = []

    if "__yaml_error__" in meta:
        return [Finding(name, f"front matter is not valid YAML — {meta['__yaml_error__']}")]

    sources = meta.get("sources") or []
    takeaways = meta.get("key_takeaways") or []
    post_date = _as_date(meta.get("date")) or today()

    if len(sources) < MIN_SOURCES:
        f.append(Finding(name, f"only {len(sources)} source(s) — at least {MIN_SOURCES} required"))

    primaries = 0
    for i, s in enumerate(sources, start=1):
        if not isinstance(s, dict):
            f.append(Finding(name, f"source [{i}] is not a mapping"))
            continue
        for field in ("title", "url", "publisher"):
            if not str(s.get(field) or "").strip():
                f.append(Finding(name, f"source [{i}] has no {field}"))
        url = str(s.get("url") or "")
        if url and not ABSOLUTE.match(url):
            f.append(Finding(name, f"source [{i}] url is not absolute http(s): {url!r}"))

        accessed = _as_date(s.get("accessed"))
        if accessed is None:
            f.append(Finding(name, f"source [{i}] has no valid `accessed` date (YYYY-MM-DD)"))
        else:
            if accessed > today():
                f.append(Finding(name, f"source [{i}] `accessed` is in the future ({accessed})"))
            age = (post_date - accessed).days
            if age > MAX_SOURCE_AGE_DAYS:
                f.append(Finding(
                    name,
                    f"source [{i}] was accessed {age} days before the post date — "
                    f"re-verify it or drop it (limit {MAX_SOURCE_AGE_DAYS})"))
        if s.get("primary"):
            primaries += 1

    quantified = sum(1 for item in takeaways
                     if isinstance(item, dict) and FIGURE.search(str(item.get("text") or "")))
    if takeaways and quantified < max(2, round(len(takeaways) * MIN_QUANTIFIED)):
        f.append(Finding(
            name,
            f"only {quantified} of {len(takeaways)} takeaways state a figure. The takeaways "
            "block is what answer engines quote, so most of it should be quantitative — "
            f"at least {MIN_QUANTIFIED:.0%} of entries."))

    if sources and primaries < MIN_PRIMARY:
        f.append(Finding(
            name,
            f"{primaries} source(s) marked `primary: true` — at least {MIN_PRIMARY} required. "
            "Mark the statistics office, central bank, exchange, regulator or filing you "
            "actually read the figure off."))

    if not takeaways:
        f.append(Finding(name, "no key_takeaways block"))

    for n, item in enumerate(takeaways, start=1):
        label = f"key_takeaway [{n}]"
        if isinstance(item, str):
            f.append(Finding(
                name,
                f"{label} is a bare string. Use `- text: \"...\"` with `source: <n>` so the "
                "figure is traceable."))
            continue
        if not isinstance(item, dict):
            f.append(Finding(name, f"{label} is not a mapping"))
            continue

        text = str(item.get("text") or "").strip()
        if not text:
            f.append(Finding(name, f"{label} has no text"))
            continue
        # Figure counting happens after the loop — see below. Requiring a number in
        # *every* takeaway was too rigid: "Samsung has no US-listed ADR" is a key
        # fact with no figure in it, and forcing one would mean inventing one.

        refs = item.get("source")
        refs = [] if refs is None else (refs if isinstance(refs, list) else [refs])
        if not refs:
            f.append(Finding(name, f"{label} cites no source"))
        for r in refs:
            if not isinstance(r, int):
                f.append(Finding(name, f"{label} source {r!r} is not an integer index"))
            elif not (1 <= r <= len(sources)):
                f.append(Finding(
                    name, f"{label} cites source [{r}] but only {len(sources)} source(s) exist"))

    return f


def _probe(url: str) -> tuple[str, int | str]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as r:
            return url, r.status
    except urllib.error.HTTPError as e:
        if e.code in (403, 405, 501):          # server dislikes HEAD, not necessarily dead
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as r:
                    return url, r.status
            except Exception as e2:             # noqa: BLE001
                return url, f"{type(e2).__name__}: {e2}"
        return url, e.code
    except Exception as e:                      # noqa: BLE001
        return url, f"{type(e).__name__}: {e}"


def online() -> bool:
    try:
        urllib.request.urlopen(
            urllib.request.Request("https://api.github.com/", method="HEAD",
                                   headers={"User-Agent": USER_AGENT}), timeout=8)
        return True
    except Exception:                           # noqa: BLE001
        return False


def check_urls(posts: list[tuple[str, dict]]) -> list[Finding]:
    """Confirm every cited URL still resolves. Requires network.

    These findings are reported as WARNINGS, not build failures — deliberately,
    and this is a correction of an earlier decision here.

    Whether a GitHub runner in a datacenter can reach moel.go.kr or nts.go.kr on a
    given morning is not a property of the article's quality. Korean government
    hosts throttle and block foreign datacenter ranges, serve different responses
    to session-less requests, and go down for maintenance. Failing the deploy on
    that means a correct, properly sourced article does not publish because a
    ministry web server had an opinion about the runner's IP — and since the
    daily loop cites those same hosts every day, it would stall permanently.

    The structural requirements in check_structure stay hard failures: a missing
    source, no primary, an uncited figure or a nonsense access date are all
    defects in the writing, and those are exactly what the gate should stop.
    A dead link is worth knowing about at the next build; it is not worth
    blocking a correct article.
    """
    jobs: dict[str, list[tuple[str, int]]] = {}
    for name, meta in posts.items() if isinstance(posts, dict) else posts:
        for i, s in enumerate(meta.get("sources") or [], start=1):
            if isinstance(s, dict) and ABSOLUTE.match(str(s.get("url") or "")):
                jobs.setdefault(s["url"], []).append((name, i))

    findings: list[Finding] = []
    if not jobs:
        return findings
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for url, status in pool.map(_probe, jobs):
            ok = isinstance(status, int) and status < 400
            if not ok:
                for name, idx in jobs[url]:
                    findings.append(Finding(
                        name, f"source [{idx}] did not resolve ({status}) — {url}. "
                              "Check it by hand; this does not block the build.",
                        fatal=False))
    return findings


def enforce_from() -> dt.date:
    """
    The date the sourcing standard takes effect.

    Posts published before it predate the schema. They are reported as warnings
    rather than errors so the live site keeps building, but they are not exempt
    from the standard — they need retro-sourcing by hand. Set
    `factcheck.enforce_from` in site.config.json.
    """
    import json
    cfg = json.load(open(os.path.join(ROOT, "site.config.json"), encoding="utf-8"))
    raw = (cfg.get("factcheck") or {}).get("enforce_from")
    return _as_date(raw) or dt.date.min


def run(offline: bool = False) -> tuple[list[Finding], list[Finding]]:
    """Return (errors, warnings). Warnings are pre-cutoff posts."""
    posts = load_posts()
    cutoff = enforce_from()
    findings: list[Finding] = []
    legacy: list[Finding] = []
    for name, meta in posts:
        found = check_structure(name, meta)
        post_date = _as_date(meta.get("date")) or today()
        (legacy if post_date < cutoff else findings).extend(found)

    if offline:
        print("  note: --offline set, skipping source URL liveness checks")
    elif not online():
        print("  note: no network available, skipping source URL liveness checks")
    else:
        current = {n for n, m in posts if (_as_date(m.get("date")) or today()) >= cutoff}
        for f in check_urls(posts):
            # Non-fatal findings are warnings whatever the post's date.
            if not f.fatal:
                legacy.append(f)
            else:
                (findings if f.post in current else legacy).append(f)
    return findings, legacy


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify every published figure is sourced.")
    ap.add_argument("--offline", action="store_true", help="skip URL liveness checks")
    args = ap.parse_args()

    findings, legacy = run(offline=args.offline)
    print(f"fact-check: {len(load_posts())} post(s), standard in force from {enforce_from()}")
    if legacy:
        by_post: dict[str, int] = {}
        for f in legacy:
            by_post[f.post] = by_post.get(f.post, 0) + 1
        print(f"\n  {len(legacy)} finding(s) on {len(by_post)} pre-cutoff post(s) "
              f"— not blocking, but these need retro-sourcing:")
        for post, count in sorted(by_post.items()):
            print(f"    · {post}: {count}")
    if findings:
        print(f"\n✗ {len(findings)} problem(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("\n✓ every figure published under the standard is sourced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
