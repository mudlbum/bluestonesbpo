#!/usr/bin/env python3
"""
Chart rendering for Bluestones BPO.

When a post declares a `chart:` block, its hero image is a real chart drawn from
the post's own figures — not decoration. Charts are rendered offline with
matplotlib in the site's own palette, so a reader can read the number off the
picture and find the same number in the text.

Front matter
------------
chart:
  type: line              # line | bar | grouped_bar
  title: "KOSPI, Jan-Aug 2026"
  y_label: "Index level"
  y_suffix: ""            # e.g. "%", "tn", "k" — appended to axis ticks
  source: "Korea Exchange"        # printed bottom-left; required
  annotate_last: true             # label the final point of each series
  series:
    - label: "KOSPI"
      points: [["Jan", 2400], ["Feb", 2680], ["Mar", 3120]]

A chart block that fails to validate raises ValueError, which fails the build —
a wrong chart is worse than no chart.
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.ticker import FuncFormatter          # noqa: E402

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "fonts")

# Matches the dark end of the site palette in static/style.css.
INK = "#eef1f6"
INK_2 = "#b3bccc"
INK_3 = "#8b95a8"
GRID = "#222a3d"
BG = "#0a0e1a"
PANEL = "#111726"

# Bluestones categories, keyed to the accents in site.config.json so a chart
# reads as the same publication as the page it sits on.
ACCENTS = {
    "accounting":  ["#39729B", "#6EA4CA", "#D1E0EB"],
    "payroll":     ["#1EABC7", "#7FD4E4", "#D1E0EB"],
    "tax":         ["#1EABC7", "#6FD6E8", "#EFF1F2"],
    "entity":      ["#6EA4CA", "#A9CBE4", "#EFF1F2"],
    "compliance":  ["#39729B", "#A9CBE4", "#D1E0EB"],
    "operations":  ["#39729B", "#7FD4E4", "#D1E0EB"],
    "_default":    ["#1EABC7", "#6EA4CA", "#D1E0EB"],
}


# The wordmark stamped under every chart. Read from config rather than
# hardcoded — the fork this generator came from printed futureofkorea.com.
def _wordmark() -> str:
    try:
        cfg = json.load(open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "site.config.json"), encoding="utf-8"))
        return cfg["domain"].split("//")[-1].rstrip("/").split("/")[0]
    except Exception:                                   # noqa: BLE001
        return ""

_FAMILY: str | None = None


def _register_fonts() -> str:
    """Use the repo's bundled fonts so charts match the site's typography."""
    global _FAMILY
    if _FAMILY is not None:
        return _FAMILY
    _FAMILY = "DejaVu Sans"
    try:
        from matplotlib import font_manager
        for fn in ("InstrumentSans-Regular.ttf", "InstrumentSans-Bold.ttf",
                   "GeistMono-Regular.ttf"):
            path = os.path.join(FONT_DIR, fn)
            if os.path.exists(path):
                font_manager.fontManager.addfont(path)
        names = {f.name for f in font_manager.fontManager.ttflist}
        for want in ("Instrument Sans", "Geist Mono"):
            if want in names:
                _FAMILY = want
                break
    except Exception:                                  # noqa: BLE001
        pass
    return _FAMILY


def validate(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise ValueError("chart: must be a mapping")
    kind = spec.get("type", "line")
    if kind not in ("line", "bar", "grouped_bar"):
        raise ValueError(f"chart.type {kind!r} is not one of line, bar, grouped_bar")
    if not str(spec.get("source") or "").strip():
        raise ValueError("chart.source is required — name where the numbers came from")
    series = spec.get("series") or []
    if not series:
        raise ValueError("chart.series is empty")
    for s in series:
        pts = s.get("points") or []
        if len(pts) < 2:
            raise ValueError(f"chart series {s.get('label')!r} needs at least 2 points")
        for p in pts:
            if not (isinstance(p, (list, tuple)) and len(p) == 2):
                raise ValueError(f"chart series {s.get('label')!r} has a malformed point: {p!r}")
            try:
                float(p[1])
            except (TypeError, ValueError):
                raise ValueError(
                    f"chart series {s.get('label')!r} has a non-numeric value: {p[1]!r}") from None


def _fmt(suffix: str):
    def f(v, _pos):
        if abs(v) >= 1000 and float(v).is_integer():
            return f"{int(v):,}{suffix}"
        if float(v).is_integer():
            return f"{int(v)}{suffix}"
        return f"{v:g}{suffix}"
    return FuncFormatter(f)


def render(spec: dict, category: str, out_path: str, size=(1600, 900), *,
           headline: str | None = None) -> None:
    """Draw the chart to `out_path`. Size is in pixels."""
    validate(spec)
    family = _register_fonts()
    colours = ACCENTS.get(category, ACCENTS["_default"])

    dpi = 100
    fig, ax = plt.subplots(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    series = spec["series"]
    kind = spec.get("type", "line")
    labels = [str(p[0]) for p in series[0]["points"]]
    x = range(len(labels))

    if kind == "line":
        for i, s in enumerate(series):
            ys = [float(p[1]) for p in s["points"]]
            c = colours[i % len(colours)]
            ax.plot(range(len(ys)), ys, color=c, linewidth=3.2, solid_capstyle="round",
                    marker="o", markersize=5, markerfacecolor=BG,
                    markeredgewidth=2, markeredgecolor=c, label=str(s.get("label", "")),
                    zorder=3)
            if spec.get("annotate_last", True) and ys:
                ax.annotate(f"{ys[-1]:,g}", (len(ys) - 1, ys[-1]),
                            textcoords="offset points", xytext=(10, 0),
                            color=c, fontsize=17, fontweight="bold",
                            fontfamily=family, va="center", zorder=4)
    elif kind == "bar":
        s = series[0]
        ys = [float(p[1]) for p in s["points"]]
        peak = max(range(len(ys)), key=lambda i: ys[i]) if ys else -1
        ax.bar(x, ys, color=[colours[0] if i == peak else GRID for i in range(len(ys))],
               edgecolor="none", width=0.62, zorder=3,
               label=str(s.get("label", "")))
    else:  # grouped_bar
        n = len(series)
        width = 0.78 / n
        for i, s in enumerate(series):
            ys = [float(p[1]) for p in s["points"]]
            off = (i - (n - 1) / 2) * width
            ax.bar([v + off for v in x], ys, width=width,
                   color=colours[i % len(colours)], edgecolor="none",
                   label=str(s.get("label", "")), zorder=3)

    # Leave room on the right for the end-of-series value label, which would
    # otherwise be clipped by the axes edge.
    if kind == "line" and spec.get("annotate_last", True):
        ax.set_xlim(-0.35, (len(labels) - 1) + 0.62)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=16, color=INK_2, fontfamily=family)
    ax.tick_params(axis="y", labelsize=16, colors=INK_2, length=0)
    ax.tick_params(axis="x", length=0, pad=10)
    for lbl in ax.get_yticklabels():
        lbl.set_fontfamily(family)
    ax.yaxis.set_major_formatter(_fmt(str(spec.get("y_suffix") or "")))

    ax.grid(axis="y", color=GRID, linewidth=1.1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    title = spec.get("title") or headline or ""
    if title:
        ax.set_title(str(title), color=INK, fontsize=27, fontweight="bold",
                     fontfamily=family, loc="left", pad=22)
    if spec.get("y_label"):
        ax.set_ylabel(str(spec["y_label"]), color=INK_3, fontsize=15, fontfamily=family,
                      labelpad=12)

    if len(series) > 1 or kind == "grouped_bar":
        leg = ax.legend(loc="upper left", frameon=False, fontsize=16,
                        labelcolor=INK_2, ncols=min(len(series), 3))
        for t in leg.get_texts():
            t.set_fontfamily(family)

    mark = _wordmark()
    footer = f"Source: {spec['source']}" + (f"   ·   {mark}" if mark else "")
    fig.text(0.012, 0.022, footer,
             color=INK_3, fontsize=14, fontfamily=family)

    fig.subplots_adjust(left=0.085, right=0.955, top=0.86, bottom=0.13)
    fig.savefig(out_path, facecolor=BG, dpi=dpi)
    plt.close(fig)
