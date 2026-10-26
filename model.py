"""Income-peer model (log PM2.5 ~ log GDP per capita) and rule-based diagnosis."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).parent
WHO_PM25_GUIDELINE = 5.0
# WHO AQG 2021 PM2.5 annual interim targets, loosest first.
INTERIM_TARGETS = [(35, "Interim target 1"), (25, "Interim target 2"), (15, "Interim target 3"),
                   (10, "Interim target 4"), (5, "WHO guideline")]
WORSE_THAN_PEERS = 1.3


def load_cities():
    return pd.read_csv(ROOT / "data" / "clean" / "cities.csv")


def load_rules():
    return json.loads((ROOT / "rules.json").read_text())


def fit(cities):
    """Fit on cities with GDP; return cities with expected_pm25 and ratio, plus model stats."""
    train = cities.dropna(subset=["gdp_pcap_ppp"])
    X = np.log(train[["gdp_pcap_ppp"]].to_numpy())
    y = np.log(train["pm25"].clip(lower=0.1).to_numpy())
    reg = LinearRegression().fit(X, y)
    out = cities.copy()
    has_gdp = out["gdp_pcap_ppp"].notna()
    out.loc[has_gdp, "expected_pm25"] = np.exp(reg.predict(np.log(out.loc[has_gdp, ["gdp_pcap_ppp"]].to_numpy())))
    out["ratio"] = out["pm25"] / out["expected_pm25"]
    stats = {"r2": float(reg.score(X, y)), "slope": float(reg.coef_[0]),
             "intercept": float(reg.intercept_), "n": int(len(train))}
    return out, stats


def who_multiple(pm25):
    return pm25 / WHO_PM25_GUIDELINE


def interim_target(pm25):
    """Strictest WHO level the city meets, or None if it misses even interim target 1."""
    met = None
    for limit, name in INTERIM_TARGETS:
        if pm25 <= limit:
            met = (limit, name)
    return met


def peer_diagnosis(ratio):
    if pd.isna(ratio):
        return None
    if ratio > WORSE_THAN_PEERS:
        return "Worse than income peers: local causes likely, local action can help now."
    return "In line with income peers: structural causes (energy, industry), national policy matters most."


def likely_causes(row, rules=None):
    """Return the matching rules (dicts) for a city row; several can apply."""
    rules = rules or load_rules()
    t, by_id = rules["thresholds"], {r["id"]: r for r in rules["rules"]}
    pm25, pm10, no2 = row["pm25"], row.get("pm10"), row.get("no2")
    if pm25 <= WHO_PM25_GUIDELINE:
        return [by_id["clean"]]
    if pd.isna(no2) or pd.isna(pm10):
        return [by_id["unclear"]]
    hits = []
    if no2 >= t["no2_high"]:
        hits.append(by_id["traffic"])
    if pm10 / pm25 >= t["pm10_to_pm25_dusty"]:
        hits.append(by_id["dust"])
    if pm25 > t["pm25_high"] and no2 < t["no2_low"]:
        hits.append(by_id["burning"])
    return hits or [by_id["mixed"]]


if __name__ == "__main__":
    cities, stats = fit(load_cities())
    (ROOT / "data" / "clean" / "model_stats.json").write_text(json.dumps(stats, indent=2))
    print(stats)
    rules = load_rules()
    for name in ["Delhi", "Beijing Shi", "Stockholm"]:
        r = cities[cities["city"] == name].iloc[0]
        print(f"{name}: {r.pm25} µg/m³, {who_multiple(r.pm25):.1f}x WHO, meets {interim_target(r.pm25)}, "
              f"expected {r.expected_pm25:.1f}, ratio {r.ratio:.2f}")
        print("   ", peer_diagnosis(r.ratio), "|", [c["label"] for c in likely_causes(r, rules)])
