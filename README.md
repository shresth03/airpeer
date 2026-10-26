# AirPeer

**Live app:** https://airpeer-h3nrbugwcghh4rijyn9egm.streamlit.app

A Streamlit app for **UN SDG 11, Sustainable Cities and Communities**. It covers target 11.6 (city air quality) and target 11.2 (sustainable transport).

Pick your city and enter a trip. AirPeer then:

1. **Compares your city's air with the WHO limit.** It shows annual PM2.5 as a multiple of the WHO 2021 guideline of 5 µg/m³, and which WHO interim target (35, 25, 15, 10, 5) the city meets.
2. **Compares it with income peers.** A regression of log PM2.5 on log GDP per capita (PPP) gives an expected level for the country's income. If the city is more than 1.3× that, local causes are likely. It also suggests a likely cause (traffic, dust, burning, mixed or unclear) using simple rules based on NO2, PM10 and PM2.5. The rules are in `rules.json`, with WHO sources.
3. **Plans your trip, Google Maps style.** It gets driving, transit, cycling and walking routes from the Google Maps Routes API, including up to 3 alternative routes per mode, and estimates CO₂ for each route. A side panel and a large map then show two routes, with the other routes Google returned drawn in grey:
   - **Fastest** (blue): the quickest mode.
   - **Best alternative** (green): the lowest-CO₂ route that is greener than the fastest and within the extra minutes you're willing to accept. If nothing greener fits your limit, it shows the greener route closest to fitting and says how many extra minutes it needs. If the fastest option is also the cleanest, only that route appears.

   Mode tabs show the time for every mode, and route cards show time, distance, transit lines, CO₂ and the saving. The app also estimates the yearly CO₂ saved by taking the alternative there and back 3 days a week.
4. **Drafts a letter to your council** asking for the intervention that fits the city's diagnosis.

## Data sources

