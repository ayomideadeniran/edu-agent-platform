"""WSGI entrypoint for Gunicorn / Render deployments.

This module exposes the Flask `app` object at module-level so gunicorn can import
it using `gunicorn wsgi:app`.

It imports the `app` instance from `src.app` (the Flask app in this repo). If you
prefer to keep a different layout, update the import accordingly or use
`gunicorn src.app:app` in the start command.
"""
from __future__ import annotations

import os

try:
    # Import the Flask app object from the src package
    from src.app import app  # type: ignore
except Exception as exc:  # pragma: no cover - helpful error message at runtime
    # Provide a clearer error message than a raw ModuleNotFoundError when the
    # module path is misconfigured on the host (common on Render).
    raise RuntimeError(
        "Failed to import Flask app from 'src.app'. Ensure 'src/app.py' exists "
        "and the start command points to the correct module (for example, "
        "'gunicorn wsgi:app' or 'gunicorn src.app:app'). Original error: "
        f"{exc!r}"
    ) from exc


if __name__ == "__main__":
    # Allow running locally with `python wsgi.py` for quick tests. Bind to the
    # PORT env var if provided (Render sets PORT). Use 0.0.0.0 so external
    # requests reach the container.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
