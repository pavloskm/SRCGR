#!/usr/bin/env python3
"""Validate independent contributor models, group earthquakes, build dist/index.html.

Usage: python build.py
Contributors need only place model JSON files into data/models/. They do not
need to coordinate event_id or model_id with other contributors. Source files
are NEVER rewritten. event_registry.json is generated and should be committed.
"""
import datetime
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime as _EventDateTime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / 'data' / 'models'
SCHEMA_PATH = HERE / 'schema.json'
TEMPLATE_PATH = HERE / 'template.html'
DIST_PATH = HERE / 'dist' / 'index.html'
REGISTRY_PATH = HERE / 'event_registry.json'
OVERRIDES_PATH = HERE / 'event_overrides.json'
REVIEW_PATH = HERE / 'event_review.json'


# ====== Automatic earthquake matching ======


class MatchError(ValueError):
    def __init__(self, message, review=None):
        super().__init__(message)
        self.review = review or []


def _parse_time(value, source):
    if not isinstance(value, str) or not value.strip():
        raise MatchError(f"{source}: event.origin_time (UTC) is required for automatic matching.")
    try:
        timestamp = _EventDateTime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('missing timezone')
        return timestamp.astimezone(timezone.utc)
    except ValueError:
        raise MatchError(f"{source}: invalid event.origin_time: {value!r}; provide an ISO 8601 UTC time (e.g. 2017-07-20T22:31:11Z).")


def _coordinates(event):
    h = event.get('hypocenter') or {}
    try:
        lat, lon = float(h.get('latitude')), float(h.get('longitude'))
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    except (TypeError, ValueError):
        pass
    return None


def _haversine(a, b):
    dlat, dlon = map(math.radians, (b[0] - a[0], b[1] - a[1]))
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def _observation(model, filename):
    event = model.get('event')
    if not isinstance(event, dict):
        raise MatchError(f'{filename}: event object is missing.')
    dt = _parse_time(event.get('origin_time'), filename)
    coords = _coordinates(event)
    try:
        mag = float(event['magnitude'])
        if not math.isfinite(mag):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise MatchError(f'{filename}: event.magnitude must be a finite number.')
    return {'origin_time_utc': dt.isoformat().replace('+00:00', 'Z'),
            'latitude': coords[0] if coords else None,
            'longitude': coords[1] if coords else None,
            'magnitude': mag,
            'name': str(event.get('name') or filename)}


def _similarity(o, anchor):
    a = _parse_time(o['origin_time_utc'], 'observation')
    b = _parse_time(anchor['origin_time_utc'], 'registry event')
    seconds = abs((a - b).total_seconds())
    if seconds > 300:
        return 'different', seconds, None
    if abs(o['magnitude'] - anchor['magnitude']) > 1.5:
        return 'different', seconds, None
    ca = (o['latitude'], o['longitude']) if o['latitude'] is not None and o['longitude'] is not None else None
    cb = (anchor['latitude'], anchor['longitude']) if anchor['latitude'] is not None and anchor['longitude'] is not None else None
    distance = _haversine(ca, cb) if ca and cb else None
    if distance is not None:
        if distance > 50:
            return 'different', seconds, distance
        if seconds <= 5 and distance <= 20 and abs(o['magnitude'] - anchor['magnitude']) <= 0.5:
            return 'match', seconds, distance
        return 'review', seconds, distance
    # No reliable map coordinates: ONLY virtually identical UTC times can auto-match.
    if seconds <= 1 and abs(o['magnitude'] - anchor['magnitude']) <= 0.4:
        return 'match', seconds, None
    return 'review', seconds, None


def _new_key(obs, keys, salt=""):
    date = _parse_time(obs['origin_time_utc'], 'new event').strftime('%Y%m%dT%H%M%S')
    fingerprint = json.dumps([obs['origin_time_utc'], obs['latitude'], obs['longitude'], obs['name'], salt], ensure_ascii=False)
    digest = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:10]
    key = f'evt_{date}_{digest}'
    if key in keys:
        raise MatchError('Event key collision; choose a different manual override or contact the maintainer.')
    return key


def _model_id_for(filename, model):
    """Generate a valid legacy-form model_id for contributors who omit it."""
    authors = (model.get('reference') or {}).get('authors') or []
    a = (str(authors[0]).split(',')[0] if authors else 'unknown').split(' ')[-1]
    author = ''.join(c for c in unicodedata.normalize('NFKD', a).lower() if c in 'abcdefghijklmnopqrstuvwxyz') or 'unknown'
    year = str((model.get('reference') or {}).get('year') or '2000')
    if not re.fullmatch(r'\d{4}', year):
        year = '2000'
    prefix = hashlib.sha1(filename.encode('utf-8')).hexdigest()[:16]
    return f'auto{prefix}_{author}_{year}'


