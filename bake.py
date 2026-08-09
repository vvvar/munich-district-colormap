#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB_ID = os.environ.get("NOTION_DB_ID") or "9680bc6275e249198244df1fc2bc7a08"
TOKEN = os.environ.get("NOTION_TOKEN", "")

HEX = {"Red": "#e6194b", "Yellow": "#ffe119", "Green": "#3cb44b", "Grey": "#d3d9e0"}

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
            note = "".join(t.get("plain_text", "") for t in props["Notes"]["rich_text"]).strip()
            if nr is not None:
                colors[str(int(nr))] = {
                    "color": sel["name"] if sel else None,
                    "map": url or None,
                    "note": note or None,
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
        hexc = HEX.get(color)
        dot = hexc or "transparent"
        label_c = hexc or "#9aa1a9"
        x, y = centroid(f["geometry"]["coordinates"])
        labels.append('{ref:"%s",name:"%s",x:%.6f,y:%.6f,c:"%s"}' % (
            ref, f["properties"]["name"], x, y, label_c))
        rows.append(
            '<div class="row" data-ref="%s"><div class="rh"><span class="dot" '
            'style="background:%s"></span>'
            '<span class="rname">%d. %s</span>%s</div>%s</div>'
            % (
                ref,
                dot,
                int(ref),
                f["properties"]["name"],
                ('<a href="%s" target="_blank" rel="noopener">Maps</a>' % info["map"])
                if info.get("map") else "",
                ('<div class="note">%s</div>' % info["note"]) if info.get("note") else "",
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
         "border:1px solid #e2e2e7;border-radius:8px;padding:6px 10px;font-size:12.5px;"
        'box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;flex-wrap:wrap;gap:8px 12px}'
        ".legend span{display:flex;align-items:center;gap:5px}"
        ".panel{width:360px;position:absolute;top:0;right:0;bottom:0;background:#fff;"
        "border-left:1px solid #e2e2e7;overflow-y:auto;display:flex;flex-direction:column;"
        "transform:translateX(100%);transition:transform .25s ease;z-index:1100;"
        "box-shadow:-4px 0 12px rgba(0,0,0,.08)}"
        ".panel.open{transform:translateX(0)}"
        ".panel header{padding:14px 46px 10px 14px;border-bottom:1px solid #e2e2e7;position:relative}"
        ".panel h1{margin:0;font-size:18px}"
        ".panel header p{margin:5px 0 0;font-size:12.5px;color:#6b7280}"
        ".panel .close{position:absolute;top:10px;right:10px;width:32px;height:32px;border:none;"
        "background:none;cursor:pointer;font-size:17px;color:#6b7280;border-radius:6px;display:flex;"
        "align-items:center;justify-content:center}"
        ".panel .close:hover{background:#f3f4f6;color:#1f2328}"
        ".row{padding:5px 10px;cursor:pointer}"
        ".row:hover{background:#f3f4f6}"
        ".row.active{background:#eef2ff}"
        ".rh{display:flex;align-items:center;gap:9px}"
        ".dot{width:16px;height:16px;flex:none;border-radius:50%;border:1px solid rgba(0,0,0,.12)}"
        ".rname{flex:1;font-size:13.5px;line-height:1.2;min-width:0;color:#1f2328;font-weight:600}"
        ".row a{flex:none;font-size:11.5px;color:#2563eb;text-decoration:none;font-weight:600}"
        ".note{display:none;margin:3px 0 2px 27px;font-size:12.5px;line-height:1.4;color:#6b7280}"
        ".row.active .note{display:block}"
        ".panel footer{padding:11px 14px;font-size:12px;color:#6b7280;border-top:1px solid #e2e2e7;margin-top:auto}"
        ".sortbar{display:flex;align-items:center;gap:8px;padding:8px 12px;"
        "border-bottom:1px solid #e2e2e7;font-size:12.5px;color:#6b7280;background:#fafafa}"
        ".sortbar select{flex:1;font:600 13px sans-serif;color:#1f2328;padding:5px 8px;"
        "border:1px solid #e2e2e7;border-radius:6px;background:#fff;cursor:pointer}"
        ".num{position:absolute;transform:translate(-50%,-50%);font:600 9.5px sans-serif;"
        "color:#111;text-shadow:0 1px 2px rgba(255,255,255,.9);pointer-events:none;z-index:500;"
        "white-space:nowrap;text-align:center}"
        ".locbtn{position:absolute;right:10px;bottom:10px;z-index:1000;width:44px;height:44px;"
        "background:#fff;border:1px solid #e2e2e7;border-radius:9px;cursor:pointer;display:flex;"
        "align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.12);"
        "color:#1f2328;font-size:22px;line-height:1;transition:right .25s ease}"
        ".burger{position:absolute;top:10px;right:10px;z-index:1000;width:44px;height:44px;"
        "background:#fff;border:1px solid #e2e2e7;border-radius:9px;cursor:pointer;display:flex;"
        "align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.12);"
        "color:#1f2328;font-size:22px;line-height:1}"
        ".burger:hover,.locbtn:hover{background:#f3f4f6}"
        ".burger:active,.locbtn:active{background:#e5e7eb}"
        ".locbtn .spin{display:none;width:14px;height:14px;border:2px solid #c7cbd1;"
        "border-top-color:#1f2328;border-radius:50%;animation:locspin .8s linear infinite}"
        ".locbtn.loading .glyph{display:none}.locbtn.loading .spin{display:block}"
        "@keyframes locspin{to{transform:rotate(360deg)}}"
        ".toast{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);z-index:1000;"
        "background:rgba(31,35,40,.92);color:#fff;font-size:11px;padding:5px 12px;border-radius:6px;"
        "display:none}"
        ".leaflet-pane{z-index:auto}.leaflet-control-container{z-index:auto}"
    )

    js = (
        "var GEO=%s;\n"
        "var LABELS=[%s];\n"
        "var map=L.map('map').setView([48.1374,11.5755],12);\n"
        "L.tileLayer('%s',{maxZoom:19,attribution:'%s'}).addTo(map);\n"
        "var layer=L.geoJSON(GEO,{\n"
        "  style:function(f){return {color:'#374151',weight:1,fillColor:null,fillOpacity:.35}}\n"
        "}).addTo(map);\n"
        "var byRef={};var activeRef=null;\n"
        "function selectRow(ref){activeRef=(activeRef===ref)?null:ref;"
        "document.querySelectorAll('.row').forEach(function(r){"
        "r.classList.toggle('active',r.dataset.ref===activeRef);});}\n"
        "layer.eachLayer(function(l){var p=l.feature.properties;byRef[p.ref]=l;"
        "l.options.color='#374151';l.options.weight=1;l.options.fillColor=COLOR[p.ref]||'transparent';"
        "l.options.fillOpacity=.35;l.setStyle(l.options);"
        "l.bindTooltip('<b>'+p.ref+'. '+p.name+'</b>',{sticky:true});"
        "l.on('mouseover',function(){l.setStyle({weight:1.8,color:'#111827',fillOpacity:.55});});"
        "l.on('mouseout',function(){l.setStyle({weight:1,color:'#374151',fillOpacity:.35});});"
        "l.on('click',function(){selectRow(p.ref);});});\n"
        "LABELS.forEach(function(b){L.marker([b.y,b.x],{icon:L.divIcon({className:'num',html:b.name,iconSize:[0,0]}),"
        "interactive:false}).addTo(map);});\n"
        "document.querySelectorAll('.row').forEach(function(r){r.addEventListener('click',function(){\n"
        "var l=byRef[r.dataset.ref];selectRow(r.dataset.ref);if(l)map.fitBounds(l.getBounds());});});\n"
        "var RATING={'#3cb44b':0,'#ffe119':1,'#e6194b':2,'#d3d9e0':3,'':4};\n"
        "function sortRows(mode){var rows=Array.prototype.slice.call(document.querySelectorAll('.row'));"
        "rows.sort(function(a,b){var an=parseInt(a.dataset.ref,10),bn=parseInt(b.dataset.ref,10);"
        "if(mode==='name'){var na=a.querySelector('.rname').textContent.replace(/^\\d+\\.\\s*/,''),"
        "nb=b.querySelector('.rname').textContent.replace(/^\\d+\\.\\s*/,'');"
        "var c=na.localeCompare(nb,'en');return c||an-bn;}"
        "if(mode==='rating'){var ra=RATING.hasOwnProperty(COLOR[a.dataset.ref])?RATING[COLOR[a.dataset.ref]]:4,"
        "rb=RATING.hasOwnProperty(COLOR[b.dataset.ref])?RATING[COLOR[b.dataset.ref]]:4;"
        "return (ra-rb)||(an-bn);}"
        "return an-bn;});"
        "var list=document.getElementById('districts');"
        "rows.forEach(function(r){list.appendChild(r);});}\n"
        "document.getElementById('sort').addEventListener('change',function(){"
        "sortRows(this.value);});\n"
        "sortRows('nr');\n"
        "var locDot=null,locAcc=null,toastTimer=null;\n"
        "var panel=document.getElementById('panel'),burger=document.getElementById('burger');\n"
        "var locbtn=document.getElementById('locbtn');\n"
        "function setPanel(open){panel.classList.toggle('open',open);"
        "locbtn.style.right=open?'370px':'10px';"
        "panel.setAttribute('aria-hidden',open?'false':'true');"
        "burger.setAttribute('aria-expanded',open?'true':'false');}\n"
        "burger.addEventListener('click',function(){setPanel(!panel.classList.contains('open'));});\n"
        "document.getElementById('panelclose').addEventListener('click',function(){setPanel(false);});\n"
        "document.addEventListener('keydown',function(e){if(e.key==='Escape')setPanel(false);});\n"
        "function showToast(msg){var t=document.getElementById('toast');t.textContent=msg;"
        "t.style.display='block';clearTimeout(toastTimer);"
        "toastTimer=setTimeout(function(){t.style.display='none';},4000);}\n"
        "function setLocating(on){document.getElementById('locbtn').classList.toggle('loading',on);}\n"
        "document.getElementById('locbtn').addEventListener('click',function(){\n"
        "if(!navigator.geolocation){showToast('Geolocation not supported by this browser');return;}\n"
        "setLocating(true);\n"
        "navigator.geolocation.getCurrentPosition(function(pos){\n"
        "setLocating(false);\n"
        "var ll=[pos.coords.latitude,pos.coords.longitude];\n"
        "if(!locDot){locAcc=L.circle(ll,{radius:pos.coords.accuracy,color:'#2563eb',"
        "weight:1,fillColor:'#3b82f6',fillOpacity:.15}).addTo(map);"
        "locDot=L.circleMarker(ll,{radius:7,color:'#fff',weight:2,fillColor:'#2563eb',"
        "fillOpacity:1}).addTo(map);}\n"
        "else{locAcc.setLatLng(ll).setRadius(pos.coords.accuracy);locDot.setLatLng(ll);}\n"
        "map.setView(ll,Math.max(map.getZoom(),14));\n"
        "},function(err){\n"
        "setLocating(false);\n"
        "var msg=err.code===1?'Location permission denied':'Location unavailable';\n"
        "showToast(msg);},{enableHighAccuracy:true,timeout:15000,maximumAge:30000});});\n"
        "map.fitBounds(layer.getBounds(),{padding:[40,40]});\n"
        % (geojson, labels, TILES, ATTRIB)
    )

    panel = (
        '<header><h1>M\u00fcnchen</h1>'
        '<p>Colors come from the \u201cMunich Districts Colors\u201d table '
        'below. Click a row to zoom to that district.</p>'
        '<button class="close" id="panelclose" aria-label="Close districts list">\u2715</button></header>'
        + '<div class="legend" style="position:static;border:none;box-shadow:none;padding:8px 12px;'
        'border-bottom:1px solid #e2e2e7">'
        '<span style="color:#e6194b">\u25cf No go</span>'
        '<span style="color:#ffe119">\u25cf Compromise</span>'
        '<span style="color:#d3d9e0">\u25cf Explore</span>'
        '<span style="color:#3cb44b">\u25cf Like</span></div>'
        + '<div class="sortbar"><label for="sort">Sort by</label><select id="sort">'
        '<option value="nr">District number</option>'
        '<option value="name">Alphabetical</option>'
        '<option value="rating">Rating</option></select></div>'
        + '<div id="districts">' + "".join(rows) + "</div>"
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
        '<span style="color:#ffe119">\u25cf Compromise</span>'
        '<span style="color:#d3d9e0">\u25cf Explore</span>'
        '<span style="color:#3cb44b">\u25cf Like</span></div>\n'
        '<button class="burger" id="burger" title="Districts list" '
        'aria-label="Open districts list" aria-expanded="false">\u2630</button>\n'
        '<button class="locbtn" id="locbtn" title="Show my location" '
        'aria-label="Show my location"><span class="glyph">\u25ce</span>'
        '<span class="spin"></span></button>\n'
        '<div class="toast" id="toast"></div>\n'
        "</div>\n<aside class=\"panel\" id=\"panel\" aria-hidden=\"true\">%s</aside>\n</div>\n"
        "<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" "
        "integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\" crossorigin=\"\"></script>\n"
        "<script>\nvar COLOR=%s;\n%s</script>\n</body>\n</html>\n"
        % (css, panel, json.dumps({f["properties"]["ref"]: HEX.get(colors.get(f["properties"]["ref"], {}).get("color")) or ""
                                    for f in feats}, separators=(",", ":")), js)
    )

    out = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    with open(out, "w") as fh:
        fh.write(html)
    print("wrote", out, "KB:", round(len(html.encode("utf-8")) / 1024, 1))


if __name__ == "__main__":
    main()
