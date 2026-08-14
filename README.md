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

## Getting started (first time, ~10 minutes)

**1. Create a GitHub account**, if you don't already have one — free, at
[github.com/join](https://github.com/join).

**2. Create a new repository.**
On github.com, click the **+** in the top right → **New repository**. Name it
something like `greece-slip-models`, set it to **Public** (required for free GitHub
Pages), leave "Add a README" unchecked, and click **Create repository**.

**3. Upload these files.**
Two ways to do this — pick whichever you're comfortable with:

- **No terminal needed:** on your new (empty) repo's page, click **"uploading an
  existing file"**. Drag this entire folder's contents in (or drag the folder itself —
  most browsers preserve the subfolder structure). Commit directly to `main`.
- **With git**, from inside this folder:
  ```bash
  git init
  git add .
  git commit -m "Initial commit"
  git branch -M main
  git remote add origin https://github.com/<your-username>/greece-slip-models.git
  git push -u origin main
  ```

**4. Turn on GitHub Pages.**
In your repo, go to **Settings → Pages**. Under "Build and deployment", set
**Source: GitHub Actions** (not "Deploy from a branch" — the workflow in this repo
handles the build itself). That's it — no folder picker needed.

**5. Watch it deploy.**
Go to the **Actions** tab — you'll see the "Build and deploy geobrowser to GitHub
Pages" run start automatically (it triggers on every push to `main`). Takes about a
minute. When it's green, go back to **Settings → Pages** and you'll see your live
public URL: `https://<your-username>.github.io/greece-slip-models/`. Anyone with that
link can open it — no login, no account needed on their end.

From here on, deploying an update just means pushing a change to `main` (or uploading
a new file through the GitHub website) — the Action rebuilds and republishes
automatically every time.

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

## What's real vs. placeholder right now

- The one existing record (`arkalochori2021_bonatis_2024.json`) has real event-level
  facts (M5.9, 2021, Arkalochori/Crete, normal faulting, ~1.0 m max slip) but a
  synthetic fault geometry and subfault slip grid — flagged explicitly in its
  `inversion.notes` field. Replace it with verified published values, or delete it,
  before treating the site as a real public database.
- The live seismicity overlay pulls real, current data from USGS's public earthquake
  feed at page-load time — genuinely live, but USGS under-detects smaller Greek
  earthquakes compared to NOA/EMSC's regional networks. Treat it as situational
  awareness, not the authoritative catalog.

## Open decisions for you and your collaborators

- Repository owner: your personal GitHub account, or an AUTH Geophysics / lab
  organization account? (Org account is generally better for a resource meant to
  outlive any one person's account.)
- Custom domain: GitHub Pages supports one for free (Settings → Pages → Custom
  domain) if you'd rather have e.g. `slipmodels.geo.auth.gr` than the
  `github.io` URL.
- Archival DOI: once the dataset has real content, a GitHub Release can be
  one-click-archived to Zenodo for a citable DOI — worth setting up when you're ready
  to point to this from the manuscript.