def group_models(model_files, registry, overrides):
    """Return (normalized_models, registry_to_save, review_events).

    model_files contains (relative_filename, model_dictionary). All operations are
    in-memory; the caller only saves the registry AFTER its full build succeeds.
    An override maps a filename to an existing event key or to 'separate'.
    """
    if not isinstance(registry, dict):
        raise MatchError('event_registry.json must contain a JSON object')
    events = json.loads(json.dumps(registry.get('events') or {}))
    old_assignments = registry.get('assignments') or {}
    assignments = {}
    if not isinstance(events, dict) or not isinstance(overrides, dict):
        raise MatchError('Invalid event registry or override format')
    normalized = []
    review = []
    for filename, original in sorted(model_files, key=lambda x: x[0].casefold()):
        model = json.loads(json.dumps(original))
        obs = _observation(model, filename)
        event_signature = hashlib.sha256(json.dumps([obs['origin_time_utc'], obs['latitude'], obs['longitude'], obs['magnitude']], ensure_ascii=False).encode()).hexdigest()
        override = overrides.get(filename)
        if override is not None and not isinstance(override, str):
            raise MatchError(f'{filename}: override must be an event key or "separate"')
        old = old_assignments.get(filename, {})
        if override and override != 'separate':
            if override not in events:
                raise MatchError(f'{filename}: manual override references unknown event key {override!r}. Known: {list(events)}')
            key = override
        elif override is None and old.get('signature') == event_signature and old.get('event_key') in events:
            key = old['event_key']
        else:
            candidates = []
            uncertainties = []
            for other_key, anchor in events.items():
                status, seconds, km = _similarity(obs, anchor)
                if status == 'match':
                    candidates.append((other_key, seconds, km))
                elif status == 'review':
                    uncertainties.append({'key': other_key, 'time_difference_seconds': round(seconds, 2),
                                          'distance_km': round(km, 2) if km is not None else None,
                                          'event_name': anchor['name']})
            if override == 'separate':
                # 'separate' must ALSO be able to undo a mistaken earlier auto-merge.
                old_key = old.get('event_key')
                siblings = any(name != filename and a.get('event_key') == old_key for name, a in old_assignments.items())
                if old_key in events and not siblings:
                    key = old_key
                else:
                    key = _new_key(obs, events, salt=filename)
            elif len(candidates) == 1 and not uncertainties:
                key = candidates[0][0]
            elif not candidates and not uncertainties:
                key = _new_key(obs, events)
            else:
                review.append({'file': filename, 'origin_time_utc': obs['origin_time_utc'],
                               'location': [obs['latitude'], obs['longitude']],
                               'matches': [x[0] for x in candidates], 'possible_matches': uncertainties,
                               'action': 'In event_overrides.json, map this filename to an existing event key, or "separate".'})
                continue
        if key not in events:
            events[key] = obs
        elif events[key].get('latitude') is None and obs['latitude'] is not None:
            # An exact-time match may enrich a previously unlocated event.
            events[key]['latitude'] = obs['latitude']
            events[key]['longitude'] = obs['longitude']
        assignments[filename] = {'event_key': key, 'signature': event_signature}
        # Existing contributor metadata is kept; IDs are not used to group events.
        model['event'].setdefault('event_id', key)
        if not model['event'].get('event_id'):
            model['event']['event_id'] = key
        if not model.get('model_id'):
            model['model_id'] = _model_id_for(filename, model)
        model['_browser_event_key'] = key
        model['_browser_event_location'] = {'latitude': events[key].get('latitude'), 'longitude': events[key].get('longitude')}
        model['_browser_model_key'] = filename
        normalized.append((filename, model))
    if review:
        raise MatchError(f'{len(review)} contributor file(s) need human review before event grouping.', review)
    # All source records for a grouped event share the same fixed map anchor,
    # even if a later paper supplied the only valid epicentral coordinates.
    for _, model in normalized:
        anchor = events[model['_browser_event_key']]
        model['_browser_event_location'] = {'latitude': anchor.get('latitude'), 'longitude': anchor.get('longitude')}
    return normalized, {'version': 1, 'events': events, 'assignments': assignments}, review


# ====== JSON validation and HTML generation ======

def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f'\nINVALID JSON: {path.name}\n  Line: {e.lineno}\n  Column: {e.colno}\n  Error: {e.msg}')
        lines = path.read_text(encoding='utf-8').splitlines()
        for i in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 2)):
            print(f'  {">>" if i + 1 == e.lineno else "  "} {i+1}: {lines[i]}')
        return None
    except (OSError, UnicodeError) as e:
        print(f'ERROR READING {path.name}: {e}')
        return None


def optional_json(path, default):
    if not path.exists():
        return default
    value = load_json(path)
    if value is None:
        raise ValueError(f'Cannot load {path.name}')
    return value


