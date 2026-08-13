---
title: "Cookie Policy"
slug: cookie-policy
seo_title: "Cookie Policy"
meta: "This site sets no cookies unless you accept analytics. What each item does, how long it lasts, and how to change your mind."
description: "A short, honest account of what this site stores in your browser — which by default is nothing."
updated: 2026-08-13
cta: false
---

## The short version

**If you do nothing, this site stores nothing.**

There is no advertising network here, no social media pixel, no session recorder, no marketing
tracker, and no third-party script that runs before you have said yes to something. That is a
design decision, not a temporary state.

## What can be stored, and when

| Item | Type | Set when | Purpose | Lifetime |
| --- | --- | --- | --- | --- |
| `bsb-consent` | Local storage | You click a choice in the banner | Remembers whether you accepted or declined analytics, so the banner stops appearing | Until you clear your browser storage |
| `_ga`, `_ga_*` | Cookie | Only after you click "Accept all" | Google Analytics 4 — aggregate, anonymised usage measurement | Up to 2 years |

That is the complete list. If you decline, or ignore the banner, the analytics cookies are never
created — Google Consent Mode is initialised to *denied* before any Google tag loads, so nothing
is sent while consent is unknown.

Note that `bsb-consent` is stored in **local storage rather than a cookie**, and it exists purely
to record your own preference. It contains no identifier and is never transmitted anywhere.

## Analytics, if you allow it

Where analytics is enabled we use **Google Analytics 4** with IP anonymisation. What we look at
is which articles get read, which services pages people arrive on, and whether the site works on
mobile. We do not attempt to identify individual visitors, and the data is not linked to anything
you send through the contact form.

## Changing your mind

Clear your browser's site data for this domain and the banner will reappear on your next visit,
letting you choose again. In most browsers: Settings → Privacy → Clear browsing data, or the
padlock icon in the address bar → Cookies and site data.

You can also block cookies entirely in your browser. Nothing on this site depends on them —
every page, form and link works with all storage disabled.

## Third parties

Two things on the site can load from elsewhere, and both are worth naming:

- **YouTube**, where an article embeds a video. We use `youtube-nocookie.com` and load the
  player lazily, so nothing is requested from YouTube until you scroll to it.
- **GitHub Pages**, which serves the site's files and processes request data including your IP
  address as an inherent part of delivering a web page.

There is nothing else. No fonts are loaded from a third party, no CDN scripts, no chat widget.

## More

See our [privacy policy](/privacy-policy/) for how we handle information you send us
deliberately, such as a contact-form enquiry.
