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
# Each category carries several tonal variants rather than one fixed palette.
# One palette per category made every payroll post the same rectangle: at
# thumbnail size the archive read as a single repeated image. The variant is
# chosen from the slug, so it is stable for a given post and different between
# two posts filed under the same category.
#
# Palette shape: [(gradient_top, gradient_bottom), glow, motif, accent]
PALETTES = {
    "accounting": [
        [("#05192C", "#0C3C60"), "#39729B", "#6EA4CA", "#D1E0EB"],
        [("#0C3C60", "#20567F"), "#6EA4CA", "#A9CBE4", "#EFF1F2"],
        [("#0A1A24", "#1C4257"), "#1EABC7", "#6EA4CA", "#D1E0EB"],
    ],
    "payroll": [
        [("#07293F", "#134A78"), "#1EABC7", "#7FD4E4", "#D1E0EB"],
        [("#0B3346", "#17607A"), "#1EABC7", "#8FD8E6", "#EFF1F2"],
        [("#122A3E", "#2A5E86"), "#6EA4CA", "#A9CBE4", "#EFF1F2"],
    ],
    "tax": [
        [("#04222E", "#0B4A5E"), "#1EABC7", "#6FD6E8", "#EFF1F2"],
        [("#062A38", "#116A7E"), "#1EABC7", "#8AE0EC", "#EFF1F2"],
        [("#0A2230", "#0F4257"), "#39729B", "#6FD6E8", "#D1E0EB"],
    ],
    "entity": [
        [("#0C3C60", "#20567F"), "#6EA4CA", "#A9CBE4", "#EFF1F2"],
        [("#123049", "#2C6390"), "#6EA4CA", "#BBD6EA", "#EFF1F2"],
        [("#0A2C48", "#19507A"), "#39729B", "#9BC2DC", "#D1E0EB"],
    ],
    "compliance": [
        [("#0E1820", "#20303C"), "#39729B", "#8FB6D2", "#D1E0EB"],
        [("#131F29", "#2B4354"), "#39729B", "#9BC2DC", "#EFF1F2"],
        [("#101C26", "#1C3A4E"), "#1EABC7", "#8FB6D2", "#D1E0EB"],
    ],
    "operations": [
        [("#082741", "#16496F"), "#39729B", "#9BC2DC", "#EFF1F2"],
        [("#0A3050", "#1E5580"), "#6EA4CA", "#A9CBE4", "#D1E0EB"],
        [("#0C2436", "#1A4A63"), "#1EABC7", "#8FD8E6", "#EFF1F2"],
    ],
    "_default": [
        [("#05192C", "#0C3C60"), "#39729B", "#6EA4CA", "#D1E0EB"],
    ],
}

# Navy-on-pale cards. A run of eighteen dark rectangles down the blog index is
# the thing a reader actually notices; roughly a third of covers rendering light
# breaks that up more than any amount of motif variation does. Same brand
# colours, inverted — never a new hue.
LIGHT_PALETTES = [
    [("#F5F7F8", "#D1E0EB"), "#6EA4CA", "#39729B", "#0C3C60"],
    [("#EFF1F2", "#C3D7E6"), "#39729B", "#20567F", "#1EABC7"],
    [("#E7EEF4", "#BCD2E2"), "#6EA4CA", "#0C3C60", "#0C3C60"],
]

LIGHT_SHARE = 0.34          # proportion of covers rendered navy-on-pale


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _seed(slug: str) -> random.Random:
    return random.Random(int(hashlib.sha256(slug.encode()).hexdigest()[:16], 16))


def _pick(slug: str, salt: str, n: int) -> int:
    """A stable index in [0, n) for this slug, independent per `salt`.

    Separate hash streams matter: deriving layout, palette, motif and tone from
    one RNG correlates them, and every post in a category ends up with the same
    combination again. Salting decorrelates the choices so two payroll posts
    differ on several axes at once, while each post stays reproducible.
    """
    h = hashlib.sha256(f"{salt}:{slug}".encode()).hexdigest()[:12]
    return int(h, 16) % max(1, n)