def save_json_atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def main():
    print('=' * 65)
    print('GREECE SLIP MODEL DATABASE - BUILD')
    print('=' * 65)
    schema = load_json(SCHEMA_PATH)
    if schema is None:
        print('BUILD FAILED: missing or invalid schema.json')
        return 1
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except Exception as e:
        print(f'INVALID SCHEMA: {e}')
        return 1

    files = sorted(MODELS_DIR.glob('*.json'))
    print(f'Found {len(files)} JSON model file(s).')
    if not files:
        print('BUILD FAILED: put contributor records into data/models/.')
        return 1
    input_models = []
    syntax_errors = 0
    for index, path in enumerate(files, start=1):
        print(f'Checking [{index}/{len(files)}]: {path.name}')
        raw = load_json(path)
        if raw is None:
            syntax_errors += 1
        else:
            input_models.append((path.name, raw))
    if syntax_errors:
        print(f'BUILD FAILED: {syntax_errors} JSON syntax/read errors. No output generated.')
        return 1
    try:
        registry = optional_json(REGISTRY_PATH, {'version': 1, 'events': {}, 'assignments': {}})
        overrides = optional_json(OVERRIDES_PATH, {})
        resolved, pending_registry, _ = group_models(input_models, registry, overrides)
    except (MatchError, ValueError) as e:
        print(f'\nEVENT MATCHING NEEDS REVIEW: {e}')
        if isinstance(e, MatchError) and e.review:
            save_json_atomic(REVIEW_PATH, {'review': e.review, 'instructions':
                'Edit event_overrides.json (create it if necessary). Map a filename to an event key from possible_matches, or to "separate". Do not edit contributor JSON.'})
            for r in e.review:
                print(f"  {r['file']}: matches={r['matches']}, possible={r['possible_matches']}")
            print(f'Review details: {REVIEW_PATH}')
        print('No new HTML generated; no potentially incorrect earthquake merging performed.')
        return 1

    models = []
    schema_errors = 0
    for filename, model in resolved:
        schema_record = {k: v for k, v in model.items() if not k.startswith('_browser_')}
        errors = sorted(validator.iter_errors(schema_record), key=lambda e: (tuple(str(p) for p in e.absolute_path), e.message))
        if errors:
            schema_errors += len(errors)
            print(f'\nINVALID SCHEMA: {filename} ({len(errors)} error(s))')
            for no, error in enumerate(errors, start=1):
                path = '/'.join(map(str, error.absolute_path)) or '(root)'
                print(f'  [{no}] at {path}: {error.message}')
        else:
            models.append(model)
            print(f'OK: {filename}')
    if schema_errors:
        print(f'\nBUILD FAILED: {schema_errors} schema validation errors. No new HTML generated.')
        print('Contributed source files have not been modified.')
        return 1

    # Two distinct files may legitimately contain identical contributor model_id
    # values (e.g. two geometry alternatives from the same publication).
    # The browser uses the unique SOURCE FILENAME as its selection key.
    duplicates = {k: n for k, n in Counter(m['model_id'] for m in models).items() if n > 1}
    if duplicates:
        print(f'NOTE: duplicate publication model_id values found; separate variants retained: {duplicates}')
    event_count = len({m['_browser_event_key'] for m in models})
    print(f'\nMatched {len(models)} models into {event_count} distinct earthquakes.')
    print(f'IDs supplied by contributors are informational, not used for matching.')

    try:
        template = TEMPLATE_PATH.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as e:
        print(f'BUILD FAILED: unable to read template.html: {e}')
        return 1
    required = ['__MODELS_JSON__', '__BUILT_AT__', '__MODEL_COUNT__']
    missing = [s for s in required if s not in template]
    if missing:
        print(f'BUILD FAILED: missing template placeholders {missing}')
        return 1
    json_blob = json.dumps(models, ensure_ascii=False).replace('<', '\\u003c')
    document = (template.replace('__MODELS_JSON__', json_blob)
                .replace('__BUILT_AT__', datetime.date.today().isoformat())
                .replace('__MODEL_COUNT__', str(len(models))))
    try:
        DIST_PATH.parent.mkdir(exist_ok=True, parents=True)
        save_json_atomic(REGISTRY_PATH, pending_registry)
        DIST_PATH.write_text(document, encoding='utf-8')
        REVIEW_PATH.unlink(missing_ok=True)
    except OSError as e:
        print(f'BUILD FAILED writing output: {e}')
        return 1

    print('\nBUILD SUCCESSFUL')
    print(f'Output: {DIST_PATH}')
    print(f'Models: {len(models)}')
    print(f'Distinct earthquakes: {event_count}')
    print(f'Persistent registry: {REGISTRY_PATH} (commit this file to version control)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
