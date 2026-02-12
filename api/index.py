# FastAPI on Vercel (Serverless Function)
# This module exposes the FastAPI `app` from backend.server using vercel-fastapi adapter.

from backend.server import app as fastapi_app

try:
    # vercel-fastapi wraps FastAPI into a Vercel-compatible handler
    from vercel_fastapi import VercelFastAPI

    app = VercelFastAPI(fastapi_app)
except Exception:
    # Fallback: export raw FastAPI app (useful for local runs)
    app = fastapi_app