def _tone(slug: str) -> str:
    return "light" if _pick(slug, "tone", 100) < int(LIGHT_SHARE * 100) else "dark"


def _palette(slug: str, category: str, tone: str):
    if tone == "light":
        return LIGHT_PALETTES[_pick(slug, "lightpal", len(LIGHT_PALETTES))]
    opts = PALETTES.get(category) or PALETTES["_default"]
    return opts[_pick(slug, "pal", len(opts))]


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


def _rings(draw, w, h, rnd, colour, accent, count=None):
    """Concentric arc sweeps — reads as a cycle, good for anything calendrical."""
    cx, cy = w * rnd.uniform(0.58, 0.92), h * rnd.uniform(0.18, 0.78)
    n = count or rnd.randint(5, 9)
    base = w * rnd.uniform(0.07, 0.12)
    for i in range(n):
        r = base + i * w * rnd.uniform(0.028, 0.045)
        start = rnd.randint(0, 360)
        extent = rnd.randint(90, 320)
        col = _hex(accent if i == n - 1 else colour)
        draw.arc([cx - r, cy - r, cx + r, cy + r], start, start + extent,
                 fill=col + (rnd.randint(55, 130),), width=max(1, int(w * 0.0022)))


def _columns(draw, w, h, rnd, colour, accent):
    """Evenly spaced tick columns of varying height — a calendar/ledger motif."""
    n = rnd.randint(14, 24)
    step = w / (n + 1)
    for i in range(n):
        x = step * (i + 1)
        seg = rnd.randint(3, 9)
        top = h * rnd.uniform(0.10, 0.34)
        gap = h * 0.018
        seg_h = h * rnd.uniform(0.020, 0.034)
        col = _hex(accent if rnd.random() < 0.12 else colour)
        for s in range(seg):
            y = top + s * (seg_h + gap)
            if y + seg_h > h * 0.94:
                break
            draw.rounded_rectangle([x, y, x + max(2, w * 0.0035), y + seg_h],
                                   radius=int(w * 0.0018), fill=col + (rnd.randint(40, 110),))


def _wave(draw, w, h, rnd, colour, accent, bands=None):
    """Stacked filled sine bands — softer than topography, fills the lower half."""
    n = bands or rnd.randint(3, 6)
    for i in range(n):
        amp = h * rnd.uniform(0.03, 0.09)
        freq = rnd.uniform(0.8, 2.2)
        phase = rnd.uniform(0, math.tau)
        base_y = h * (0.42 + 0.13 * i)
        pts = [(x, base_y + math.sin(x / w * math.tau * freq + phase) * amp)
               for x in range(0, w + 10, 10)]
        pts += [(w, h), (0, h)]
        col = _hex(accent if i == n - 1 else colour)
        draw.polygon(pts, fill=col + (rnd.randint(14, 30),))


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


# Each category leans towards motifs that suit it, but never locks to one.
# The old map bound category to a single motif, which — with the publishing mix
# weighted to payroll and tax — meant almost every cover carried the same faint
# bar chart. Weighted lists keep the association loose enough to vary.
MOTIF_WEIGHTS = {
    "payroll":    ["bars", "bars", "columns", "wave", "topo"],
    "accounting": ["bars", "bars", "grid_bars", "columns", "topo"],
    "tax":        ["topo", "topo", "wave", "bars", "rings"],
    "compliance": ["columns", "rings", "topo", "columns", "wave"],
    "entity":     ["nodes", "nodes", "rings", "topo", "bars"],
    "operations": ["nodes", "wave", "columns", "nodes", "rings"],
}


