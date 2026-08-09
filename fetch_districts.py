#!/usr/bin/env python3
"""Fetch Munich's official sub-district boundaries (Stadtbezirksteile) as
GeoJSON and attach community names from OpenStreetMap.

Two sources are combined:

  1. Official: GeodatenService München WFS layer `gsm_wfs:vablock_bezirksteil`
     (~110 real administrative polygons). The city only exposes a numeric code
     (`bt_nummer`, e.g. "09.1") and an area for each one - there is no official
     name field.
  2. OpenStreetMap: named suburb/quarter/neighbourhood centroids (e.g.
     "Neuhausen", "Nymphenburg"). OSM has no polygon boundaries for these, so
     each OSM name is assigned to the official polygon that contains its
     centroid.

Output:
  - munich_bezirksteile_named.geojson : 110 features, WGS84
  - munich_districts_detail.md         : human-readable table

Only the Python standard library is used. The WFS reprojects server-side to
EPSG:4326, so no pyproj is needed.
"""

import json
import math
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

WFS_BASE = "https://geoportal.muenchen.de/geoserver/gsm_wfs/ows"
OVERLAPS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]

STADTBEZIRKE_NAMES = {
    1: "Altstadt-Lehel", 2: "Ludwigsvorstadt-Isarvorstadt", 3: "Maxvorstadt",
    4: "Schwabing-West", 5: "Au-Haidhausen", 6: "Sendling",
    7: "Sendling-Westpark", 8: "Schwanthalerhöhe", 9: "Neuhausen-Nymphenburg",
    10: "Moosach", 11: "Milbertshofen-Am Hart", 12: "Schwabing-Freimann",
    13: "Bogenhausen", 14: "Berg am Laim", 15: "Trudering-Riem",
    16: "Ramersdorf-Perlach", 17: "Obergiesing-Fasangarten", 18: "Untergiesing-Harlaching",
    19: "Thalkirchen-Obersendling-Forstenried-Fürstenried-Solln", 20: "Hadern",
    21: "Pasing-Obermenzing", 22: "Aubing-Lochhausen-Langwied", 23: "Allach-Untermenzing",
    24: "Feldmoching-Hasenbergl", 25: "Laim",
}

NAME_PRIORITY = {"suburb": 0, "quarter": 1, "neighbourhood": 2}


def http_json(url, headers=None, timeout=120):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_bezirksteile():
    """Official sub-district polygons, already reprojected to WGS84."""
    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "typeName": "gsm_wfs:vablock_bezirksteil",
        "outputFormat": "application/json",
        "srsName": "urn:ogc:def:crs:EPSG::4326",
    }
    url = WFS_BASE + "?" + urllib.parse.urlencode(params)
    return http_json(url)


def overpass(query, attempts=3):
    for i in range(attempts):
        for base in OVERLAPS:
            try:
                return http_json(base + "?" + urllib.parse.urlencode(
                    {"data": query}), timeout=60)
            except Exception:
                continue
        time.sleep(5 * (i + 1))
    raise RuntimeError("Overpass unreachable after %d attempts" % attempts)


def fetch_osm_names():
    """Named OSM suburb/quarter/neighbourhood centroids in Munich.

    In Munich these places are mapped as plain nodes (there are no way or
    relation boundaries for them), so a node-only query keeps the Overpass
    response cheap and fast.
    """
    q = ('[out:json][timeout:60];'
         'area["name:de"="München"]["boundary"="administrative"]["admin_level"="6"]->.m;'
         'node(area.m)["place"~"^(suburb|quarter|neighbourhood)$"];'
         'out center;')
    data = overpass(q)
    out = []
    for e in data.get("elements", []):
        name = e.get("tags", {}).get("name")
        place = e.get("tags", {}).get("place")
        if not name or place not in NAME_PRIORITY:
            continue
        c = e.get("center")
        lat = c["lat"] if c else e.get("lat")
        lon = c["lon"] if c else e.get("lon")
        if lat is None or lon is None:
            continue
        out.append({"name": name, "place": place, "lat": lat, "lon": lon})
    return out


def point_in_poly(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygon_contains(x, y, geom):
    """True if point (x=lon, y=lat) is inside a Polygon/MultiPolygon geometry."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        if point_in_poly(x, y, poly[0]):
            return True
    return False


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


def borough_of(bt_nummer):
    prefix = bt_nummer.split(".")[0]
    try:
        return STADTBEZIRKE_NAMES.get(int(prefix))
    except ValueError:
        return None


def build_features():
    print("Fetching official sub-districts from WFS ...", flush=True)
    bt = fetch_bezirksteile()
    print("  %d features" % len(bt["features"]), flush=True)
    print("Fetching OSM named places from Overpass ...", flush=True)
    osm = fetch_osm_names()
    print("  %d named places" % len(osm), flush=True)

    # name candidates per feature, keep the best (lowest priority number)
    candidates = {f["properties"]["bt_nummer"]: {} for f in bt["features"]}
    assigned = 0
    for p in osm:
        for f in bt["features"]:
            code = f["properties"]["bt_nummer"]
            geom = f["geometry"]
            if polygon_contains(p["lon"], p["lat"], geom):
                cur = candidates[code].get(p["name"])
                if cur is None or NAME_PRIORITY[p["place"]] < NAME_PRIORITY[cur[1]]:
                    candidates[code][p["name"]] = (p["place"], NAME_PRIORITY[p["place"]])
                assigned += 1
                break

    for f in bt["features"]:
        props = f["properties"]
        code = props["bt_nummer"]
        names = sorted(candidates[code].items(), key=lambda kv: (kv[1][1], kv[0]))
        os_names = [n for n, _ in names]
        props["stadtbezirk_name"] = borough_of(code)
        props["os_names"] = os_names
        props["name"] = os_names[0] if os_names else "%s (unnamed)" % code
        x, y = centroid(f["geometry"]["coordinates"])
        props["centroid_lat"] = round(y, 6)
        props["centroid_lng"] = round(x, 6)
    return bt


def main():
    data = build_features()
    geojson_path = os.path.join(HERE, "munich_bezirksteile_named.geojson")
    with open(geojson_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("Saved -> %s (%d features)" % (geojson_path, len(data["features"])))

    md_path = os.path.join(HERE, "munich_districts_detail.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Munich sub-districts (Stadtbezirksteile)\n\n")
        fh.write("110 official sub-district polygons with OSM names attached.\n\n")
        fh.write("| Code | Borough | OSM name(s) | Area km² | Centroid (lat, lon) |\n")
        fh.write("| --- | --- | --- | --- | --- |\n")
        for f in sorted(data["features"], key=lambda f: f["properties"]["bt_nummer"]):
            p = f["properties"]
            area_km2 = p.get("flaeche_qm", 0) / 1e6
            fh.write("| %s | %s | %s | %.2f | %.6f, %.6f |\n" % (
                p["bt_nummer"],
                p["stadtbezirk_name"] or "",
                ", ".join(p["os_names"]) or "—",
                area_km2,
                p["centroid_lat"], p["centroid_lng"]))
    print("Saved -> %s" % md_path)


if __name__ == "__main__":
    main()
