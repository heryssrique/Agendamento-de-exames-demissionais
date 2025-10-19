# FastAPI on Vercel (Serverless Function)
# This module exposes the FastAPI `app` from backend.server using vercel-fastapi adapter.

from backend.server import app as fastapi_app

# Expose the FastAPI app directly. The Vercel Python runtime will detect and serve this ASGI app.
app = fastapi_app
