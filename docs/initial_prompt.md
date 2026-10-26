You are helping my team build a hackathon app in about 90 minutes. Work fast, keep it simple, and check in with me at each checkpoint below. You have access to my Chrome browser; use it to download the public datasets listed here.

What we're building

AirPeer: a Streamlit web app for UN SDG 11 (Sustainable Cities and Communities), targets 11.6 (city air quality) and 11.2 (sustainable transport). Stay on SDG 11 only.

A resident picks their city and enters a trip. The app:

Shows how their city's air compares to the WHO safe limit (one big number, e.g. "9× the WHO limit").
Diagnoses whether the city is worse than cities in similarly wealthy countries, and the likely cause (traffic, dust, burning or structural).
Compares driving, transit, cycling and walking for their trip using Google Maps, estimates CO₂ for each, and recommends the cleanest option within the extra time they're willing to accept, with the routes on a map.
Generates a ready-to-send letter to their local council asking for the intervention that fits their city's diagnosis.

The app must have four parts: data, a model, a utility and a front end. All data must come from the official sources below. Never invent numbers; if something is missing, tell me.

Datasets (download these with Chrome into data/raw/)
WHO Ambient Air Quality Database, 2022 update (city annual means of PM2.5, PM10, NO2; mostly 2010–2019)
Page: https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database/2022
Excel file: https://cdn.who.int/media/docs/default-source/air-pollution-documents/air-quality-and-health/who_aap_2021_v9_11august2022.xlsx?sfvrsn=9035996c_3
Methods PDF: https://cdn.who.int/media/docs/default-source/air-pollution-documents/air-quality-and-health/methodology_who-air-quality-database-2022.pdf?sfvrsn=bdcf9241_10
World Bank GDP per capita, PPP (current international $), indicator NY.GDP.PCAP.PP.CD
API (no key needed): https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.PP.CD?format=json&per_page=20000&date=2010:2019
UK Government GHG conversion factors 2025 (per-km CO₂e for car, bus, rail/metro, etc.)
Page: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025
Download the "condensed set" spreadsheet from that page.
Google Maps Routes API (live trip routes). I will create the API key myself and put it in .streamlit/secrets.toml as GOOGLE_MAPS_API_KEY = "...". Do not create keys, enter credentials or change billing in the browser. Add secrets.toml to .gitignore.
Checkpoint 0 (minutes 0–5): inspect before building

Open the WHO Excel file and report to me: sheet names, column names, whether there are ISO3 codes, measurement year, station counts, latitude/longitude, and any flag showing PM2.5 converted from PM10. Do the same quick check on the conversion-factors sheet (find the rows for average petrol/diesel car, average local bus, national rail / underground, and per-passenger-km units). Then stop and show me what you found before continuing.

Step 1 (minutes 5–25): data
prep.py builds data/clean/cities.csv: one row per city with its most recent year that has PM2.5, plus PM10 and NO2 from that year, country, ISO3, year and station count if available.
Join World Bank GDP per capita on ISO3, using the GDP value for the same year (or nearest year available).
Build data/clean/emission_factors.json with kg CO₂e per passenger-km for: car, bus, rail/metro, bicycle (0), walk (0). Record the exact table name, row label and year for each factor so the app can cite it.
Commit the cleaned files so the app runs offline.
Step 2 (minutes 25–45): model and rules
model.py: fit a linear regression of log(PM2.5) on log(GDP per capita) with scikit-learn. For each city compute expected_pm25 and ratio = actual / expected. Save the R² and show it in the app.
Diagnosis:
ratio > 1.3 → "Worse than income peers: local causes likely, local action can help now."
otherwise → "In line with income peers: structural causes (energy, industry), national policy matters most."
Likely-cause rules (keep to about 6, each with a WHO/UNEP source link in a rules.json): high NO2 → traffic → low-emission zones, transit, cycling lanes; high PM10/PM2.5 ratio → dust → construction controls, paving, green cover; high PM2.5 with low NO2 → burning → clean cooking/heating, waste-burning bans. If NO2 or PM10 is missing, say "cause unclear" rather than guessing.
WHO limit multiple = PM2.5 / 5. Also show which WHO interim target the city meets (35, 25, 15, 10, then 5 µg/m³).
Step 3 (minutes 25–50, in parallel): trip comparison
routes.py: call the Routes API computeRoutes (POST https://routes.googleapis.com/directions/v2:computeRoutes) once each for DRIVE, TRANSIT, BICYCLE, WALK. Use a field mask for distance, duration and encoded polyline (plus transit step details if easy). Check the current Google docs for exact field names.
CO₂ per option = distance in km × factor. Recommendation = lowest-CO₂ option whose extra time over driving is within the user's tolerance slider (default 15 minutes).
Handle missing modes (e.g. no transit route in that city) gracefully.
Save one real API response to data/demo_route.json and add a "demo mode" toggle that loads it, so the demo works without internet or a key.
Step 4 (minutes 45–75): Streamlit front end (app.py)

One page, top to bottom:

City search with fuzzy matching (e.g. rapidfuzz).
Score card: big "N× the WHO limit" number, colour badge, data year, station count.
Peer comparison bar: actual vs expected PM2.5, with the diagnosis and likely cause.
Trip planner: from/to text inputs, time-tolerance slider, comparison cards for each mode (time, distance, kg CO₂), the recommended option, a map with routes drawn using folium + streamlit-folium (decode polylines with polyline), and a yearly-savings line ("3 days a week = X kg CO₂ a year").
"Write to your council" button: fills a letter template with the city's numbers, diagnosis and recommended intervention; show it in a text area with a copy/download button.
Footer citing WHO, World Bank, UK DESNZ conversion factors and Google Maps, plus a short honest note: station data, mostly 2010–2019, sparse in lower-income countries, not the official modelled SDG 11.6.2 figure.

Keep the design clean and readable; plain language, no jargon like "11.6.2" or "residual" on the main screen.

Step 5 (minutes 75–90): ship
requirements.txt, a short README.md (what it does, SDG link, data sources, how to run).
Run it locally and test three cities: Delhi, Beijing, Stockholm, plus one trip in a city with transit.
If I ask, help me deploy to Streamlit Community Cloud.
Cut rules if we fall behind
Minute 25 with no clean data: skip GDP, compare only against the WHO limit.
Minute 45 with no regression: use the country average as the comparison.
Minute 60 with Routes API problems: use demo mode only.
Minute 70: drop the council letter. Minute 80: stop adding features and fix bugs only.

Ask me before installing anything unusual, spending money, or entering any personal data in the browser.
