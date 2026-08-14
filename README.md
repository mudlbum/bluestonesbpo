# Bluestones BPO — website

A bilingual (English / Korean) static site for a Seoul accounting, payroll and operations
outsourcing firm serving foreign-invested companies in South Korea.

Replaces `mudlbum.wixsite.com/bluestone`.

```bash
pip install -r requirements.txt
python build.py --serve          # http://localhost:8000
python scripts/validate.py       # the publication gate
```

---

## Why this exists

The Wix site it replaces shipped this on **every single page**:

```html
<meta name="robots" content="max-image-preview:standard, max-snippet:-1,
      max-video-preview:-1, noarchive, nofollow, noimageindex, nosnippet">
```

`nofollow` told Google not to follow any link on the site. `noimageindex` removed every
image from Google Images. `nosnippet` forbade a search snippet — and a page with no snippet
**cannot be quoted by an AI answer engine at all**. Combined with a `wixsite.com` subdomain,
a Wix advertising banner above the header, and identical meta descriptions across four
pages, the site was structurally incapable of ranking.

`scripts/validate.py` now fails the build if any page carries those directives. That is the
first check in the file and the reason the file exists.

### What else changed

| | Old Wix site | This site |
| --- | --- | --- |
| Indexability | `nofollow, nosnippet, noimageindex` sitewide | Full indexing, explicit AI-crawler allow-list |
| Domain | `mudlbum.wixsite.com/bluestone` | Custom domain, HTTPS, canonical URLs |
| Meta descriptions | Identical on 4 of 5 pages | Unique per page, length-validated per language |
| Structured data | None | Organization + ProfessionalService + AccountingService with full NAP, Service, FAQPage, BlogPosting, BreadcrumbList |
| Languages | English only | English + Korean with reciprocal hreflang and x-default |
| Service pages | One combined "Services" page | Five keyword-targeted pillar pages, each with FAQ schema |
| Blog | Generic AI filler, no sources, dormant since Dec 2025 | Sourced, dated, citation-gated, automated daily |
| Machine readability | None | `sitemap.xml` with hreflang + images, `rss.xml`, `llms.txt`, `robots.txt` |
| Performance | Wix runtime, render-blocking JS, banner ad | Static HTML, no framework, no web-font request, inline SVG hero |
| Contact | Wix form | Form with configurable endpoint, mailto fallback, consent-gated analytics |

---

## Layout

```
build.py                  static site generator
site.config.json          domain, business NAP, languages, categories, services, analytics
CLAUDE.md                 editorial rules for the daily loop
automation/daily-post.md  the daily publishing procedure
content/
  services/*.md           five English service pillar pages
  services/ko/*.md        Korean counterparts (same basename = hreflang pair)
  posts/*.md              articles, YYYY-MM-DD-slug.md
  posts/ko/*.md           Korean articles
  pages/*.md              about, contact, legal, editorial policy
  pages/ko/*.md           Korean counterparts
  _data/keyword-map.md    the demand model — what to write and why
  _data/published-topics.md  regenerated each build; the dedupe reference
scripts/
  validate.py             publication gate (run in CI; blocks the deploy)
  factcheck.py            sourcing gate — sources, primaries, access dates, link liveness
  dedupe.py               duplicate-topic gate
  new_post.py             scaffolds a correctly-shaped post
  imagegen.py             procedural hero and social artwork, offline and deterministic
static/                   style.css, script.js, consent.js — copied verbatim
dist/                     build output (git-ignored; CI rebuilds it)
```

## URL structure

```
/                                 English home
/ko/                              Korean home
/services/                        service index
/services/payroll-outsourcing/    service pillar page
/blog/                        article index
/blog/payroll/                category
/blog/payroll/<slug>/         article
/about/  /contact/  /terms/ …     pages
```

Korean mirrors everything under `/ko/`.

## The bilingual model

A Korean file with the **same basename** as an English file is automatically its
translation, and the pair gets reciprocal `hreflang` plus `x-default`. There is no manifest
to maintain — the filename is the mapping.

Korean articles are **written natively, not machine-translated**. A translated duplicate is
a content-quality liability and reads as foreign to a Korean professional.

## Adding an article

```bash
python3 scripts/new_post.py "Do you pay severance if an employee resigns?" \
    --category payroll --services payroll-outsourcing --ko
```

Fill in every `TK`. Then:

```bash
python3 build.py && python3 scripts/validate.py
```

The gate will reject the post if a figure has no source, if no source is primary, if a
takeaway has no bolded number, if the article is under 900 words, if it has fewer than two
internal links, or if a source URL is dead.

## Before you launch

See `SETUP.md`. The items that matter most are the custom domain, the 301 redirects from
the old Wix URLs, Google Search Console, **Naver Search Advisor** (without it the Korean
pages are invisible in Korea), and a Google Business Profile whose address matches
`site.config.json` exactly.
