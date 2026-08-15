# Daily publishing run

The procedure the scheduled task follows. Written to be executed by Claude with web search
and shell access to this repository.

## 0. Setup

```bash
cd <REPO>
git pull --rebase
TZ=Asia/Seoul date          # the publication date is the KST date, not the runner's
```

Read `CLAUDE.md` if it is not already in context. Read
`content/_data/published-topics.md` — regenerated on every build — so you know what exists.

**Check today's date in Seoul before anything else.** The machine running this job may be on
a clock thirteen hours behind KST, and a post dated to the runner's "today" is dated to
yesterday in the timezone the site publishes in. That mis-sorts it below posts it should lead
and makes it look like nothing was published.

## 1. Choose today's topic

Open `content/_data/keyword-map.md`. That is the demand model. Work down it, but apply
judgement in this order:

**a. Is there something that changed?** Check for Korean regulatory news in the last 72
hours that has an operational consequence for a foreign-owned entity:

| Source | What to look for |
| --- | --- |
| National Tax Service | filing notices, tax law amendment announcements, new guidance |
| Ministry of Economy and Finance | annual tax revision proposals, effective dates |
| Ministry of Employment and Labor | minimum wage decisions, working-hour rules, labour law amendments |
| Four major insurance authorities | contribution rate changes (these change annually — high value) |
| Korea Immigration Service / Hi Korea | visa category changes affecting employed foreigners |
| Bank of Korea / FSS | foreign exchange transaction rule changes |

A rate change is the single highest-value post available. It is searched immediately, it is
searched again all year, and it forces every competitor's existing article out of date.

**b. If nothing changed, take the next unwritten Tier 2 question.** Prefer:
- questions with an answer that is a *number* (these win featured snippets and AI citations)
- questions where existing English coverage is thin, undated, or wrong
- questions that bridge naturally to a service page

**c. Is an existing article now out of date?** Updating it beats writing a new one. Korean
rates are revised annually, so the update path is the normal path, not the exception.

**Selection rule.** Publish only if you can (a) verify every figure at source today,
(b) say something the existing English coverage does not, and (c) leave the reader able to
act. If nothing clears all three, publish nothing and say so plainly. That is a valid outcome.

## 2. Verify — this is the step that matters

For every number you intend to publish, **open the primary source and read it**. Record the
URL, the publisher, and the period the figure covers.

> Never state a Korean rate, threshold or deadline on the authority of your own prior
> knowledge. They are revised annually. Your recollection is probably from a superseded
> year, and you will be confidently wrong in exactly the way that damages a professional
> services firm.

If sources disagree, publish the range and name both. If you cannot verify it, it does not
go in the article — not even hedged.

> **The URL you cite must survive a plain GET from a machine.** CI fetches every
> `sources:` URL from a bare runner with no session, no cookies and no JavaScript. Korean
> government sites frequently serve a working page to your browser and a 404 to that
> request — search-result URLs, `eng_mobile/…` viewers and anything carrying a
> `key=`/`query=` parameter are the usual offenders. Prefer the canonical document URL
> (`elaw.klri.re.kr/eng_service/lawView.do?hseq=…&lang=ENG` rather than the mobile viewer
> you happened to land on). If in doubt, open it in a private window with JavaScript
> disabled before you cite it.

### Record the evidence as you go

1. Add each source to `sources:` with `title`, `url`, `publisher`, `accessed:` (today) and
   `primary: true` where it is the authority itself. Minimum three sources, at least one
   primary.
2. Write each takeaway as a mapping pointing at the source index:

   ```yaml
   key_takeaways:
     - text: "The standard VAT rate is **10%**, unchanged for the 2026 tax year."
       source: 1
   ```

3. Every takeaway needs a **bolded figure**. No number, no takeaway.

## 3. Find supporting material

- **4–6 official resources**: the portals a reader would actually open — Hometax, the four
  major insurance portal, Hi Korea, DART, KOTRA. Prefer English interfaces where they exist,
  and say when only a Korean interface is available.
- **2–4 internal links.** At least one to the relevant service page. List what exists first:
  `ls content/posts/ content/services/` so every URL is real.
- **A video** only if one genuinely helps and you have taken the ID from a real search result.
  Never guess a YouTube ID. Omit the field if nothing suitable exists.

## 4. Write

```bash
python3 scripts/new_post.py "Headline goes here" --category payroll --services payroll-outsourcing
```

This scaffolds `content/posts/YYYY-MM-DD-slug.md` with correct front matter. Fill it in
following `CLAUDE.md`. Target 1,400–2,600 words.

**Decide whether it needs a Korean version.** If a Korean-speaking finance staffer at a
foreign company would search this, write one — natively, at
`content/posts/ko/<same-basename>.md`. Do not machine-translate. If the audience is purely
the overseas parent, skip it.

## 5. Build, validate, ship

```bash
python3 build.py
python3 scripts/validate.py     # must exit 0
```

