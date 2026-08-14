#!/usr/bin/env python3
"""
Bluestones BPO — static site generator.

    python3 build.py            # build into dist/
    python3 build.py --serve    # build, then serve dist/ on :8000

Design goals, in order:

  1. Findable. Every page ships a unique title, a unique meta description, a
     self-referencing canonical, reciprocal hreflang, and a JSON-LD graph that
     names the business, its address, its phone number and the specific service
     the page is about. The site this replaces shipped
     `nofollow, nosnippet, noimageindex, noarchive` on every URL — which is why
     it was invisible. Nothing here emits those, ever.

  2. Quotable (GEO). Answer engines cite pages that state a fact, date it, and
     name its source. So: key-takeaway blocks with per-figure citations, FAQ
     blocks that mirror real questions, comparison tables, dated figures, an
     llms.txt site map, and an explicit robots allow-list for the AI crawlers.

  3. Bilingual. English for the foreign parent company making the decision;
     Korean for Naver and for local searches. Reciprocal hreflang + x-default,
     never machine-duplicated content without a human pass.

  4. Fast. No framework, no web-font request, no render-blocking JS, explicit
     image dimensions, lazy loading below the fold. Core Web Vitals is a
     ranking input and a static file is unbeatable at it.

  5. Commercial. Every template routes to one action: book a consultation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
import unicodedata
from email.utils import format_datetime

import markdown
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import imagegen  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.environ.get("BSB_DIST") or os.path.join(ROOT, "dist")
CFG = json.load(open(os.path.join(ROOT, "site.config.json"), encoding="utf-8"))

# Staging mode. The site is reachable at a subdomain for review while the live
# domain still serves the old site. A crawlable copy of a site is duplicate
# content competing with the original, so staging is the single case where
# noindex is the correct answer rather than the defect this project exists to fix.
STAGING = CFG.get("staging") or {}
IS_STAGING = bool(STAGING.get("enabled"))
SITE = (STAGING.get("domain") if IS_STAGING else CFG["domain"]).rstrip("/")

# BASE is the sub-path the site is served from, empty when it sits at a domain
# root. A GitHub Pages project site lives at user.github.io/<repo>/, so every
# root-relative link ("/services/", "/style.css") would 404 there. Rather than
# thread a prefix through every template and every markdown link, the base is
# derived once from the domain and applied as a single rewrite in write(),
# which also catches links written by hand in content files.
_scheme, _, _rest = SITE.partition("://")
BASE = ("/" + _rest.partition("/")[2].strip("/")) if "/" in _rest else ""
BASE = "" if BASE == "/" else BASE

ROBOTS_DEFAULT = ("noindex,nofollow" if IS_STAGING else
                  "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1")

CATS = {c["slug"]: c for c in CFG["categories"]}
BIZ = CFG["business"]
BRAND = CFG["brand"]
LANGS = {l["code"]: l for l in CFG["languages"]}
DEFAULT_LANG = CFG["default_language"]


# ─────────────────────────────────────────────────────────── i18n strings ──
# Interface copy only. Article and service prose lives in content/, never here.
STR = {
    "en": {
        "skip": "Skip to content",
        "menu": "Open menu",
        "primary": "Primary",
        "home": "Home",
        "services": "Services",
        "insights": "Blog",
        "other_services": "Other services",
        "included": "What's included",
        "browse_topic": "Browse by topic",
        "more_articles": "More articles",
        "contact": "Contact",
        "about": "About",
        "cta": "Book a consultation",
        "cta_short": "Get a quote",
        "breadcrumb": "Breadcrumb",
        "on_this_page": "On this page",
        "takeaways": "Key takeaways",
        "faq": "Frequently asked questions",
        "sources": "Sources & further reading",
        "sources_note": ("Every figure in the key takeaways is numbered to the source it was read "
                         "from. Sources marked <span class=\"src-primary\">primary</span> are the "
                         "tax office, ministry, insurance authority or statute itself."),
        "resources": "Official portals & tools",
        "resources_note": "The government portals behind this topic. Opens in a new tab.",
        "read_next": "Read next",
        "published": "Published",
        "updated": "Updated",
        "min_read": "min read",
        "by": "By",
        "latest": "From the blog",
        "all_insights": "All articles",
        "no_posts": "No articles in this section yet.",
        "related_services": "How we help with this",
        "lang_switch": "한국어로 보기",
        "last_updated": "Last updated",
        "disclosure_h": "How this article was produced",
        "verified": "verified",
        "primary_tag": "primary",
        "sections": "Sections",
        "legal": "Legal",
        "company": "Company",
        "back_home": "Back to the front page",
        "form_name": "Your name",
        "form_company": "Company",
        "form_email": "Work email",
        "form_country": "Where is your head office?",
        "form_need": "What do you need help with?",
        "form_msg": "Tell us briefly what you need",
        "form_send": "Send enquiry",
        "form_privacy": "We use what you send only to answer your enquiry. See our privacy policy.",
    },
    "ko": {
        "skip": "본문으로 건너뛰기",
        "menu": "메뉴 열기",
        "primary": "주요 메뉴",
        "home": "홈",
        "services": "서비스",
        "insights": "블로그",
        "other_services": "다른 서비스",
        "included": "제공 범위",
        "browse_topic": "주제별로 보기",
        "more_articles": "다른 글",
        "contact": "문의",
        "about": "회사 소개",
        "cta": "상담 신청",
        "cta_short": "견적 문의",
        "breadcrumb": "탐색 경로",
        "on_this_page": "목차",
        "takeaways": "핵심 요약",
        "faq": "자주 묻는 질문",
        "sources": "출처 및 참고 자료",
        "sources_note": ("핵심 요약의 모든 수치에는 출처 번호가 붙어 있습니다. "
                         "<span class=\"src-primary\">1차</span> 표시는 국세청·고용노동부·"
                         "공단 또는 법령 원문임을 뜻합니다."),
        "resources": "공식 포털 및 자료",
        "resources_note": "이 주제와 관련된 정부 포털입니다. 새 탭에서 열립니다.",
        "read_next": "다음 읽을거리",
        "published": "발행",
        "updated": "수정",
        "min_read": "분 소요",
        "by": "작성",
        "latest": "블로그 최신 글",
        "all_insights": "전체 글 보기",
        "no_posts": "이 섹션에는 아직 글이 없습니다.",
        "related_services": "관련 서비스",
        "lang_switch": "View in English",
        "last_updated": "최종 수정",
        "disclosure_h": "이 글의 작성 방식",
        "verified": "확인일",
        "primary_tag": "1차",
        "sections": "섹션",
        "legal": "약관 및 정책",
        "company": "회사",
        "back_home": "첫 페이지로",
        "form_name": "성함",
        "form_company": "회사명",
        "form_email": "회사 이메일",
        "form_country": "본사 소재 국가",
        "form_need": "필요하신 서비스",
        "form_msg": "필요하신 내용을 간단히 적어 주세요",
        "form_send": "문의 보내기",
        "form_privacy": "보내주신 정보는 문의 답변에만 사용합니다. 개인정보처리방침을 참고하세요.",
    },
}


def T(lang: str, key: str) -> str:
    return STR.get(lang, STR[DEFAULT_LANG]).get(key, STR[DEFAULT_LANG].get(key, key))


# ───────────────────────────────────────────────────────────── home FAQ ──
# The questions an answer engine is actually asked about operating in Korea.
# Answered completely, on the page carrying the most entity signal, so that an
# assistant summarising "how do I run a company in Korea" has a citable source
# that names a firm. Kept free of annually-revised figures on purpose: the two
# numbers here (VAT rate, corporate tax deadline) are the stable ones. Anything
# that moves each year belongs in a dated article, not on an evergreen page.
HOME_FAQ = {
    "en": [
        {"q": "Can a foreign company hire employees in Korea without setting up an entity?",
         "a": "Not directly. Running a Korean payroll requires a registered Korean employer, "
              "which means either establishing an entity — usually a subsidiary — or using an "
              "employer-of-record arrangement in which a third party is the legal employer. "
              "The two are not equivalent: an employer-of-record limits your control over the "
              "employee and does not remove permanent establishment risk if the work being done "
              "in Korea is your core business. Which is right depends on how long you expect to "
              "be here and what the people will actually do."},
        {"q": "Should we set up a subsidiary, a branch, or a liaison office in Korea?",
         "a": "A **subsidiary** is a separate Korean company that can trade, invoice and hire "
              "freely, and it is the only one of the three eligible for foreign-invested company "
              "status. A **branch** is an extension of the foreign parent, taxed in Korea on "
              "Korean-source income, with liability sitting with the parent. A **liaison office** "
              "cannot conduct profit-making activity at all and may not issue invoices — it is "
              "for market research and liaison only. Most operating businesses need a subsidiary. "
              "See our [company registration guide](/services/company-registration/) for the "
              "full comparison."},
        {"q": "How often does a company in Korea have to file VAT and corporate tax?",
         "a": "Korea's VAT year is divided into two taxable periods, each carrying a preliminary "
              "and a final return, so a corporation files **four times a year** at the standard "
              "**10%** rate. The corporate income tax return is due within **three months** of "
              "the fiscal year end, with an interim return during the year. Payroll withholding "
              "is filed monthly, and there is an annual year-end settlement for every employee "
              "in February."},
        {"q": "What does outsourced accounting and payroll cost in Korea?",
         "a": "It scales with transaction volume, headcount and how much reporting your head "
              "office needs, so any figure quoted before those are known is a guess. What we "
              "can tell you quickly is what a compliant month looks like for an entity your "
              "size, which is usually the more useful number. Send us your last trial balance or "
              "VAT return and we will be specific in the first reply — no discovery call "
              "required."},
        {"q": "Do we need a Korean CPA, or is a bookkeeper enough?",
         "a": "Routine bookkeeping does not legally require a Korean Certified Public Accountant. "
              "Tax filings, statutory financial statements, and any position the National Tax "
              "Service might challenge are a different matter. Companies that split the work — a "
              "low-cost bookkeeper plus an occasional tax agent — tend to find the gap during an "
              "audit, when neither party owns the answer. A KICPA is involved in every engagement "
              "here for exactly that reason."},
        {"q": "How quickly can you take over from our current provider?",
         "a": "Usually within one filing cycle. We take the trial balance, supporting ledgers, "
              "fixed asset register, payroll registers and filing history, reconcile the opening "
              "position, and flag anything that does not tie. That reconciliation is the "
              "valuable part — it is often the first independent check anyone has run on the "
              "previous provider's closing balances. Expect the first month to involve more "
              "questions than a steady-state month."},
    ],
    "ko": [
        {"q": "한국 법인 없이 직원을 고용할 수 있나요?",
         "a": "직접 고용은 불가능합니다. 한국에서 급여를 지급하려면 등록된 한국 사용자가 필요하므로, "
              "법인을 설립하시거나 제3자가 법적 사용자가 되는 EOR 방식을 이용하셔야 합니다. 두 방식은 "
              "동등하지 않습니다. EOR은 직원에 대한 통제 범위가 제한되고, 한국에서 수행되는 업무가 "
              "본업에 해당한다면 고정사업장 위험이 사라지지도 않습니다. 체류 기간과 실제 수행 업무에 "
              "따라 적합한 선택이 달라집니다."},
        {"q": "현지법인, 지점, 연락사무소 중 무엇을 선택해야 하나요?",
         "a": "**현지법인**은 독립된 한국 회사로 영업·세금계산서 발행·채용이 자유롭고, 셋 중 유일하게 "
              "외국인투자기업 지위를 받을 수 있습니다. **지점**은 본사의 연장으로 국내원천소득에 "
              "과세되며 책임은 본사가 집니다. **연락사무소**는 영리 활동을 할 수 없고 세금계산서도 "
              "발행할 수 없어 시장조사와 연락 업무에만 사용됩니다. 실제 영업을 하는 기업에는 대부분 "
              "현지법인이 필요합니다. 자세한 비교는 "
              "[법인 설립](/ko/services/company-registration/) 페이지를 참고하십시오."},
        {"q": "한국 법인은 부가세와 법인세를 얼마나 자주 신고하나요?",
         "a": "부가가치세 과세기간은 두 기간으로 나뉘고 각각 예정·확정 신고가 있어 법인은 연 **4회** "
              "신고하며, 표준세율은 **10퍼센트**입니다. 법인세는 사업연도 종료일부터 **3개월** 이내에 "
              "신고하고 사업연도 중 중간예납이 있습니다. 근로소득 원천세는 매월 신고하며, 매년 2월에 "
              "전 직원 연말정산이 있습니다."},
        {"q": "회계·급여 아웃소싱 비용은 어느 정도인가요?",
         "a": "거래 건수, 인원, 본사 보고 요구 수준에 따라 달라지므로 이를 모른 채 제시하는 금액은 "
              "추정에 불과합니다. 다만 귀사 규모의 법인이 한 달에 처리해야 하는 업무가 무엇인지는 "
              "빠르게 말씀드릴 수 있고, 대체로 그 편이 더 유용한 정보입니다. 최근 시산표나 부가세 "
              "신고서를 보내주시면 첫 회신에서 구체적으로 답변드립니다."},
        {"q": "공인회계사가 반드시 필요한가요?",
         "a": "단순 기장에 한국공인회계사가 법적으로 필수는 아닙니다. 다만 세무 신고, 법정 재무제표, "
              "그리고 국세청이 문제 삼을 수 있는 판단 사항은 다릅니다. 저렴한 기장 대리와 별도의 세무 "
              "대리로 업무를 나눈 기업은 세무조사 시점에 그 공백을 발견하는 경우가 많습니다. 저희가 "
              "모든 계약 건에 한국공인회계사를 참여시키는 이유입니다."},
        {"q": "기존 업체에서 얼마나 빨리 이관할 수 있나요?",
         "a": "통상 한 번의 신고 주기 안에 가능합니다. 시산표, 보조원장, 고정자산 대장, 급여대장, 과거 "
              "신고 내역을 받아 기초 잔액을 대사하고 일치하지 않는 항목을 정리합니다. 이 대사 작업이 "
              "가장 가치 있는 부분입니다. 이전 업체의 기말 잔액을 제3자가 독립적으로 검증하는 첫 "
              "기회인 경우가 많기 때문입니다."},
    ],
}


# ────────────────────────────────────────────────────────────── helpers ──
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


_REBASE = re.compile(r'\b(href|src)="/(?!/)')


def rebase(html: str) -> str:
    """Prefix every root-relative URL with BASE. No-op when BASE is empty.

    Matches href/src starting with a single slash, which is exactly the set of
    internal links. Protocol-relative ("//cdn…"), absolute ("https://…") and
    fragment ("#faq") URLs are left alone.
    """
    return _REBASE.sub(rf'\1="{BASE}/', html) if BASE else html


def write(path: str, content: str):
    if BASE and path.endswith(".html"):
        content = rebase(content)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_front_matter(raw: str):
    if not raw.startswith("---"):
        return {}, raw
    _, fm, body = raw.split("---", 2)
    return yaml.safe_load(fm) or {}, body.lstrip("\n")


def pfx(lang: str) -> str:
    """URL prefix for a language. English sits at the root; Korean under /ko."""
    return LANGS[lang]["prefix"]


MD = markdown.Markdown(
    extensions=["extra", "sane_lists", "tables", "attr_list", "footnotes", "toc", "smarty"],
    extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}},
)


def md_frag(text: str) -> str:
    MD.reset()
    return MD.convert(text or "")


def md_inline(text: str) -> str:
    out = md_frag(text).strip()
    if out.startswith("<p>") and out.endswith("</p>") and out.count("<p>") == 1:
        out = out[3:-4]
    return out


def plain(text: str) -> str:
    """Markdown → plain text, for JSON-LD values."""
    return html.unescape(re.sub(r"<[^>]+>", "", md_frag(text))).strip()


def render_md(text: str):
    MD.reset()
    return MD.convert(text), getattr(MD, "toc_tokens", [])


def clamp(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:—-") + "…"


def seo_title(obj, lang=DEFAULT_LANG, limit=62) -> str:
    """<title> under ~62 chars so Google renders it whole rather than truncating."""
    suffix = " | Bluestones BPO"
    base = (obj.get("seo_title") or obj.get("title") or "").strip()
    if len(base) + len(suffix) <= limit:
        return base + suffix
    return clamp(base, limit)


def meta_desc(obj, limit=158) -> str:
    return clamp(obj.get("meta") or obj.get("description") or "", limit)


def reading_time(text: str, lang=DEFAULT_LANG) -> int:
    if lang == "ko":                      # Korean reads slower per character
        return max(1, round(len(re.sub(r"\s", "", text)) / 500))
    return max(1, round(len(re.findall(r"\w+", text)) / 225))


def iso(d) -> str:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    if isinstance(d, dt.datetime):
        return d.replace(tzinfo=dt.timezone(dt.timedelta(hours=9))).isoformat()
    return dt.datetime(d.year, d.month, d.day, 9, 0,
                       tzinfo=dt.timezone(dt.timedelta(hours=9))).isoformat()


def pretty_date(d, lang=DEFAULT_LANG) -> str:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    if lang == "ko":
        return f"{d.year}년 {d.month}월 {d.day}일"
    return d.strftime("%d %B %Y").lstrip("0")


# ────────────────────────────────────────── callouts, video, resources ──
CALLOUT_ICONS = {
    "TIP":     ("Practical tip", "&#9733;"),
    "KEY":     ("Key figure", "&#9679;"),
    "WARNING": ("Watch out", "&#9888;"),
    "NOTE":    ("Context", "&#9432;"),
    "ACTION":  ("What to do", "&#10143;"),
    "DEADLINE": ("Deadline", "&#9200;"),
}
CALLOUT_KO = {
    "TIP": "실무 팁", "KEY": "핵심 수치", "WARNING": "주의",
    "NOTE": "참고", "ACTION": "체크리스트", "DEADLINE": "기한",
}


def transform_callouts(md_text: str, lang=DEFAULT_LANG) -> str:
    """GitHub-style admonitions: `> [!DEADLINE]` becomes a styled, quotable box."""
    out, i, lines = [], 0, md_text.split("\n")
    while i < len(lines):
        m = re.match(r"^>\s*\[!(TIP|KEY|WARNING|NOTE|ACTION|DEADLINE)\]\s*(.*)$", lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        kind, title = m.group(1), (m.group(2) or "").strip()
        i += 1
        buf = []
        while i < len(lines) and lines[i].startswith(">"):
            buf.append(re.sub(r"^>\s?", "", lines[i])); i += 1
        label, icon = CALLOUT_ICONS[kind]
        if lang == "ko":
            label = CALLOUT_KO[kind]
        inner = md_frag("\n".join(buf))
        out.append(f'<aside class="callout callout-{kind.lower()}">'
                   f'<p class="callout-h"><span class="callout-icon" aria-hidden="true">{icon}</span>'
                   f'{esc(title or label)}</p>{inner}</aside>')
    return "\n".join(out)


def video_embed(video) -> str:
    """Privacy-enhanced YouTube facade: youtube-nocookie, lazy, no third-party JS upfront."""
    if not video:
        return ""
    vid = video.get("id", "")
    title = video.get("title", "Related video")
    cap = (f'<figcaption class="muted small">{esc(title)}'
           f'{" — " + esc(video["channel"]) if video.get("channel") else ""}</figcaption>')
    return f"""<figure class="video">
  <div class="video-frame">
    <iframe src="https://www.youtube-nocookie.com/embed/{esc(vid)}?rel=0" title="{esc(title)}"
      loading="lazy" referrerpolicy="strict-origin-when-cross-origin"
      allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowfullscreen></iframe>
  </div>{cap}
