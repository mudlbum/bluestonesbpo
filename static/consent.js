/* Google Consent Mode v2 defaults + cookie banner.
 *
 * This file is loaded SYNCHRONOUSLY and BEFORE gtag.js — deliberately. The
 * consent defaults must be on the dataLayer before any Google tag runs, or the
 * first pageview escapes before consent state is known. That is the specific
 * mistake that gets sites flagged under the EU user consent policy, and it is
 * an ordering problem, not a code-quality one.
 *
 * It only does anything when analytics.ga4_id is set in site.config.json. With
 * no measurement ID configured, the site sets no cookies at all and no banner
 * is shown — which is the correct behaviour, not a placeholder.
 */
(function () {
  "use strict";
  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }

  var KEY = "bsb-consent";
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* private mode */ }

  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    functionality_storage: "granted",
    security_storage: "granted",
    wait_for_update: 500
  });

  if (saved === "all") {
    gtag("consent", "update", {
      ad_storage: "granted",
      ad_user_data: "granted",
      ad_personalization: "granted",
      analytics_storage: "granted"
    });
    return;
  }
  if (saved === "essential") { return; }

  document.addEventListener("DOMContentLoaded", function () {
    var ko = (document.documentElement.lang || "").indexOf("ko") === 0;
    var bar = document.createElement("div");
    bar.className = "consent-bar";
    bar.setAttribute("role", "dialog");
    bar.setAttribute("aria-label", ko ? "쿠키 동의" : "Cookie consent");
    bar.innerHTML =
      '<p>' + (ko
        ? '이 사이트는 방문 통계를 위해 쿠키를 사용할 수 있습니다. 거부하셔도 사이트 이용에는 지장이 없습니다. '
        : 'We would like to use analytics cookies to understand which pages are useful. Declining changes nothing about how the site works. ')
      + '<a href="/cookie-policy/">' + (ko ? '쿠키 정책' : 'Cookie policy') + '</a></p>'
      + '<div class="consent-actions">'
      + '<button type="button" data-c="essential">' + (ko ? '필수만 허용' : 'Essential only') + '</button>'
      + '<button type="button" data-c="all" class="primary">' + (ko ? '모두 허용' : 'Accept all') + '</button>'
      + '</div>';

    var css = document.createElement("style");
    css.textContent =
      ".consent-bar{position:fixed;left:0;right:0;bottom:0;z-index:200;background:#08243D;color:#fff;" +
      "padding:1rem 1.2rem;display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap;justify-content:center;" +
      "box-shadow:0 -4px 24px rgba(0,0,0,.35);font-size:.9rem}" +
      ".consent-bar p{margin:0;max-width:70ch}.consent-bar a{color:#6EA4CA}" +
      ".consent-actions{display:flex;gap:.6rem}" +
      ".consent-bar button{font:inherit;font-weight:700;padding:.55rem 1.1rem;border-radius:4px;cursor:pointer;" +
      "border:1px solid rgba(255,255,255,.4);background:transparent;color:#fff}" +
      ".consent-bar button.primary{background:#1EABC7;border-color:#1EABC7;color:#06222B}";
    document.head.appendChild(css);

    bar.addEventListener("click", function (e) {
      var c = e.target && e.target.getAttribute("data-c");
      if (!c) { return; }
      try { localStorage.setItem(KEY, c); } catch (err) { /* ignore */ }
      if (c === "all") {
        gtag("consent", "update", {
          ad_storage: "granted",
          ad_user_data: "granted",
          ad_personalization: "granted",
          analytics_storage: "granted"
        });
      }
      bar.remove();
    });

    document.body.appendChild(bar);
  });
})();
