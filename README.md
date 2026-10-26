# AirPeer

A Streamlit app for **UN SDG 11, Sustainable Cities and Communities**. It covers target 11.6 (city air quality) and target 11.2 (sustainable transport).

Pick your city and enter a trip. AirPeer then:

1. **Compares your city's air with the WHO limit.** It shows annual PM2.5 as a multiple of the WHO 2021 guideline of 5 µg/m³, and which WHO interim target (35, 25, 15, 10, 5) the city meets.
2. **Compares it with income peers.** A regression of log PM2.5 on log GDP per capita (PPP) gives an expected level for the country's income. If the city is more than 1.3× that, local causes are likely. It also suggests a likely cause (traffic, dust, burning, mixed or unclear) using simple rules based on NO2, PM10 and PM2.5. The rules are in `rules.json`, with WHO sources.
3. **Compares ways to make your trip.** It gets driving, transit, cycling and walking routes from the Google Maps Routes API and estimates CO₂ for each. It then recommends the cleanest option within the extra time you're willing to accept.
4. **Drafts a letter to your council** asking for the intervention that fits the city's diagnosis.

## Data sources

| Data | Source | File |
|---|---|---|
| City annual PM2.5, PM10 and NO2 (mostly 2010–2019) | [WHO Ambient Air Quality Database, 2022 update](https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database/2022) | `data/raw/who_aap_2021_v9_11august2022.xlsx` |
| GDP per capita, PPP (NY.GDP.PCAP.PP.CD) | [World Bank API](https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.PP.CD?format=json&per_page=20000&date=2010:2019) | `data/raw/wb_gdp_pcap_ppp_2010_2019.json` |
| kg CO₂e per km by mode | [UK Government GHG conversion factors 2025, condensed set](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025), sheet "Business travel- land" | `data/raw/ghg-conversion-factors-2025-condensed-set.xlsx` |
| Live trip routes | [Google Maps Routes API](https://developers.google.com/maps/documentation/routes) (`computeRoutes`) | `data/demo_route.json` (saved response for demo mode) |

## Project layout

- `prep.py` (data): builds `data/clean/cities.csv` (one row per city: latest year with PM2.5, plus PM10, NO2, stations and same-year GDP) and `data/clean/emission_factors.json`, with the table, row and year of each factor.
- `model.py` (model): income-peer regression, WHO multiple, interim targets and cause rules.
- `routes.py` (utility): Routes API calls, CO₂ per option, recommendation and yearly savings.
- `app.py` (front end): the Streamlit page.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The cleaned data is committed, so the app runs offline. Demo mode uses the saved trip and needs no key.

For live trips, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your `GOOGLE_MAPS_API_KEY` (the Routes API must be enabled). This file is git-ignored.

To rebuild the clean data: `python prep.py && python model.py`. To save a new demo trip: `python routes.py "<from>" "<to>"`.

## Limitations

- Values are station-based annual means, mostly from 2010–2019. Stations are sparse in many lower-income countries.
- The WHO file does not include its "PM type" columns, so we can't tell measured PM2.5 from PM2.5 converted from PM10.
- This is **not** the official modelled SDG 11.6.2 indicator.
- Income explains about half the variation between cities (R² ≈ 0.53). "Expected" is a rough peer benchmark.
- CO₂ factors are UK averages applied everywhere. The car factor is per vehicle-km, so it assumes one person driving alone.
- The dust threshold (PM10 ≥ 2× PM2.5) is our own choice. The NO2 and PM2.5 thresholds are WHO guideline values.
