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
