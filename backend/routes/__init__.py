"""EtOH backend modular routers (admin, subscription, public_hub, enrich…).

Each module here exposes a `router: APIRouter` registered by `server.py`
via `app.include_router(...)`. New domains should land here, not in server.py.
"""
