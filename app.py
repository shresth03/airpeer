"""AirPeer: how clean is your city's air, and what's the cleanest way to get around it?"""
import json
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import polyline
import streamlit as st
from rapidfuzz import fuzz, process
from streamlit_folium import st_folium

import model
import routes

ROOT = Path(__file__).parent
MODE_COLORS = {"DRIVE": "#6b7280", "TRANSIT": "#2563eb", "BICYCLE": "#16a34a", "WALK": "#b45309"}
MODE_ICONS = {"DRIVE": "🚗", "TRANSIT": "🚆", "BICYCLE": "🚲", "WALK": "🚶"}

st.set_page_config(page_title="AirPeer", page_icon="🌍", layout="centered")


@st.cache_data
def load():
    cities, stats = model.fit(model.load_cities())
    cities["label"] = cities["city"] + ", " + cities["country"]
    return cities, stats, model.load_rules(), routes.load_factors()


cities, stats, rules, factors = load()


def badge(pm25):
    """Colour + plain-language label for the score card (label always shown, never colour alone)."""
    if pm25 <= 5:
        return "#15803d", "✅ Meets the WHO limit"
    if pm25 <= 15:
        return "#a16207", "⚠️ Above the WHO limit"
    if pm25 <= 35:
        return "#c2410c", "🟠 Well above the WHO limit"
    return "#b91c1c", "🔴 Far above the WHO limit"


# ---------- Header ----------
st.title("🌍 AirPeer")
st.write("See how clean your city's air is, why, and the cleanest way to make your trip. "
         "Part of UN Sustainable Development Goal 11: sustainable cities and communities.")

# ---------- City search ----------
query = st.text_input("Your city", value="Delhi", placeholder="Start typing a city, e.g. Stockholm")
matches = process.extract(query, cities["label"], scorer=fuzz.WRatio, limit=8) if query else []
if not matches:
    st.info("Type a city name to begin.")
    st.stop()
choice = st.selectbox("Pick the closest match", [m[0] for m in matches])
city = cities[cities["label"] == choice].iloc[0]

# ---------- Score card ----------
mult = model.who_multiple(city.pm25)
color, verdict = badge(city.pm25)
met = model.interim_target(city.pm25)
stations = f"{int(city.stations)} monitoring stations" if pd.notna(city.stations) else "station count not reported"
st.markdown(
    f"""<div style="border:1px solid #e5e7eb;border-left:8px solid {color};border-radius:12px;padding:20px 24px;margin:8px 0 16px">
    <div style="font-size:15px;color:#6b7280">Fine-particle pollution (PM2.5) in {city.city}</div>
    <div style="font-size:56px;font-weight:700;line-height:1.1;color:{color}">{mult:.1f}× the WHO limit</div>
    <div style="font-size:17px;margin-top:6px"><b>{verdict}</b> · {city.pm25:.1f} µg/m³ vs the WHO limit of 5 µg/m³</div>
    <div style="font-size:14px;color:#6b7280;margin-top:6px">Measured in {city.year} · {stations}</div>
    </div>""", unsafe_allow_html=True)
if met:
    st.caption(f"WHO step reached: **{met[1]}** ({met[0]} µg/m³ or less)."
               + ("" if met[0] == 5 else " The WHO sets stepping-stone targets of 35, 25, 15, 10 and finally 5."))
else:
    st.caption("This city has not yet reached even the first WHO stepping-stone target (35 µg/m³).")

# ---------- Peer comparison ----------
st.subheader("Is it worse than similar cities?")
causes = model.likely_causes(city, rules)
diagnosis = model.peer_diagnosis(city.ratio)
if diagnosis:
    bars = pd.DataFrame({
        "what": [f"{city.city} (measured)", "Typical for a country this wealthy", "WHO limit"],
        "pm25": [city.pm25, city.expected_pm25, 5.0],
        "kind": ["city", "peer", "who"],
    })
    chart = alt.Chart(bars).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("pm25:Q", title="PM2.5 (µg/m³)", axis=alt.Axis(grid=False)),
        y=alt.Y("what:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["city", "peer", "who"],
                                                  range=[color, "#9ca3af", "#15803d"]), legend=None),
        tooltip=[alt.Tooltip("what:N", title=""), alt.Tooltip("pm25:Q", title="µg/m³", format=".1f")],
    )
    text = chart.mark_text(align="left", dx=6).encode(text=alt.Text("pm25:Q", format=".1f"),
                                                      color=alt.value("#374151"))
    st.altair_chart((chart + text).properties(height=alt.Step(34)), width="stretch")
    st.markdown(f"**{diagnosis}**  \n{city.city} has **{city.ratio:.1f}×** the pollution we'd expect "
                f"for a country with {city.country}'s income (GDP per person ${city.gdp_pcap_ppp:,.0f}, {int(city.gdp_year)}).")
    st.caption(f"Expected level comes from comparing {stats['n']:,} cities' pollution with their country's "
               f"income; income explains {stats['r2']:.0%} of the differences between cities (R² = {stats['r2']:.2f}).")
