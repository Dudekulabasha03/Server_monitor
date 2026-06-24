"""
AMD Fleet Monitor — FastAPI Application Entry Point
"""
import asyncio
from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import make_asgi_app

from app.config import settings
from app.api.servers import router as servers_router
from app.api.alerts import router as alerts_router
from app.api.metrics import router as metrics_router
from app.api.inventory import router as inventory_router
from app.api.racks import router as racks_router
from app.api.users import router as users_router
from app.api.intelligence import router as intelligence_router
from app.api.firmware import router as firmware_router
from app.api.lifecycle import router as lifecycle_router
from app.api.reports import router as reports_router
from app.api.timeseries import router as timeseries_router
from app.api.utilization import router as utilization_router
from app.api.changelog import router as changelog_router
from app.api.triage import router as triage_router
from app.api.usage import router as usage_router
from app.api.ai import router as ai_router
from app.api.bios import router as bios_router
from app.api.livemon import router as livemon_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.reservations import router as reservations_router
from app.api.superadmin import router as superadmin_router
from app.api.export import router as export_router

log = structlog.get_logger(__name__)

# Active WebSocket connections for real-time push
_ws_clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("fleet_monitor_starting", version=settings.APP_VERSION)
    if settings.RBAC_ENABLED:
        from app.database import AsyncSessionLocal
        from app.core.seed import seed_rbac
        async with AsyncSessionLocal() as db:
            await seed_rbac(db)
    yield
    log.info("fleet_monitor_shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Routers
app.include_router(servers_router)
app.include_router(alerts_router)
app.include_router(metrics_router)
app.include_router(inventory_router)
app.include_router(racks_router)
app.include_router(users_router)
app.include_router(intelligence_router)
app.include_router(firmware_router)
app.include_router(lifecycle_router)
app.include_router(reports_router)
app.include_router(timeseries_router)
app.include_router(utilization_router)
app.include_router(changelog_router)
app.include_router(usage_router)
app.include_router(ai_router)
app.include_router(bios_router)
app.include_router(livemon_router)
app.include_router(triage_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(reservations_router)
app.include_router(superadmin_router)
app.include_router(export_router)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    Real-time metric push to dashboard clients.
    Sends server status updates every 5 seconds.
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    log.info("ws_client_connected", clients=len(_ws_clients))
    try:
        while True:
            # Keep connection alive; data pushed via broadcast_update()
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
        log.info("ws_client_disconnected", clients=len(_ws_clients))


async def broadcast_update(data: dict):
    """Broadcast to all connected WebSocket clients."""
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.add(ws)
    _ws_clients.difference_update(disconnected)
