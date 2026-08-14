# Greece Finite-Fault Slip Model Geobrowser

A FAIR-aligned, public, interactive database of published finite-fault slip models for
earthquakes in Greece — companion resource to Vavlas & Bonatis, *Unveiling the Unseen*.

This repo contains:
- `schema.json` — the data format every slip model record follows.
- `data/models/*.json` — one file per published model (currently one illustrative
  placeholder record; add real ones here).
- `template.html` + `build.py` — `build.py` validates every file in `data/models/`
  against `schema.json`, then inlines the whole dataset into `template.html` to
  produce `dist/index.html`: a single self-contained, interactive map/browser page
  (basemap switcher, live seismicity overlay, filters, per-model slip visualization).
- `.github/workflows/deploy.yml` — rebuilds and republishes the site automatically
  every time you push a change.

## Adding a new slip model

1. Copy `data/models/arkalochori2021_bonatis_2024.json` as a starting template.
2. Fill in real values for the new event/model, following the field definitions in
   `schema.json` (each field has a `description`).
3. Commit and push (or upload via the GitHub website). The Action validates the file
   against the schema automatically — if something's missing or malformed, the Action
   run fails with a clear error instead of breaking the live site.
4. Once the Action succeeds, the new model appears on the live page within a minute or
   two.

## Running/testing locally before pushing (optional)

```bash
pip install jsonschema --break-system-packages   # once
python3 build.py
open dist/index.html   # or just double-click it
```
