"""Download the real public inputs for the Brussels courier-positioning optimiser into data/raw/brussels/.

Sources (raw files are not committed; derived tables credit each source):
  Statbel statistical sectors 2025 (boundaries)      CC BY 4.0   "Source: Statbel"
  Statbel population by statistical sector, 2025      CC BY 4.0   "Source: Statbel"
  OpenStreetMap restaurants, fast food and cafés      ODbL        "© OpenStreetMap contributors"
  Open-Meteo historical hourly weather, Brussels      CC BY 4.0   "Weather data by Open-Meteo.com"

Run from the repository root: python src/optimiser/download.py
"""
import io
import json
import os
import zipfile

import requests

RAW = "data/raw/brussels/"
HEADERS = {"User-Agent": "dinner-rush-portfolio-case/1.0 (independent analysis)"}
STATBEL = "https://statbel.fgov.be/sites/default/files/files/opendata/"
SECTORS_URL = STATBEL + "Statistische%20sectoren/sh_statbel_statistical_sectors_31370_20250101.geojson.zip"
POPULATION_URL = STATBEL + "bevolking/sectoren/OPENDATA_SECTOREN_2025_NEW.zip"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """
[out:json][timeout:180];
area["ISO3166-2"="BE-BRU"]->.brussels;
nwr["amenity"~"^(restaurant|fast_food|cafe)$"](area.brussels);
out center tags;
"""
WEATHER_URL = ("https://archive-api.open-meteo.com/v1/archive?latitude=50.8466&longitude=4.3528"
               "&start_date=2026-09-01&end_date=2026-10-31&hourly=precipitation,rain,temperature_2m"
               "&timezone=Europe%2FBrussels")


def fetch(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=300, **kwargs)
    r.raise_for_status()
    return r


def unzip_to(url, folder):
    with zipfile.ZipFile(io.BytesIO(fetch(url).content)) as z:
        names = [n for n in z.namelist() if not n.startswith("__MACOSX")]
        z.extractall(folder, members=names)
    return names


def main():
    os.makedirs(RAW, exist_ok=True)
    print("statistical sectors:", unzip_to(SECTORS_URL, RAW))
    print("population by sector:", unzip_to(POPULATION_URL, RAW))

    r = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, headers=HEADERS, timeout=300)
    r.raise_for_status()
    json.dump(r.json(), open(RAW + "osm_food_places.json", "w", encoding="utf-8"))
    print("OSM food places:", len(r.json()["elements"]))

    weather = fetch(WEATHER_URL).json()
    json.dump(weather, open(RAW + "weather_brussels_2026_09_10.json", "w"))
    print("weather hours:", len(weather["hourly"]["time"]))


if __name__ == "__main__":
    main()
