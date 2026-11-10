"""Restaurant gap: which Brussels zones have many residents but few food places?

A first shortlist of where restaurant recruitment could shorten trips (pickups closer to customers).
Uses the same real inputs as the map: Statbel residents and OpenStreetMap food places (restaurants,
fast food, cafés). Limits: it counts ALL food places, not Uber Eats partners, and says nothing about
restaurant quality or demand. Run from the repository root: python src/optimiser/restaurant_gap.py
"""
import pandas as pd

OUT = "data/optimiser/"


def restaurant_gap():
    z = pd.read_csv(OUT + "zones.csv")[["zone", "residents", "food_places"]]
    city_ratio = z.residents.sum() / z.food_places.sum()          # residents per food place, all Brussels
    z["residents_per_food_place"] = (z.residents / z.food_places).round(0)
    # Food places the zone would have at the Brussels average, minus what it has (negative = surplus)
    z["gap_vs_city_average"] = (z.residents / city_ratio - z.food_places).round(0)
    z["residents"] = z.residents.round(0)
    return z.sort_values("residents_per_food_place", ascending=False), city_ratio


def main():
    z, city_ratio = restaurant_gap()
    z.to_csv(OUT + "restaurant_gap.csv", index=False)
    print(f"Brussels average: {city_ratio:.0f} residents per food place")
    print(z.to_string(index=False))


if __name__ == "__main__":
    main()
