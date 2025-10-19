import os
from mangum import Mangum

# Ensure backend module is importable
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "backend"))

try:
    # backend/server.py defines `app` (FastAPI)
    from server import app as fastapi_app
except Exception as e:
    # If import fails, provide a simple fallback app to surface errors in logs
    from fastapi import FastAPI
    fallback = FastAPI()

    @fallback.get("/")
    def fallback_root():
        return {"error": "failed to import backend.server", "detail": str(e)}

    fastapi_app = fallback

# Mangum handler turns ASGI app into a Netlify function-compatible handler
handler = Mangum(fastapi_app)

def handler_function(event, context):
    # Netlify Python functions expect a callable named `handler` by default, but
    # we expose `handler_function` to make logs explicit.
    return handler(event, context)
