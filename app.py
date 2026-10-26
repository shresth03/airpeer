"""AirPeer: how clean is your city's air, and what's the cleanest way to get around it?"""
import importlib
import math
from pathlib import Path

import altair as alt
import folium
import numpy as np
import pandas as pd
import polyline
import streamlit as st
from rapidfuzz import fuzz, process
from streamlit_folium import st_folium

import model
import routes

# Streamlit Cloud reruns app.py on a push but keeps imported modules in memory; reload them so
# changes to model.py/routes.py take effect without a manual reboot.
importlib.reload(model)
importlib.reload(routes)

ROOT = Path(__file__).parent
MODE_ICONS = {"DRIVE": "🚗", "TRANSIT": "🚆", "BICYCLE": "🚲", "WALK": "🚶"}
# Google Maps-style route colours: blue for the fastest, green for the greener alternative.
FAST = {"color": "#1a73e8", "casing": "#0b57d0"}
GREEN = {"color": "#1e8e3e", "casing": "#0d652d"}

st.set_page_config(page_title="AirPeer", page_icon="🌍", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
html, body, p, li, td, th, label, input, textarea, button, h1, h2, h3 { font-family: 'Roboto', sans-serif; }
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
.block-container { padding-top: 1.5rem; max-width: 1400px; }
.ap-panel { background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(60,64,67,.3),0 4px 8px 3px rgba(60,64,67,.15); padding:4px 0; }
.ap-tabs { display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 10px; }
.ap-tab { border:1px solid #dadce0; border-radius:18px; padding:6px 12px; font-size:14px; color:#3c4043; background:#fff; }
.ap-tab.on { background:#e8f0fe; border-color:#e8f0fe; color:#0b57d0; font-weight:500; }
.ap-tab.off { color:#9aa0a6; }
.ap-route { border-bottom:1px solid #e8eaed; padding:14px 18px; display:flex; gap:14px; }
.ap-route:last-child { border-bottom:none; }
.ap-bar { width:4px; border-radius:2px; flex-shrink:0; }
.ap-tag { font-size:12px; font-weight:500; letter-spacing:.3px; text-transform:uppercase; }
.ap-time { font-size:22px; font-weight:500; color:#202124; }
.ap-sub { font-size:14px; color:#5f6368; margin-top:2px; }
.ap-co2 { font-size:14px; color:#202124; margin-top:4px; }
</style>""", unsafe_allow_html=True)


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


def route_card(o, tag, tag_color, detail):
    """One Google Maps-style route row. Joined on one line so Markdown never shows the HTML as code."""
    return "".join([
        f'<div class="ap-route"><div class="ap-bar" style="background:{tag_color}"></div><div style="flex:1">',
        f'<div class="ap-tag" style="color:{tag_color}">{tag}</div>',
        f'<div style="display:flex;justify-content:space-between;align-items:baseline">',
        f'<span style="font-size:16px;color:#202124">{MODE_ICONS[o["mode"]]} {o["label"]}'
        f'{" · route " + str(o["route_no"]) if o.get("route_no", 1) > 1 else ""}</span>',
        f'<span class="ap-time">{o["minutes"]:.0f} min</span></div>',
        f'<div class="ap-sub">{o["km"]:.1f} km{" · " + ", ".join(o["lines"]) if o["lines"] else ""}</div>',
        f'<div class="ap-co2">{detail}</div></div></div>',
    ])


def add_route(fmap, path, style, label):
    """Draw a route Google-style (dark casing under a bright line) with a time bubble at its midpoint."""
    folium.PolyLine(path, color=style["casing"], weight=10, opacity=0.9).add_to(fmap)
    folium.PolyLine(path, color=style["color"], weight=6, opacity=1, tooltip=label).add_to(fmap)
    mid = path[len(path) // 2]
    folium.Marker(mid, icon=folium.DivIcon(icon_size=(150, 30), icon_anchor=(0, 15), html=(
        f'<div style="display:inline-block;background:{style["color"]};color:#fff;font:500 13px Roboto,sans-serif;'
        f'padding:4px 9px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.35);white-space:nowrap">{label}</div>'
    ))).add_to(fmap)


# ---------- Header ----------
st.title("🌍 AirPeer")
st.write("See how clean your city's air is, why, and the cleanest way to make your trip. "
         "Part of UN Sustainable Development Goal 11: sustainable cities and communities.")

left, right = st.columns([1, 1.2], gap="large")

# ---------- City search + score card ----------
with left:
    query = st.text_input("Your city", value="Delhi", placeholder="Start typing a city, e.g. Stockholm")
    matches = process.extract(query, cities["label"], scorer=fuzz.WRatio, limit=8) if query else []
    if not matches:
        st.info("Type a city name to begin.")
        st.stop()
    choice = st.selectbox("Pick the closest match", [m[0] for m in matches])
    city = cities[cities["label"] == choice].iloc[0]

    mult = model.who_multiple(city.pm25)
    color, verdict = badge(city.pm25)
    met = model.interim_target(city.pm25)
    stations = f"{int(city.stations)} monitoring stations" if pd.notna(city.stations) else "station count not reported"
    st.markdown(
        f"""<div style="border:1px solid #e5e7eb;border-left:8px solid {color};border-radius:12px;padding:20px 24px;margin:8px 0 16px">
        <div style="font-size:15px;color:#6b7280">Fine-particle pollution (PM2.5) in {city.city}</div>
        <div style="font-size:52px;font-weight:700;line-height:1.1;color:{color}">{mult:.1f}× the WHO limit</div>
        <div style="font-size:17px;margin-top:6px"><b>{verdict}</b> · {city.pm25:.1f} µg/m³ vs the WHO limit of 5 µg/m³</div>
        <div style="font-size:14px;color:#6b7280;margin-top:6px">Measured in {city.year} · {stations}</div>
        </div>""", unsafe_allow_html=True)
    if met:
        st.caption(f"WHO step reached: **{met[1]}** ({met[0]} µg/m³ or less)."
                   + ("" if met[0] == 5 else " The WHO sets stepping-stone targets of 35, 25, 15, 10 and finally 5."))
    else:
        st.caption("This city has not yet reached even the first WHO stepping-stone target (35 µg/m³).")

# ---------- Peer comparison ----------
causes = model.likely_causes(city, rules)
diagnosis = model.peer_diagnosis(city.ratio)
with right:
    st.subheader("Is it worse than similar cities?")
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

# ---------- Trip planner (Maps-style: panel on the left, map on the right) ----------
st.divider()
st.subheader("Plan a cleaner trip")
try:  # local secrets.toml or the Streamlit Cloud secrets panel
    api_key = st.secrets.get("GOOGLE_MAPS_API_KEY")
except FileNotFoundError:
    api_key = None

panel, map_col = st.columns([1, 1.8], gap="medium")
with panel:
    demo = st.toggle("Demo mode (use a saved trip, no internet needed)", value=True)
    if demo:
        raw = routes.load_demo() if routes.DEMO_FILE.exists() else None
        if raw:
            st.text_input("🟢 From", raw["origin"], disabled=True)
            st.text_input("📍 To", raw["destination"], disabled=True)
        else:
            st.warning("No saved demo trip yet. Add a Google Maps API key and run `python routes.py` to save one.")
    else:
        with st.form("trip_form", border=False):
            origin = st.text_input("🟢 From", placeholder=f"Choose a starting point in {city.city}")
            dest = st.text_input("📍 To", placeholder="Choose a destination")
            go = st.form_submit_button("Get routes", type="primary", width="stretch")
        if go:
            if not api_key:
                st.error("No Google Maps API key found (.streamlit/secrets.toml locally, or the app's Secrets "
                         "settings on Streamlit Cloud). Switch on demo mode instead.")
            elif origin and dest:
                with st.spinner("Asking Google Maps for routes…"):
                    st.session_state["trip"] = routes.fetch_all(origin, dest, api_key)
        raw = st.session_state.get("trip")
    tolerance = st.slider("Extra minutes you'd accept for a greener trip", 0, 60, 15, step=5)

options = routes.summarise(raw, factors) if raw else []
fastest, alternative, within = routes.fastest_and_alternative(options, tolerance)

with panel:
    if raw and not fastest:
        st.error("Google Maps found no route for any mode. Check the addresses.")
    elif fastest:
        shown = {fastest["mode"], alternative["mode"] if alternative else None}
        st.markdown('<div class="ap-tabs">' + "".join(
            f'<span class="ap-tab {"on" if o["mode"] in shown else ""}">{MODE_ICONS[o["mode"]]} {o["minutes"]:.0f} min</span>'
            if o["available"] else f'<span class="ap-tab off">{MODE_ICONS[o["mode"]]} n/a</span>'
            for o in routes.best_per_mode(options)) + "</div>", unsafe_allow_html=True)

        cards = [route_card(fastest, "Fastest", FAST["color"], f'{fastest["kg_co2"]:.2f} kg CO₂')]
        if alternative:
            extra = alternative["minutes"] - fastest["minutes"]
            saved = fastest["kg_co2"] - alternative["kg_co2"]
            tag = "Best alternative · greener" if within else f"Greener option · over your {tolerance}-min limit"
            cards.append(route_card(alternative, tag, GREEN["color"],
                                    f'{alternative["kg_co2"]:.2f} kg CO₂ · <b>{saved:.2f} kg less</b> · {extra:+.0f} min'))
        st.markdown('<div class="ap-panel">' + "".join(cards) + "</div>", unsafe_allow_html=True)

        if not alternative:
            st.success(f"{fastest['label']} is already the fastest and the cleanest option.")
        else:
            saving = routes.yearly_saving_kg(fastest, alternative)
            if within:
                st.success(f"🌱 Going by {alternative['label'].lower()} there and back **3 days a week saves about "
                           f"{saving:,.0f} kg CO₂ a year**.")
            else:
                need = alternative["minutes"] - fastest["minutes"]
                st.info(f"No greener option is within {tolerance} extra minutes. Allow at least {math.ceil(need)} to get "
                        f"{alternative['label'].lower()} recommended (saves about {saving:,.0f} kg CO₂ a year).")
        missing = [o["label"] for o in routes.best_per_mode(options) if not o["available"]]
        if missing:
            st.caption("Not available for this trip: " + ", ".join(missing) + ".")

with map_col:
    shown_routes = [(o, s, t) for o, s, t in [(alternative, GREEN, "greener"), (fastest, FAST, "fastest")]
                    if o and o.get("polyline")]
    if shown_routes:
        paths = [polyline.decode(o["polyline"]) for o, _, _ in shown_routes]
        pts = [p for path in paths for p in path]
        fmap = folium.Map(tiles="OpenStreetMap", scrollWheelZoom=False, zoom_control=True)  # page scrolling must not zoom the map
        # Other routes Google returned, in grey underneath, as Google Maps shows alternatives.
        others = [o for o in options if o["available"] and o.get("polyline") and o is not fastest and o is not alternative]
        for o in others:
            name = o["label"] + (f" · route {o['route_no']}" if o["route_no"] > 1 else "")
            folium.PolyLine(polyline.decode(o["polyline"]), color="#9aa0a6", weight=5, opacity=0.7,
                            tooltip=f"{MODE_ICONS[o['mode']]} {name}: {o['minutes']:.0f} min · {o['kg_co2']:.2f} kg CO₂").add_to(fmap)
        # Alternative drawn first so the fastest (blue) sits on top where they overlap, as in Google Maps.
        for (o, style, _), path in zip(shown_routes, paths):
            add_route(fmap, path, style, f"{MODE_ICONS[o['mode']]} {o['minutes']:.0f} min · {o['kg_co2']:.2f} kg CO₂")
        folium.CircleMarker(paths[-1][0], radius=7, color="#202124",
                            weight=3, fill=True, fill_color="#fff", fill_opacity=1, tooltip="Start").add_to(fmap)
        folium.Marker(paths[-1][-1], tooltip="Destination", icon=folium.Icon(color="red", icon="map-marker",
                                                                             prefix="fa")).add_to(fmap)
        fmap.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)],
                         [max(p[0] for p in pts), max(p[1] for p in pts)]], padding=(30, 30))
        st_folium(fmap, height=560, use_container_width=True, returned_objects=[],
                  key=f"map_{raw['origin']}_{raw['destination']}_{tolerance}")
    else:
        fmap = folium.Map(location=[20, 0], zoom_start=2, tiles="OpenStreetMap", scrollWheelZoom=False)
        st_folium(fmap, height=560, use_container_width=True, returned_objects=[], key="map_empty")
    st.caption(f"CO₂ uses UK government 2025 factors: car {factors['car']['kg_co2e_per_km']} kg per km "
               f"(one person driving alone), bus {factors['bus']['kg_co2e_per_km']}, metro "
               f"{factors['metro']['kg_co2e_per_km']}, rail {factors['rail']['kg_co2e_per_km']} kg per passenger-km. "
               "Cycling and walking count as zero. Grey lines are other routes Google returned; hover for details.")
    st.caption("**Air quality along routes is not compared.** Routes are ranked by CO₂ and travel time only. The WHO "
               "data has one yearly average per city, so it can't tell one street from another, and street-level air "
               "data (such as Google's Air Quality API) needs a paid API, so it is left out.")

# ---------- Council letter ----------
st.divider()
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
    "averages applied to every country. Routes are not ranked by street-level air quality (that needs a paid API)."
)

# ---------- How the model works ----------
st.divider()
st.subheader("How the model works")
st.markdown(
    "Richer countries usually have cleaner air, so comparing a city only with the WHO limit isn't the whole story. "
    "The model asks a fairer question: **is this city's air worse than we'd expect for a country this wealthy?**"
)
steps, chart_col = st.columns([1, 1.4], gap="large")
with steps:
    st.markdown(f"""
1. **Collect the data.** For each of {stats['n']:,} cities we take the latest yearly PM2.5 from the WHO database and the country's GDP per person (PPP) from the World Bank for the same year.
2. **Draw the line.** We fit one straight line through all cities, using log scales for both, so each step on the line is a percentage change. Income explains **{stats['r2']:.0%}** of the differences between cities (R² = {stats['r2']:.2f}).
3. **Read off the expected level.** For a city, the line gives the PM2.5 typical for its country's income: expected = e^({stats['intercept']:.2f} − {abs(stats['slope']):.2f} × ln(GDP per person)). In plain terms, each 1% richer goes with about {abs(stats['slope']):.2f}% cleaner air.
4. **Compare.** Measured ÷ expected gives the ratio. Above **{model.WORSE_THAN_PEERS}** means "worse than income peers: local causes likely". Otherwise, national, structural causes such as energy and industry matter most.
5. **Suggest a cause.** Simple rules check the other pollutants: high NO2 points to traffic, PM10 at least twice PM2.5 points to dust, and high PM2.5 with low NO2 points to burning. If NO2 or PM10 wasn't measured, we say the cause is unclear rather than guess.
""")
    if diagnosis:
        st.info(f"**{city.city}:** GDP per person ${city.gdp_pcap_ppp:,.0f} gives an expected "
                f"{city.expected_pm25:.1f} µg/m³. Measured {city.pm25:.1f} ÷ expected {city.expected_pm25:.1f} = "
                f"**{city.ratio:.2f}**, so {'worse than' if city.ratio > model.WORSE_THAN_PEERS else 'in line with'} "
                "its income peers.")
with chart_col:
    pts = cities.dropna(subset=["gdp_pcap_ppp"])[["label", "gdp_pcap_ppp", "pm25"]]
    gdp_grid = np.geomspace(pts["gdp_pcap_ppp"].min(), pts["gdp_pcap_ppp"].max(), 50)
    line = pd.DataFrame({"gdp_pcap_ppp": gdp_grid,
                         "pm25": np.exp(stats["intercept"] + stats["slope"] * np.log(gdp_grid))})
    x = alt.X("gdp_pcap_ppp:Q", title="GDP per person, PPP ($, log scale)",
              scale=alt.Scale(type="log", domain=[gdp_grid[0], gdp_grid[-1]], nice=False),
              axis=alt.Axis(grid=False, format="$,.0f", values=[1000, 3000, 10000, 30000, 100000]))
    y = alt.Y("pm25:Q", title="PM2.5 (µg/m³, log scale)",
              scale=alt.Scale(type="log", domain=[max(pts["pm25"].min(), 0.5), pts["pm25"].max()], nice=False),
              axis=alt.Axis(grid=True, gridColor="#eef0f2", values=[1, 3, 10, 30, 100, 300]))
    dots = alt.Chart(pts).mark_circle(size=14, opacity=0.35, color="#9ca3af").encode(
        x=x, y=y, tooltip=[alt.Tooltip("label:N", title="City"),
                           alt.Tooltip("gdp_pcap_ppp:Q", title="GDP per person", format="$,.0f"),
                           alt.Tooltip("pm25:Q", title="PM2.5", format=".1f")])
    fit = alt.Chart(line).mark_line(color="#1a73e8", strokeWidth=2, clip=True).encode(x=x, y=y)
    layers = [dots, fit]
    if diagnosis:
        me = pd.DataFrame({"gdp_pcap_ppp": [city.gdp_pcap_ppp], "pm25": [city.pm25], "label": [city.city]})
        layers += [alt.Chart(me).mark_circle(size=120, color=color, stroke="#fff", strokeWidth=2).encode(x=x, y=y),
                   alt.Chart(me).mark_text(dx=10, align="left", fontWeight="bold", color="#202124").encode(
                       x=x, y=y, text="label:N")]
    st.altair_chart(alt.layer(*layers).properties(height=360), width="stretch")
    st.caption(f"Each grey dot is a city. The blue line is the expected level for each income. "
               f"Cities above the line are more polluted than their income suggests"
               f"{'; ' + city.city + ' is highlighted' if diagnosis else ''}.")

# ---------- How we built it ----------
st.divider()
st.subheader("Team contributions")
st.markdown("""
| Member | Contribution |
|---|---|
| **Shresth Prakash** | Came up with the idea of an SDG 11 air-quality app built only on official data. |
| **Shreya Jadav** | Came up with the idea of comparing cities to income peers and writing to the council. |
| **Daniel Nwachi** | Came up with the idea of a fastest vs greener trip planner in a Maps-style design. |
""")

with st.expander("The prompt we started from"):
    st.code((ROOT / "docs" / "initial_prompt.md").read_text(), language=None, wrap_lines=True)
