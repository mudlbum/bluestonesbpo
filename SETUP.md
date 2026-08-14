# Launch checklist

Work top to bottom. Items marked **(traffic)** are the ones that actually determine whether
this site gets visitors — skipping them makes everything else pointless.

---

## 0. Things only you can decide

- [ ] **Confirm the domain.** `site.config.json` is set to `https://www.bluestonesbpo.com`,
      inferred from your email address. If the real domain differs, change `domain` there —
      it drives canonicals, sitemap, hreflang, `llms.txt` and the `CNAME` file.
- [ ] **Verify the address.** The site publishes `Construction Building #711, Eonju-ro,
      Gangnam-gu, Seoul 06050` as structured data. If any part is wrong, fix it in
      `site.config.json` before launch — a wrong NAP in schema is worse than none, and it
      must match Google Business Profile character for character.
- [ ] **Check the latitude/longitude** in `site.config.json`. They are approximate for
      Gangnam-gu. Replace with your building's actual coordinates.
- [ ] **Legal review.** `privacy-policy`, `terms` and `disclaimer` (both languages) are
      drafted to match how the site actually works, but they carry a review note at the top
      and should be read by Korean counsel before launch. Delete the note once reviewed.
- [ ] **Verify the regulatory statements** in the five service pages. They are written to be
      stable and general, but two figures appear that you should confirm against current
      law: the **10% VAT rate**, the **3-month corporate tax deadline**, and the
      **KRW 100 million foreign-investment threshold**. Everything else is qualitative.

## 1. Get it online

The repository is already initialised and the first commit is made. To create the
GitHub repo and push:

**Easy way** — double-click `publish-to-github.bat` in this folder. It creates the repo,
pushes `main`, and turns on Pages. It borrows the token from your neighbouring
`futureofkorea` remote and does not write a copy of it anywhere.

**Manual way** — create an empty repo at <https://github.com/new> named `bluestonesbpo`
(no README, no .gitignore, no licence), then:

```bash
git remote add origin https://github.com/<your-username>/bluestonesbpo.git
git branch -M main
git push -u origin main
```

- [ ] Repo created and `main` pushed
- [ ] **Settings → Pages → Source: GitHub Actions**
- [ ] Wait for the first workflow run to go green

### 1a. Staging first — this is where the build currently points

`www.bluestonesbpo.com` is **already live and serving the Wix site**, so the build ships
in staging mode. `staging.enabled` is `true` in `site.config.json`, which makes it use
`new.bluestonesbpo.com`, emit `noindex,nofollow` on every page, serve a `Disallow: /`
robots.txt, and show an orange banner. Nothing about the live Wix site changes.

- [ ] DNS at your registrar: add a `CNAME` record — host `new`, value
      `<your-github-username>.github.io`
- [ ] **Settings → Pages → Custom domain:** `new.bluestonesbpo.com` → Save
- [ ] Wait for the certificate, then tick **Enforce HTTPS** (can take an hour)
- [ ] Review at `https://new.bluestonesbpo.com`

> The `noindex` here is deliberate, and it is the one place it belongs. A crawlable copy
> of your site is duplicate content competing with the real one. `validate.py` enforces
> it in reverse while staging is on — it now *fails* the build if a page is missing
> `noindex`.

### 1b. Go live, when you're happy with it

- [ ] Set `staging.enabled` to `false` in `site.config.json`
- [ ] `python build.py && python scripts/validate.py` — confirm the robots meta is back to
      `index,follow` and `dist/CNAME` reads `www.bluestonesbpo.com`
- [ ] Commit and push
- [ ] **Settings → Pages → Custom domain:** `www.bluestonesbpo.com` → Save
- [ ] DNS: repoint the `www` `CNAME` from Wix to `<your-github-username>.github.io`
- [ ] DNS: four `A` records on the apex pointing to
      `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
- [ ] Delete the `new` CNAME record so the staging copy stops resolving
- [ ] Keep the Wix site in your account, unpublished, for a few weeks as a rollback
- [ ] Tick **Enforce HTTPS** once the certificate issues (can take an hour)

## 2. Migrate from Wix without losing what little equity exists **(traffic)**

The Wix site has some signal — it has Google, Bing and Yandex verification tokens, so it has
been in Search Console for a while, and it has inbound links from your LinkedIn and Facebook
pages.

- [ ] **Do not delete the Wix site on day one.** Keep it live until the new site is indexed.
- [ ] If `bluestonesbpo.com` currently points at Wix, point it at GitHub Pages and set up
      **301 redirects** from every old path. The mapping:

      | Old | New |
      | --- | --- |
      | `/` | `/` |
      | `/about-us` | `/about/` |
      | `/services` | `/services/` |
      | `/team` | `/services/operation-support/` |
      | `/news` | `/insights/` |
      | `/news/post/<slug>` | `/insights/<category>/<slug>/` if rewritten, else `/insights/` |
      | `/contact` | `/contact/` |

- [ ] If the old blog posts are not being rewritten, redirect them to `/insights/` rather
      than letting them 404. They were thin and unsourced, so there is no case for porting
      them as-is.
- [ ] Update the links on **LinkedIn** and **Facebook** to the new domain. These are two of
      your only inbound links; leaving them pointed at `wixsite.com` wastes them.

## 3. Tell the search engines it exists **(traffic)**

- [ ] **Google Search Console** — add a domain property, verify by DNS TXT
- [ ] Submit `https://<domain>/sitemap.xml`
- [ ] Request indexing on the home page and all five service pages
- [ ] **Naver Search Advisor** (`searchadvisor.naver.com`) — register the site, verify, and
      submit the sitemap. **This is not optional.** Naver holds a large share of Korean
      search, and the entire `/ko/` half of this site is invisible in Korea without it. Put
      the verification token in `analytics.naver_site_verification`.
