"""Build the Brussels grid: H3 hexagons (resolution 8, ~0.74 km2) with residents, food places and a dispatch zone.

Inputs : data/raw/brussels/ (src/optimiser/download.py): Statbel 2025 statistical sectors + population, OSM food places
Output : data/optimiser/hexes.csv   one row per hexagon: h3 id, zone, residents, food places, centre
         data/optimiser/zones.csv   one row per dispatch zone: residents, food places, centre, neighbouring zones

Zones: the 19 municipalities of the Brussels-Capital Region, with the City of Brussels split into its seven
Statbel sub-areas (Pentagon, European Quarter, Louise, North, Laeken, Neder-Over-Heembeek, Haren): 25 zones.
Residents are spread from statistical sectors to hexagons by area overlap. Food places = OSM amenity
restaurant, fast_food or cafe (point, or centre of the building outline).
Sources: Statbel (CC BY 4.0, "Source: Statbel"); © OpenStreetMap contributors (ODbL).
Run from the repository root: python src/optimiser/grid.py
"""
import json
import os

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Point, Polygon

RAW = "data/raw/brussels/"
OUT = "data/optimiser/"
RES = 8
LAMBERT = 31370
CITY_PARTS = {"21004A": "Brussels Pentagon", "21004B": "European Quarter", "21004C": "Louise",
              "21004D": "Brussels North", "21004E": "Laeken", "21004F": "Neder-Over-Heembeek", "21004G": "Haren"}
SECTORS = RAW +"sh_statbel_statistical_sectors_31370_20250101.geojson/sh_statbel_statistical_sectors_31370_20250101.geojson"


def sectors():
    g = gpd.read_file(SECTORS)
    g = g[g.cd_rgn_refnis == "04000"].copy()
    pop = pd.read_csv(RAW + "OPENDATA_SECTOREN_2025_NEW.txt", sep="|", encoding="latin-1", usecols=["CD_SECTOR", "TOTAL"])
    g = g.merge(pop, left_on="cd_sector", right_on="CD_SECTOR", how="left")
    g["residents"] = g.TOTAL.fillna(0)
    city = g.tx_munty_descr_fr == "Bruxelles"
    g["zone"] = g.tx_munty_descr_fr.where(~city, g.cd_sub_munty.map(CITY_PARTS))
    return g[["cd_sector", "zone", "residents", "geometry"]]


def hexagons(region):
    """All resolution-8 cells whose centre lies in the region."""
    shape = region.to_crs(4326).union_all()
    polys = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
    cells = set()
    for p in polys:
        cells |= set(h3.polygon_to_cells(h3.LatLngPoly([(y, x) for x, y in p.exterior.coords]), RES))
    rows = [{"h3": c, "geometry": Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)])} for c in sorted(cells)]
    return gpd.GeoDataFrame(rows, crs=4326).to_crs(LAMBERT)


def apportion_residents(hexes, sec):
    """Residents of each sector shared over hexagons in proportion to the overlapping area."""
    sec = sec.assign(sector_area=sec.area)
    inter = gpd.overlay(hexes[["h3", "geometry"]], sec, how="intersection", keep_geom_type=True)
    inter["residents_part"] = inter.residents * inter.area / inter.sector_area
    inter["area_part"] = inter.area
    res = inter.groupby("h3").residents_part.sum().rename("residents")
    zone = inter.sort_values("area_part").groupby("h3").zone.last()      # zone with the largest overlap
    return hexes.join(res, on="h3").join(zone, on="h3").fillna({"residents": 0})


def food_places():
    els = json.load(open(RAW + "osm_food_places.json", encoding="utf-8"))["elements"]
    pts = [(e.get("lat") or e["center"]["lat"], e.get("lon") or e["center"]["lon"], e["tags"].get("amenity")) for e in els]
    df = pd.DataFrame(pts, columns=["lat", "lng", "amenity"])
    df["h3"] = [h3.latlng_to_cell(a, b, RES) for a, b in zip(df.lat, df.lng)]
    return df


def neighbours(hexes):
    """Zones that share at least one adjacent hexagon."""
    zone_of = dict(zip(hexes.h3, hexes.zone))
    pairs = set()
    for c, z in zone_of.items():
        for n in h3.grid_disk(c, 1):
            if n in zone_of and zone_of[n] != z:
                pairs.add(tuple(sorted((z, zone_of[n]))))
    out = {}
    for a, b in pairs:
        out.setdefault(a, []).append(b)
        out.setdefault(b, []).append(a)
    return {k: sorted(v) for k, v in out.items()}


def main():
    os.makedirs(OUT, exist_ok=True)
    sec = sectors()
    hexes = apportion_residents(hexagons(sec), sec)
    hexes = hexes[hexes.zone.notna()].copy()
    food = food_places()
    hexes = hexes.join(food.groupby("h3").size().rename("food_places"), on="h3").fillna({"food_places": 0})
    centre = hexes.geometry.centroid.to_crs(4326)
    hexes["lat"], hexes["lng"] = centre.y.round(5), centre.x.round(5)
    hexes["residents"] = hexes.residents.round(1)
    hexes["food_places"] = hexes.food_places.astype(int)
    hexes[["h3", "zone", "residents", "food_places", "lat", "lng"]].to_csv(OUT + "hexes.csv", index=False)

    z = hexes.groupby("zone").agg(hexes=("h3", "size"), residents=("residents", "sum"), food_places=("food_places", "sum"),
                                  lat=("lat", "mean"), lng=("lng", "mean")).round(4)
    nb = neighbours(hexes)
    z["neighbours"] = [";".join(nb.get(k, [])) for k in z.index]
    z.reset_index().to_csv(OUT + "zones.csv", index=False)
    missed = len(food) - int(hexes.food_places.sum())
    print(f"{len(hexes)} hexagons, {z.shape[0]} zones, {int(z.residents.sum()):,} residents, "
          f"{int(z.food_places.sum()):,} food places ({missed} fell outside the region's hexagons)")
    print(z.drop(columns="neighbours").sort_values("food_places", ascending=False).to_string())


if __name__ == "__main__":
    main()
