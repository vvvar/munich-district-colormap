#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB_ID = os.environ.get("NOTION_DB_ID", "9680bc6275e249198244df1fc2bc7a08")
TOKEN = os.environ.get("NOTION_TOKEN", "")

HEX = {"Red": "#e6194b", "Yellow": "#ffe119", "Green": "#3cb44b"}
GREY = "#d3d9e0"
PAD = 60


def fetch_colors():
    if not TOKEN:
        return {}
    colors = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        req = urllib.request.Request(
            "https://api.notion.com/v1/databases/%s/query" % DB_ID,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer %s" % TOKEN,
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            data = json.load(r)
        for row in data["results"]:
            props = row["properties"]
            nr = props["Nr"]["number"]
            sel = props["Color"]["select"]
            url = props["Map"]["url"]
            if nr is not None:
                colors[str(int(nr))] = {
                    "color": sel["name"] if sel else None,
                    "map": url or None,
                }
        if data.get("has_more"):
            cursor = data["next_cursor"]
        else:
            break
    return colors


def main():
    data = json.load(open(os.path.join(HERE, "paths.json")))
    feats = data["features"]
    colors = fetch_colors()
    vb = (
        data["xmin"] - PAD,
        data["ymin"] - PAD,
        data["xmax"] - data["xmin"] + 2 * PAD,
        data["ymax"] - data["ymin"] + 2 * PAD,
    )

    groups = []
    for i, f in enumerate(feats):
        ref = f["ref"]
        info = colors.get(ref, {})
        fill = HEX.get(info.get("color"), GREY)
        g = '<g class="g{i}"><path class="p{i}" d="{d}"><title>{name}</title></path>' \
            '<text class="lbl lbl{i}" x="{cx:.1f}" y="{cy:.1f}">{ref}</text>' \
            '<text class="nm nm{i}" x="{cx:.1f}" y="{cy:.1f}">{name}</text></g>'
        if info.get("map"):
            g = '<g class="g{i}"><a href="{href}" target="_blank" rel="noopener">' \
                '<path class="p{i}" d="{d}"><title>{name}</title></path></a>' \
                '<text class="lbl lbl{i}" x="{cx:.1f}" y="{cy:.1f}">{ref}</text>' \
                '<text class="nm nm{i}" x="{cx:.1f}" y="{cy:.1f}">{name}</text></g>'.format(
                href=info["map"], i=i, d=f["d"], name=f["name"],
                cx=f["cx"], cy=f["cy"], ref=ref)
        else:
            g = g.format(i=i, d=f["d"], name=f["name"],
                         cx=f["cx"], cy=f["cy"], ref=ref)
        groups.append(g)
    svg = (
        '<svg viewBox="%.1f %.1f %.1f %.1f" role="img" '
        'aria-label="Munich district map">\n' % vb
        + "\n".join(groups)
        + "\n</svg>"
    )

    rules = []
    for i, f in enumerate(feats):
        info = colors.get(f["ref"], {})
        rules.append(".p%d{fill:%s}" % (i, HEX.get(info.get("color"), GREY)))
    css = (
        "html,body{margin:0;height:100%;overflow:hidden;background:#eef1f4;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2328}"
        ".l{position:fixed;inset:0;display:flex}"
        ".map{flex:1;position:relative;min-width:0;background:#cfe3ea}"
        ".map svg{position:absolute;inset:0;width:100%;height:100%}"
        "path{stroke:#374151;stroke-width:1;fill-opacity:.85;transition:fill-opacity .12s}"
        ".g:hover path{stroke:#111827;stroke-width:1.8;fill-opacity:1}"
        ".lbl{font:600 10px sans-serif;fill:#111;pointer-events:none;text-anchor:middle}"
        ".nm{font:700 9.5px sans-serif;fill:#111;opacity:0;pointer-events:none;text-anchor:middle;"
        "paint-order:stroke;stroke:#fff;stroke-width:2.5}"
        ".g:hover .lbl{opacity:0}.g:hover .nm{opacity:1}"
        ".maptitle{position:absolute;top:10px;left:10px;z-index:2;background:rgba(255,255,255,.92);"
        "border:1px solid #e2e2e7;border-radius:8px;padding:6px 10px;font-size:12px;"
        "box-shadow:0 2px 8px rgba(0,0,0,.08)}"
        ".panel{width:250px;flex:none;background:#fff;border-left:1px solid #e2e2e7;overflow-y:auto;"
        "display:flex;flex-direction:column}"
        ".panel header{padding:12px 12px 8px;border-bottom:1px solid #e2e2e7}"
        ".panel h1{margin:0;font-size:15px}"
        ".panel header p{margin:4px 0 0;font-size:11px;color:#6b7280}"
        ".row{display:flex;align-items:center;gap:8px;padding:4px 10px}"
        ".row:hover{background:#f3f4f6}"
        ".dot{width:14px;height:14px;flex:none;border-radius:50%;border:1px solid rgba(0,0,0,.12)}"
        ".row .nm{flex:1;font-size:11.5px;line-height:1.15;min-width:0}"
        ".row a{flex:none;font-size:10px;color:#2563eb;text-decoration:none;font-weight:600}"
        ".legend{display:flex;gap:12px;padding:8px 12px;border-bottom:1px solid #e2e2e7;font-size:10.5px}"
        ".legend span{display:flex;align-items:center;gap:5px}"
        ".panel footer{padding:10px 12px;font-size:10.5px;color:#6b7280;border-top:1px solid #e2e2e7;margin-top:auto}"
        + "".join(rules)
    )

    rows = []
    for i, f in enumerate(feats):
        info = colors.get(f["ref"], {})
        color = info.get("color")
        hexc = HEX.get(color, GREY)
        rows.append(
            '<div class="row"><span class="dot" style="background:%s"></span>'
            '<span class="nm">%d. %s</span>%s</div>'
            % (
                hexc,
                int(f["ref"]),
                f["name"],
                ('<a href="%s" target="_blank" rel="noopener">Maps</a>' % info["map"])
                if info.get("map") else "",
            )
        )
    panel = (
        '<header><h1>M\u00fcnchen</h1>'
        '<p>Colors come from the \u201cMunich Districts Colors\u201d table '
        'below. Open a district in Google Maps via the Map link in that table '
        'or the Maps button here.</p></header>'
        + '<div class="legend"><span style="color:#e6194b">\u25cf No go</span>'
        '<span style="color:#ffe119">\u25cf Explore</span>'
        '<span style="color:#3cb44b">\u25cf Like</span></div>'
        + "".join(rows)
        + "<footer>25 Stadtbezirke \u00b7 auto-synced from the table</footer>"
    )

    html = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>Munich Desired Districts Map</title>\n<style>\n%s\n</style>\n"
        "</head>\n<body>\n<div class=\"l\">\n<div class=\"map\">\n"
        '<div class="maptitle">M\u00fcnchen &middot; 25 Stadtbezirke</div>\n%s\n</div>\n'
        '<aside class="panel">%s</aside>\n</div>\n</body>\n</html>\n'
        % (css, svg, panel)
    )

    out = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    with open(out, "w") as fh:
        fh.write(html)
    print("wrote", out, "KB:", round(len(html.encode("utf-8")) / 1024, 1))


if __name__ == "__main__":
    main()
