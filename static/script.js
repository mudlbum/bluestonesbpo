/* Bluestones BPO — progressive enhancement only.
   Everything below is optional. The site is fully navigable, readable and
   convertible with JavaScript disabled; nothing here is required to render. */
(function () {
  "use strict";

  // Close the mobile menu after a tap. The menu is a CSS :checked toggle, so
  // without this the panel stays open over the page you just navigated to.
  var toggle = document.getElementById("navtoggle");
  if (toggle) {
    document.querySelectorAll(".site-nav a").forEach(function (a) {
      a.addEventListener("click", function () { toggle.checked = false; });
    });
  }

  // Outbound links open in a new tab and are marked up safely. Doing this here
  // rather than in the templates keeps the markdown source clean.
  var host = location.hostname;
  document.querySelectorAll(".prose a[href^='http']").forEach(function (a) {
    if (a.hostname && a.hostname !== host) {
      a.target = "_blank";
      a.rel = "noopener";
    }
  });

  // Open the FAQ item a visitor arrived at via an anchor, so a deep link from a
  // search result lands on an expanded answer rather than a collapsed summary.
  if (location.hash) {
    var t = document.querySelector(location.hash);
    var d = t && t.closest("details");
    if (d) { d.open = true; }
  }

  // Track which service page a lead form was submitted from, without cookies
  // and without sending anything anywhere until the visitor actually submits.
  document.querySelectorAll(".lead-form").forEach(function (f) {
    var src = document.createElement("input");
    src.type = "hidden";
    src.name = "page";
    src.value = location.pathname;
    f.appendChild(src);
  });
})();
