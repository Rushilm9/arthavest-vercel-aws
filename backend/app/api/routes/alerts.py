"""
Alerts Routes — Endpoint for retrieving background job alerts, plus WebSocket for instant push.
"""

import asyncio
import uuid
from datetime import datetime
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.models import Alerts, Users
from app.core.config import get_db, logger

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ── WebSocket Connection Manager ────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"[cyan]WebSocket client connected. Total: {len(self.active_connections)}[/cyan]"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"[yellow]WebSocket client disconnected. Total: {len(self.active_connections)}[/yellow]"
            )

    async def broadcast_alert(self, alert_data: dict):
        """Send a JSON payload to all connected clients instantly."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(alert_data)
            except Exception as e:
                logger.error(f"[red]Failed to send WS message: {e}[/red]")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


# Global manager instance
manager = ConnectionManager()


# ── Helper: fire-and-forget broadcast from sync code ────────────
def push_alert(alert_type: str, message: str):
    """
    Fire a WebSocket alert from anywhere in the backend (sync or async).
    Safe to call from sync pipeline code — schedules the coroutine on
    the running event loop without blocking.
    """
    alert_data = {
        "id": str(uuid.uuid4()),
        "type": alert_type,
        "message": message,
        "date": datetime.utcnow().isoformat(),
        "is_read": False,
    }
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast_alert(alert_data))
    except RuntimeError:
        # No running loop — skip silently (e.g. unit tests, CLI scripts)
        pass


# ── WebSocket Route ─────────────────────────────────────────────
@router.websocket("/ws")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alert streaming.
    Clients connect to ws://localhost:8000/alerts/ws
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive silently, waiting for the server to broadcast
            data = await websocket.receive_text()
            # We don't really expect client messages, but we hold the connection open
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Standard REST Route ─────────────────────────────────────────
@router.get("/")
def get_alerts(db: Session = Depends(get_db)):
    """
    Fetch all active alerts (for initial load when dashboard boots).
    Returns alerts for any user, or an empty list if none exist.
    """
    logger.info("[cyan]API: /alerts GET endpoint hit[/cyan]")
    try:
        alerts = db.query(Alerts).order_by(Alerts.created_at.desc()).limit(50).all()

        result = []
        for alert in alerts:
            result.append(
                {
                    "id": str(alert.id),
                    "type": alert.alert_type,
                    "message": alert.message,
                    "date": alert.created_at.isoformat() if alert.created_at else None,
                    "is_read": alert.is_read,
                }
            )

        return {"alerts": result}

    except Exception as e:
        logger.error(f"[red]API: /alerts failed — {e}[/red]")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch alerts: {str(e)}",
        )


# ── Test / Simulate endpoint ────────────────────────────────────
class SimulateAlertRequest(BaseModel):
    type: str = "INFO"
    message: str = "Test alert from backend"


@router.post("/test", summary="Push a test alert to all WebSocket clients")
async def test_alert(req: SimulateAlertRequest):
    """
    Dev/demo endpoint: broadcasts a fake alert to every connected
    WebSocket client so you can verify the pipeline end-to-end.
    """
    alert_data = {
        "id": str(uuid.uuid4()),
        "type": req.type,
        "message": req.message,
        "date": datetime.utcnow().isoformat(),
        "is_read": False,
    }
    await manager.broadcast_alert(alert_data)
    return {"ok": True, "sent_to": len(manager.active_connections), "alert": alert_data}
