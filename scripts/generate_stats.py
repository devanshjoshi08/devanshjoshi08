"""Draw four stat SVGs from the GitHub GraphQL API — standard library only.

Outputs: stats.svg (hero total + weekly sparkline), streak.svg (current +
longest streak), langs.svg (top languages), year.svg (contribution heatmap).

Two determinism rules keep the nightly diff empty unless something real
changed:
  1. The contribution window is pinned to whole UTC days, so two runs minutes
     apart bucket days into the same weeks.
  2. Repositories are filtered to PUBLIC, so language totals do not depend on
     whether a personal token (which sees private repos) or the workflow
     token ran the script.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

import svgkit as kit
from svgkit import esc

API = "https://api.github.com/graphql"
REST = "https://api.github.com/"

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    name
    login
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays { date contributionCount }
        }
      }
    }
    repositories(first:100, privacy:PUBLIC, ownerAffiliations:OWNER,
                 isFork:false, orderBy:{field:PUSHED_AT, direction:DESC}) {
      nodes {
        name
        defaultBranchRef { name }
      }
    }
  }
}
"""

# Language colors (GitHub Linguist palette) for the dots in langs.svg.
LANG_COLORS = {
    "SystemVerilog": "#DAE1C2", "Verilog": "#b2b7f8", "VHDL": "#adb2cb",
    "Tcl": "#e4cc98", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Java": "#b07219", "Python": "#3572A5", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "MATLAB": "#e16737", "Assembly": "#6E4C13",
    "GDScript": "#355570", "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "R": "#198CE7", "SQL": "#e38c00",
}
DEFAULT_LANG_COLOR = "#8b949e"

# --- honest language accounting --------------------------------------------
# GitHub's language stats count every recognized byte, including imported and
# generated code (a committed Unity Library/ can bury real work under a
# language never actually written). These stats instead walk each repository's
# file tree, skip vendored and generated paths, and total only hand-written
# source by extension.

VENDOR = re.compile(
    r"(^|/)("
    r"library/packagecache|packagecache|node_modules|bower_components|vendor|"
    r"third[_-]?party|pods|\.venv|venv|virtualenv|dist|build|out|obj|target|"
    r"\.git|__pycache__|packages|assets/samples|samples~|library|temp|logs|"
    r"\.vs|\.idea|coverage|externals?|deps"
    r")(/|$)", re.I)

GENERATED = re.compile(
    r"(\.min\.(js|css)$|\.designer\.cs$|[.-]lock\.|package-lock\.json$|"
    r"yarn\.lock$|\.pb\.go$|_pb2\.py$|\.g\.dart$|\.map$)", re.I)

