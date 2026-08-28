"""Guard the ASGI entry-point that `start_all.py` and deployment both launch.

`uvicorn asgi:app` is the only way the API server is ever started
(`src/reasoner/start_all.py:34`, and the command documented in CLAUDE.md).
Nothing else imports `asgi`, so when the `from reasoner.api import app` line was
dropped during a refactor the module still imported cleanly and every test still
passed -- uvicorn just died with `Attribute "app" not found in module "asgi"`
and the UI returned 502/504 from the Next proxy until someone read the log.
"""

from fastapi import FastAPI


def test_asgi_module_exposes_app() -> None:
    # Arrange / Act
    import asgi

    # Assert
    assert isinstance(asgi.app, FastAPI), "uvicorn asgi:app needs a FastAPI instance named 'app'"
