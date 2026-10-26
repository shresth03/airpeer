"""Build data/clean/cities.csv and data/clean/emission_factors.json from the raw official files."""
import json
import re
from pathlib import Path

import pandas as pd

RAW = Path(__file__).parent / "data" / "raw"
CLEAN = Path(__file__).parent / "data" / "clean"

WHO_XLSX = RAW / "who_aap_2021_v9_11august2022.xlsx"
WHO_SHEET = "AAP_2022_city_v9"
WB_JSON = RAW / "wb_gdp_pcap_ppp_2010_2019.json"
GHG_XLSX = RAW / "ghg-conversion-factors-2025-condensed-set.xlsx"
GHG_SHEET = "Business travel- land"


def station_count(text):
    """Sum the leading numbers in e.g. '1 City Centre, 2 Industrial' -> 3. None if not reported."""
    if not isinstance(text, str):
        return None
    nums = re.findall(r"(?:^|,)\s*(\d+)\b", text.split("/ FOR")[0].split("/FOR")[0])
    return sum(int(n) for n in nums) if nums else None


def build_cities():
    who = pd.read_excel(WHO_XLSX, sheet_name=WHO_SHEET)
    who = who.rename(columns={
        "WHO Region": "who_region", "ISO3": "iso3", "WHO Country Name": "country",
        "City or Locality": "city", "Measurement Year": "year",
        "PM2.5 (μg/m3)": "pm25", "PM10 (μg/m3)": "pm10", "NO2 (μg/m3)": "no2",
        "Number and type of monitoring stations": "stations_text", "Reference": "reference",
    })
    # WHO states the database covers 2010-2019; drop the few rows outside it.
    who = who[who["year"].between(2010, 2019) & who["pm25"].notna() & who["city"].notna()]
    latest = who.sort_values("year").groupby(["iso3", "city"], as_index=False).tail(1)
    latest = latest.assign(stations=latest["stations_text"].map(station_count))

    meta, rows = json.loads(WB_JSON.read_text())
    gdp = pd.DataFrame(
        {"iso3": r["countryiso3code"], "gdp_year": int(r["date"]), "gdp_pcap_ppp": r["value"]}
        for r in rows if r["value"] is not None and r["countryiso3code"]
    )
    merged = latest.merge(gdp, on="iso3", how="left")
    merged["year_gap"] = (merged["gdp_year"] - merged["year"]).abs()
    # Nearest GDP year to the measurement year; ties go to the earlier year.
    merged = merged.sort_values(["year_gap", "gdp_year"]).groupby(["iso3", "city"], as_index=False).head(1)
    merged = latest.merge(merged[["iso3", "city", "gdp_year", "gdp_pcap_ppp"]], on=["iso3", "city"], how="left")

    cols = ["city", "country", "iso3", "who_region", "year", "pm25", "pm10", "no2",
            "stations", "stations_text", "gdp_pcap_ppp", "gdp_year", "reference"]
    out = merged[cols].sort_values(["country", "city"]).reset_index(drop=True)
    out["stations"] = out["stations"].astype("Int64")
    out["gdp_year"] = out["gdp_year"].astype("Int64")
    out.to_csv(CLEAN / "cities.csv", index=False)
    return out


def build_emission_factors():
    ghg = pd.read_excel(GHG_XLSX, sheet_name=GHG_SHEET, header=None)
    year = ghg.iloc[5].tolist()
    year = year[year.index("Year:") + 1]

    def lookup(activity, type_, unit, fuel=None):
        """Find the kg CO2e value for a row; for cars, pick the fuel column from the header row above."""
        act = ghg[0].ffill()
        hit = ghg[(act == activity) & (ghg[1].ffill() == type_) & (ghg[2] == unit)]
        assert len(hit) == 1, (activity, type_, unit)
        i = hit.index[0]
        if fuel is None:
            return float(ghg.iloc[i, 3]), f"{activity} › {type_}"
        header_row = max(j for j in range(i) if ghg.iloc[j].astype(str).str.contains(fuel, regex=False).any())
        fuels = ghg.iloc[header_row].ffill()
        kinds = ghg.iloc[header_row + 1]
        col = next(c for c in range(ghg.shape[1]) if fuels[c] == fuel and kinds[c] == "kg CO2e")
        return float(ghg.iloc[i, col]), f"{activity} › {type_} › {fuel}"

    table = f"UK Government GHG Conversion Factors for Company Reporting {year}, condensed set, sheet '{GHG_SHEET}'"
    spec = {
        "car": ("Cars (by size)", "Average car", "km", "Unknown",
                "Per vehicle-km; treated as one person driving alone."),
        "bus": ("Bus", "Average local bus", "passenger.km", None, ""),
        "rail": ("Rail", "National rail", "passenger.km", None, ""),
        "metro": ("Rail", "London Underground", "passenger.km", None, "Used for subway/metro steps."),
        "tram": ("Rail", "Light rail and tram", "passenger.km", None, ""),
    }
    factors = {}
    for mode, (activity, type_, unit, fuel, note) in spec.items():
        value, row = lookup(activity, type_, unit, fuel)
        factors[mode] = {"kg_co2e_per_km": value, "unit": unit, "table": table, "row": row,
                         "year": int(year), "note": note}
    for mode in ("bicycle", "walk"):
        factors[mode] = {"kg_co2e_per_km": 0.0, "unit": "passenger.km", "table": None, "row": None,
                         "year": None, "note": "Zero tailpipe emissions (not from the conversion factors)."}
    (CLEAN / "emission_factors.json").write_text(json.dumps(factors, indent=2, ensure_ascii=False))
    return factors


if __name__ == "__main__":
    CLEAN.mkdir(parents=True, exist_ok=True)
    cities = build_cities()
    print(f"cities.csv: {len(cities)} cities, {cities['gdp_pcap_ppp'].notna().sum()} with GDP")
    for mode, f in build_emission_factors().items():
        print(f"{mode:8s} {f['kg_co2e_per_km']:.5f} {f['unit']:13s} {f['row']}")
