"""Subset JetBrains Mono into the few woff2 files the SVGs inline.

Run locally once (and again only if the source TTFs change). The tiny woff2
outputs are committed to the repo so the GitHub Action — which has no
fonttools — can base64-embed them at generation time.

    pip install fonttools brotli
    python scripts/build_fonts.py
"""
import os
from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")

# The 13-step brightness ramp the portrait draws with. Keep in sync with
# generate_portrait.RAMP.
RAMP = " .`:-=+*cs#%@"
BASIC_LATIN = "".join(chr(c) for c in range(0x20, 0x7F))


def subset_font(src, out, text, name):
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = []      # no ligatures/kerning needed
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = []
    opts.notdef_outline = False
    opts.recalc_bounds = True
    font = subset.load_font(os.path.join(FONTS, src), opts)
    ss = subset.Subsetter(options=opts)
    ss.populate(text=text)
    ss.subset(font)
    dst = os.path.join(FONTS, out)
    subset.save_font(font, dst, opts)
    font.close()
    print("{:<18} {:>4} glyphs  {:>6,} bytes  ({})".format(
        out, len(set(text)), os.path.getsize(dst), name))


def main():
    subset_font("JetBrainsMono-Regular.ttf", "ramp.woff2", RAMP, "portrait ramp")
    subset_font("JetBrainsMono-Regular.ttf", "mono.woff2", BASIC_LATIN, "regular")
    subset_font("JetBrainsMono-Bold.ttf", "mono-bold.woff2", BASIC_LATIN, "bold")
    total = sum(
        os.path.getsize(os.path.join(FONTS, f))
        for f in ("ramp.woff2", "mono.woff2", "mono-bold.woff2")
    )
    print("total embedded: {:,} bytes".format(total))


if __name__ == "__main__":
    main()
