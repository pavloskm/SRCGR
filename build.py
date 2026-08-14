#!/usr/bin/env python3
"""
Build dist/index.html: validate every data/models/*.json record against
schema.json, then inline the whole dataset into template.html to produce a
single self-contained, shareable HTML file (no server, no backend, no CORS
issues when opened directly from disk).

Run this again any time you add/edit a model file in data/models/.
"""
import datetime
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
MODELS_DIR = HERE / "data" / "models"
SCHEMA_PATH = HERE / "schema.json"
TEMPLATE_PATH = HERE / "template.html"
DIST_PATH = HERE / "dist" / "index.html"


def main():
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema)

    models = []
    had_errors = False
    files = sorted(MODELS_DIR.glob("*.json"))
    if not files:
        print(f"No model files found in {MODELS_DIR}")
        return 1

    for f in files:
        record = json.loads(f.read_text())
        errors = list(validator.iter_errors(record))
        if errors:
            had_errors = True
            print(f"INVALID: {f.name}")
            for e in errors:
                path = "/".join(str(p) for p in e.path) or "(root)"
                print(f"  - at {path}: {e.message}")
        else:
            models.append(record)
            print(f"OK: {f.name}")

    if had_errors:
        print("\nBuild aborted — fix the errors above before rebuilding.")
        return 1

    # de-dupe check on model_id
    ids = [m["model_id"] for m in models]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"\nBuild aborted — duplicate model_id(s): {dupes}")
        return 1

    template = TEMPLATE_PATH.read_text()
    data_json = json.dumps(models, ensure_ascii=False)
    built_at = datetime.date.today().isoformat()

    out = (
        template
        .replace("__MODELS_JSON__", data_json)
        .replace("__BUILT_AT__", built_at)
        .replace("__MODEL_COUNT__", str(len(models)))
    )

    DIST_PATH.parent.mkdir(exist_ok=True, parents=True)
    DIST_PATH.write_text(out, encoding="utf-8")
    print(f"\nBuilt {DIST_PATH} with {len(models)} model(s), {len(set(ids))} distinct event(s).")
    print("This single file is ready to deploy — see README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
