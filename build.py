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
