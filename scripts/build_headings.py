"""Render header.svg — the one heading in the user's own typeface.

Image headings are the only way to put a custom font on README heading text
(GitHub strips <style>, class, and inline SVG from markdown). Static, no API,
standard library only. Run locally and commit the result.

    python scripts/build_headings.py
"""
import os

import svgkit as kit

NAME = "Devansh Joshi"
SUB = "Electrical and Computer Engineering (ECE) @ UT Austin"


def main():
    W, H = 700, 96
    faces = kit.font_faces(
        ("mono.woff2", "JBM", 400),
        ("mono-bold.woff2", "JBM", 700),
    )
    style = "<style>{f}\n{t}\ntext{{font-family:'JBM',monospace}}" \
            ".ink{{fill:var(--ink)}}.muted{{fill:var(--muted)}}" \
            ".accent{{fill:var(--accent)}}</style>".format(
                f=faces, t=kit.theme_vars())
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" role="img" aria-label="{name}, {sub}">'.format(
            w=W, h=H, name=kit.esc(NAME), sub=kit.esc(SUB)),
        style,
        '<text x="0" y="44" class="ink" font-size="34" font-weight="700" '
        'letter-spacing="1">{}</text>'.format(kit.esc(NAME)),
        '<text x="2" y="72" class="muted" font-size="13" '
        'letter-spacing="0.5">{}</text>'.format(kit.esc(SUB)),
        '<rect x="2" y="84" width="120" height="3" rx="1.5" class="accent"/>',
        "</svg>",
    ]
    kit.write(os.path.join(kit.ROOT, "header.svg"), "".join(svg))


if __name__ == "__main__":
    main()