# Extension to language. Programming and hardware description languages only;
# prose, config, and data formats are intentionally left out.
EXT_LANG = {
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".ino": "C++",
    ".sv": "SystemVerilog", ".svh": "SystemVerilog",
    ".v": "Verilog", ".vh": "Verilog",
    ".vhd": "VHDL", ".vhdl": "VHDL",
    ".py": "Python", ".java": "Java", ".cs": "C#",
    ".js": "JavaScript", ".mjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".m": "MATLAB", ".mlx": "MATLAB",
    ".tcl": "Tcl", ".gd": "GDScript",
    ".s": "Assembly", ".asm": "Assembly",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".swift": "Swift",
    ".kt": "Kotlin", ".sql": "SQL", ".r": "R",
}


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def fetch(login, token):
    today = dt.datetime.now(dt.timezone.utc).date()
    frm = dt.datetime.combine(today - dt.timedelta(days=364), dt.time(0, 0, 0),
                              tzinfo=dt.timezone.utc)
    to = dt.datetime.combine(today, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
    payload = json.dumps({
        "query": QUERY,
        "variables": {
            "login": login,
            "from": frm.isoformat(),
            "to": to.isoformat(),
        },
    }).encode("utf-8")
    req = urllib.request.Request(API, data=payload, headers={
        "Authorization": "bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "profile-self-generator",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "errors" in body:
        raise SystemExit("GraphQL errors: " + json.dumps(body["errors"], indent=2))
    return body["data"]["user"]


def flatten_days(cal):
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort(key=lambda x: x[0])
    return days


def week_totals(cal):
    return [sum(d["contributionCount"] for d in w["contributionDays"])
            for w in cal["weeks"]]


def fmt_range(a, b):
    da = dt.date.fromisoformat(a)
    db = dt.date.fromisoformat(b)
    if da == db:
        return da.strftime("%b %-d, %Y") if os.name != "nt" else da.strftime("%b %d, %Y").replace(" 0", " ")
    same_year = da.year == db.year
    left = da.strftime("%b %d").replace(" 0", " ")
    right = db.strftime("%b %d, %Y").replace(" 0", " ")
    if not same_year:
        left = da.strftime("%b %d, %Y").replace(" 0", " ")
    return "{} - {}".format(left, right)


def streaks(days):
    """Return (current, longest) each as dict(len, start, end)."""
    longest = {"len": 0, "start": None, "end": None}
    run = 0
    run_start = None
    for date, count in days:
        if count > 0:
            run += 1
            if run == 1:
                run_start = date
            if run > longest["len"]:
                longest = {"len": run, "start": run_start, "end": date}
        else:
            run = 0
            run_start = None

    # Current streak: walk back from the most recent day. A zero-count *today*
    # does not break the streak (the day is not over yet) — skip it and count
    # from yesterday.
    cur = {"len": 0, "start": None, "end": None}
    idx = len(days) - 1
    if idx >= 0 and days[idx][1] == 0:
        idx -= 1
    end = None
    while idx >= 0 and days[idx][1] > 0:
        if end is None:
            end = days[idx][0]
        cur["start"] = days[idx][0]
        cur["len"] += 1
        idx -= 1
    cur["end"] = end
    return cur, longest


def _rest(path, token):
    req = urllib.request.Request(REST + path, headers={
        "Authorization": "bearer " + token,
        "User-Agent": "profile-self-generator",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ext(path):
    i = path.rfind(".")
    return path[i:].lower() if i >= 0 else ""


def top_languages(login, repos, token, n=6):
    """Total hand-written source bytes per language across the public repos.

    Walks each repository's file tree and counts blob sizes by extension,
    skipping vendored and generated paths, so imported libraries never inflate
    a language.
    """
    by_bytes = {}
    for repo in repos:
        ref = repo.get("defaultBranchRef") or {}
        branch = ref.get("name")
        if not branch:
            continue
        try:
            tree = _rest("repos/{}/{}/git/trees/{}?recursive=1".format(
                login, repo["name"], branch), token)
        except Exception:
            continue
        for node in tree.get("tree", []):
            if node.get("type") != "blob":
                continue
            path = node["path"]
            if VENDOR.search(path) or GENERATED.search(path):
                continue
            lang = EXT_LANG.get(_ext(path))
            if not lang:
                continue
            by_bytes[lang] = by_bytes.get(lang, 0) + node.get("size", 0)
    ordered = sorted(by_bytes.items(), key=lambda x: -x[1])[:n]
    total = sum(v for _, v in ordered) or 1
    return [(name, size, size / total) for name, size in ordered]


# --------------------------------------------------------------------------
# svg building blocks
# --------------------------------------------------------------------------
def prelude(extra_css=""):
    faces = kit.font_faces(
        ("mono.woff2", "JBM", 400),
        ("mono-bold.woff2", "JBM", 700),
    )
    base = (
        "text{font-family:'JBM','SFMono-Regular',ui-monospace,Menlo,Consolas,monospace}"
        ".ink{fill:var(--ink)}.muted{fill:var(--muted)}.accent{fill:var(--accent)}"
        ".green{fill:var(--green)}.track{fill:var(--track)}.faint{stroke:var(--faint)}"
        ".b{font-weight:700}"
    )
    return "<style>{}\n{}\n{}\n{}</style>".format(
        faces, kit.theme_vars(), base, extra_css)


def open_svg(w, h, css=""):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" role="img">'.format(w=w, h=h) + prelude(css)
    )


def heading(x, y, label):
    """A lowercase mono section label with a hairline rule to the right."""
    return (
        '<text x="{x}" y="{y}" class="muted b" font-size="11" '
        'letter-spacing="2.5">{lbl}</text>'.format(x=x, y=y, lbl=esc(label.upper()))
    )


# --------------------------------------------------------------------------
# 1. hero: total + weekly sparkline
# --------------------------------------------------------------------------
def render_stats(user, out):
    cal = user["contributionsCollection"]["contributionCalendar"]
    total = cal["totalContributions"]
    weeks = week_totals(cal)
    W, H = 480, 172
    pad = 22
    svg = [open_svg(W, H)]

    svg.append(heading(pad, 30, "public contributions / 52 weeks"))
    svg.append('<text x="{}" y="92" class="ink b" font-size="52">{}</text>'.format(
        pad, "{:,}".format(total)))
    svg.append('<text x="{}" y="118" class="muted" font-size="12">'
               'public commits, PRs, issues &amp; reviews &#183; private work not shown</text>'.format(pad))

    # Sparkline across the bottom.
    gx, gy, gw, gh = pad, 132, W - 2 * pad, 26
    mx = max(weeks) or 1
    n = len(weeks)
    pts = []
    for i, v in enumerate(weeks):
        px = gx + (gw * i / (n - 1 if n > 1 else 1))
        py = gy + gh - (gh * v / mx)
        pts.append((px, py))
    line = " ".join("{:.1f},{:.1f}".format(px, py) for px, py in pts)
    area = "{:.1f},{:.1f} ".format(gx, gy + gh) + line + " {:.1f},{:.1f}".format(gx + gw, gy + gh)
    svg.append('<polygon points="{}" fill="var(--accent)" opacity="0.10"/>'.format(area))
    svg.append('<polyline points="{}" fill="none" stroke="var(--accent)" '
               'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'.format(line))
    lx, ly = pts[-1]
    svg.append('<circle cx="{:.1f}" cy="{:.1f}" r="3" fill="var(--accent)"/>'.format(lx, ly))

    svg.append("</svg>")
    kit.write(out, "".join(svg))


# --------------------------------------------------------------------------
# 2. streaks
# --------------------------------------------------------------------------
def render_streak(user, out):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = flatten_days(cal)
    cur, longest = streaks(days)
    W, H = 480, 150
    svg = [open_svg(W, H)]
    cols = [(0, "current streak", cur, "green"),
            (W // 2, "longest streak", longest, "accent")]
    svg.append('<line x1="{x}" y1="34" x2="{x}" y2="{b}" class="faint" '
               'stroke-width="1"/>'.format(x=W // 2, b=H - 22))
    for ox, label, s, cls in cols:
        cx = ox + W // 4
        svg.append(heading(ox + 22, 30, label))
        svg.append('<text x="{}" y="92" text-anchor="middle" class="{} b" '
                   'font-size="46">{}</text>'.format(cx, cls, s["len"]))
        svg.append('<text x="{}" y="112" text-anchor="middle" class="muted" '
                   'font-size="11">{}</text>'.format(cx, "days" if s["len"] != 1 else "day"))
        if s["start"]:
            rng = fmt_range(s["start"], s["end"])
            svg.append('<text x="{}" y="132" text-anchor="middle" class="muted" '
                       'font-size="10.5">{}</text>'.format(cx, esc(rng)))
    svg.append("</svg>")
    kit.write(out, "".join(svg))


# --------------------------------------------------------------------------
# 3. languages
# --------------------------------------------------------------------------
def render_langs(langs, out):
    W = 480
    pad = 22
    top = 46
    row_h = 30
    H = top + row_h * len(langs) + 14
    svg = [open_svg(W, H)]
    svg.append(heading(pad, 30, "most used languages / public repos"))

    bar_x = pad + 118
    bar_w = W - bar_x - pad - 44
    y = top
    for name, size, frac in langs:
        color = LANG_COLORS.get(name, DEFAULT_LANG_COLOR)
        cy = y + 11
        svg.append('<circle cx="{}" cy="{}" r="5" fill="{}"/>'.format(pad + 5, cy, color))
        svg.append('<text x="{}" y="{}" class="ink" font-size="12.5">{}</text>'.format(
            pad + 16, cy + 4, esc(name)))
        svg.append('<rect x="{}" y="{}" width="{}" height="8" rx="4" '
                   'class="track"/>'.format(bar_x, cy - 4, bar_w))
        svg.append('<rect x="{}" y="{}" width="{:.1f}" height="8" rx="4" '
                   'fill="{}"/>'.format(bar_x, cy - 4, max(bar_w * frac, 3), color))
        svg.append('<text x="{}" y="{}" text-anchor="end" class="muted" '
                   'font-size="11">{:.0f}%</text>'.format(W - pad, cy + 4, frac * 100))
        y += row_h
    svg.append("</svg>")
    kit.write(out, "".join(svg))


# --------------------------------------------------------------------------
# 4. year heatmap
# --------------------------------------------------------------------------
def render_year(user, out):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    mx = max(counts) or 1

    def level(c):
        if c <= 0:
            return 0
        if c >= mx:
            return 4
        q = c / mx
        return 1 + min(3, int(q * 4))

    cell, gap = 11, 3
    step = cell + gap
    pad = 22
    top = 44
    grid_w = len(weeks) * step
    W = max(480, pad * 2 + grid_w)
    H = top + 7 * step + 26
    css = "".join(
        ".l{} {{fill:var(--l{})}}".format(i, i) for i in range(5)
    )
    svg = [open_svg(W, H, css)]
    svg.append(heading(pad, 30, "contribution activity / past year"))

    # Month labels along the top.
    last_month = None
    for wi, wk in enumerate(weeks):
        first = wk["contributionDays"][0]["date"]
        m = dt.date.fromisoformat(first).strftime("%b")
        if m != last_month:
            svg.append('<text x="{}" y="{}" class="muted" font-size="9.5">{}</text>'.format(
                pad + wi * step, top - 6, m))
            last_month = m

    for wi, wk in enumerate(weeks):
        # Align partial first week so weekdays line up (pad from the top).
        offset = 7 - len(wk["contributionDays"]) if wi == 0 else 0
        for di, d in enumerate(wk["contributionDays"]):
            row = di + offset
            x = pad + wi * step
            yy = top + row * step
            svg.append('<rect x="{}" y="{}" width="{}" height="{}" rx="2.5" '
                       'class="l{}"><title>{}: {}</title></rect>'.format(
                           x, yy, cell, cell, level(d["contributionCount"]),
                           d["date"], d["contributionCount"]))

    # Less / more legend.
    lx = W - pad - (5 * step + 62)
    ly = H - 16
    svg.append('<text x="{}" y="{}" class="muted" font-size="10">Less</text>'.format(lx, ly + 9))
    for i in range(5):
        svg.append('<rect x="{}" y="{}" width="{}" height="{}" rx="2.5" '
                   'class="l{}"/>'.format(lx + 34 + i * step, ly, cell, cell, i))
    svg.append('<text x="{}" y="{}" class="muted" font-size="10">More</text>'.format(
        lx + 34 + 5 * step + 4, ly + 9))
    svg.append("</svg>")
    kit.write(out, "".join(svg))


def main():
    login = os.environ.get("GH_LOGIN", "devanshjoshi08")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN (or GH_TOKEN) in the environment.")
    user = fetch(login, token)
    langs = top_languages(login, user["repositories"]["nodes"], token)
    render_stats(user, os.path.join(kit.ROOT, "stats.svg"))
    render_streak(user, os.path.join(kit.ROOT, "streak.svg"))
    render_langs(langs, os.path.join(kit.ROOT, "langs.svg"))
    render_year(user, os.path.join(kit.ROOT, "year.svg"))


if __name__ == "__main__":
    main()