else:
    st.warning(f"The World Bank has no income figure for {city.country}, so we can only compare with the WHO limit.")

st.markdown("**Likely cause**")
for c in causes:
    st.markdown(f"- **{c['label']}**: {c['explain']}  \n  What helps: {'; '.join(c['actions'])}. "
                f"[Source]({rules['sources'][c['source']]})")
if pd.notna(city.no2) or pd.notna(city.pm10):
    st.caption(f"Other readings in {city.year}: NO2 {city.no2 if pd.notna(city.no2) else 'not measured'} µg/m³ · "
               f"PM10 {city.pm10 if pd.notna(city.pm10) else 'not measured'} µg/m³.")

# ---------- Trip planner ----------
st.subheader("Plan a cleaner trip")
demo = st.toggle("Demo mode (use a saved trip, no internet needed)", value=True)
api_key = st.secrets.get("GOOGLE_MAPS_API_KEY") if (ROOT / ".streamlit" / "secrets.toml").exists() else None
tolerance = st.slider("How many extra minutes would you accept compared with driving?", 0, 60, 15, step=5)

if demo:
    if routes.DEMO_FILE.exists():
        raw = routes.load_demo()
        st.caption(f"Saved trip: {raw['origin']} → {raw['destination']}")
    else:
        raw = None
        st.warning("No saved demo trip yet. Add a Google Maps API key and run `python routes.py` to save one.")
else:
    with st.form("trip"):
        c1, c2 = st.columns(2)
        origin = c1.text_input("From", placeholder=f"e.g. a station in {city.city}")
        dest = c2.text_input("To", placeholder="e.g. your workplace")
        go = st.form_submit_button("Compare ways to get there")
    if go:
        if not api_key:
            st.error("No Google Maps API key found in .streamlit/secrets.toml. Switch on demo mode instead.")
        elif origin and dest:
            with st.spinner("Asking Google Maps for routes…"):
                st.session_state["trip"] = routes.fetch_all(origin, dest, api_key)
    raw = st.session_state.get("trip")

