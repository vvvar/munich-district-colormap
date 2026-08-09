#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB_ID = os.environ.get("NOTION_DB_ID") or "9680bc6275e249198244df1fc2bc7a08"
TOKEN = os.environ.get("NOTION_TOKEN", "")

HEX = {"Red": "#e6194b", "Yellow": "#ffe119", "Green": "#3cb44b"}
GREY = "#d3d9e0"

TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ATTRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'


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


def centroid(coords):
    # area-weighted centroid over all rings; good enough for labels
    def ring_centroid(ring):
        a = 0.0
        cx = cy = 0.0
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            cross = x1 * y2 - x2 * y1
            a += cross
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
        if abs(a) < 1e-12:
            return ring[0][0], ring[0][1]
        a /= 2
        return cx / (6 * a), cy / (6 * a)

    if coords and isinstance(coords[0][0][0], list):
        # MultiPolygon: coords = list of polygons, each a list of rings
        rings = [r for poly in coords for r in poly]
    else:
        rings = coords
    tot = 0.0
    cx = cy = 0.0
    for ring in rings:
        x, y = ring_centroid(ring)
        area = abs(0.5 * sum(ring[i][0] * ring[(i + 1) % len(ring)][1] -
                             ring[(i + 1) % len(ring)][0] * ring[i][1]
                             for i in range(len(ring))))
        tot += area
        cx += x * area
        cy += y * area
    if tot == 0:
        return ring_centroid(rings[0])
    return cx / tot, cy / tot


def compact(geojson):
    # round coords to 6 decimals to shrink the payload
    for f in geojson["features"]:
        g = f["geometry"]
        rings = g["coordinates"] if g["type"] == "Polygon" else [
            r for p in g["coordinates"] for r in p]
        for ring in rings:
            for pt in ring:
                pt[0] = round(pt[0], 6)
                pt[1] = round(pt[1], 6)
    return geojson


