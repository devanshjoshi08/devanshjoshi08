"""Shared helpers for the profile SVGs: font embedding + a single theme.

Runtime-safe: standard library only, so the GitHub Action can import this
without installing anything. Font subsetting (build_fonts.py) is the only
step that needs third-party packages, and it runs locally, not in CI.
"""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "fonts")

# One palette, two themes. Every SVG references these via CSS classes, so the
# graphics follow the reader's OS light/dark setting with no per-file tweaking.
LIGHT = {
    "ink":    "#1f2328",  # primary text / portrait fill
    "muted":  "#59636e",  # secondary text
    "accent": "#0969da",  # signature highlight (GitHub blue)
    "green":  "#1a7f37",  # streaks / positive
    "track":  "#eaeef2",  # empty bars, gridlines
    "faint":  "#d1d9e0",  # hairlines
    "l0": "#ebedf0", "l1": "#9be9a8", "l2": "#40c463", "l3": "#30a14e", "l4": "#216e39",
}
DARK = {
    "ink":    "#e6edf3",
    "muted":  "#9198a1",
    "accent": "#4493f8",
    "green":  "#3fb950",
    "track":  "#21262d",
    "faint":  "#30363d",
    "l0": "#161b22", "l1": "#0e4429", "l2": "#006d32", "l3": "#26a641", "l4": "#39d353",
}


def _b64_font(filename):
    path = os.path.join(FONT_DIR, filename)
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def font_faces(*specs):
    """Build @font-face rules from (file, family, weight) specs.

    An external font URL cannot work inside an SVG loaded through <img> —
    browsers refuse subresource fetches for image documents — so every face
    is inlined as a base64 woff2 data URI. Missing files are skipped so the
    scripts still run before build_fonts.py has been executed.
    """
    rules = []
    for filename, family, weight in specs:
        path = os.path.join(FONT_DIR, filename)
        if not os.path.exists(path):
            continue
        data = _b64_font(filename)
        rules.append(
            "@font-face{{font-family:'{fam}';font-style:normal;font-weight:{w};"
            "font-display:block;src:url(data:font/woff2;base64,{d}) format('woff2');}}".format(
                fam=family, w=weight, d=data
            )
        )
    return "\n".join(rules)


def theme_vars():
    """CSS custom properties: light on :root, dark via prefers-color-scheme.

    These live inside the SVG's own <style>, which GitHub does not sanitise
    (only inline HTML in the markdown is stripped), so the media query runs.
    """
    def block(selector, palette):
        body = ";".join("--{}:{}".format(k, v) for k, v in palette.items())
        return "{}{{{}}}".format(selector, body)
    return (
        block(":root", LIGHT)
        + "@media(prefers-color-scheme:dark){"
        + block(":root", DARK)
        + "}"
    )


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def write(path, svg):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    print("wrote", os.path.relpath(path, ROOT), "({:,} bytes)".format(len(svg.encode("utf-8"))))