if raw:
    options = routes.summarise(raw, factors)
    best = routes.recommend(options, tolerance)
    errors = [o for o in options if not o["available"]]
    avail = [o for o in options if o["available"]]
    if not avail:
        st.error("Google Maps found no route for any mode. Check the addresses.")
    else:
        cols = st.columns(len(avail))
        for col, o in zip(cols, avail):
            is_best = best and o["mode"] == best["mode"]
            border = "#15803d" if is_best else "#e5e7eb"
            col.markdown(
                f"""<div style="border:2px solid {border};border-radius:12px;padding:12px;text-align:center">
                <div style="font-size:26px">{MODE_ICONS[o['mode']]}</div><b>{o['label']}</b>
                {'<div style="color:#15803d;font-size:13px;font-weight:600">Recommended</div>' if is_best else ''}
                <div style="font-size:14px;margin-top:6px">{o['minutes']:.0f} min · {o['km']:.1f} km</div>
                <div style="font-size:18px;font-weight:600">{o['kg_co2']:.2f} kg CO₂</div></div>""",
                unsafe_allow_html=True)
        for o in errors:
            st.caption(f"{MODE_ICONS[o['mode']]} {o['label']}: not available for this trip.")

        drive = next((o for o in avail if o["mode"] == "DRIVE"), None)
        if best:
            extra = best["minutes"] - drive["minutes"] if drive else 0
            msg = f"**Go by {best['label'].lower()}**"
            if drive and best["mode"] != "DRIVE":
                msg += f": {extra:+.0f} min compared with driving, {drive['kg_co2'] - best['kg_co2']:.2f} kg less CO₂."
            elif best["mode"] == "DRIVE":
                msg = "**Driving is the only option within your time limit.** Try allowing more extra minutes."
            st.success(msg)
            if best["lines"]:
                st.caption("Transit lines: " + ", ".join(best["lines"]))
            saving = routes.yearly_saving_kg(options, best)
            if saving and saving > 0:
                st.markdown(f"🌱 Doing this trip there and back **3 days a week saves about {saving:,.0f} kg CO₂ a year**.")

        # Map with every route; recommended one drawn thicker.
        paths = {o["mode"]: polyline.decode(o["polyline"]) for o in avail if o.get("polyline")}
        if paths:
            pts = [p for path in paths.values() for p in path]
            fmap = folium.Map(tiles="cartodbpositron")
            for o in avail:
                if o["mode"] in paths:
                    is_best = best and o["mode"] == best["mode"]
                    folium.PolyLine(paths[o["mode"]], color=MODE_COLORS[o["mode"]], weight=7 if is_best else 3,
                                    opacity=0.9 if is_best else 0.6,
                                    tooltip=f"{o['label']}: {o['minutes']:.0f} min, {o['kg_co2']:.2f} kg CO₂").add_to(fmap)
            folium.Marker(pts[0], tooltip="Start", icon=folium.Icon(color="green")).add_to(fmap)
            folium.Marker(pts[-1], tooltip="End", icon=folium.Icon(color="red")).add_to(fmap)
            fmap.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)],
                             [max(p[0] for p in pts), max(p[1] for p in pts)]])
            st_folium(fmap, height=380, use_container_width=True, returned_objects=[])
            st.caption("  ".join(f"<span style='color:{MODE_COLORS[m]}'>━━</span> {routes.MODES[m]}"
                                 for m in paths), unsafe_allow_html=True)
        st.caption(f"CO₂ uses UK government 2025 factors: car {factors['car']['kg_co2e_per_km']} kg per km "
                   f"(one person driving alone), bus {factors['bus']['kg_co2e_per_km']}, metro "
                   f"{factors['metro']['kg_co2e_per_km']}, rail {factors['rail']['kg_co2e_per_km']} kg per passenger-km. "
                   "Cycling and walking count as zero.")

# ---------- Council letter ----------
st.subheader("Write to your council")
if st.button("✉️ Draft my letter"):
    main = causes[0]
    peer_line = ""
    if diagnosis and city.ratio > model.WORSE_THAN_PEERS:
        peer_line = (f"That is {city.ratio:.1f} times the level typical for a country with our income, "
                     "which suggests local causes that the council can act on now.\n\n")
    elif diagnosis:
        peer_line = ("That is in line with cities in similarly wealthy countries, so national energy and industry "
                     "policy matters most, and I ask the council to press the national government on it.\n\n")
    asks = "\n".join(f"  - {a}" for a in main["actions"])
    st.session_state["letter"] = f"""Dear Councillors,

I live in {city.city} and I am writing about our air quality.

According to the World Health Organization's Ambient Air Quality Database, the average level of fine-particle pollution (PM2.5) in {city.city} was {city.pm25:.1f} µg/m³ in {city.year}. That is {mult:.1f} times the WHO's recommended limit of 5 µg/m³.

{peer_line}The likely main cause is: {main['label'].lower()}. {main['explain']}

I am asking the council to commit to:
{asks}

Cleaner air protects our health and helps meet UN Sustainable Development Goal 11 for sustainable cities. I would welcome a reply setting out what the council plans to do and by when.

Yours sincerely,
[Your name]
[Your address]

Sources: WHO Ambient Air Quality Database (2022 update); World Bank GDP per capita, PPP; WHO guidance: {rules['sources'][main['source']]}
"""
if "letter" in st.session_state:
    letter = st.text_area("Your letter (edit freely)", st.session_state["letter"], height=420)
    st.download_button("⬇️ Download letter", letter, file_name=f"letter_{city.city}.txt")
    st.caption("To copy: click in the box, select all (Ctrl/Cmd+A), then copy.")

# ---------- Footer ----------
st.divider()
st.caption(
    "**Data:** [WHO Ambient Air Quality Database, 2022 update](https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database/2022) · "
    "[World Bank GDP per capita, PPP](https://data.worldbank.org/indicator/NY.GDP.PCAP.PP.CD) · "
    "[UK DESNZ greenhouse gas conversion factors 2025](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025) · "
    "Routes by Google Maps.\n\n"
    "**Please note:** these are yearly averages from ground monitoring stations, mostly measured between 2010 and 2019. "
    "Stations are sparse in many lower-income countries, and some cities' values may have been estimated from other "
    "particle measurements. These are not the UN's official modelled city air-quality figures. CO₂ factors are UK "
    "averages applied to every country."
)