- [ ] **Bing Webmaster Tools** — the Wix site already had an `msvalidate.01` token; reuse it
      via `analytics.bing_verification`. Bing feeds ChatGPT search, so this has direct GEO
      value.
- [ ] **Daum/Kakao** search registration if you want full Korean coverage.
- [ ] Optional: create a GA4 property and put the measurement ID in
      `analytics.ga4_id`. The moment it is set, `consent.js` loads before gtag, Consent Mode
      v2 defaults land as *denied*, and the cookie banner appears. Order matters — the
      consent defaults must land before any Google tag or the first pageview escapes before
      consent is known.

## 4. Local and entity signals **(traffic)**

These are what make an AI assistant able to answer "who does payroll outsourcing in Seoul
for foreign companies" with your name.

- [ ] **Google Business Profile.** Category: Accountant / Business management consultant.
      Address, phone and name **identical** to `site.config.json`. Add the website URL.
- [ ] **Naver Place** registration — the Korean equivalent, and it matters more locally.
- [ ] **LinkedIn company page**: ensure the description, address and website match the site.
      LinkedIn is a strong entity signal and it is already in your `sameAs` schema.
- [ ] Consider listings in **KOTRA / Invest Korea** partner directories, AMCHAM Korea, and
      your national chamber of commerce in Korea (BritCham, ECCK, etc.). These are the
      highest-quality inbound links available in this niche and they are cheap or free.

## 5. Make the contact form actually deliver

The form currently degrades to a `mailto:` link, which works but is ugly and loses on mobile.

- [ ] Create an endpoint at **Formspree**, **Basin** or **Web3Forms** (all have free tiers
      and all work with a static host)
- [ ] Put the endpoint URL in `contact.form_endpoint` in `site.config.json`
- [ ] Rebuild, push, and **send yourself a test enquiry from the live site.** A contact form
      that silently fails is the single most expensive bug a B2B site can have.
- [ ] Confirm `info@bluestonesbpo.com` actually receives and is monitored.

## 6. Start the daily loop

- [ ] Confirm `content/_data/keyword-map.md` reflects what you actually want to sell
- [ ] Set up the recurring scheduled task that runs `automation/daily-post.md`
- [ ] Watch the first week's posts closely. The gate catches unsourced figures and dead
      links; it does not catch a figure that is sourced, live, and simply the wrong figure
      for the reader's situation.

## 7. Realistic expectations

Search takes months, not days. A new domain typically sees very little organic traffic for
three to six months regardless of content quality, then compounds.

What will produce traffic first, in order:

1. **Branded search.** People who already know you, arriving from LinkedIn or a referral.
   This works immediately and is why the migration step matters.
2. **The service pages.** Long-tail commercial queries — "payroll outsourcing korea foreign
   company" — have low volume and low competition. Expect first rankings in 2–4 months.
3. **The evergreen explainers.** Severance, the four insurances, VAT cycles. These take
   longest and last longest. They are what will still be earning in two years.
4. **AI citations.** Faster than organic ranking, in our experience of this pattern, because
   almost nothing in this niche publishes dated, sourced figures. The takeaway blocks exist
   for this.

News-style posts are what keeps the site crawled frequently in the meantime. They are not
the asset.

---

## Where the levers are

| Want to change | Edit |
| --- | --- |
| Domain, address, phone, hours | `site.config.json` → `business` |
| Brand colours | `site.config.json` → `brand` **and** `:root` in `static/style.css` |
| Nav items | `site.config.json` → `nav` |
| Service list and order | `site.config.json` → `services` + files in `content/services/` |
| Blog categories | `site.config.json` → `categories` |
| Analytics / verification tokens | `site.config.json` → `analytics` |
| Contact form endpoint | `site.config.json` → `contact.form_endpoint` |
| Interface wording (buttons, labels) | `STR` dict near the top of `build.py` |
| Editorial rules for the daily loop | `CLAUDE.md` |
| What gets written | `content/_data/keyword-map.md` |
