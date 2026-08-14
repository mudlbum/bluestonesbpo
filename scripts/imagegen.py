"""
Deterministic, offline artwork generator for Bluestones BPO.

No external API, no network, no licensing risk: every hero image and social card
is drawn procedurally with Pillow from a seed derived from the post slug, so the
same post always produces the same artwork and every post looks different.

Outputs per post:
  dist/img/<slug>-hero.webp   1600x900  (article hero)
  dist/img/<slug>-og.png      1200x630  (Open Graph / Twitter card, with title)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

# The wordmark stamped on generated covers. Read from config rather than
# hardcoded — the fork this generator came from was printing futureofkorea.com
# onto every Bluestones article image.
def _wordmark() -> str:
    try:
        cfg = json.load(open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "site.config.json"), encoding="utf-8"))
        return cfg["domain"].split("//")[-1].rstrip("/").split("/")[0]
    except Exception:                                   # noqa: BLE001
        return ""

# Bluestones BPO palette. Every beat is a variation on the corporate navy so the
# archive reads as one publication; the accent shifts just enough to tell the
# sections apart at card size. [(gradient top, gradient bottom), accent, light, highlight]
PALETTES = {
    "accounting": [("#08243D", "#0C3C60"), "#39729B", "#6EA4CA", "#D1E0EB"],
    "payroll":    [("#0A2E4A", "#134A78"), "#1EABC7", "#7FD4E4", "#D1E0EB"],
    "tax":        [("#062A38", "#0B4A5E"), "#1EABC7", "#6FD6E8", "#EFF1F2"],
    "entity":     [("#0C3C60", "#20567F"), "#6EA4CA", "#A9CBE4", "#EFF1F2"],
    "compliance": [("#14202A", "#20303C"), "#39729B", "#8FB6D2", "#D1E0EB"],
    "operations": [("#0A3050", "#16496F"), "#39729B", "#9BC2DC", "#EFF1F2"],
    "_default":   [("#08243D", "#0C3C60"), "#39729B", "#6EA4CA", "#D1E0EB"],
}


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _seed(slug: str) -> random.Random:
    return random.Random(int(hashlib.sha256(slug.encode()).hexdigest()[:16], 16))


def _font(name: str, size: int):
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _gradient(size, top, bottom, rnd):
    w, h = size
    base = Image.new("RGB", (1, h))
    px = base.load()
    t, b = _hex(top), _hex(bottom)
    ang = rnd.random()
    for y in range(h):
        f = (y / max(h - 1, 1)) ** (0.8 + ang * 0.6)
        px[0, y] = tuple(int(t[i] + (b[i] - t[i]) * f) for i in range(3))
    return base.resize((w, h), Image.BILINEAR)


def _glow(img, cx, cy, radius, colour, strength=0.55):
    layer = Image.new("RGB", img.size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=_hex(colour))
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.55))
    return Image.blend(img, Image.blend(img, layer, 1.0), 0).point(lambda v: v) if False else \
        Image.fromarray(_screen(img, layer, strength))


def _screen(a, b, strength):
    import numpy as np
    A = np.asarray(a).astype("float32") / 255.0
    B = (np.asarray(b).astype("float32") / 255.0) * strength
    out = 1.0 - (1.0 - A) * (1.0 - B)
    return (out.clip(0, 1) * 255).astype("uint8")


def _topography(draw, w, h, rnd, colour, lines=26, alpha=70):
    """Contour-style ridgelines — reads as data/terrain, on-brief for an analysis site."""
    col = _hex(colour)
    for i in range(lines):
        base_y = h * (i + 0.5) / lines
        amp = rnd.uniform(h * 0.015, h * 0.075)
        freq = rnd.uniform(1.1, 3.4)
        phase = rnd.uniform(0, math.tau)
        pts = []
        for x in range(0, w + 8, 8):
            t = x / w
            y = base_y + math.sin(t * math.tau * freq + phase) * amp \
                       + math.sin(t * math.tau * freq * 2.3 + phase * 1.7) * amp * 0.35
            pts.append((x, y))
        draw.line(pts, fill=col + (alpha,), width=rnd.choice([1, 1, 2]), joint="curve")


def _bars(draw, w, h, rnd, colour, accent):
    """A faint chart motif anchored bottom-left."""
    n = rnd.randint(9, 16)
    bw = w * 0.030
    gap = bw * 0.55
    total = n * (bw + gap)
    x0 = w * 0.06
    v = rnd.uniform(0.25, 0.5)
    for i in range(n):
        v = max(0.08, min(1.0, v + rnd.uniform(-0.18, 0.26)))
        bh = h * 0.34 * v
        x = x0 + i * (bw + gap)
        c = _hex(accent if i == n - 1 else colour)
        draw.rounded_rectangle([x, h * 0.86 - bh, x + bw, h * 0.86], radius=int(bw * 0.28),
                               fill=c + (150 if i == n - 1 else 70,))


def _nodes(draw, w, h, rnd, colour, accent, count=16):
    pts = [(rnd.uniform(w * 0.45, w * 0.98), rnd.uniform(h * 0.08, h * 0.92)) for _ in range(count)]
    col = _hex(colour)
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            d = math.dist(p, q)
            if d < w * 0.17:
                a = int(90 * (1 - d / (w * 0.17)))
                draw.line([p, q], fill=col + (a,), width=1)
    for i, p in enumerate(pts):
        r = rnd.uniform(2.5, 7.0)
        c = _hex(accent) if i % 5 == 0 else col
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=c + (190,))


def _lattice(draw, w, h, colour, cell=None, alpha=24):
    """Hanok window lattice (정자살) — a square grid with a diamond in each cell.

    The plain grid form deliberately, not 완자살: that pattern's meander motif
    can read as a swastika to a Western viewer, and this site's entire audience
    is foreign companies. Drawn rather than photographed for the same reason as
    the rest of the artwork — no licence to clear, nothing to 404.
    """
    col = _hex(colour) + (alpha,)
    cell = cell or int(w / 7.5)
    lw = max(1, int(w * 0.0016))
    for x in range(0, w + cell, cell):
        draw.line([(x, 0), (x, h)], fill=col, width=lw)
        draw.line([(x + cell // 2, 0), (x + cell // 2, h)], fill=col, width=lw)
    for y in range(0, h + cell, cell):
        draw.line([(0, y), (w, y)], fill=col, width=lw)
        draw.line([(0, y + cell // 2), (w, y + cell // 2)], fill=col, width=lw)
    d = cell * 0.30
    for x in range(0, w + cell, cell):
        for y in range(0, h + cell, cell):
            cx, cy = x + cell / 2, y + cell / 2
            draw.polygon([(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
                         outline=col)


def _grid(draw, w, h, colour, step=64, alpha=26):
    col = _hex(colour) + (alpha,)
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=col, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=col, width=1)


def _grain(img, rnd, amount=7):
    import numpy as np
    a = np.asarray(img).astype("int16")
    noise = np.random.default_rng(rnd.randint(0, 2**32 - 1)).normal(0, amount, a.shape[:2])
    a = (a + noise[..., None]).clip(0, 255).astype("uint8")
    return Image.fromarray(a)


def _canvas(slug: str, category: str, size):
    pal = PALETTES.get(category, PALETTES["_default"])
    (top, bottom), primary, secondary, highlight = pal
    rnd = _seed(slug)
    w, h = size

    img = _gradient(size, top, bottom, rnd).convert("RGB")
    img = _glow(img, w * rnd.uniform(0.55, 0.9), h * rnd.uniform(0.1, 0.5),
                w * rnd.uniform(0.28, 0.45), primary, 0.5)
    img = _glow(img, w * rnd.uniform(0.02, 0.3), h * rnd.uniform(0.55, 0.95),
                w * rnd.uniform(0.22, 0.36), secondary, 0.35)

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")
    # Hanok lattice as the base texture, with the fine grid over it. Ties the
    # article covers to the site heroes, which carry the same motif in SVG.
    _lattice(d, w, h, "#CFE2F0", alpha=22)
    _grid(d, w, h, "#ffffff", step=int(w / 22), alpha=16)

    # Motif keyed to the category rather than chosen at random, so a reader
    # starts to recognise a payroll piece from its thumbnail. Random per-slug
    # motifs made the archive look like an unrelated set of stock backgrounds.
    motif = {
        "payroll": "bars", "accounting": "bars",
        "tax": "topo", "compliance": "topo",
        "entity": "nodes", "operations": "nodes",
    }.get(category, rnd.choice(["topo", "nodes", "bars"]))
    if motif == "topo":
        _topography(d, w, h, rnd, "#ffffff", lines=rnd.randint(20, 32), alpha=rnd.randint(45, 85))
        _bars(d, w, h, rnd, secondary, highlight)
    elif motif == "nodes":
        _nodes(d, w, h, rnd, secondary, highlight, count=rnd.randint(14, 22))
        _topography(d, w, h, rnd, "#ffffff", lines=10, alpha=30)
    else:
        _bars(d, w, h, rnd, secondary, highlight)
        _nodes(d, w, h, rnd, secondary, highlight, count=10)

    # Signature arc — a nod to the taegeuk without reproducing the flag.
    r = w * rnd.uniform(0.16, 0.26)
    cx, cy = w * rnd.uniform(0.62, 0.86), h * rnd.uniform(0.22, 0.6)
    d.arc([cx - r, cy - r, cx + r, cy + r], rnd.randint(0, 360), rnd.randint(120, 300),
          fill=_hex(highlight) + (170,), width=max(2, int(w * 0.0035)))

    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return _grain(img, rnd), pal


FIGURE_RE = re.compile(r"\*\*([^*]*\d[^*]*)\*\*")


def lead_figure(post: dict) -> str:
    """The first bolded number the article itself leads with, e.g. '92%' or '₩104.8tn'."""
    for item in post.get("key_takeaways") or []:
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        m = FIGURE_RE.search(text)
        if m:
            fig = m.group(1).strip().rstrip(".,;:")
            if len(fig) <= 26:
                return fig
    return ""


def editorial_cover(post: dict, out_path: str, size=(1600, 900)):
    """
    Typographic cover built from the article's own headline and lead figure.

    Used when a post declares no `chart:` block. Unlike decorative art, this is
    never unrelated to the piece — every word on it comes from the piece.
    """
    slug, category = post["slug"], post.get("category", "_default")
    img, pal = _canvas(slug, category, size)
    (_, _), primary, secondary, highlight = pal
    w, h = size

    # Diagonal scrim, not a full-frame wash. The old version laid 150–235 alpha
    # of near-black over the whole canvas, which guaranteed legible text and also
    # flattened every generated background into the same dark rectangle. Text
    # sits bottom-left, so darken there and let the artwork stay visible in the
    # top-right where the arc and nodes are.
    scrim = Image.new("RGBA", size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim, "RGBA")
    for i in range(h):
        v = i / h                                  # 0 at top, 1 at bottom
        for band in range(0, w, 8):
            u = band / w                           # 0 at left, 1 at right
            # strongest bottom-left, weakest top-right
            a = int(28 + 170 * (v ** 0.85) * (1.0 - 0.55 * u) + 40 * (1.0 - u) * (1.0 - v))
            sd.rectangle([band, i, band + 8, i + 1], fill=(4, 10, 20, min(232, a)))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    d = ImageDraw.Draw(img, "RGBA")
    pad = int(w * 0.055)

    kicker = str(post.get("category_name") or category).upper()
    kf = _font("GeistMono-Regular.ttf", int(w * 0.0165))
    d.rectangle([pad, pad + 4, pad + 5, pad + int(w * 0.019)], fill=_hex(highlight))
    d.text((pad + 18, pad), kicker, font=kf, fill=_hex(highlight) + (240,))

    fig = lead_figure(post)
    y_cursor = h - pad
    if fig:
        ff = _font("InstrumentSans-Bold.ttf", int(w * 0.105))
        fw = d.textlength(fig, font=ff)
        if fw > w - pad * 2:
            ff = _font("InstrumentSans-Bold.ttf", int(w * 0.105 * (w - pad * 2) / fw))
        fh = int(w * 0.105 * 1.05)
        y_cursor = h - pad - fh
        d.text((pad + 3, y_cursor + 3), fig, font=ff, fill=(0, 0, 0, 120))
        d.text((pad, y_cursor), fig, font=ff, fill=_hex(highlight) + (255,))
        d.line([(pad, y_cursor - int(h * 0.035)), (pad + int(w * 0.07), y_cursor - int(h * 0.035))],
               fill=_hex(highlight) + (200,), width=4)
        y_cursor -= int(h * 0.075)

    title = str(post.get("title", ""))
    box_h = max(int(h * 0.20), y_cursor - pad - int(w * 0.05))
    f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - pad * 2, box_h,
                        int(w * 0.048), min_size=int(w * 0.022))
    y = y_cursor - len(lines) * fs * 1.14
    for line in lines:
        d.text((pad + 2, y + 2), line, font=f, fill=(0, 0, 0, 130))
        d.text((pad, y), line, font=f, fill=(255, 255, 255, 250))
        y += fs * 1.14

    mark = _wordmark()
    if mark:
        mono = _font("GeistMono-Regular.ttf", int(w * 0.0135))
        d.text((w - pad - d.textlength(mark, font=mono), pad),
               mark, font=mono, fill=(255, 255, 255, 165))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "WEBP", quality=86, method=6)
    return out_path


def photo_cover(post: dict, photo_path: str, out_path: str, size=(1600, 900)):
    """
    Photographic hero: the licensed image, darkened, with the headline over it.

    The gradient scrim is what makes this readable rather than a stock-photo
    cliché — text sits on near-solid colour at the bottom while the photograph
    still reads at the top. Contrast is fixed by construction, so a bright or
    busy photo can never render the headline illegible.
    """
    w, h = size
    category = post.get("category", "_default")
    pal = PALETTES.get(category, PALETTES["_default"])
    highlight = pal[3]

    img = Image.open(photo_path).convert("RGB")
    # cover-fit, centred
    sr, tr = img.width / img.height, w / h
    if sr > tr:
        nh = h; nw = int(h * sr)
    else:
        nw = w; nh = int(w / sr)
    img = img.resize((nw, nh), Image.LANCZOS).crop(
        ((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))

    scrim = Image.new("RGBA", size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim, "RGBA")
    for i in range(h):
        t = i / h
        sd.line([(0, i), (w, i)], fill=(6, 9, 18, int(40 + 215 * (t ** 1.6))))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    d = ImageDraw.Draw(img, "RGBA")
    pad = int(w * 0.055)

    kicker = str(post.get("category_name") or category).upper()
    kf = _font("GeistMono-Regular.ttf", int(w * 0.0165))
    d.rectangle([pad, pad + 4, pad + 5, pad + int(w * 0.019)], fill=_hex(highlight))
    d.text((pad + 18, pad), kicker, font=kf, fill=(255, 255, 255, 240))

    fig = lead_figure(post)
    y_bottom = h - pad
    if fig:
        ff = _font("InstrumentSans-Bold.ttf", int(w * 0.055))
        d.text((pad, y_bottom - int(w * 0.058)), fig, font=ff, fill=_hex(highlight) + (255,))
        y_bottom -= int(w * 0.078)

    title = str(post.get("title", ""))
    f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - pad * 2,
                        int(h * 0.42), int(w * 0.046), min_size=int(w * 0.022))
    y = y_bottom - len(lines) * fs * 1.14
    for line in lines:
        d.text((pad + 2, y + 2), line, font=f, fill=(0, 0, 0, 150))
        d.text((pad, y), line, font=f, fill=(255, 255, 255, 252))
        y += fs * 1.14

    _mk = _wordmark()
    if _mk:
        mono = _font("GeistMono-Regular.ttf", int(w * 0.0135))
        d.text((w - pad - d.textlength(_mk, font=mono), pad),
               _mk, font=mono, fill=(255, 255, 255, 165))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "WEBP", quality=84, method=6)
    return out_path


def hero(post, category=None, out_path=None, size=(1600, 900)):
    """
    Article hero. Renders the post's data as a chart when it declares one,
    otherwise a typographic cover derived from its headline and lead figure.

    Accepts the modern form hero(post_dict, out_path) and the legacy positional
    form hero(slug, category, out_path) so older callers keep working.
    """
    if isinstance(post, str):                       # legacy: (slug, category, path)
        post = {"slug": post, "category": category}
    else:
        out_path = category if out_path is None and isinstance(category, str) else out_path

    # Priority: the article's own data > a licensed photograph > typography.
    # Each step degrades silently to the next, so a missing API key or a failed
    # fetch costs visual richness but never breaks a build.
    spec = post.get("chart")
    if spec:
        import chartgen
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        png = out_path.rsplit(".", 1)[0] + "-chart.png"
        chartgen.render(spec, post.get("category", "_default"), png, size=size,
                        headline=post.get("title"))
        Image.open(png).convert("RGB").save(out_path, "WEBP", quality=88, method=6)
        os.remove(png)
        return out_path

    try:
        import photos
        rec = photos.fetch(post, offline=bool(os.environ.get("FOK_OFFLINE")))
        if rec and os.path.exists(rec["path"]):
            post["_photo_credit"] = photos.credit_html(rec)
            if rec.get("alt"):
                post["_photo_alt"] = rec["alt"]
            return photo_cover(post, rec["path"], out_path, size)
    except Exception as e:                                  # noqa: BLE001
        print(f"  photos: unavailable ({type(e).__name__}) — using typographic cover")

    return editorial_cover(post, out_path, size)


def _fit(draw, text, font_path, max_w, max_h, start, min_size=34, line_gap=1.16):
    size = start
    while size >= min_size:
        f = _font(font_path, size)
        approx = max(12, int(max_w / (size * 0.50)))
        lines = textwrap.wrap(text, width=approx)
        if not lines:
            lines = [text]
        widest = max(draw.textlength(l, font=f) for l in lines)
        height = len(lines) * size * line_gap
        if widest <= max_w and height <= max_h and len(lines) <= 4:
            return f, lines, size
        size -= 3
    f = _font(font_path, min_size)
    return f, textwrap.wrap(text, width=int(max_w / (min_size * 0.50)))[:4] or [text], min_size


def social_card(slug: str, category: str, title: str, kicker: str, out_path: str,
                site_name="FUTURE OF KOREA", size=(1200, 630)):
    img, pal = _canvas(slug, category, size)
    (_, _), primary, secondary, highlight = pal
    w, h = size

    scrim = Image.new("RGBA", size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim, "RGBA")
    for i in range(h):
        sd.line([(0, i), (w, i)], fill=(4, 7, 14, int(215 * (i / h) ** 0.55)))
    sd.rectangle([0, 0, w, h], outline=(255, 255, 255, 26), width=2)
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    d = ImageDraw.Draw(img, "RGBA")
    pad = 64

    # Masthead
    mast = _font("InstrumentSans-Bold.ttf", 26)
    d.rectangle([pad, pad + 6, pad + 6, pad + 32], fill=_hex(highlight))
    d.text((pad + 20, pad + 2), site_name, font=mast, fill=(255, 255, 255, 235))

    # Kicker chip
    if kicker:
        kf = _font("GeistMono-Regular.ttf", 21)
        kw = d.textlength(kicker.upper(), font=kf)
        d.rounded_rectangle([pad, h - pad - 46, pad + kw + 40, h - pad], radius=23,
                            fill=_hex(highlight) + (36,), outline=_hex(highlight) + (150,), width=1)
        d.text((pad + 20, h - pad - 36), kicker.upper(), font=kf, fill=_hex(highlight) + (255,))

    # Title block
    box_w, box_h = w - pad * 2, h - pad * 2 - 190
    f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", box_w, box_h, 74)
    y = h - pad - 100 - len(lines) * fs * 1.16
    for line in lines:
        d.text((pad + 2, y + 2), line, font=f, fill=(0, 0, 0, 130))
        d.text((pad, y), line, font=f, fill=(255, 255, 255, 252))
        y += fs * 1.16

    _mk = _wordmark()
    d.text((w - pad - d.textlength(_mk, font=_font("GeistMono-Regular.ttf", 21)),
            h - pad - 34), _mk,
           font=_font("GeistMono-Regular.ttf", 21), fill=(255, 255, 255, 155))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def logo(out_path: str, size=(512, 512)):
    """The Bluestones mark: a faceted blue stone on corporate navy.

    Drawn rather than sourced so the favicon, the social cards and the PWA icon
    are all guaranteed to be the same object at every size.
    """
    w, h = size
    img = Image.new("RGB", size, _hex("#0C3C60"))
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(h):                      # subtle vertical gradient, navy → deeper navy
        t = i / max(1, h - 1)
        top, bot = _hex("#0C3C60"), _hex("#08243D")
        d.line([(0, i), (w, i)],
               fill=tuple(int(top[c] + (bot[c] - top[c]) * t) for c in range(3)))

    cx, cy, s = w * .50, h * .52, w * .30
    # A cut stone: crown apex, girdle, pavilion tip. Facets are separate polygons
    # so each can take its own tint — that is what reads as "faceted" at 32px.
    apex   = (cx,            cy - s * 1.05)
    left   = (cx - s * .96,  cy - s * .16)
    right  = (cx + s * .96,  cy - s * .16)
    lmid   = (cx - s * .42,  cy - s * .52)
    rmid   = (cx + s * .42,  cy - s * .52)
    tip    = (cx,            cy + s * 1.08)

    keel = (cx, cy + s * .10)           # where the pavilion facets meet
    facets = [
        ([apex, lmid, left],        "#6EA4CA"),
        ([apex, rmid, right],       "#A9CBE4"),
        ([apex, lmid, rmid],        "#D1E0EB"),
        ([lmid, rmid, right, left], "#8FB6D2"),
        ([left, keel, tip],         "#39729B"),
        ([right, keel, tip],        "#2E5F86"),
    ]
    for pts, col in facets:
        d.polygon(pts, fill=_hex(col))
    # edge highlights
    for a, b in [(apex, left), (apex, right), (left, tip), (right, tip),
                 (left, right), (apex, lmid), (apex, rmid)]:
        d.line([a, b], fill=(255, 255, 255, 90), width=max(2, int(w * .006)))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "demo-post"
    cat = sys.argv[2] if len(sys.argv) > 2 else "markets"
    hero(slug, cat, f"/tmp/{slug}-hero.webp")
    social_card(slug, cat, "Demo headline for the social card generator", cat, f"/tmp/{slug}-og.png")
    print("wrote /tmp")