If `validate.py` fails, **fix the cause, do not weaken the check.** The gate exists because
the site it replaced shipped `nofollow, nosnippet` on every page for years and nobody noticed.

### If the build cannot clear `dist/`

The repo lives on a OneDrive mount that sometimes refuses `unlink` on build artefacts, and
`build.py` dies with `PermissionError` on a stale PNG. Do not build over the top — validation
would then be reading files the current code did not produce. Build a clean copy instead:

```bash
rm -rf /tmp/bs && mkdir -p /tmp/bs
tar cf - --exclude=dist --exclude='dist.stale-*' --exclude=.git --exclude=__pycache__ . \
  | (cd /tmp/bs && tar xf -)
cd /tmp/bs && python3 build.py && python3 scripts/validate.py
```

`dist/` is git-ignored and CI rebuilds it from scratch, so a scratch build proves exactly what
CI will see. Orphaned `dist.stale-*` directories are harmless; mention them and move on.

### Committing

The same mount leaves stale git lock files behind. Clear them first, then commit:

```bash
for f in $(find .git -name "*.lock" ! -name "*.dead"); do mv "$f" "$f.dead"; done
git add -A && git -c core.fileMode=false commit -m "post: <slug>"
```

`warning: unable to unlink .git/objects/**/tmp_obj_*` is noise from the mount, not a failure —
check for the `[main <sha>]` line to confirm the commit landed.

### Pushing — the sandbox cannot reach github.com

`git push` from bash fails with `could not read Username for 'https://github.com'`. There are
no credentials in the sandbox and you must not ask for any. Push through the GitHub Desktop app
on the user's machine:

1. `request_access` for **GitHub Desktop**. In a scheduled run this is refused unless the app is
   already listed in the task's settings — if it is refused, commit locally, say plainly that
   the push did not happen, and stop. Do not claim it succeeded.
2. `open_application` GitHub Desktop, then click its taskbar icon to bring the window forward.
   Clicking the taskbar needs a `request_access` for **File Explorer** (the Windows shell).
3. Confirm the repo is `bluestonesbpo` and the branch is `main`. If the toolbar reads
   **Push origin ↑N**, click it. If it reads **Fetch origin**, click that first — the app's view
   of the branch can predate a commit made from bash — then re-check.
4. Screenshot to confirm: the ↑N badge disappears and the button returns to "Fetch origin".

### Verify the deploy — not just the URL

Wait ~90 seconds, then check the article is actually **reachable and in the right place**:

```
https://mudlbum.github.io/bluestonesbpo/blog/<category>/<slug>/
https://mudlbum.github.io/bluestonesbpo/ko/blog/<category>/<slug>/   # if bilingual
https://mudlbum.github.io/bluestonesbpo/blog/                        # must lead with today's post
```

A resolving URL is not proof the post is visible. Check that it leads the blog index and the
homepage's "From the blog" block. A post that exists but sorts third looks missing to the
person who asked for it.

If a run is red, open the failed job at
<https://github.com/mudlbum/bluestonesbpo/actions>, read the log, fix the cause and push again.

The `noindex,nofollow` on every page is **intentional** while `staging.enabled` is set in
`site.config.json` — the banner says so. Do not "fix" it.

## 6. Weekly housekeeping

- **Refresh figures that moved.** Update the number, bump `updated:`, note the change in the
  text. Do not touch `updated:` if nothing changed — a false modification date is a quality
  signal you are spending for nothing.
- **Check for dead links** in `sources` and `resources`. CI does this, but a link that dies
  between deploys will not surface until the next build.
- **Check the mix** against the target in `keyword-map.md`.
- **Review Search Console queries.** The most valuable input available: real queries where
  the site is appearing at position 8–20. Those are articles that need to be better, not new
  articles.
- **Re-submit the sitemap** in Search Console after a batch of posts.

## What "no post today" looks like

Say so plainly, name what you checked, and stop. Do not pad. Do not rewrite yesterday's post
with new adjectives.

A firm that publishes a wrong tax figure to hit a daily quota has done more damage to itself
than a firm that published nothing. The quota is a tool for consistency, not an obligation.

---

## Post-launch checklist for the first month

Traffic does not arrive because content exists. In order:

1. Verify the site is indexed: search `site:bluestonesbpo.com` in Google.
2. Submit the sitemap in Google Search Console **and** in Naver Search Advisor (the Korean
   pages are worthless without the latter — Naver has a large share of Korean search).
3. Register the business in Google Business Profile with the same NAP as
   `site.config.json`. Local search for "accounting firm Gangnam foreign company" depends on
   it, and the address consistency is what ties it to the `Organization` schema.
4. Update the LinkedIn and Facebook pages to point at the new domain, not the Wix URL.
5. Set 301 redirects from the old Wix URLs if the Wix site is retained on a domain
   (see `SETUP.md`).
6. Expect very little organic traffic for three to six months on a new domain, then
   compounding. The service pages and the evergreen explainers are what will still be
   earning in two years.
