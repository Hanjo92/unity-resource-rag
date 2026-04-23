# Contributing

Thanks for helping improve Unity Resource RAG.

## Local setup

Use Python 3.11 or 3.12 for the sidecar and test suite.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If `python3.12` is not available, use another Python 3.11+ interpreter such as `python3.11`, `python3`, or the equivalent Windows launcher.

## Verification

Run the Python checks before you open a PR:

```bash
python -m unittest discover -s tests -v
python -m compileall pipeline
python scripts/build_sidecar_bundle.py --output-dir dist
```

The bundle smoke test should finish without errors and leave a portable sidecar bundle under the output directory.

## Unity smoke check

Do a minimal Unity validation before asking for review:

1. Open the project in a supported Unity editor.
2. Confirm `Window > Unity Resource RAG` opens.
3. Run `Quick Setup`.
4. Refresh the Readiness Dashboard and confirm the editor can see the package and sidecar path you expect.

If the change touches the package surface or editor integration, also verify the package loads in a clean project or a fresh project checkout.

## Quality cases

Use the existing `quality-case-report` issue template when you want to record a real validation run.

- Keep the report tied to one concrete project or screen.
- Include the reference source, blueprint path, and before/after artifacts.
- Capture what matched well, what did not, and the most useful follow-up ideas.

Do not replace the quality-case template with a generic bug report; it exists to preserve real project validation history.