def _canvas(slug: str, category: str, size, tone: str = "dark"):
    """Background plate. `tone` selects navy-on-pale or the original dark ground."""
    pal = _palette(slug, category, tone)
    (top, bottom), primary, secondary, highlight = pal
    rnd = _seed(slug)
    w, h = size
    light = tone == "light"

    img = _gradient(size, top, bottom, rnd).convert("RGB")
    # Screen-blend glows brighten, which blows out a pale ground — keep them
    # faint there and let the gradient carry the depth instead.
    if light:
        img = _glow(img, w * rnd.uniform(0.55, 0.9), h * rnd.uniform(0.1, 0.5),
                    w * rnd.uniform(0.28, 0.45), "#FFFFFF", 0.30)
    else:
        img = _glow(img, w * rnd.uniform(0.55, 0.9), h * rnd.uniform(0.1, 0.5),
                    w * rnd.uniform(0.28, 0.45), primary, 0.5)
        img = _glow(img, w * rnd.uniform(0.02, 0.3), h * rnd.uniform(0.55, 0.95),
                    w * rnd.uniform(0.22, 0.36), secondary, 0.35)

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")

    # Hanok lattice ties the covers to the site heroes, which carry the same
    # motif in SVG — but drawing it on every card was part of what made them
    # interchangeable, so it now appears on about half.
    texture = _pick(slug, "texture", 4)
    lat_col, grid_col = ("#0C3C60", "#20567F") if light else ("#CFE2F0", "#ffffff")
    if texture in (0, 1):
        _lattice(d, w, h, lat_col, alpha=14 if light else 22)
    if texture in (0, 2):
        _grid(d, w, h, grid_col, step=int(w / 22), alpha=10 if light else 16)

    opts = MOTIF_WEIGHTS.get(category) or ["topo", "nodes", "bars", "columns", "wave", "rings"]
    motif = opts[_pick(slug, "motif", len(opts))]
    line_col = secondary if light else "#ffffff"
    a = 0.55 if light else 1.0                      # motifs read harder on pale

    if motif == "topo":
        _topography(d, w, h, rnd, line_col, lines=rnd.randint(20, 32),
                    alpha=int(rnd.randint(45, 85) * a))
    elif motif == "nodes":
        _nodes(d, w, h, rnd, secondary, highlight, count=rnd.randint(14, 22))
    elif motif == "bars":
        _bars(d, w, h, rnd, secondary, highlight)
    elif motif == "grid_bars":
        _bars(d, w, h, rnd, secondary, highlight)
        _topography(d, w, h, rnd, line_col, lines=8, alpha=int(28 * a))
    elif motif == "columns":
        _columns(d, w, h, rnd, secondary, highlight)
    elif motif == "wave":
        _wave(d, w, h, rnd, secondary, highlight)
    elif motif == "rings":
        _rings(d, w, h, rnd, secondary, highlight)

    # Signature arc — a nod to the taegeuk without reproducing the flag. Now
    # optional, and free to sit in any quadrant rather than always upper-right.
    if _pick(slug, "arc", 3) > 0:
        r = w * rnd.uniform(0.14, 0.30)
        quad = _pick(slug, "arcpos", 4)
        cx = w * (rnd.uniform(0.62, 0.88) if quad in (0, 1) else rnd.uniform(0.10, 0.34))
        cy = h * (rnd.uniform(0.14, 0.42) if quad in (0, 2) else rnd.uniform(0.58, 0.88))
        d.arc([cx - r, cy - r, cx + r, cy + r], rnd.randint(0, 360), rnd.randint(120, 300),
              fill=_hex(highlight) + (110 if light else 170,),
              width=max(2, int(w * 0.0035)))

    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return _grain(img, rnd, amount=4 if light else 7), pal


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