def main():
    data = json.load(open(os.path.join(HERE, "stadtbezirke.geojson")))
    compact(data)
    colors = fetch_colors()
    geojson = json.dumps(data, ensure_ascii=True, separators=(",", ":"))

    feats = data["features"]
    labels = []
    rows = []
    for i, f in enumerate(feats):
        ref = f["properties"]["ref"]
        info = colors.get(ref, {})
        color = info.get("color")
        hexc = HEX.get(color, GREY)
        x, y = centroid(f["geometry"]["coordinates"])
        labels.append('{ref:"%s",name:"%s",x:%.6f,y:%.6f,c:"%s"}' % (
            ref, f["properties"]["name"], x, y, hexc))
        rows.append(
            '<div class="row" data-ref="%s"><span class="dot" style="background:%s"></span>'
            '<span class="rname">%d. %s</span>%s</div>'
            % (
                ref,
                hexc,
                int(ref),
                f["properties"]["name"],
                ('<a href="%s" target="_blank" rel="noopener">Maps</a>' % info["map"])
                if info.get("map") else "",
            )
        )
    labels = ",".join(labels)

    css = (
        "html,body{margin:0;height:100%;overflow:hidden;font-family:-apple-system,"
        "BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2328}"
        ".l{position:fixed;inset:0;display:flex}"
        ".map{flex:1;position:relative;min-width:0}"
        "#map{position:absolute;inset:0}"
        ".maptitle{position:absolute;top:10px;left:10px;z-index:1000;background:rgba(255,255,255,.92);"
        "border:1px solid #e2e2e7;border-radius:8px;padding:6px 10px;font-size:12px;"
        "box-shadow:0 2px 8px rgba(0,0,0,.08)}"
        ".legend{position:absolute;top:48px;left:10px;z-index:1000;background:rgba(255,255,255,.92);"
        "border:1px solid #e2e2e7;border-radius:8px;padding:6px 10px;font-size:11px;"
        "box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;gap:12px}"
        ".legend span{display:flex;align-items:center;gap:5px}"
        ".panel{width:250px;flex:none;background:#fff;border-left:1px solid #e2e2e7;overflow-y:auto;"
        "display:flex;flex-direction:column}"
        ".panel header{padding:12px 12px 8px;border-bottom:1px solid #e2e2e7}"
        ".panel h1{margin:0;font-size:15px}"
        ".panel header p{margin:4px 0 0;font-size:11px;color:#6b7280}"
        ".row{display:flex;align-items:center;gap:8px;padding:4px 10px;cursor:pointer}"
        ".row:hover{background:#f3f4f6}"
        ".dot{width:14px;height:14px;flex:none;border-radius:50%;border:1px solid rgba(0,0,0,.12)}"
        ".rname{flex:1;font-size:11.5px;line-height:1.15;min-width:0;color:#1f2328;font-weight:600}"
        ".row a{flex:none;font-size:10px;color:#2563eb;text-decoration:none;font-weight:600}"
        ".panel footer{padding:10px 12px;font-size:10.5px;color:#6b7280;border-top:1px solid #e2e2e7;margin-top:auto}"
        ".num{position:absolute;transform:translate(-50%,-50%);font:600 9.5px sans-serif;"
        "color:#111;text-shadow:0 1px 2px rgba(255,255,255,.9);pointer-events:none;z-index:500;"
        "white-space:nowrap;text-align:center}"
        ".leaflet-pane{z-index:auto}.leaflet-control-container{z-index:auto}"
    )

    js = (
        "var GEO=%s;\n"
        "var LABELS=[%s];\n"
        "var map=L.map('map').setView([48.1374,11.5755],12);\n"
        "L.tileLayer('%s',{maxZoom:19,attribution:'%s'}).addTo(map);\n"
        "var layer=L.geoJSON(GEO,{\n"
        "  style:function(f){return {color:'#374151',weight:1,fillColor:null,fillOpacity:.55}}\n"
        "}).addTo(map);\n"
        "var byRef={};\n"
        "layer.eachLayer(function(l){var p=l.feature.properties;byRef[p.ref]=l;"
        "l.options.color='#374151';l.options.weight=1;l.options.fillColor=COLOR[p.ref]||'%s';"
        "l.options.fillOpacity=.55;l.setStyle(l.options);"
        "l.bindTooltip('<b>'+p.ref+'. '+p.name+'</b>',{sticky:true});"
        "l.on('mouseover',function(){l.setStyle({weight:1.8,color:'#111827',fillOpacity:.8});});"
        "l.on('mouseout',function(){l.setStyle({weight:1,color:'#374151',fillOpacity:.55});});});\n"
        "LABELS.forEach(function(b){L.marker([b.y,b.x],{icon:L.divIcon({className:'num',html:b.name,iconSize:[0,0]}),"
        "interactive:false}).addTo(map);});\n"
        "document.querySelectorAll('.row').forEach(function(r){r.addEventListener('click',function(){\n"
        "var l=byRef[r.dataset.ref];if(l)map.fitBounds(l.getBounds());});});\n"
        "map.fitBounds(layer.getBounds(),{padding:[40,40]});\n"
        % (geojson, labels, TILES, ATTRIB, GREY)
    )

    panel = (
        '<header><h1>M\u00fcnchen</h1>'
        '<p>Colors come from the \u201cMunich Districts Colors\u201d table '
        'below. Click a row to zoom to that district.</p></header>'
        + '<div class="legend" style="position:static;border:none;box-shadow:none;padding:8px 12px;'
        'border-bottom:1px solid #e2e2e7">'
        '<span style="color:#e6194b">\u25cf No go</span>'
        '<span style="color:#ffe119">\u25cf Explore</span>'
        '<span style="color:#3cb44b">\u25cf Like</span></div>'
        + "".join(rows)
        + "<footer>25 Stadtbezirke \u00b7 auto-synced from the table</footer>"
    )

    html = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>Munich Desired Districts Map</title>\n"
        "<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" "
        "integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\" crossorigin=\"\">\n"
        "<style>\n%s\n</style>\n"
        "</head>\n<body>\n<div class=\"l\">\n<div class=\"map\">\n"
        '<div id="map"></div>\n'
        '<div class="maptitle">M\u00fcnchen &middot; 25 Stadtbezirke</div>\n'
        '<div class="legend"><span style="color:#e6194b">\u25cf No go</span>'
        '<span style="color:#ffe119">\u25cf Explore</span>'
        '<span style="color:#3cb44b">\u25cf Like</span></div>\n'
        "</div>\n<aside class=\"panel\">%s</aside>\n</div>\n"
        "<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" "
        "integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\" crossorigin=\"\"></script>\n"
        "<script>\nvar COLOR=%s;\n%s</script>\n</body>\n</html>\n"
        % (css, panel, json.dumps({f["properties"]["ref"]: HEX.get(colors.get(f["properties"]["ref"], {}).get("color"), GREY)
                                    for f in feats}, separators=(",", ":")), js)
    )

    out = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    with open(out, "w") as fh:
        fh.write(html)
    print("wrote", out, "KB:", round(len(html.encode("utf-8")) / 1024, 1))


if __name__ == "__main__":
    main()