</figure>"""


def resources_block(p, lang) -> str:
    if not p.get("resources"):
        return ""
    rows = "".join(
        f'<li><a href="{esc(r["url"])}" rel="noopener" target="_blank">{esc(r["title"])}</a>'
        f'<span class="muted"> — {esc(r.get("note",""))}</span></li>' for r in p["resources"])
    return f"""<section class="resources" aria-labelledby="res-h">
  <h2 id="res-h">{T(lang,'resources')}</h2>
  <p class="muted small">{T(lang,'resources_note')}</p>
  <ul class="plain linky">{rows}</ul></section>"""


# ─────────────────────────────────────────────────────────────── content ──
def _load_dir(subdir: str, kind: str):
    """Load a content collection in every configured language.

    English lives in content/<subdir>/*.md, Korean in content/<subdir>/ko/*.md.
    A Korean file whose basename matches an English one is automatically treated
    as its translation, which is what drives the reciprocal hreflang pair. There
    is no separate manifest to keep in sync — the filenames are the mapping.
    """
    items = []
    base = os.path.join(ROOT, "content", subdir)
    if not os.path.isdir(base):
        return items
    for lang in LANGS:
        d = base if lang == DEFAULT_LANG else os.path.join(base, lang)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            meta, body = parse_front_matter(read(os.path.join(d, name)))
            if meta.get("draft"):
                continue
            meta["lang"] = lang
            meta["kind"] = kind
            meta["basename"] = name[:-3]
            meta["slug"] = meta.get("slug") or slugify(meta.get("title", meta["basename"]))
            meta["body_md"] = body
            meta["reading_time"] = reading_time(body, lang)
            meta["source_file"] = os.path.join(d, name)
            items.append(meta)
    return items


def _pair_translations(items):
    """Group by basename so each item knows its counterpart in the other language."""
    by_base = {}
    for it in items:
        by_base.setdefault(it["basename"], {})[it["lang"]] = it
    for it in items:
        it["alternates"] = {lg: o["url"] for lg, o in by_base[it["basename"]].items()}
    return items


def load_posts():
    posts = _load_dir("posts", "post")
    for p in posts:
        p["category"] = p.get("category", "accounting")
        p["date"] = p.get("date") or dt.date.today()
        p["updated"] = p.get("updated") or p["date"]
        p["url"] = f"{pfx(p['lang'])}/blog/{p['category']}/{p['slug']}/"
        p["abs_url"] = SITE + p["url"]
    _pair_translations(posts)
    posts.sort(key=lambda p: (str(p["date"]), p["slug"]), reverse=True)
    return posts


def load_services():
    svcs = _load_dir("services", "service")
    for s in svcs:
        s["url"] = f"{pfx(s['lang'])}/services/{s['slug']}/"
        s["abs_url"] = SITE + s["url"]
        s["updated"] = s.get("updated") or dt.date.today()
    _pair_translations(svcs)
    order = [x["slug"] for x in CFG["services"]]
    svcs.sort(key=lambda s: order.index(s["slug"]) if s["slug"] in order else 99)
    return svcs


def load_pages():
    pages = _load_dir("pages", "page")
    for pg in pages:
        pg["url"] = f"{pfx(pg['lang'])}/{pg['slug']}/"
        pg["abs_url"] = SITE + pg["url"]
        pg["updated"] = pg.get("updated") or dt.date.today()
    _pair_translations(pages)
    return pages


def live_categories(posts, lang):
    """Only surface a category once it has an article in this language.

    An empty category page is a thin page, and thin pages drag the whole domain
    down under Google's helpful-content system. New beats stay invisible — no
    nav entry, no index, no sitemap row — until their first article exists.
    """
    used = {p["category"] for p in posts if p["lang"] == lang}
    return [c for c in CFG["categories"] if c["slug"] in used]


# ─────────────────────────────────────────────────────────── CTA blocks ──
def cta_band(lang, *, service=None, compact=False):
    """The commercial unit. Where the ad slot used to be on the blog template,
    this site puts the one action every page exists to produce."""
    head = {
        "en": "Talk to someone who has done this before",
        "ko": "먼저 겪어 본 사람과 상의하세요",
    }[lang]
    body = {
        "en": ("Tell us what your Korean entity needs to do this month. We will tell you what it "
               "actually involves, what it costs, and what you can safely leave until later — "
               "before you commit to anything."),
        "ko": ("이번 달 한국 법인이 처리해야 할 일을 알려 주시면, 실제로 무엇이 필요하고 "
               "비용은 어느 정도이며 무엇을 나중으로 미뤄도 되는지 먼저 말씀드립니다."),
    }[lang]
    if service:
        head = service.get("cta_title") or head
        body = service.get("cta_body") or body
    return f"""<aside class="cta-band{' cta-compact' if compact else ''}">
  <div class="cta-inner">
    <div>
      <h2>{esc(head)}</h2>
      <p>{esc(body)}</p>
      <p class="cta-promise">{esc(CFG['contact']['response_promise'] if lang == 'en' else '영업일 기준 1일 이내에 답변드립니다.')}</p>
    </div>
    <div class="cta-actions">
      <a class="btn btn-primary" href="{pfx(lang)}/contact/">{T(lang,'cta')}</a>
      <a class="btn btn-ghost" href="mailto:{BIZ['email']}">{BIZ['email']}</a>
      <a class="btn btn-ghost" href="tel:{BIZ['telephone'].replace(' ', '')}">{esc(BIZ['telephone'])}</a>
    </div>
  </div>
</aside>"""


def inject_cta(html_body: str, lang: str, every: int = 4) -> str:
    """Drop one compact CTA mid-article, between H2s — never inside a section."""
    parts = re.split(r"(?=<h2)", html_body)
    if len(parts) < 4:
        return html_body
    out = []
    for i, part in enumerate(parts):
        out.append(part)
        if i == min(every, len(parts) - 2) and i > 0:
            out.append(cta_band(lang, compact=True))
    return "".join(out)


# ──────────────────────────────────────────────────────────────── layout ──
def head(title, description, canonical, *, lang, og_image, og_type="website",
         published=None, modified=None, jsonld=None, alternates=None, robots=None):
    """
    The <head>.

    The `robots` default is the single most important line in this file. The Wix
    site this replaces shipped `noarchive, nofollow, noimageindex, nosnippet` on
    every page — which told Google not to follow its links, not to index its
    images, and not to show a snippet. A page with no snippet cannot be quoted by
    an AI answer engine at all. Nothing in this generator can emit those values:
    the only override used anywhere is `noindex,follow` on the 404.
    """
    # In staging every page is noindex regardless of what the caller asked for.
    robots = ROBOTS_DEFAULT if robots is None else ("noindex,nofollow" if IS_STAGING else robots)
    L = LANGS[lang]
    gsc = CFG["analytics"].get("search_console_verification")
    naver = CFG["analytics"].get("naver_site_verification")
    bing = CFG["analytics"].get("bing_verification")
    ga = CFG["analytics"].get("ga4_id")

    bits = [f"""<!doctype html>
<html lang="{L['hreflang']}" prefix="og: https://ogp.me/ns#">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:site_name" content="{esc(CFG['site_name'])}">
<meta property="og:locale" content="{L['locale']}">
{chr(10).join(f'<meta property="og:locale:alternate" content="{LANGS[o]["locale"]}">' for o in LANGS if o != lang)}
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(og_image)}">
<meta name="theme-color" content="{BRAND['navy']}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/img/logo.png">
<link rel="alternate" type="application/rss+xml" title="{esc(CFG['site_name'])}" href="/rss.xml">
<link rel="sitemap" type="application/xml" href="/sitemap.xml">
<link rel="stylesheet" href="/style.css">"""]

    # hreflang. Emitted only when a real counterpart exists — pointing hreflang at
    # a page that was never translated is worse than omitting it.
    if alternates and len(alternates) > 1:
        for lg, url in alternates.items():
            bits.append(f'<link rel="alternate" hreflang="{LANGS[lg]["hreflang"]}" href="{SITE}{url}">')
        bits.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}{alternates.get(DEFAULT_LANG, canonical)}">')

    if published:
        bits.append(f'<meta property="article:published_time" content="{published}">')
    if modified:
        bits.append(f'<meta property="article:modified_time" content="{modified}">')
    if gsc:
        bits.append(f'<meta name="google-site-verification" content="{esc(gsc)}">')
    if naver:
        bits.append(f'<meta name="naver-site-verification" content="{esc(naver)}">')
    if bing:
        bits.append(f'<meta name="msvalidate.01" content="{esc(bing)}">')
    if jsonld:
        bits.append('<script type="application/ld+json">'
                    + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
                    + "</script>")
    if ga:
        # Consent Mode v2 defaults must land before gtag.js, so this is synchronous
        # and deliberately first. Analytics stays denied until the reader accepts.
        bits.append('<script src="/consent.js"></script>')
        bits.append('<link rel="preconnect" href="https://www.googletagmanager.com" crossorigin>')
        bits.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>'
                    "<script>window.dataLayer=window.dataLayer||[];"
                    "function gtag(){dataLayer.push(arguments)}"
                    "gtag('js',new Date());"
                    f"gtag('config','{ga}',{{anonymize_ip:true}});</script>")
    bits.append("</head>")
    return "\n".join(bits)


def logo_svg(cls="brand-mark"):
    """The faceted stone, inline so it costs no request and inherits currentColor."""
    return f"""<svg class="{cls}" viewBox="0 0 40 44" width="34" height="37" aria-hidden="true">
  <polygon points="20,2 12,13 2,17" fill="{BRAND['sky']}"/>
  <polygon points="20,2 28,13 38,17" fill="#A9CBE4"/>
  <polygon points="20,2 12,13 28,13" fill="{BRAND['pale']}"/>
  <polygon points="12,13 28,13 38,17 2,17" fill="#8FB6D2"/>
  <polygon points="2,17 20,23 20,42" fill="{BRAND['blue']}"/>
  <polygon points="38,17 20,23 20,42" fill="#2E5F86"/>
</svg>"""


def header_html(lang, active="", alternates=None):
    """`active` is the current page's path, e.g. "/services/payroll-outsourcing/".

    Exactly one nav item is marked current: the one whose URL is the longest
    prefix of that path. Matching on the first path segment instead lit up both
    "Services" and "Company Setup" on every service page, because
    /services/company-registration/ starts with /services/ — two underlines, and
    no signal about where you actually are.
    """
    best = ""
    for n in CFG["nav"]:
        u = n["url"]
        if (active == u or active.startswith(u)) and len(u) > len(best):
            best = u

    def _link(n):
        url = pfx(lang) + n["url"]
        cur = ' aria-current="page"' if n["url"] == best else ""
        label = n.get("label_" + lang, n["label"])
        return f'<a href="{url}"{cur}>{esc(label)}</a>'

    links = "".join(_link(n) for n in CFG["nav"])

    # Language switch points at the counterpart page when one exists, and at the
    # other language's front page when it does not. Never a dead end.
    other = "ko" if lang == "en" else "en"
    other_url = (alternates or {}).get(other) or (pfx(other) + "/")
    switch = (f'<a class="lang-switch" href="{other_url}" hreflang="{LANGS[other]["hreflang"]}" '
              f'rel="alternate">{esc(T(lang, "lang_switch"))}</a>')

    banner = ""
    if IS_STAGING:
        banner = ('<div class="staging-bar" role="status">Staging preview — not indexed by '
                  'search engines. The live site is still '
                  '<a href="https://www.bluestonesbpo.com">www.bluestonesbpo.com</a>.</div>')

    return f"""<body>
<a class="skip" href="#main">{T(lang,'skip')}</a>
{banner}
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{pfx(lang)}/" aria-label="{esc(CFG['site_name'])}">
      {logo_svg()}
      <span class="brand-text">
        <span class="brand-name"><b>BLUE</b>STONES<sup>BPO</sup></span>
        <span class="brand-sub">Business Process Outsourcing</span>
      </span>
    </a>
    <input type="checkbox" id="navtoggle" class="navtoggle" aria-label="{T(lang,'menu')}">
    <label for="navtoggle" class="burger" aria-hidden="true"><span></span><span></span><span></span></label>
    <nav class="site-nav" aria-label="{T(lang,'primary')}">
      {links}
      {switch}
      <a class="btn btn-primary btn-sm nav-cta" href="{pfx(lang)}/contact/">{T(lang,'cta_short')}</a>
    </nav>
  </div>
</header>
<main id="main">"""


def footer_html(lang, services, posts):
    """The footer carries contact details, the company links and the legal links.

    Services and Insights used to have columns here too. They were removed: the
    header already links to both, every service page cross-links the other four,
    and five columns of links is the pattern that makes a footer unreadable. No
    crawl path is lost — the sitemap and the header cover it.
    """
    year = dt.date.today().year
    addr_en = (f"{BIZ['street']}, {BIZ['locality']}, {BIZ['region']} {BIZ['postal_code']}, "
               f"{BIZ['country_name']}")
    legal = {
        "en": [("Privacy policy", "/privacy-policy/"), ("Cookie policy", "/cookie-policy/"),
               ("Terms of use", "/terms/"), ("Disclaimer", "/disclaimer/")],
        "ko": [("개인정보처리방침", "/privacy-policy/"), ("쿠키 정책", "/cookie-policy/"),
               ("이용약관", "/terms/"), ("면책 고지", "/disclaimer/")],
    }[lang]
    legal_html = "".join(f'<li><a href="{pfx(lang)}{u}">{esc(t)}</a></li>' for t, u in legal)
    company = {
        "en": [("About us", "/about/"), ("Contact", "/contact/"), ("Blog", "/blog/"),
               ("Editorial policy", "/editorial-policy/")],
        "ko": [("회사 소개", "/about/"), ("문의", "/contact/"), ("블로그", "/blog/"),
               ("콘텐츠 정책", "/editorial-policy/")],
    }[lang]
    company_html = "".join(f'<li><a href="{pfx(lang)}{u}">{esc(t)}</a></li>' for t, u in company)
    blurb = {
        "en": ("Bluestones BPO is a Seoul-based accounting, payroll and operations outsourcing firm "
               "for foreign-invested companies in Korea. We keep your Korean entity compliant so "
               "your team can concentrate on the business."),
        "ko": ("블루스톤즈 BPO는 외국인투자기업을 위한 회계·급여·운영 아웃소싱 전문 기업입니다. "
               "한국 법인의 규제 준수를 저희가 맡고, 고객사는 본업에 집중하실 수 있도록 지원합니다."),
    }[lang]
    colophon = {
        "en": (f"&copy; {year} Bluestones BPO. All rights reserved. Guidance published here is "
               f"general information about Korean accounting, payroll and tax practice, not advice "
               f"on your specific facts — see our "
               f'<a href="{pfx(lang)}/disclaimer/">disclaimer</a>.'),
        "ko": (f"&copy; {year} Bluestones BPO. 본 사이트의 내용은 한국의 회계·급여·세무 실무에 "
               f"관한 일반적인 정보이며 개별 사안에 대한 자문이 아닙니다. "
               f'<a href="{pfx(lang)}/disclaimer/">면책 고지</a>를 참고하십시오.'),
    }[lang]

    return f"""</main>
<footer class="site-footer">
  <div class="wrap footer-grid">
    <div class="footer-brand-col">
      <p class="footer-brand">{logo_svg("brand-mark-sm")}<span><b>BLUE</b>STONES <sup>BPO</sup></span></p>
      <p class="muted">{esc(blurb)}</p>
      <address class="footer-address">
        <span>{esc(addr_en)}</span>
        <a href="mailto:{BIZ['email']}">{BIZ['email']}</a>
        <span>Tel {esc(BIZ['telephone'])} · Fax {esc(BIZ['fax'])}</span>
      </address>
      <p class="social">
        <a href="{CFG['social']['linkedin']}" rel="noopener me" target="_blank">LinkedIn</a>
        <a href="{CFG['social']['facebook']}" rel="noopener me" target="_blank">Facebook</a>
      </p>
    </div>
    <div><h2 class="footer-h">{T(lang,'company')}</h2><ul class="plain">{company_html}</ul></div>
    <div><h2 class="footer-h">{T(lang,'legal')}</h2><ul class="plain">{legal_html}</ul></div>
  </div>
  <div class="wrap footer-bottom">
    <p class="muted small">{colophon}</p>
  </div>
</footer>
<script src="/script.js" defer></script>
</body></html>"""


# ────────────────────────────────────────────────────────────── JSON-LD ──
def org_node():
    """The entity. This is the node that makes the business *resolvable* — to
    Google's Knowledge Graph and to answer engines deciding whether a
    'Korean payroll outsourcing firm' exists at a checkable address."""
    return {
        "@type": ["Organization", "ProfessionalService", BIZ["type"]],
        "@id": SITE + "/#organization",
        "name": BIZ["name"],
        "legalName": BIZ["legal_name"],
        "url": SITE + "/",
        "logo": {"@type": "ImageObject", "url": SITE + "/img/logo.png",
                 "width": 512, "height": 512},
        "image": SITE + "/img/logo.png",
        "email": BIZ["email"],
        "telephone": BIZ["telephone"],
        "faxNumber": BIZ["fax"],
        "foundingDate": BIZ["founded"],
        "description": CFG["strapline"],
        "priceRange": BIZ["price_range"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": BIZ["street"],
            "addressLocality": BIZ["locality"],
            "addressRegion": BIZ["region"],
            "postalCode": BIZ["postal_code"],
            "addressCountry": BIZ["country"],
        },
        "geo": {"@type": "GeoCoordinates",
                "latitude": BIZ["latitude"], "longitude": BIZ["longitude"]},
        "openingHours": BIZ["hours"],
        "areaServed": [{"@type": "AdministrativeArea", "name": a} for a in BIZ["areas_served"]],
        "knowsLanguage": BIZ["languages_spoken"],
        "knowsAbout": BIZ["knows_about"],
        "sameAs": [CFG["social"]["linkedin"], CFG["social"]["facebook"]],
        "contactPoint": [{
            "@type": "ContactPoint",
            "contactType": "sales",
            "email": BIZ["email"],
            "telephone": BIZ["telephone"],
            "availableLanguage": BIZ["languages_spoken"],
            "areaServed": "KR",
        }],
        # Referenced by @id; the full Person nodes are emitted on /about/.
        "employee": [{"@id": f"{SITE}/about/#{slugify(t['name'])}"}
                     for t in CFG.get("team", [])],
    }


def website_node(lang):
    return {
        "@type": "WebSite",
        "@id": SITE + "/#website",
        "url": SITE + "/",
        "name": CFG["site_name"],
        "description": CFG["strapline"],
        "publisher": {"@id": SITE + "/#organization"},
        "inLanguage": [LANGS[l]["hreflang"] for l in LANGS],
    }


def author_node():
    return {
        "@type": "Organization",
        "@id": SITE + "/about/#desk",
        "name": CFG["editorial"]["author_name"],
        "url": SITE + "/about/",
        "description": CFG["editorial"]["author_bio"],
        "parentOrganization": {"@id": SITE + "/#organization"},
    }


def team_cards(lang):
    """The professionals, as cards rather than a run of bold lines in the prose.

    Rendered from the same `team` block in site.config.json that produces the
    Person JSON-LD, so what a reader sees and what a search engine reads cannot
    drift apart. Initials stand in for photographs — inventing headshots for real
    named people is not an option, and a consistent monogram reads better than a
    stock portrait that obviously is not them.
    """
    def one(t):
        name = t.get(f"name_{lang}") or t["name"]
        role = t.get(f"job_title_{lang}") or t["job_title"]
        cred = t.get(f"credential_{lang}", t.get("credential", ""))
        aff = t.get(f"affiliation_{lang}", t.get("affiliation", ""))
        alum = t.get(f"alumni_{lang}", t.get("alumni", ""))
        back = t.get(f"background_{lang}") or t.get("background", "")
        # Initials from the Latin name so Korean and English cards match visually.
        parts = [p for p in re.split(r"\s+", t["name"]) if p and p[0].isalpha()]
        initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

        meta = []
        if cred:
            meta.append(f'<li class="tm-cred">{esc(cred)}</li>')
        if aff:
            meta.append(f"<li>{esc(aff)}</li>")
        if back:
            meta.append(f"<li>{esc(back)}</li>")
        if alum:
            meta.append(f'<li class="tm-alum">{esc(alum)}</li>')

        return f"""<article class="tm-card">
  <div class="tm-head">
    <span class="tm-avatar" aria-hidden="true">{initials}</span>
    <div>
      <h3>{esc(name)}</h3>
      <p class="tm-role">{esc(role)}</p>
    </div>
  </div>
  <ul class="tm-meta">{''.join(meta)}</ul>
</article>"""

    heading = {"en": "Our professionals", "ko": "구성원"}[lang]
    return (f'<section class="team" aria-labelledby="team-h">'
            f'<h2 id="team-h">{esc(heading)}</h2>'
            f'<div class="team-grid">{"".join(one(t) for t in CFG.get("team", []))}</div>'
            f"</section>")


def person_nodes():
    """Named professionals, marked up as Person entities.

    This site publishes tax and payroll guidance, which is money-adjacent
    territory where both Google's quality raters and answer engines weigh who is
    behind the advice. A named accountant with a stated credential, employer and
    university is a far stronger expertise signal than an anonymous "team", and
    it is also what lets an assistant answer "who at Bluestones handles Korean
    tax" with a name. Everything here is drawn from the About page — no invented
    qualifications.
    """
    out = []
    for t in CFG.get("team", []):
        node = {
            "@type": "Person",
            "@id": f"{SITE}/about/#{slugify(t['name'])}",
            "name": t["name"],
            "jobTitle": t["job_title"],
            "worksFor": {"@id": SITE + "/#organization"},
            "url": SITE + "/about/",
        }
        if t.get("knows_about"):
            node["knowsAbout"] = t["knows_about"]
        if t.get("credential"):
            node["hasCredential"] = {
                "@type": "EducationalOccupationalCredential",
                "credentialCategory": "professional certification",
                "name": t["credential"],
            }
        if t.get("alumni"):
            node["alumniOf"] = {"@type": "CollegeOrUniversity", "name": t["alumni"]}
        if t.get("affiliation"):
            node["affiliation"] = {"@type": "Organization", "name": t["affiliation"]}
        out.append(node)
    return out


def breadcrumbs(items):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + u}
            for i, (n, u) in enumerate(items)
        ],
    }


def faq_node(obj, url):
    return {
        "@type": "FAQPage",
        "@id": url + "#faq",
        "mainEntity": [{"@type": "Question", "name": f["q"],
                        "acceptedAnswer": {"@type": "Answer", "text": plain(f["a"])}}
                       for f in obj["faq"]],
    }


# ──────────────────────────────────────────────────────────────── cards ──
def post_card(p, *, eager=False, size="md"):
    c = CATS.get(p["category"], {})
    return f"""<article class="card card-{size}">
  <a class="card-media" href="{p['url']}" tabindex="-1" aria-hidden="true">
    <img src="/img/{p['slug']}-hero.webp" alt="" width="1600" height="900"
         loading="{'eager' if eager else 'lazy'}" {'fetchpriority="high"' if eager else 'decoding="async"'}>
  </a>
  <div class="card-body">
    <a class="chip" href="{pfx(p['lang'])}/blog/{p['category']}/">{esc(c.get('name', p['category']))}</a>
    <h3 class="card-title"><a href="{p['url']}">{esc(p['title'])}</a></h3>
    <p class="card-dek">{esc(p.get('description', ''))}</p>
    <p class="card-meta"><time datetime="{iso(p['date'])}">{pretty_date(p['date'], p['lang'])}</time>
      <span aria-hidden="true">·</span> {p['reading_time']} {T(p['lang'],'min_read')}</p>
  </div>
</article>"""


def feature_card(p):
    """The lead article: image left, text right, full content width."""
    c = CATS.get(p["category"], {})
    return f"""<article class="feature">
  <a class="feature-media" href="{p['url']}" tabindex="-1" aria-hidden="true">
    <img src="/img/{p['slug']}-hero.webp" alt="" width="1600" height="900"
         loading="eager" fetchpriority="high">
  </a>
  <div class="feature-body">
    <a class="chip" href="{pfx(p['lang'])}/blog/{p['category']}/">{esc(c.get('name', p['category']))}</a>
    <h2 class="feature-title"><a href="{p['url']}">{esc(p['title'])}</a></h2>
    <p class="feature-dek">{esc(p.get('description', ''))}</p>
    <p class="card-meta"><time datetime="{iso(p['date'])}">{pretty_date(p['date'], p['lang'])}</time>
      <span aria-hidden="true">·</span> {p['reading_time']} {T(p['lang'],'min_read')}</p>
  </div>
</article>"""


def service_card(s):
    pts = "".join(f"<li>{esc(x)}</li>" for x in (s.get("highlights") or [])[:4])
    return f"""<article class="svc-card">
  <h3><a href="{s['url']}">{esc(s.get('card_title') or s['title'])}</a></h3>
  <p>{esc(s.get('description',''))}</p>
  <ul class="svc-points">{pts}</ul>
  <a class="svc-go" href="{s['url']}">{esc(s.get('cta_link') or 'More info')} &rarr;</a>
</article>"""


# ───────────────────────────────────────────────────────────── renderers ──
def takeaways_block(obj, lang):
    if not obj.get("key_takeaways"):
        return ""

    def one(k):
        if not isinstance(k, dict):
            return f"<li>{md_inline(k)}</li>"
        refs = k.get("source")
        refs = [] if refs is None else (refs if isinstance(refs, list) else [refs])
        cites = "".join(f'<sup class="cite"><a href="#source-{r}" '
                        f'aria-label="Source {r}">{r}</a></sup>' for r in refs)
        return f'<li>{md_inline(k.get("text", ""))}{cites}</li>'

    items = "".join(one(k) for k in obj["key_takeaways"])
    return f"""<aside class="takeaways" aria-labelledby="key-takeaways">
  <h2 id="key-takeaways">{T(lang,'takeaways')}</h2>
  <ul>{items}</ul></aside>"""


def faq_block(obj, lang):
    if not obj.get("faq"):
        return ""
    rows = "".join(
        f'<details class="faq-item"><summary><h3>{esc(f["q"])}</h3></summary>'
        f'<div class="faq-a">{md_frag(f["a"])}</div></details>' for f in obj["faq"])
    return f"""<section class="faq" aria-labelledby="faq-h">
  <h2 id="faq-h">{T(lang,'faq')}</h2>{rows}</section>"""


def sources_block(obj, lang):
    if not obj.get("sources"):
        return ""

    def row(i, s):
        acc = s.get("accessed")
        stamp = (f'<span class="muted small"> · {T(lang,"verified")} {esc(str(acc))}</span>'
                 if acc else "")
        tag = (f'<span class="src-primary">{T(lang,"primary_tag")}</span>'
               if s.get("primary") else "")
        return (f'<li id="source-{i}"><span class="src-n">{i}</span>'
                f'<a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">'
                f'{esc(s["title"])}</a>{tag}'
                f'<span class="muted"> — {esc(s.get("publisher",""))}</span>{stamp}</li>')

    rows = "".join(row(i, s) for i, s in enumerate(obj["sources"], start=1))
    return f"""<section class="sources" aria-labelledby="src-h">
  <h2 id="src-h">{T(lang,'sources')}</h2>
  <p class="muted small">{T(lang,'sources_note')}</p>
  <ol class="plain sourcelist">{rows}</ol></section>"""


def toc_block(toc, lang, sticky=False):
    if len(toc) < 3:
        return ""

    def li(nodes):
        return "".join(f'<li><a href="#{n["id"]}">{esc(n["name"])}</a>'
                       + (f'<ul>{li(n["children"])}</ul>' if n.get("children") else "")
                       + "</li>" for n in nodes)

    # The sticky variant sits in a sidebar beside the article. On a 3,000-word
    # service page that is the difference between scanning and scrolling blind;
    # it collapses to a normal block on narrow screens.
    cls = "toc toc-sticky" if sticky else "toc"
    return f"""<nav class="{cls}" aria-labelledby="toc-h">
  <h2 id="toc-h">{T(lang,'on_this_page')}</h2><ul>{li(toc)}</ul></nav>"""


def render_post(p, all_posts, services):
    lang = p["lang"]
    cat = CATS.get(p["category"], {})
    body_html, toc = render_md(transform_callouts(p["body_md"], lang))
    body_html = inject_cta(body_html, lang)

    related = [q for q in all_posts
               if q["lang"] == lang and q["slug"] != p["slug"] and q["category"] == p["category"]][:3]
    if len(related) < 3:
        related += [q for q in all_posts if q["lang"] == lang and q["slug"] != p["slug"]
                    and q not in related][:3 - len(related)]
    rel_html = (f"""<section class="related" aria-labelledby="rel-h">
  <h2 id="rel-h">{T(lang,'read_next')}</h2>
  <div class="grid grid-3">{''.join(post_card(q, size='sm') for q in related)}</div></section>"""
                if related else "")

    # Service cross-links: the commercial bridge from an explainer to the offer.
    svc_html = ""
    linked = [s for s in services if s["lang"] == lang and s["slug"] in (p.get("services") or [])]
    if linked:
        svc_html = f"""<section class="svc-strip" aria-labelledby="svc-h">
  <h2 id="svc-h">{T(lang,'related_services')}</h2>
  <div class="grid grid-3">{''.join(service_card(s) for s in linked)}</div></section>"""

    graph = [org_node(), website_node(lang), author_node(),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"),
                          (T(lang, "insights"), pfx(lang) + "/blog/"),
                          (cat.get("name", p["category"]), f"{pfx(lang)}/blog/{p['category']}/"),
                          (p["title"], p["url"])])]
    article = {
        "@type": "BlogPosting",
        "@id": p["abs_url"] + "#article",
        "isPartOf": {"@id": SITE + "/#website"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": p["abs_url"]},
        "headline": p["title"][:110],
        "name": p["title"],
        "description": meta_desc(p),
        "url": p["abs_url"],
        "datePublished": iso(p["date"]),
        "dateModified": iso(p["updated"]),
        "author": {"@id": SITE + "/about/#desk"},
        "publisher": {"@id": SITE + "/#organization"},
        "articleSection": cat.get("name", p["category"]),
        "keywords": ", ".join(p.get("tags", [])),
        "wordCount": len(re.findall(r"\w+", p["body_md"])),
        "inLanguage": LANGS[lang]["hreflang"],
        "image": {"@type": "ImageObject", "url": SITE + f"/img/{p['slug']}-og.png",
                  "width": 1200, "height": 630},
        # Tells assistants which blocks are safe to read aloud / quote.
        "speakable": {"@type": "SpeakableSpecification",
                      "cssSelector": [".takeaways", ".article-dek"]},
        "isAccessibleForFree": True,
    }
    if p.get("about"):
        article["about"] = [{"@type": "Thing", "name": t} for t in p["about"]]
    graph.append(article)
    if p.get("faq"):
        graph.append(faq_node(p, p["abs_url"]))

    doc = head(seo_title(p, lang), meta_desc(p), p["abs_url"], lang=lang,
               og_image=SITE + f"/img/{p['slug']}-og.png", og_type="article",
               published=iso(p["date"]), modified=iso(p["updated"]),
               alternates=p.get("alternates"),
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, f"/blog/{p['category']}/{p['slug']}/", p.get("alternates"))
    upd = ("" if str(p["updated"]) == str(p["date"]) else
           f'<span aria-hidden="true">·</span><time datetime="{iso(p["updated"])}">'
           f'{T(lang,"updated")} {pretty_date(p["updated"], lang)}</time>')
    doc += f"""
<article class="article">
  <div class="wrap wrap-narrow">
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}">
      <ol><li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li><a href="{pfx(lang)}/blog/">{T(lang,'insights')}</a></li>
      <li><a href="{pfx(lang)}/blog/{p['category']}/">{esc(cat.get('name',''))}</a></li>
      <li aria-current="page">{esc(p['title'])}</li></ol>
    </nav>
    <header class="article-head">
      <a class="chip" href="{pfx(lang)}/blog/{p['category']}/">{esc(cat.get('name',''))}</a>
      <h1>{esc(p['title'])}</h1>
      <p class="article-dek">{esc(p.get('description',''))}</p>
      <div class="byline">
        <span>{T(lang,'by')} <a href="{pfx(lang)}/about/">{esc(CFG['editorial']['author_name'])}</a></span>
        <span aria-hidden="true">·</span>
        <time datetime="{iso(p['date'])}">{T(lang,'published')} {pretty_date(p['date'], lang)}</time>
        {upd}
        <span aria-hidden="true">·</span><span>{p['reading_time']} {T(lang,'min_read')}</span>
      </div>
    </header>
  </div>
  <figure class="hero">
    <img src="/img/{p['slug']}-hero.webp" alt="{esc(p.get('image_alt') or p['title'])}"
         width="1600" height="900" fetchpriority="high" decoding="async">
    {p.get('photo_credit', '')}
  </figure>
  <div class="wrap wrap-narrow">
    {takeaways_block(p, lang)}
    {toc_block(toc, lang)}
    <div class="prose">{body_html}</div>
    {video_embed(p.get('video'))}
    {resources_block(p, lang)}
    {faq_block(p, lang)}
    {sources_block(p, lang)}
    <aside class="disclosure">
      <h2>{T(lang,'disclosure_h')}</h2>
      <p>{esc(CFG['editorial']['author_bio'])}</p>
    </aside>
    {svc_html}
    {cta_band(lang)}
    {rel_html}
  </div>
</article>"""
    doc += footer_html(lang, services, all_posts)
    write(os.path.join(DIST, p["url"].strip("/"), "index.html"), doc)


def render_service(s, services, posts):
    lang = s["lang"]
    body_html, toc = render_md(transform_callouts(s["body_md"], lang))

    rel_posts = [p for p in posts
                 if p["lang"] == lang and s["slug"] in (p.get("services") or [])][:3]
    if not rel_posts:
        rel_posts = [p for p in posts
                     if p["lang"] == lang and p["category"] == s.get("category")][:3]
    posts_html = (f"""<section class="related" aria-labelledby="rp-h">
  <h2 id="rp-h">{T(lang,'insights')}</h2>
  <div class="grid grid-3">{''.join(post_card(q, size='sm') for q in rel_posts)}</div></section>"""
                  if rel_posts else "")

    others = [x for x in services if x["lang"] == lang and x["slug"] != s["slug"]]

    graph = [org_node(), website_node(lang),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"),
                          (T(lang, "services"), pfx(lang) + "/services/"),
                          (s["title"], s["url"])]),
             {"@type": "WebPage", "@id": s["abs_url"] + "#webpage", "url": s["abs_url"],
              "name": s["title"], "description": meta_desc(s),
              "isPartOf": {"@id": SITE + "/#website"},
              "inLanguage": LANGS[lang]["hreflang"],
              "dateModified": iso(s["updated"])},
             # The Service node is what lets an answer engine say "yes, this firm
             # does Korean payroll" rather than "this page mentions payroll".
             {"@type": "Service",
              "@id": s["abs_url"] + "#service",
              "name": s.get("service_name") or s["title"],
              "serviceType": s.get("service_type") or s["title"],
              "description": plain(s.get("description", "")),
              "url": s["abs_url"],
              "provider": {"@id": SITE + "/#organization"},
              "areaServed": [{"@type": "AdministrativeArea", "name": a}
                             for a in BIZ["areas_served"]],
              "availableLanguage": BIZ["languages_spoken"],
              "audience": {"@type": "BusinessAudience",
                           "audienceType": s.get("audience")
                           or "Foreign-invested companies operating in South Korea"},
              **({"hasOfferCatalog": {
                  "@type": "OfferCatalog",
                  "name": s["title"],
                  "itemListElement": [
                      {"@type": "Offer", "itemOffered":
                          {"@type": "Service", "name": x}}
                      for x in s["deliverables"]]}} if s.get("deliverables") else {})}]
    if s.get("faq"):
        graph.append(faq_node(s, s["abs_url"]))

    doc = head(seo_title(s, lang), meta_desc(s), s["abs_url"], lang=lang,
               og_image=SITE + f"/img/service-{s['slug']}-og.png",
               og_type="website", modified=iso(s["updated"]),
               alternates=s.get("alternates"),
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, f"/services/{s['slug']}/", s.get("alternates"))

    # The deliverables list moves into the hero as a summary card. It answers
    # "what do I actually get" before the reader commits to 3,000 words, and it
    # fills the right-hand column that a headline alone leaves empty.
    deliver = ""
    if s.get("deliverables"):
        deliver = f"""<aside class="svc-summary">
      <h2>{T(lang,'included')}</h2>
      <ul>{''.join(f'<li>{esc(x)}</li>' for x in s['deliverables'])}</ul>
    </aside>"""

    # Photo fetched once per service (English pass) and reused by the Korean
    # counterpart — the same page in two languages should not wear two faces.
    ph_url, ph_credit = hero_photo(s["slug"], s.get("hero_query", ""))
    doc += f"""
<div class="svc-hero">
  {hero_photo_layer(ph_url)}
  <div class="wrap">
    {f'<p class="hero-credit">{ph_credit}</p>' if ph_credit else ''}
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}">
      <ol><li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li><a href="{pfx(lang)}/services/">{T(lang,'services')}</a></li>
      <li aria-current="page">{esc(s['title'])}</li></ol>
    </nav>
    <div class="svc-hero-grid">
      <div class="svc-hero-main">
        <h1>{esc(s['title'])}</h1>
        <p class="svc-dek">{esc(s.get('description',''))}</p>
        <p class="svc-actions">
          <a class="btn btn-primary" href="{pfx(lang)}/contact/">{T(lang,'cta')}</a>
          <a class="btn btn-outline" href="mailto:{BIZ['email']}">{BIZ['email']}</a>
        </p>
      </div>
      {deliver}
    </div>
  </div>
</div>
<div class="wrap svc-layout">
  <div class="svc-side">{toc_block(toc, lang, sticky=True)}</div>
  <div class="svc-main">
    <div class="prose">{body_html}</div>
    {resources_block(s, lang)}
    {faq_block(s, lang)}
    {sources_block(s, lang)}
    {cta_band(lang, service=s)}
  </div>
</div>
<div class="wrap">
  {posts_html}
  <section class="related" aria-labelledby="os-h">
    <h2 id="os-h" class="section-h">{T(lang,'other_services')}</h2>
    <div class="grid grid-3 svc-grid">{''.join(service_card(x) for x in others)}</div>
  </section>
</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, s["url"].strip("/"), "index.html"), doc)


def render_services_index(lang, services, posts):
    items = [s for s in services if s["lang"] == lang]
    title = {"en": "Outsourcing Services in Korea",
             "ko": "한국 아웃소싱 서비스"}[lang]
    dek = {"en": ("Accounting, payroll, tax, company registration and financial controls for "
                  "foreign-invested companies — run by a Seoul team, reported in the format your "
                  "head office already uses."),
           "ko": ("외국인투자기업을 위한 회계·급여·세무·법인 설립·자금 통제 서비스입니다. 서울 현지 "
                  "팀이 수행하고 본사가 쓰는 양식 그대로 보고합니다.")}[lang]
    alternates = {l: f"{pfx(l)}/services/" for l in LANGS}
    url = f"{SITE}{pfx(lang)}/services/"
    graph = [org_node(), website_node(lang),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"), (T(lang, "services"), pfx(lang) + "/services/")]),
             {"@type": "CollectionPage", "@id": url + "#webpage", "url": url,
              "name": title, "description": dek, "inLanguage": LANGS[lang]["hreflang"],
              "isPartOf": {"@id": SITE + "/#website"},
              "mainEntity": {"@type": "ItemList", "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "url": s["abs_url"], "name": s["title"]}
                  for i, s in enumerate(items)]}}]
    doc = head(seo_title({"seo_title": title}, lang),
               clamp(dek, 158), url, lang=lang, og_image=SITE + "/img/logo.png",
               alternates=alternates, jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, "/services/", alternates)
    doc += f"""
<div class="page-hero">
  <div class="wrap">
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}"><ol>
      <li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li aria-current="page">{T(lang,'services')}</li></ol></nav>
    <h1>{esc(title)}</h1><p class="page-dek">{esc(dek)}</p>
  </div>
</div>
<div class="wrap">
  <div class="grid grid-3 svc-grid">{''.join(service_card(s) for s in items)}</div>
  {cta_band(lang)}
</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, f"{pfx(lang)}/services".strip("/"), "index.html"), doc)


def render_insights_index(lang, posts, services):
    items = [p for p in posts if p["lang"] == lang]
    # The H1 is the plain word, not a keyword string. "Korea Payroll, Tax &
    # Accounting Insights" as a headline reads like a meta tag that escaped onto
    # the page; the keywords live in seo_title and the standfirst, which is where
    # they actually do the work.
    title = {"en": "Blog", "ko": "블로그"}[lang]
    seo = {"en": "Korea Payroll, Tax & Accounting Blog",
           "ko": "한국 회계·급여·세무 블로그"}[lang]
    dek = {"en": ("Notes on Korean payroll, tax, accounting and compliance from the team that files "
                  "them. Every figure is dated and sourced to the authority it came from."),
           "ko": ("한국의 회계·급여·세무·규제 준수에 관한 실무 노트입니다. 모든 수치에 기준 시점과 "
                  "출처 기관을 명시합니다.")}[lang]
    alternates = {l: f"{pfx(l)}/blog/" for l in LANGS}
    url = f"{SITE}{pfx(lang)}/blog/"
    cats = live_categories(posts, lang)
    # A filter row listing a single topic is not a filter, it is a stray tag.
    cat_nav = ""
    if len(cats) > 1:
        chips = "".join(
            f'<a class="chip" href="{pfx(lang)}/blog/{c["slug"]}/">{esc(c["name"])}</a>'
            for c in cats)
        cat_nav = (f'<div class="topic-filter"><span class="topic-label">'
                   f'{T(lang,"browse_topic")}</span><div class="chip-row">{chips}</div></div>')
    graph = [org_node(), website_node(lang),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"), (T(lang, "insights"), pfx(lang) + "/blog/")]),
             {"@type": "Blog", "@id": url + "#blog", "url": url, "name": title,
              "description": dek, "inLanguage": LANGS[lang]["hreflang"],
              "publisher": {"@id": SITE + "/#organization"},
              "blogPost": [{"@type": "BlogPosting", "@id": p["abs_url"] + "#article",
                            "headline": p["title"], "url": p["abs_url"],
                            "datePublished": iso(p["date"])} for p in items[:30]]}]
    doc = head(seo_title({"seo_title": seo}, lang), clamp(dek, 158), url, lang=lang,
               og_image=SITE + "/img/logo.png", alternates=alternates,
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, "/blog/", alternates)

    # Newest post leads at full width, the rest follow in a grid. A single post
    # in an auto-fill grid renders as one narrow card marooned on the left; as a
    # lead it reads deliberate, and it still looks right at twenty posts.
    body = f'<p class="muted">{T(lang,"no_posts")}</p>'
    if items:
        lead, rest = items[0], items[1:]
        body = feature_card(lead)
        if rest:
            body += (f'<h2 class="section-h">{T(lang,"more_articles")}</h2>'
                     f'<div class="grid grid-3">'
                     f'{"".join(post_card(p) for p in rest)}</div>')
    doc += f"""
<div class="page-hero">
  <div class="wrap">
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}"><ol>
      <li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li aria-current="page">{T(lang,'insights')}</li></ol></nav>
    <h1>{esc(title)}</h1><p class="page-dek">{esc(dek)}</p>
    {cat_nav}
  </div>
</div>
<div class="wrap">{body}{cta_band(lang)}</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, f"{pfx(lang)}/blog".strip("/"), "index.html"), doc)


def render_category(c, lang, posts, services):
    items = [p for p in posts if p["lang"] == lang and p["category"] == c["slug"]]
    url = f"{SITE}{pfx(lang)}/blog/{c['slug']}/"
    alternates = {l: f"{pfx(l)}/blog/{c['slug']}/" for l in LANGS
                  if any(p["lang"] == l and p["category"] == c["slug"] for p in posts)}
    graph = [org_node(), website_node(lang),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"),
                          (T(lang, "insights"), pfx(lang) + "/blog/"),
                          (c["name"], f"{pfx(lang)}/blog/{c['slug']}/")]),
             {"@type": "CollectionPage", "@id": url + "#webpage", "url": url,
              "name": c["name"], "description": meta_desc(c),
              "isPartOf": {"@id": SITE + "/#website"},
              "inLanguage": LANGS[lang]["hreflang"],
              "mainEntity": {"@type": "ItemList", "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "url": p["abs_url"], "name": p["title"]}
                  for i, p in enumerate(items[:30])]}}]
    doc = head(seo_title({"seo_title": c["name"] + (" in Korea" if lang == "en" else "")}, lang),
               meta_desc(c), url, lang=lang, og_image=SITE + "/img/logo.png",
               alternates=alternates,
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, f"/blog/{c['slug']}/", alternates)
    grid = "".join(post_card(p, eager=(i == 0)) for i, p in enumerate(items)) or \
        f'<p class="muted">{T(lang,"no_posts")}</p>'
    doc += f"""
<div class="page-hero">
  <div class="wrap">
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}"><ol>
      <li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li><a href="{pfx(lang)}/blog/">{T(lang,'insights')}</a></li>
      <li aria-current="page">{esc(c['name'])}</li></ol></nav>
    <h1>{esc(c['name'])}</h1><p class="page-dek">{esc(c['blurb'])}</p>
  </div>
</div>
<div class="wrap"><div class="grid grid-3">{grid}</div>{cta_band(lang)}</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, f"{pfx(lang)}/blog/{c['slug']}".strip("/"), "index.html"), doc)


def contact_form(lang):
    ep = CFG["contact"]["form_endpoint"]
    # No endpoint configured yet? Degrade to mailto so the form is never a dead
    # end — a broken contact route is an instant trust failure on a B2B site.
    action = ep or f"mailto:{BIZ['email']}"
    method = "post" if ep else "get"
    enc = '' if ep else ' enctype="text/plain"'
    needs = {
        "en": ["Accounting & bookkeeping", "Payroll & HR", "Tax & VAT",
               "Company registration", "Operation support", "Something else"],
        "ko": ["회계·기장", "급여·인사", "세무·부가세", "법인 설립", "운영 지원", "기타"],
    }[lang]
    opts = "".join(f"<option>{esc(n)}</option>" for n in needs)
    return f"""<form class="lead-form" action="{esc(action)}" method="{method}"{enc}>
  <div class="field"><label for="f-name">{T(lang,'form_name')}</label>
    <input id="f-name" name="name" type="text" autocomplete="name" required></div>
  <div class="field"><label for="f-co">{T(lang,'form_company')}</label>
    <input id="f-co" name="company" type="text" autocomplete="organization" required></div>
  <div class="field"><label for="f-email">{T(lang,'form_email')}</label>
    <input id="f-email" name="email" type="email" autocomplete="email" required></div>
  <div class="field"><label for="f-country">{T(lang,'form_country')}</label>
    <input id="f-country" name="head_office" type="text" autocomplete="country-name"></div>
  <div class="field"><label for="f-need">{T(lang,'form_need')}</label>
    <select id="f-need" name="need">{opts}</select></div>
  <div class="field field-wide"><label for="f-msg">{T(lang,'form_msg')}</label>
    <textarea id="f-msg" name="message" rows="5"></textarea></div>
  <div class="field field-wide">
    <button class="btn btn-primary" type="submit">{T(lang,'form_send')}</button>
    <p class="muted small">{T(lang,'form_privacy')}</p>
  </div>
</form>"""


def render_page(pg, services, posts):
    lang = pg["lang"]
    body, toc = render_md(transform_callouts(pg["body_md"], lang))
    # `<!--team-->` in the markdown marks where the team card grid belongs, so
    # the page keeps control of the position without the card markup living in
    # content. Falls back to appending if the marker is missing.
    if "<!--team-->" in body:
        body = body.replace("<!--team-->", team_cards(lang))
    if pg.get("form"):
        body += contact_form(lang)
    graph = [org_node(), website_node(lang),
             breadcrumbs([(T(lang, "home"), pfx(lang) + "/"), (pg["title"], pg["url"])]),
             {"@type": pg.get("page_type", "WebPage"),
              "@id": pg["abs_url"] + "#webpage", "url": pg["abs_url"],
              "name": pg["title"], "description": meta_desc(pg),
              "isPartOf": {"@id": SITE + "/#website"},
              "inLanguage": LANGS[lang]["hreflang"],
              "dateModified": iso(pg["updated"])}]
    if pg.get("faq"):
        graph.append(faq_node(pg, pg["abs_url"]))
    if pg["slug"] == "about":
        graph.extend(person_nodes())
    doc = head(seo_title(pg, lang), meta_desc(pg), pg["abs_url"], lang=lang,
               og_image=SITE + "/img/logo.png", modified=iso(pg["updated"]),
               alternates=pg.get("alternates"),
               robots=pg.get("robots", "index,follow,max-image-preview:large,max-snippet:-1"),
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, f"/{pg['slug']}/", pg.get("alternates"))
    doc += f"""
<div class="page-hero">
  <div class="wrap wrap-narrow">
    <nav class="crumbs" aria-label="{T(lang,'breadcrumb')}"><ol>
      <li><a href="{pfx(lang)}/">{T(lang,'home')}</a></li>
      <li aria-current="page">{esc(pg['title'])}</li></ol></nav>
    <h1>{esc(pg['title'])}</h1>
    <p class="page-dek">{esc(pg.get('description',''))}</p>
  </div>
</div>
<div class="wrap wrap-narrow">
  <p class="muted small">{T(lang,'last_updated')} {pretty_date(pg['updated'], lang)}</p>
  {toc_block(toc, lang) if pg.get('toc') else ''}
  <div class="prose">{body}</div>
  {faq_block(pg, lang)}
  {cta_band(lang) if pg.get('cta', True) else ''}
</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, pg["url"].strip("/"), "index.html"), doc)


def render_home(lang, posts, services, pages):
    items = [p for p in posts if p["lang"] == lang][:6]
    svcs = [s for s in services if s["lang"] == lang]
    alternates = {l: f"{pfx(l)}/" for l in LANGS}
    url = f"{SITE}{pfx(lang)}/"

    title = {"en": "Korea Accounting, Payroll & Tax Outsourcing",
             "ko": "한국 회계·급여·세무 아웃소싱"}[lang]
    desc = {
        "en": ("Seoul-based accounting, payroll, tax and operations outsourcing for foreign "
               "companies in Korea. Stay compliant without hiring a local finance team."),
        "ko": ("외국인투자기업을 위한 서울 현지 회계·급여·세무·운영 아웃소싱. 한국에 재무팀을 "
               "채용하지 않고도 법인의 규제 준수를 유지하실 수 있습니다."),
    }[lang]
    h1 = {"en": "Your companion in Korea",
          "ko": "한국에서의 동반자"}[lang]
    sub = {
        "en": ("Foreign companies do not fail in Korea because the market is hard. They fail "
               "because a filing was missed, a payroll was wrong, or nobody told head office "
               "what the numbers meant. We handle that part."),
        "ko": ("외국 기업이 한국에서 어려움을 겪는 이유는 시장이 어려워서가 아닙니다. 신고 기한을 "
               "놓치거나, 급여가 잘못 계산되거나, 본사가 숫자의 의미를 전달받지 못했기 때문입니다. "
               "저희가 그 부분을 맡습니다."),
    }[lang]
    proof = {
        "en": [("Seoul", "Local team, Korean-language filings, English-language reporting"),
               ("KICPA", "Korean Certified Public Accountant on every engagement"),
               ("1 day", "Response time on any enquiry, Korean business days")],
        "ko": [("서울", "현지 팀이 국문으로 신고하고 영문으로 보고합니다"),
               ("한국공인회계사", "모든 계약 건에 한국공인회계사가 참여합니다"),
               ("1영업일", "모든 문의에 대한 회신 소요 시간")],
    }[lang]
    proof_html = "".join(f'<div class="stat"><span class="stat-n">{esc(n)}</span>'
                         f'<span class="stat-l">{esc(l)}</span></div>' for n, l in proof)

    why_h = {"en": "Why companies hand this to us",
             "ko": "기업들이 저희에게 맡기는 이유"}[lang]
    why = {
        "en": [("One team, not four vendors",
                "Bookkeeping, payroll, VAT and the corporate return are done by the same people, "
                "so nothing falls between a bookkeeper and a tax agent."),
               ("Reporting your head office can read",
                "Statutory books in Korean for the tax office; a management pack in your group's "
                "format and language for the people who actually make decisions."),
               ("Bank controls that survive an audit",
                "Acting as bank signatory and reconciling the accounts gives you segregation of "
                "duties that a two-person local office cannot create on its own."),
               ("You can leave",
                "Your books, your files, your access. If you outgrow us and hire in-house, we hand "
                "over cleanly — that is the point of outsourcing, not a hostage situation.")],
        "ko": [("네 곳의 업체가 아닌 하나의 팀",
                "기장·급여·부가세·법인세를 같은 팀이 처리하므로 담당자 사이에서 누락되는 일이 없습니다."),
               ("본사가 이해할 수 있는 보고",
                "세무 신고용 국문 장부와 별도로, 본사 그룹 양식과 언어에 맞춘 경영 보고 패키지를 제공합니다."),
               ("감사에서 견디는 자금 통제",
                "은행 서명권자 역할과 계좌 대사를 함께 수행하여, 소규모 법인이 자체적으로 만들기 어려운 "
                "직무 분리를 구현합니다."),
               ("언제든 회수 가능",
                "장부와 파일, 접근 권한은 모두 고객사의 것입니다. 내부 채용으로 전환하실 때 깔끔하게 "
                "인계해 드립니다.")],
    }[lang]
    why_html = "".join(f"<div class='why-item'><h3>{esc(a)}</h3><p>{esc(b)}</p></div>"
                       for a, b in why)

    latest_html = ("".join(post_card(p) for p in items) or
                   f'<p class="muted">{T(lang,"no_posts")}</p>')

    # The front-page FAQ is the highest-value block on the site for answer engines.
    # These are the six questions an assistant is actually asked about operating in
    # Korea, answered completely, in the one place with the most authority signals
    # attached to it. It also earns the home page FAQ rich results in Google.
    home_faq = HOME_FAQ[lang]

    graph = [org_node(), website_node(lang),
             {"@type": "WebPage", "@id": url + "#webpage", "url": url,
              "name": title, "description": desc,
              "isPartOf": {"@id": SITE + "/#website"},
              "about": {"@id": SITE + "/#organization"},
              "inLanguage": LANGS[lang]["hreflang"]},
             faq_node({"faq": home_faq}, url)]

    doc = head(title + " | Bluestones BPO", desc, url, lang=lang,
               og_image=SITE + "/img/logo.png", og_type="website",
               alternates=alternates,
               jsonld={"@context": "https://schema.org", "@graph": graph})
    doc += header_html(lang, "/", alternates)
    photo_url, photo_credit = hero_photo("home", (CFG.get("hero") or {}).get("query", ""))
    credit_line = (f'<p class="hero-credit">{photo_credit}</p>' if photo_credit else "")
    doc += f"""
<section class="masthead">
  {hero_photo_layer(photo_url)}
  <div class="masthead-art" aria-hidden="true">{skyline_svg(photo=bool(photo_url))}</div>
  {credit_line}
  <div class="wrap masthead-inner">
    <div class="masthead-panel">
      <h1>{esc(h1)}</h1>
      <p class="masthead-dek">{esc(sub)}</p>
      <p class="masthead-actions">
        <a class="btn btn-primary" href="{pfx(lang)}/contact/">{T(lang,'cta')}</a>
        <a class="btn btn-outline" href="{pfx(lang)}/services/">{T(lang,'services')}</a>
      </p>
    </div>
  </div>
</section>
<section class="stats"><div class="wrap stats-row">{proof_html}</div></section>
<div class="wrap">
  <section aria-labelledby="svc-h">
    <h2 id="svc-h" class="section-h">{T(lang,'services')}</h2>
    <div class="grid grid-3 svc-grid">{''.join(service_card(s) for s in svcs)}</div>
  </section>
  <section class="why" aria-labelledby="why-h">
    <h2 id="why-h" class="section-h">{esc(why_h)}</h2>
    <div class="why-grid">{why_html}</div>
  </section>
  {cta_band(lang)}
  <section aria-labelledby="latest-h">
    <h2 id="latest-h" class="section-h">{T(lang,'latest')}</h2>
    <div class="grid grid-3">{latest_html}</div>
    <p class="more"><a href="{pfx(lang)}/blog/">{T(lang,'all_insights')} &rarr;</a></p>
  </section>
  {faq_block({"faq": home_faq}, lang)}
</div>"""
    doc += footer_html(lang, services, posts)
    write(os.path.join(DIST, f"{pfx(lang)}".strip("/"), "index.html"), doc)


def hero_photo(key: str, query: str, size=(1920, 1000)):
    """Fetch and prepare a photographic backdrop for a page hero.

    Returns (url, credit_html) — both empty strings when there is no API key, no
    network, or no acceptable match, in which case the hero falls back to the
    gradient and lattice it already had. A missing photo is never an error.

    The image is deliberately saved at low quality: it sits behind an overlay at
    roughly 10% visibility, so detail is invisible and bytes spent on it are
    bytes wasted on a page whose LCP is the headline.
    """
    if not query:
        return "", ""
    try:
        import photos
        from PIL import Image
        rec = photos.fetch({"slug": f"hero-{key}", "photo_query": query,
                            "title": query, "tags": []},
                           offline=bool(os.environ.get("BSB_OFFLINE")))
        if not rec or not os.path.exists(rec["path"]):
            return "", ""
        img = Image.open(rec["path"]).convert("RGB")
        tw, th = size
        scale = max(tw / img.width, th / img.height)
        img = img.resize((max(tw, int(img.width * scale)), max(th, int(img.height * scale))),
                         Image.LANCZOS)
        left, top = (img.width - tw) // 2, (img.height - th) // 2
        img = img.crop((left, top, left + tw, top + th))
        out = os.path.join(DIST, "img", f"hero-{key}.webp")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        img.save(out, "WEBP", quality=62, method=6)
        return f"{BASE}/img/hero-{key}.webp", photos.credit_html(rec)
    except Exception as e:                                  # noqa: BLE001
        print(f"  hero photo for {key} unavailable ({type(e).__name__}) — using the gradient")
        return "", ""


def hero_photo_layer(url: str) -> str:
    """The photograph as its own stacked layer, not an inline background-image.

    Two reasons it is a separate element rather than a style on the band itself:

    * `.svc-hero` already carries background layers — the cyan radial and the
      hanok lattice. An inline `background-image` replaces that property whole,
      so the lattice would silently vanish on any page that got a photo.
    * Opacity on a background-image cannot be set independently of the element's
      contents. On a layer it is one number, which is what makes "low enough to
      blend in" adjustable rather than a guess baked into an overlay gradient.

    Sits at 14%, under the text and over the base colour.
    """
    if not url:
        return ""
    return (f'<div class="hero-photo" aria-hidden="true" '
            f'style="background-image:url(&quot;{url}&quot;)"></div>')


def hanok_defs():
    """Traditional Korean motifs, drawn rather than photographed.

    Two patterns, both taken from hanok architecture:

    * `latt` — 정자살, the square-grid window lattice, with a diamond inset in
      each cell. Deliberately the plain grid form and not 완자살, whose meander
      motif can be misread as a swastika by a Western viewer. On a site whose
      whole audience is foreign companies, that risk is not worth the ornament.
    * `giwa` — the scalloped end-tiles of a 기와 roof, run as a band.

    Drawn instead of sourced for the same reason the rest of the artwork is: a
    photograph needs a licence, and a hotlinked one eventually 404s. Two
    kilobytes of SVG costs no request, scales to any screen, and is ours.
    """
    return """
  <pattern id="latt" width="132" height="132" patternUnits="userSpaceOnUse">
    <g fill="none" stroke="#CFE2F0" stroke-width="2.2" opacity=".85">
      <rect x="0" y="0" width="132" height="132"/>
      <path d="M66 0V132M0 66H132"/>
      <rect x="18" y="18" width="30" height="30"/>
      <rect x="84" y="18" width="30" height="30"/>
      <rect x="18" y="84" width="30" height="30"/>
      <rect x="84" y="84" width="30" height="30"/>
      <path d="M66 26 92 66 66 106 40 66Z"/>
    </g>
  </pattern>
  <pattern id="giwa" width="96" height="52" patternUnits="userSpaceOnUse">
    <g fill="none" stroke="#CFE2F0" stroke-width="2.4" opacity=".9">
      <path d="M0 44a24 24 0 0 1 48 0a24 24 0 0 1 48 0"/>
      <path d="M0 52h96"/>
      <circle cx="24" cy="40" r="5"/>
      <circle cx="72" cy="40" r="5"/>
    </g>
  </pattern>"""


def skyline_svg(photo: bool = False):
    """An original, drawn-not-photographed Seoul-ish skyline.

    The Wix site used a stock night-skyline photograph. Rather than reuse an image
    we have no licence for, the same feeling is produced as ~2 KB of inline SVG,
    which also happens to cost nothing in Largest Contentful Paint.
    """
    # With a photograph behind it, the drawn skyline is both redundant and
    # opaque — its base rect would hide the photo entirely. In that case only
    # the lattice and the giwa band are drawn, over a transparent canvas.
    base = "" if photo else '<rect width="1440" height="420" fill="url(#sky)"/>'
    buildings = "" if photo else """
  <g fill="#061C30" opacity=".85">
    <rect x="40" y="250" width="70" height="170"/><rect x="126" y="292" width="52" height="128"/>
    <rect x="196" y="228" width="84" height="192"/><rect x="298" y="272" width="60" height="148"/>
    <rect x="374" y="196" width="46" height="224"/><rect x="436" y="256" width="92" height="164"/>
    <rect x="546" y="300" width="58" height="120"/><rect x="620" y="150" width="64" height="270"/>
    <rect x="700" y="238" width="78" height="182"/><rect x="796" y="286" width="54" height="134"/>
    <rect x="866" y="206" width="88" height="214"/><rect x="972" y="262" width="62" height="158"/>
    <rect x="1050" y="180" width="52" height="240"/><rect x="1118" y="270" width="86" height="150"/>
    <rect x="1222" y="232" width="66" height="188"/><rect x="1304" y="288" width="96" height="132"/>
  </g>
  <g fill="#7FD4E4" opacity=".55">
    <rect x="636" y="132" width="6" height="20"/><rect x="1068" y="164" width="5" height="18"/>
    <rect x="390" y="180" width="5" height="18"/>
  </g>
  <g fill="#FFD9A0" opacity=".75">
    <rect x="54" y="272" width="7" height="9"/><rect x="76" y="296" width="7" height="9"/>
    <rect x="212" y="252" width="7" height="9"/><rect x="240" y="288" width="7" height="9"/>
    <rect x="452" y="278" width="7" height="9"/><rect x="486" y="318" width="7" height="9"/>
    <rect x="634" y="182" width="7" height="9"/><rect x="656" y="230" width="7" height="9"/>
    <rect x="716" y="262" width="7" height="9"/><rect x="742" y="306" width="7" height="9"/>
    <rect x="882" y="232" width="7" height="9"/><rect x="914" y="276" width="7" height="9"/>
    <rect x="1064" y="208" width="7" height="9"/><rect x="1136" y="296" width="7" height="9"/>
    <rect x="1240" y="258" width="7" height="9"/><rect x="1330" y="312" width="7" height="9"/>
  </g>"""

    return f"""<svg viewBox="0 0 1440 420" preserveAspectRatio="xMidYMax slice" role="presentation">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0C3C60"/><stop offset="55%" stop-color="#134A78"/>
      <stop offset="100%" stop-color="#08243D"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6EA4CA" stop-opacity=".00"/>
      <stop offset="100%" stop-color="#1EABC7" stop-opacity=".22"/>
    </linearGradient>
    <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fff" stop-opacity=".85"/>
      <stop offset="70%" stop-color="#fff" stop-opacity=".15"/>
      <stop offset="100%" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <mask id="latt-fade"><rect width="1440" height="420" fill="url(#fade)"/></mask>
    {hanok_defs()}
  </defs>
  {base}
  <!-- Hanok lattice, faint and fading downward so it never competes with the
       headline panel that sits over the lower-left of this band. -->
  <g mask="url(#latt-fade)" opacity=".09">
    <rect width="1440" height="420" fill="url(#latt)"/>
  </g>
  <g opacity=".10"><rect y="0" width="1440" height="52" fill="url(#giwa)"/></g>
  <rect y="250" width="1440" height="170" fill="url(#glow)"/>
  {buildings}
</svg>"""


def render_404():
    lang = DEFAULT_LANG
    doc = head("Page not found | Bluestones BPO",
               "That page could not be found. Browse our Korean accounting, payroll and tax "
               "outsourcing services, or get in touch with the Seoul team.",
               SITE + "/404.html", lang=lang, og_image=SITE + "/img/logo.png",
               robots="noindex,follow")
    doc += header_html(lang)
    doc += f"""<div class="wrap wrap-narrow"><header class="page-head">
  <h1>We could not find that page</h1>
  <p class="page-dek">The link may be broken, or the page may have moved when this site was
  rebuilt. Try the <a href="/">front page</a>, the <a href="/services/">services index</a>,
  or <a href="/contact/">contact us</a> directly.</p></header></div>"""
    doc += footer_html(lang, [], [])
    write(os.path.join(DIST, "404.html"), doc)


# ─────────────────────────────────────────────────────── machine outputs ──
def render_feeds(posts, services, pages):
    today = dt.date.today()
    urls = []
    for lang in LANGS:
        alts = {l: f"{pfx(l)}/" for l in LANGS}
        urls.append((f"{SITE}{pfx(lang)}/", "weekly", "1.0", today, None, None, alts))
        urls.append((f"{SITE}{pfx(lang)}/services/", "monthly", "0.9", today, None, None,
                     {l: f"{pfx(l)}/services/" for l in LANGS}))
        urls.append((f"{SITE}{pfx(lang)}/blog/", "daily", "0.8", today, None, None,
                     {l: f"{pfx(l)}/blog/" for l in LANGS}))
        for c in live_categories(posts, lang):
            urls.append((f"{SITE}{pfx(lang)}/blog/{c['slug']}/", "daily", "0.7",
                         today, None, None, None))
    for s in services:
        urls.append((s["abs_url"], "monthly", "0.9", s["updated"],
                     f"{SITE}/img/service-{s['slug']}-og.png", s["title"], s.get("alternates")))
    for p in posts:
        urls.append((p["abs_url"], "monthly", "0.7", p["updated"],
                     f"{SITE}/img/{p['slug']}-hero.webp",
                     p.get("image_alt") or p["title"], p.get("alternates")))
    for pg in pages:
        if pg.get("robots", "").startswith("noindex"):
            continue
        urls.append((pg["abs_url"], "yearly", "0.4", pg["updated"], None, None,
                     pg.get("alternates")))

    def entry(u, cf, pr, d, img, cap, alts):
        block = (f"<url><loc>{u}</loc>"
                 f"<lastmod>{d if isinstance(d, str) else d.isoformat()}</lastmod>"
                 f"<changefreq>{cf}</changefreq><priority>{pr}</priority>")
        if alts and len(alts) > 1:
            for lg, path in alts.items():
                block += (f'<xhtml:link rel="alternate" hreflang="{LANGS[lg]["hreflang"]}" '
                          f'href="{SITE}{path}"/>')
        if img:
            block += (f"<image:image><image:loc>{img}</image:loc>"
                      f"<image:title>{esc(cap)}</image:title></image:image>")
        return block + "</url>"

    write(os.path.join(DIST, "sitemap.xml"),
          '<?xml version="1.0" encoding="UTF-8"?>'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" '
          'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
          + "".join(entry(*u) for u in urls) + "</urlset>")

    if IS_STAGING:
        # Only robots.txt differs in staging. Everything below this — the feed, the
        # llms.txt map, the favicon, the manifest — still has to be written, or the
        # pages that reference them ship broken links.
        write(os.path.join(DIST, "robots.txt"),
              "# Staging copy of bluestonesbpo.com — not for indexing.\n"
              "# The production site is the canonical one.\n"
              "User-agent: *\nDisallow: /\n")
    else:
        write(os.path.join(DIST, "robots.txt"), f"""User-agent: *
Allow: /

# Answer engines are welcome. This site is written to be cited: figures are dated,
# sources are named, and the key-takeaway blocks are designed to be quoted whole.
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-Web
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Applebot-Extended
Allow: /
User-agent: Bingbot
Allow: /
User-agent: Yeti
Allow: /

Sitemap: {SITE}/sitemap.xml
""")

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    en_posts = [p for p in posts if p["lang"] == "en"][:40]
    items = "".join(f"""<item>
<title>{esc(p['title'])}</title>
<link>{p['abs_url']}</link>
<guid isPermaLink="true">{p['abs_url']}</guid>
<description>{esc(p.get('description',''))}</description>
<category>{esc(CATS.get(p['category'],{}).get('name',''))}</category>
<pubDate>{format_datetime(dt.datetime.fromisoformat(iso(p['date'])))}</pubDate>
</item>""" for p in en_posts)
    write(os.path.join(DIST, "rss.xml"), f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>{esc(CFG['site_name'])} — Insights</title>
<link>{SITE}/blog/</link>
<atom:link href="{SITE}/rss.xml" rel="self" type="application/rss+xml"/>
<description>{esc(CFG['strapline'])}</description>
<language>en-us</language>
<lastBuildDate>{format_datetime(now)}</lastBuildDate>
{items}
</channel></rss>""")

    # llms.txt — a clean, machine-readable map for answer engines. This is the
    # GEO equivalent of a sitemap: it tells a model what the site is, who runs it,
    # and which page answers which question, without making it parse nav chrome.
    lines = [
        f"# {CFG['site_name']}", "",
        f"> {CFG['strapline']}", "",
        f"{BIZ['name']} is an accounting, payroll and business-process outsourcing firm based in "
        f"{BIZ['locality']}, {BIZ['region']}, {BIZ['country_name']}. It serves foreign-invested "
        f"companies operating in South Korea — subsidiaries, branches and liaison offices of "
        f"overseas parents — handling statutory bookkeeping, monthly payroll and the four major "
        f"insurances, VAT and corporate income tax filing, company registration, bank signatory "
        f"and cash controls, and head-office reporting.", "",
        f"Contact: {BIZ['email']} · {BIZ['telephone']}",
        f"Address: {BIZ['street']}, {BIZ['locality']}, {BIZ['region']} {BIZ['postal_code']}, "
        f"{BIZ['country_name']}",
        f"Languages: {', '.join(BIZ['languages_spoken'])}",
        "Site languages: English (/) and Korean (/ko/).", "",
        "## Services", ""]
    for s in [x for x in services if x["lang"] == "en"]:
        lines.append(f"- [{s['title']}]({s['abs_url']}): {s.get('description','')}")
    lines.append("")
    for c in live_categories(posts, "en"):
        items_c = [p for p in posts if p["lang"] == "en" and p["category"] == c["slug"]]
        if not items_c:
            continue
        lines += [f"## {c['name']}", c["blurb"], ""]
        for p in items_c:
            lines.append(f"- [{p['title']}]({p['abs_url']}): {p.get('description','')} "
                         f"(updated {p['updated']})")
        lines.append("")
    lines += ["## About", ""]
    lines += [f"- [{pg['title']}]({pg['abs_url']})" for pg in pages if pg["lang"] == "en"]
    lines += ["", "## Sourcing", "",
              "Figures published on this site are checked against the issuing authority — the "
              "National Tax Service, the Ministry of Employment and Labor, the National Pension "
              "Service, the National Health Insurance Service, the Korea Immigration Service or "
              "the statute itself — and each article states the date its figures were current. "
              "Where a rate or threshold changes annually, the article names the year it applies "
              "to. Please cite the article URL and its stated period.", ""]
    write(os.path.join(DIST, "llms.txt"), "\n".join(lines) + "\n")

    b = BRAND
    write(os.path.join(DIST, "favicon.svg"), f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44">
<rect width="40" height="44" rx="6" fill="{b['navy']}"/>
<polygon points="20,6 13,15 5,18" fill="{b['sky']}"/>
<polygon points="20,6 27,15 35,18" fill="#A9CBE4"/>
<polygon points="20,6 13,15 27,15" fill="{b['pale']}"/>
<polygon points="13,15 27,15 35,18 5,18" fill="#8FB6D2"/>
<polygon points="5,18 20,23 20,38" fill="{b['blue']}"/>
<polygon points="35,18 20,23 20,38" fill="#2E5F86"/></svg>""")

    write(os.path.join(DIST, "manifest.webmanifest"), json.dumps({
        "name": CFG["site_name"], "short_name": "Bluestones", "start_url": BASE + "/",
        "display": "standalone", "background_color": b["navy"], "theme_color": b["navy"],
        "icons": [{"src": BASE + "/img/logo.png", "sizes": "512x512", "type": "image/png"}]}))


# ──────────────────────────────────────────────────────────────── build ──
def build():
    # Clearing dist has to actually happen. Overwriting in place leaves orphaned
    # files from a previous build, and validate.py then passes against artefacts
    # the current code did not produce — a false green that only surfaces in CI,
    # where the checkout is clean. Some synced/network mounts refuse unlink but
    # still permit rename, so fall back to moving the stale tree aside.
    if os.path.isdir(DIST):
        try:
            shutil.rmtree(DIST)
        except OSError as e:
            stale = f"{DIST}.stale-{dt.datetime.now():%Y%m%d-%H%M%S}"
            try:
                os.rename(DIST, stale)
                print(f"! could not delete {DIST} ({e.strerror}); moved aside to "
                      f"{os.path.basename(stale)} — safe to delete by hand")
            except OSError:
                print(f"!! could not clear or rename {DIST} ({e.strerror}).\n"
                      f"!! Building over the top. Validation results may reflect stale\n"
                      f"!! files from an earlier build — verify with a clean directory:\n"
                      f"!!     BSB_DIST=/tmp/dist-check python3 build.py")
    os.makedirs(DIST, exist_ok=True)

    posts, services, pages = load_posts(), load_services(), load_pages()
    print(f"→ {len(posts)} posts, {len(services)} service pages, {len(pages)} pages")

    imagegen.logo(os.path.join(DIST, "img", "logo.png"))
    for p in posts:
        meta = {**p, "category_name": CATS.get(p["category"], {}).get("name", "")}
        imagegen.hero(meta, os.path.join(DIST, "img", f"{p['slug']}-hero.webp"))
        if meta.get("_photo_credit"):
            p["photo_credit"] = meta["_photo_credit"]
        if meta.get("_photo_alt"):
            p["image_alt"] = meta["_photo_alt"]
        imagegen.social_card(p["slug"], p["category"], p["title"],
                             CATS.get(p["category"], {}).get("name", ""),
                             os.path.join(DIST, "img", f"{p['slug']}-og.png"))
    for s in services:
        if s["lang"] != DEFAULT_LANG:
            continue
        imagegen.social_card(f"service-{s['slug']}", s.get("category", "_default"),
                             s.get("card_title") or s["title"], "Bluestones BPO",
                             os.path.join(DIST, "img", f"service-{s['slug']}-og.png"))
    print("→ artwork generated")

    for p in posts:
        render_post(p, posts, services)
    for s in services:
        render_service(s, services, posts)
    for pg in pages:
        render_page(pg, services, posts)
    for lang in LANGS:
        render_home(lang, posts, services, pages)
        render_services_index(lang, services, posts)
        render_insights_index(lang, posts, services)
        for c in live_categories(posts, lang):
            render_category(c, lang, posts, services)
    render_404()
    render_feeds(posts, services, pages)

    for f in os.listdir(os.path.join(ROOT, "static")):
        shutil.copy(os.path.join(ROOT, "static", f), os.path.join(DIST, f))

    try:
        import dedupe
        write(os.path.join(ROOT, "content", "_data", "published-topics.md"), dedupe.topic_index())
    except Exception as e:                      # noqa: BLE001
        print(f"  topic index skipped ({type(e).__name__}: {e})")

    # A CNAME file only makes sense when the site owns a whole hostname. On a
    # project page the host belongs to github.io, and writing one there makes
    # Pages redirect to a domain that does not exist.
    if BASE:
        print(f"→ serving from sub-path {BASE}/ — no CNAME written")
    else:
        write(os.path.join(DIST, "CNAME"), SITE.split("//")[1] + "\n")
    write(os.path.join(DIST, ".nojekyll"), "")
    print(f"✓ built → {DIST}")
    return posts, services, pages


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    a = ap.parse_args()
    build()
    if a.serve:
        import http.server, socketserver, functools
        os.chdir(DIST)
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
        print("serving http://localhost:8000")
        socketserver.TCPServer(("", 8000), h).serve_forever()
