# -*- coding: utf-8 -*-
"""Turn the Blender render into a labelled figure.

    python annotate_3d.py

Reads renders/aerial.png and renders/anchors.json (written by build_3d.py, which
projects each 3D anchor point into screen space), then draws leader lines out to
label columns in the margins. Labels never overlap the render, so nothing that
matters is covered.

Output: renders/aerial_labelled.png
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REN = os.path.join(HERE, "renders")

NAVY = (23, 54, 93)
TEAL = (28, 140, 135)
GREY = (110, 123, 128)
RULE = (198, 206, 209)
INK = (21, 39, 44)
WHITE = (255, 255, 255)

MARGIN = 640          # width of each label column
TOP = 150             # title band
BOTTOM = 92           # caption band


def font(size, bold=False):
    names = ("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


# The Blender script keeps its labels ASCII-only so the .py stays portable;
# proper typography is restored here, where the figure is actually drawn.
TYPO = [
    ("m2", "m²"), ("m3", "m³"),
    ("120-180 C", "120–180 °C"), ("~30 C", "~30 °C"),
    ("Tier 1 - ", "Tier 1 — "), ("Tier 2 - ", "Tier 2 — "),
    ("Al-Fe", "Al–Fe"), ("2 x 0.52", "2 × 0.52"),
]


def typo(text):
    for a, b in TYPO:
        text = text.replace(a, b)
    return text


def wrap(draw, text, f, width):
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=f) <= width or not line:
                line = trial
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    src = Image.open(os.path.join(REN, "aerial.png")).convert("RGB")
    anchors = json.load(open(os.path.join(REN, "anchors.json"), encoding="utf-8"))["aerial"]
    W, H = src.size

    canvas = Image.new("RGB", (W + MARGIN * 2, H + TOP + BOTTOM), WHITE)
    canvas.paste(src, (MARGIN, TOP))
    d = ImageDraw.Draw(canvas)

    f_title, f_sub = font(46, True), font(24)
    f_lab, f_note, f_cap = font(24, True), font(21), font(20)

    # ---------- title band ----------
    d.text((MARGIN, 42), "PHYTO-RECLAIM reference unit", font=f_title, fill=NAVY)
    d.text((MARGIN, 100),
           "50 m³/day onshore train · 725 m² plot (37.6 × 19.3 m) · "
           "generated from the dimensions in Tables 1–3, not drawn by eye",
           font=f_sub, fill=GREY)

    # ---------- split labels left / right of the scene ----------
    items = [(k, v) for k, v in anchors.items() if v["visible"]]
    left = sorted([i for i in items if i[1]["x"] < 1100], key=lambda i: i[1]["y"])
    right = sorted([i for i in items if i[1]["x"] >= 1100], key=lambda i: i[1]["y"])

    def column(entries, side):
        if not entries:
            return
        # even vertical spacing down the margin, independent of anchor crowding
        top, bot = TOP + 60, TOP + H - 60
        step = (bot - top) / max(len(entries), 1)
        for i, (label, a) in enumerate(entries):
            cy = top + step * (i + 0.5)
            head, *rest = typo(label).split("\n")
            note = " ".join(rest)

            pad = 26
            box_w = MARGIN - pad * 2
            tx = pad if side == "left" else MARGIN + W + pad
            lines = wrap(d, head, f_lab, box_w)
            nlines = wrap(d, note, f_note, box_w) if note else []
            th = len(lines) * 30 + len(nlines) * 26
            ty = cy - th / 2

            for j, ln in enumerate(lines):
                d.text((tx, ty + j * 30), ln, font=f_lab, fill=NAVY)
            for j, ln in enumerate(nlines):
                d.text((tx, ty + len(lines) * 30 + j * 26), ln, font=f_note, fill=GREY)

            # leader: from the label edge, along the margin, then to the anchor
            ax, ay = a["x"] + MARGIN, a["y"] + TOP
            ex = (MARGIN - pad + 4) if side == "left" else (MARGIN + W + pad - 4)
            mid = ex + (60 if side == "left" else -60)
            d.line([(ex, cy), (mid, cy)], fill=RULE, width=2)
            d.line([(mid, cy), (ax, ay)], fill=RULE, width=2)
            r = 6
            d.ellipse([ax - r, ay - r, ax + r, ay + r], outline=TEAL, width=3, fill=WHITE)

    column(left, "left")
    column(right, "right")

    # ---------- caption band ----------
    cy = TOP + H + 26
    d.line([(MARGIN, cy - 12), (MARGIN + W, cy - 12)], fill=RULE, width=2)
    d.text((MARGIN, cy),
           "Subsurface-flow wetland: the water table sits inside the 0.60 m media bed, "
           "so no open water is shown. Screening-level layout —",
           font=f_cap, fill=GREY)
    d.text((MARGIN, cy + 28),
           "final siting still needs a geotechnical survey and site-specific hydraulics. "
           "Equipment sizes are pre-FEED design-basis estimates.",
           font=f_cap, fill=GREY)

    out = os.path.join(REN, "aerial_labelled.png")
    canvas.save(out)
    print(f"Saved: {out}  ({canvas.width}x{canvas.height} px)")
    print(f"  labelled {len(items)} items  ({len(left)} left, {len(right)} right)")


if __name__ == "__main__":
    main()