def _wash(img, tone: str, anchor: str):
    """Directional scrim that guarantees text contrast without flattening the art.

    A full-frame wash is what made every cover the same rectangle: it buried the
    background under one uniform slab. This ramps opacity towards wherever the
    type actually sits and leaves the opposite corner showing the artwork.
    """
    import numpy as np
    w, h = img.size
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]

    if anchor == "bl":
        m = (ys ** 0.85) * (1 - 0.55 * xs) + 0.25 * (1 - xs) * (1 - ys)
    elif anchor == "tl":
        m = ((1 - ys) ** 0.85) * (1 - 0.55 * xs) + 0.25 * (1 - xs) * ys
    elif anchor == "tr":
        m = ((1 - ys) ** 0.85) * (0.45 + 0.55 * xs)
    elif anchor == "br":
        m = (ys ** 0.85) * (0.45 + 0.55 * xs)
    elif anchor == "left":
        m = ((1 - xs) ** 0.75) * 0.95 + 0.15
    elif anchor == "band":                           # type at top and bottom
        m = np.maximum((1 - ys) ** 1.6, ys ** 1.6) * 0.95 + 0.10
        m = np.broadcast_to(m, (h, w))
    else:                                            # centred
        m = 0.55 + 0.45 * (np.abs(ys - 0.5) * 2) ** 2 * 0.3 + 0.0 * xs
        m = np.broadcast_to(m, (h, w))

    m = np.broadcast_to(m, (h, w)).astype("float32")
    if tone == "light":
        col, base, span, cap = (255, 255, 255), 40.0, 175.0, 215.0
    else:
        col, base, span, cap = (4, 10, 20), 26.0, 190.0, 234.0

    alpha = np.clip(base + span * m, 0, cap).astype("uint8")
    scrim = np.dstack([
        np.full((h, w), col[0], "uint8"),
        np.full((h, w), col[1], "uint8"),
        np.full((h, w), col[2], "uint8"),
        alpha,
    ])
    return Image.alpha_composite(img.convert("RGBA"),
                                 Image.fromarray(scrim, "RGBA")).convert("RGB")


def _inks(pal, tone: str):
    """(title, figure, accent) colours for this tone. Contrast is fixed here."""
    highlight = pal[3]
    if tone == "light":
        fig = "#0E7C90" if highlight.upper() == "#1EABC7" else "#0C3C60"
        return "#0B2942", fig, highlight
    return "#FFFFFF", highlight, highlight


# Six compositions. The old cover had exactly one, so every post in the archive
# resolved to the same shape at thumbnail size regardless of palette.
LAYOUTS = ["stack", "figure", "centred", "split", "topbar", "rule"]
_ANCHOR = {"stack": "bl", "figure": "left", "centred": "centre",
           "split": "left", "topbar": "band", "rule": "bl"}


