"""Turn a headshot into a self-typing ASCII portrait SVG.

Run locally (it needs rembg/opencv/pillow, and rembg downloads a ~176 MB
model on first use). The generated portrait.svg is committed to the repo; the
nightly workflow never touches it.

    pip install pillow numpy opencv-python-headless rembg onnxruntime
    python scripts/generate_portrait.py            # uses assets/photo.*
    python scripts/generate_portrait.py path/to/photo.jpg

Photo tips (they matter more than any parameter):
  * side light at ~45 degrees, everything else off — ASCII draws with shadow
  * crop tight, chin to just above the hair, subject filling the frame
  * 1200px+ and a plain background; do not wear black on a dark wall
"""
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image

import svgkit as kit

# 13-step ramp, light -> dense. Keep in sync with build_fonts.RAMP.
RAMP = " .`:-=+*cs#%@"

COLS = 90            # columns of characters; below ~88 the face muddies
ROW_ASPECT = 0.48    # monospace cells are ~2x tall as wide
CHAR_W = 7.74        # advance width at font-size 12.9 (exactly 0.600 em)
FONT_SIZE = 12.9
CHAR_H = CHAR_W / ROW_ASPECT   # 16.125, keeps the portrait's aspect ratio
GAMMA = 1.7          # darkening curve; what makes brows/glasses/lips survive
STAGGER = 0.09       # seconds between rows starting to type
CHAR_TIME = 0.012    # seconds per character within a row


def find_photo(argv):
    if len(argv) > 1:
        return argv[1]
    for pattern in ("assets/photo.*", "assets/*.jpg", "assets/*.jpeg",
                    "assets/*.png", "assets/*.webp"):
        hits = sorted(glob.glob(os.path.join(kit.ROOT, pattern)))
        hits = [h for h in hits if not h.lower().endswith(".svg")]
        if hits:
            return hits[0]
    return None


def cut_out(path):
    """Remove the background so everything outside the subject maps to blank.

    Skip this and the background fills with '@' and drowns the portrait.
    """
    try:
        from rembg import remove
    except Exception as exc:  # pragma: no cover - depends on local install
        print("rembg unavailable ({}); using the photo as-is.".format(exc))
        img = Image.open(path).convert("RGB")
        return np.array(img)
    with open(path, "rb") as fh:
        cut = remove(fh.read())
    rgba = Image.open(__import__("io").BytesIO(cut)).convert("RGBA")
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return np.array(Image.alpha_composite(white, rgba).convert("RGB"))


def to_ascii(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Smooth skin while keeping edges.
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=55, sigmaSpace=55)
    # Local contrast per tile — global autocontrast leaves a flat face as one tone.
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    h, w = gray.shape
    rows = max(1, round(COLS * (h / w) * ROW_ASPECT))
    small = cv2.resize(gray, (COLS, rows), interpolation=cv2.INTER_AREA)

    # Darkening curve — the fix that keeps thin features from washing out.
    norm = (small.astype(np.float32) / 255.0) ** GAMMA

    # Bright pixel -> blank end of the ramp; dark pixel -> dense end.
    idx = np.clip(np.round((1.0 - norm) * (len(RAMP) - 1)), 0, len(RAMP) - 1).astype(int)
    lines = ["".join(RAMP[v] for v in row) for row in idx]
    return lines


def build_svg(lines):
    ncols = max((len(ln) for ln in lines), default=COLS)
    width = round(ncols * CHAR_W)
    top = CHAR_H                       # first baseline
    height = round(len(lines) * CHAR_H + CHAR_H * 0.4)

    faces = kit.font_faces(("ramp.woff2", "JBMramp", 400))
    style = (
        "<style>{faces}\n{theme}\n"
        "text{{font-family:'JBMramp',monospace;font-size:{fs}px;"
        "white-space:pre;fill:var(--ink)}}"
        ".cur{{fill:var(--accent)}}</style>"
    ).format(faces=faces, theme=kit.theme_vars(), fs=FONT_SIZE)

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" role="img" '
        'aria-label="ASCII self-portrait">'.format(w=width, h=height),
        style,
        "<defs>",
    ]
    body = []
    for i, line in enumerate(lines):
        y = top + i * CHAR_H
        stripped = line.rstrip(" ")
        vis = len(stripped)
        if vis == 0:
            continue
        full_w = vis * CHAR_W
        dur = max(0.25, vis * CHAR_TIME)
        begin = i * STAGGER
        clip_id = "c{}".format(i)
        # Each row is revealed by a rect wiping from 0 to its visible width.
        out.append(
            '<clipPath id="{cid}"><rect x="0" y="{ry:.2f}" width="0" '
            'height="{rh:.2f}"><animate attributeName="width" from="0" '
            'to="{fw:.2f}" dur="{dur:.2f}s" begin="{beg:.2f}s" '
            'calcMode="linear" fill="freeze"/></rect></clipPath>'.format(
                cid=clip_id, ry=y - CHAR_H, rh=CHAR_H,
                fw=full_w, dur=dur, beg=begin)
        )
        text = (
            '<g clip-path="url(#{cid})"><text x="0" y="{y:.2f}" '
            'xml:space="preserve">{txt}</text></g>'.format(
                cid=clip_id, y=y, txt=kit.esc(stripped))
        )
        # A block cursor rides the wipe edge, then vanishes when the row finishes.
        cursor = (
            '<rect class="cur" x="0" y="{ry:.2f}" width="{cw:.2f}" '
            'height="{rh:.2f}" opacity="0">'
            '<animate attributeName="x" from="0" to="{fw:.2f}" dur="{dur:.2f}s" '
            'begin="{beg:.2f}s" calcMode="linear" fill="freeze"/>'
            '<set attributeName="opacity" to="0.85" begin="{beg:.2f}s"/>'
            '<set attributeName="opacity" to="0" begin="{end:.2f}s"/>'
            '</rect>'.format(
                ry=y - CHAR_H * 0.92, cw=CHAR_W, rh=CHAR_H * 0.92,
                fw=full_w, dur=dur, beg=begin, end=begin + dur)
        )
        body.append(text)
        body.append(cursor)

    out.append("</defs>")
    out.extend(body)
    out.append("</svg>")
    return "".join(out)


def main():
    photo = find_photo(sys.argv)
    if not photo or not os.path.exists(photo):
        sys.exit(
            "No photo found. Drop a headshot at assets/photo.jpg (or pass a "
            "path), then rerun. See the header of this file for photo tips."
        )
    print("source:", os.path.relpath(photo, kit.ROOT))
    rgb = cut_out(photo)
    lines = to_ascii(rgb)
    svg = build_svg(lines)
    kit.write(os.path.join(kit.ROOT, "portrait.svg"), svg)
    print("{} columns x {} rows".format(
        max(len(l) for l in lines), len(lines)))


if __name__ == "__main__":
    main()
