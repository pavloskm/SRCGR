
#!/usr/bin/env python3
"""
Build dist/index.html.

Validate every data/models/*.json record against schema.json,
then inline the complete dataset into template.html to produce
a single self-contained, shareable HTML file.

No server, backend, or CORS issues when opened directly from disk.

Run this script whenever you add or edit a model file.

The script reports all JSON syntax and schema validation errors
instead of stopping at the first invalid file.
"""

import datetime
import json
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent

MODELS_DIR = HERE / "data" / "models"
SCHEMA_PATH = HERE / "schema.json"
TEMPLATE_PATH = HERE / "template.html"
DIST_PATH = HERE / "dist" / "index.html"


def load_json(path):
    """
    Read and parse a JSON file.

    Return the parsed object if successful.
    Return None if the file cannot be parsed.
    """

    try:
        return json.loads(path.read_text(encoding="utf-8"))

    except json.JSONDecodeError as error:
        print(f"\nINVALID JSON: {path.name}")
        print(f"  Line: {error.lineno}")
        print(f"  Column: {error.colno}")
        print(f"  Error: {error.msg}")

        # Display the problematic line and its surroundings.
        lines = path.read_text(encoding="utf-8").splitlines()

        start = max(0, error.lineno - 3)
        end = min(len(lines), error.lineno + 2)

        print("\n  Context:")

        for index in range(start, end):
            marker = ">>" if index + 1 == error.lineno else "  "
            print(f"  {marker} {index + 1}: {lines[index]}")

        print()
        return None

    except (OSError, UnicodeError) as error:
        print(f"\nERROR READING: {path.name}")
        print(f"  {error}")
        return None


def main():

    print("=" * 65)
    print("GREECE SLIP MODEL DATABASE - BUILD")
    print("=" * 65)

    # --------------------------------------------------
    # 1. Load and validate the JSON Schema
    # --------------------------------------------------

    print("\nLoading schema.json...")

    schema = load_json(SCHEMA_PATH)

    if schema is None:
        print("\nBuild aborted: unable to load schema.json.")
        return 1

    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

    except Exception as error:
        print("\nINVALID SCHEMA: schema.json")
        print(f"  {error}")
        return 1

    print("Schema loaded successfully.")

    # --------------------------------------------------
    # 2. Find model files
    # --------------------------------------------------

    if not MODELS_DIR.exists():
        print(f"\nERROR: Model directory does not exist: {MODELS_DIR}")
        return 1

    files = sorted(MODELS_DIR.glob("*.json"))

    if not files:
        print(f"\nNo model files found in {MODELS_DIR}")
        return 1

    print(f"\nFound {len(files)} JSON model file(s).")

    # --------------------------------------------------
    # 3. Parse and validate every model
    # --------------------------------------------------

    models = []

    syntax_errors = 0
    schema_errors = 0
    valid_files = 0

    for index, file_path in enumerate(files, start=1):

        print("\n" + "-" * 65)
        print(
            f"Checking [{index}/{len(files)}]: "
            f"{file_path.name}",
            flush=True
        )

        # Parse the JSON file.
        record = load_json(file_path)

        if record is None:
            syntax_errors += 1
            continue

        # Validate against schema.json.
        errors = sorted(
            validator.iter_errors(record),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message
            )
        )

        if errors:
            schema_errors += len(errors)

            print(f"\nINVALID SCHEMA: {file_path.name}")
            print(f"  Found {len(errors)} validation error(s).")

            for error_number, error in enumerate(errors, start=1):

                path = "/".join(
                    str(part) for part in error.absolute_path
                ) or "(root)"

                print(
                    f"  [{error_number}] "
                    f"at {path}: {error.message}"
                )

            continue

        # Only valid models are added.
        models.append(record)
        valid_files += 1

        print(f"OK: {file_path.name}")

    # --------------------------------------------------
    # 4. Print validation summary
    # --------------------------------------------------

    print("\n" + "=" * 65)
    print("VALIDATION SUMMARY")
    print("=" * 65)

    print(f"Total model files:       {len(files)}")
    print(f"Valid model files:       {valid_files}")
    print(f"Files with syntax errors:{syntax_errors:>5}")
    print(f"Schema validation errors:{schema_errors:>5}")

    if syntax_errors > 0 or schema_errors > 0:

        print("\nBUILD FAILED.")
        print("Fix the errors listed above before rebuilding.")
        print("No new HTML file has been generated.")

        return 1

    # --------------------------------------------------
    # 5. Check duplicate model IDs
    # --------------------------------------------------

    ids = [model["model_id"] for model in models]

    counts = Counter(ids)

    duplicates = {
        model_id: count
        for model_id, count in counts.items()
        if count > 1
    }

    if duplicates:

        print("\nBUILD FAILED: Duplicate model_id values detected.")

        for model_id, count in sorted(duplicates.items()):
            print(f"  {model_id}: appears {count} times")

        return 1

    print("\nAll model IDs are unique.")

    # --------------------------------------------------
    # 6. Load HTML template
    # --------------------------------------------------

    print("\nLoading HTML template...")

    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

    except (OSError, UnicodeError) as error:
        print(f"\nERROR READING TEMPLATE: {error}")
        return 1

    # Check required placeholders.
    placeholders = [
        "__MODELS_JSON__",
        "__BUILT_AT__",
        "__MODEL_COUNT__"
    ]

    missing = [
        placeholder
        for placeholder in placeholders
        if placeholder not in template
    ]

    if missing:
        print("\nBUILD FAILED: Missing template placeholders.")

        for placeholder in missing:
            print(f"  {placeholder}")

        return 1

    # --------------------------------------------------
    # 7. Generate the website
    # --------------------------------------------------

    print("\nGenerating website...")

    data_json = json.dumps(
        models,
        ensure_ascii=False
    )

    # Prevent embedded model text from terminating an HTML script tag.
    data_json = data_json.replace("<", "\\u003c")

    built_at = datetime.date.today().isoformat()

    out = (
        template
        .replace("__MODELS_JSON__", data_json)
        .replace("__BUILT_AT__", built_at)
        .replace("__MODEL_COUNT__", str(len(models)))
    )

    # --------------------------------------------------
    # 8. Save the generated HTML
    # --------------------------------------------------

    try:
        DIST_PATH.parent.mkdir(
            exist_ok=True,
            parents=True
        )

        DIST_PATH.write_text(
            out,
            encoding="utf-8"
        )

    except OSError as error:
        print(f"\nBUILD FAILED: Cannot write output file: {error}")
        return 1

    # --------------------------------------------------
    # 9. Final success message
    # --------------------------------------------------

    event_ids = {
        model["event"]["event_id"]
        for model in models
    }

    print("\n" + "=" * 65)
    print("BUILD SUCCESSFUL")
    print("=" * 65)

    print(f"Output: {DIST_PATH}")
    print(f"Models: {len(models)}")
    print(f"Distinct earthquakes: {len(event_ids)}")

    print("\nAll models passed JSON syntax and schema validation.")
    print("The website is ready for deployment.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