def editorial_cover(post: dict, out_path: str, size=(1600, 900)):
    """
    Typographic cover built from the article's own headline and lead figure.

    Used when a post declares no `chart:` block. Unlike decorative art, this is
    never unrelated to the piece — every word on it comes from the piece.

    Layout, palette, motif and tone are each drawn from an independent hash of
    the slug, so a cover is reproducible for a given post but two posts rarely
    agree on more than one axis.
    """
    slug, category = post["slug"], post.get("category", "_default")
    tone = _tone(slug)
    layout = LAYOUTS[_pick(slug, "layout", len(LAYOUTS))]

    # Two layouts are built around the lead figure. A post whose takeaways carry
    # no bolded number would render them as an empty panel, so fall back.
    _fig_probe = lead_figure(post)
    if not _fig_probe and layout in ("figure", "split"):
        layout = "stack"

    img, pal = _canvas(slug, category, size, tone)
    highlight = pal[3]
    ink, fig_col, accent = _inks(pal, tone)
    w, h = size

    img = _wash(img, tone, _ANCHOR[layout])
    d = ImageDraw.Draw(img, "RGBA")
    pad = int(w * 0.055)
    shadow = (0, 0, 0, 130) if tone == "dark" else (255, 255, 255, 90)

    fig = lead_figure(post)
    title = str(post.get("title", ""))
    kicker = str(post.get("category_name") or category).upper()
    kf = _font("GeistMono-Regular.ttf", int(w * 0.0165))
    mark = _wordmark()
    mono = _font("GeistMono-Regular.ttf", int(w * 0.0135))

    def draw_kicker(x, y, centred=False):
        tw = d.textlength(kicker, font=kf)
        if centred:
            x -= (tw + 18) / 2
        d.rectangle([x, y + 4, x + 5, y + int(w * 0.019)], fill=_hex(accent))
        d.text((x + 18, y), kicker, font=kf, fill=_hex(accent) + (240,))

    def draw_lines(lines, f, fs, x, y, align="left"):
        for line in lines:
            lx = x
            if align == "centre":
                lx = x - d.textlength(line, font=f) / 2
            elif align == "right":
                lx = x - d.textlength(line, font=f)
            d.text((lx + 2, y + 2), line, font=f, fill=shadow)
            d.text((lx, y), line, font=f, fill=_hex(ink) + (252,))
            y += fs * 1.14
        return y

    def figure_font(target_frac, max_w):
        ff = _font("InstrumentSans-Bold.ttf", int(w * target_frac))
        fw = d.textlength(fig, font=ff)
        if fw > max_w:
            ff = _font("InstrumentSans-Bold.ttf", max(12, int(w * target_frac * max_w / fw)))
        return ff

    if layout == "figure" and fig:
        # Figure dominant: the number is the image.
        draw_kicker(pad, pad)
        ff = figure_font(0.175, w - pad * 2)
        fh = ff.size * 1.02
        fy = h * 0.30
        d.text((pad + 4, fy + 4), fig, font=ff, fill=shadow)
        d.text((pad, fy), fig, font=ff, fill=_hex(fig_col) + (255,))
        ry = fy + fh + int(h * 0.035)
        d.line([(pad, ry), (pad + int(w * 0.09), ry)], fill=_hex(accent) + (210,), width=4)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - pad * 2,
                            h - ry - pad * 1.4, int(w * 0.034), min_size=int(w * 0.019))
        draw_lines(lines, f, fs, pad, ry + int(h * 0.05))

    elif layout == "centred":
        draw_kicker(w / 2, pad, centred=True)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w * 0.80,
                            h * 0.34, int(w * 0.044), min_size=int(w * 0.021))
        block = len(lines) * fs * 1.14 + (h * 0.16 if fig else 0)
        y = (h - block) / 2 + h * 0.03
        y = draw_lines(lines, f, fs, w / 2, y, align="centre")
        if fig:
            d.line([(w / 2 - w * 0.045, y + h * 0.030), (w / 2 + w * 0.045, y + h * 0.030)],
                   fill=_hex(accent) + (210,), width=4)
            ff = figure_font(0.088, w * 0.82)
            fw = d.textlength(fig, font=ff)
            fy = y + h * 0.062
            d.text((w / 2 - fw / 2 + 3, fy + 3), fig, font=ff, fill=shadow)
            d.text((w / 2 - fw / 2, fy), fig, font=ff, fill=_hex(fig_col) + (255,))

    elif layout == "split":
        # Accent panel down the left, figure inside it, headline to the right.
        panel = int(w * 0.36)
        px = int(w * 0.045)
        inner = panel - px - int(w * 0.03)
        band = Image.new("RGBA", size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(band, "RGBA")
        bd.rectangle([0, 0, panel, h],
                     fill=_hex(highlight) + (34 if tone == "dark" else 60,))
        bd.line([(panel, 0), (panel, h)], fill=_hex(accent) + (170,), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        draw_kicker(px, pad)

        # Figures here are often long ("18 September 2026"), and forcing them
        # onto one line inside a 36%-wide panel shrank them to caption size.
        # Wrap instead, and centre the block against the headline opposite.
        if fig:
            gf, glines, gs = _fit(d, fig, "InstrumentSans-Bold.ttf", inner,
                                  h * 0.42, int(w * 0.062), min_size=int(w * 0.026))
            block = len(glines) * gs * 1.10
            fy = (h - block) / 2 + h * 0.02
            d.line([(px, fy - h * 0.052), (px + w * 0.055, fy - h * 0.052)],
                   fill=_hex(accent) + (215,), width=4)
            for line in glines:
                d.text((px + 3, fy + 3), line, font=gf, fill=shadow)
                d.text((px, fy), line, font=gf, fill=_hex(fig_col) + (255,))
                fy += gs * 1.10

        tx = panel + int(w * 0.05)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - tx - pad,
                            h * 0.56, int(w * 0.040), min_size=int(w * 0.020))
        draw_lines(lines, f, fs, tx, (h - len(lines) * fs * 1.14) / 2)

    elif layout == "topbar":
        draw_kicker(pad, pad)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - pad * 2,
                            h * 0.34, int(w * 0.044), min_size=int(w * 0.021))
        draw_lines(lines, f, fs, pad, pad + int(h * 0.10))
        if fig:
            ff = figure_font(0.098, w - pad * 2)
            fw = d.textlength(fig, font=ff)
            fy = h - pad - ff.size * 1.05
            d.text((w - pad - fw + 3, fy + 3), fig, font=ff, fill=shadow)
            d.text((w - pad - fw, fy), fig, font=ff, fill=_hex(fig_col) + (255,))
            d.line([(w - pad - w * 0.07, fy - h * 0.032), (w - pad, fy - h * 0.032)],
                   fill=_hex(accent) + (210,), width=4)

    elif layout == "rule":
        # Heavy vertical accent rule at the left margin, everything set against it.
        rx = int(w * 0.045)
        d.rectangle([rx, int(h * 0.16), rx + max(4, int(w * 0.005)), int(h * 0.84)],
                    fill=_hex(accent) + (225,))
        tx = rx + int(w * 0.035)
        draw_kicker(tx, pad)
        y_cursor = h - pad
        if fig:
            ff = figure_font(0.100, w - tx - pad)
            y_cursor = h - pad - ff.size * 1.05
            d.text((tx + 3, y_cursor + 3), fig, font=ff, fill=shadow)
            d.text((tx, y_cursor), fig, font=ff, fill=_hex(fig_col) + (255,))
            y_cursor -= int(h * 0.055)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - tx - pad,
                            max(h * 0.20, y_cursor - pad - h * 0.06),
                            int(w * 0.044), min_size=int(w * 0.021))
        draw_lines(lines, f, fs, tx, y_cursor - len(lines) * fs * 1.14)

    else:                                            # "stack" — the original
        draw_kicker(pad, pad)
        y_cursor = h - pad
        if fig:
            ff = figure_font(0.105, w - pad * 2)
            y_cursor = h - pad - ff.size * 1.05
            d.text((pad + 3, y_cursor + 3), fig, font=ff, fill=shadow)
            d.text((pad, y_cursor), fig, font=ff, fill=_hex(fig_col) + (255,))
            d.line([(pad, y_cursor - int(h * 0.035)),
                    (pad + int(w * 0.07), y_cursor - int(h * 0.035))],
                   fill=_hex(accent) + (200,), width=4)
            y_cursor -= int(h * 0.075)
        f, lines, fs = _fit(d, title, "InstrumentSans-Bold.ttf", w - pad * 2,
                            max(int(h * 0.20), y_cursor - pad - int(w * 0.05)),
                            int(w * 0.048), min_size=int(w * 0.022))
        draw_lines(lines, f, fs, pad, y_cursor - len(lines) * fs * 1.14)

    if mark:
        d.text((w - pad - d.textlength(mark, font=mono), pad), mark, font=mono,
               fill=(_hex(ink) + (150,)) if tone == "light" else (255, 255, 255, 165))

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
    pal = _palette(post.get("slug", ""), category, "dark")
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
        rec = photos.fetch(post, offline=bool(os.environ.get("BSB_OFFLINE")))
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
                site_name="BLUESTONES BPO", size=(1200, 630)):
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