| Data | Source | File |
|---|---|---|
| City annual PM2.5, PM10 and NO2 (mostly 2010–2019) | [WHO Ambient Air Quality Database, 2022 update](https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database/2022) | `data/raw/who_aap_2021_v9_11august2022.xlsx` (not in the repo, © WHO; [download it here](https://cdn.who.int/media/docs/default-source/air-pollution-documents/air-quality-and-health/who_aap_2021_v9_11august2022.xlsx?sfvrsn=9035996c_3)) |
| GDP per capita, PPP (NY.GDP.PCAP.PP.CD) | [World Bank API](https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.PP.CD?format=json&per_page=20000&date=2010:2019) | `data/raw/wb_gdp_pcap_ppp_2010_2019.json` |
| kg CO₂e per km by mode | [UK Government GHG conversion factors 2025, condensed set](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025), sheet "Business travel- land" | `data/raw/ghg-conversion-factors-2025-condensed-set.xlsx` |
| Live trip routes | [Google Maps Routes API](https://developers.google.com/maps/documentation/routes) (`computeRoutes`) | `data/demo_route.json` (saved response for demo mode) |

## Project layout

- `prep.py` (data): builds `data/clean/cities.csv` (one row per city: latest year with PM2.5, plus PM10, NO2, stations and same-year GDP) and `data/clean/emission_factors.json`, with the table, row and year of each factor.
- `model.py` (model): income-peer regression, WHO multiple, interim targets and cause rules.
- `routes.py` (utility): Routes API calls, CO₂ per option (transit is worked out per step by vehicle type), the fastest and best-alternative choice, and yearly savings.
- `app.py` (front end): the Streamlit page. It has the air score and peer chart side by side, the Maps-style trip planner (folium on OpenStreetMap tiles) and the council letter.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The cleaned data is committed, so the app runs offline. Demo mode uses the saved trip and needs no key.

For live trips, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your `GOOGLE_MAPS_API_KEY` (the Routes API must be enabled). This file is git-ignored.

## Deploy on Streamlit Community Cloud

1. Create an app from this repo: branch `main`, main file `app.py`.
2. In **Settings → Secrets**, paste one line: `GOOGLE_MAPS_API_KEY = "your-key"`. Demo mode works without it.
3. In Google Cloud, restrict the key to the Routes API, since every visitor's search uses your quota.

Streamlit Cloud uses Python 3.14 by default, and the pinned versions in `requirements.txt` (Streamlit 1.66.1, Altair 6.3.0) work with it. `app.py` reloads `routes.py` and `model.py` on every run, so pushes take effect without a reboot. If the app ever seems stuck on old code, use **Manage app → Reboot app**.

## Rebuild the data

To rebuild the clean data, first download the WHO Excel into `data/raw/` (link above), then run `python prep.py && python model.py`. To save a new demo trip: `python routes.py "<from>" "<to>"`.

## Limitations

- Values are station-based annual means, mostly from 2010–2019. Stations are sparse in many lower-income countries.
- The WHO file does not include its "PM type" columns, so we can't tell measured PM2.5 from PM2.5 converted from PM10.
- This is **not** the official modelled SDG 11.6.2 indicator.
- Income explains about half the variation between cities (R² ≈ 0.53). "Expected" is a rough peer benchmark.
- **Routes are not ranked by air quality along the way.** The WHO data has one yearly average per city, so it can't tell one street from another. Street-level air data (e.g. Google's Air Quality API) needs a paid API, so it is left out. Routes are ranked by CO₂ and travel time only.
- Google Maps has no cycling routes in some countries (e.g. India), and transit coverage varies by city. Missing modes are listed as not available.
- CO₂ factors are UK averages applied everywhere. The car factor is per vehicle-km, so it assumes one person driving alone.
- The dust threshold (PM10 ≥ 2× PM2.5) is our own choice. The NO2 and PM2.5 thresholds are WHO guideline values.

## Team contributions

| Member | Focus | Contribution |
|---|---|---|
| **Shresth Prakash** | Problem framing and data thinking | Framed the idea around UN SDG 11: residents can't act on air quality they can't see or compare. Brainstormed what a resident actually needs to know (how bad is it, why, and what can I do today) and decided every number must come from an official source. Chose the WHO, World Bank and UK government datasets and set the honesty rules: show data gaps rather than guess. |
| **Shreya Jadav** | Diagnosis and policy concept | Came up with comparing each city to cities in similarly wealthy countries, so "is this just poverty, or something local?" has an answer. Worked out the cause categories (traffic, dust, burning, structural) and which real-world fixes match each one, and conceived the letter to the council so the app ends in civic action, not just information. |
| **Daniel Nwachi** | Trip experience and design | Imagined the trip planner as the everyday hook: show the fastest route next to a greener one and let people choose how much extra time they'd trade. Sketched the Google Maps-style layout, the yearly-savings framing ("3 days a week = X kg CO₂"), and the plain-language, no-jargon tone of the whole page. |

## How the model works

Richer countries usually have cleaner air, so the model asks: is this city's air worse than we'd expect for a country this wealthy?

1. **Collect the data.** For each of 4,027 cities, take the latest yearly PM2.5 (WHO) and the country's GDP per person, PPP (World Bank), for the same year.
2. **Draw the line.** Fit one straight line through all cities on log scales: ln(PM2.5) = 11.71 − 0.86 × ln(GDP per person). Income explains 53% of the differences between cities (R² = 0.53).
3. **Read off the expected level.** Each 1% richer goes with about 0.86% cleaner air.
4. **Compare.** Measured ÷ expected gives the ratio. Above 1.3 means "worse than income peers: local causes likely". Otherwise structural, national causes matter most.
5. **Suggest a cause.** High NO2 points to traffic, PM10 at least twice PM2.5 points to dust, and high PM2.5 with low NO2 points to burning. If NO2 or PM10 is missing, the cause is "unclear".

Example: Delhi, with India's GDP per person of $6,945, is expected to have 59.7 µg/m³. Its measured 105.0 gives a ratio of 1.76, so it's worse than its income peers. The app shows these steps with a chart of every city, the line, and the selected city highlighted. The fitted numbers are in `data/clean/model_stats.json`.

## The prompt we started from

The full brief is in [`docs/initial_prompt.md`](docs/initial_prompt.md). The app also shows it at the bottom of the page.
