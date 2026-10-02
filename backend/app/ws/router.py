import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.security import decode_access_token
from app.config import settings
from app.risk.access import is_risk_viewer

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_access_token(token)
        account_id = int(payload["sub"])
        can_view_risk = is_risk_viewer(payload.get("username"))
    except Exception:
        await websocket.close(code=4401)
        return

    manager = websocket.app.state.ws_manager
    engine = websocket.app.state.engine

    await websocket.accept()
    manager.connect(websocket, account_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")
            symbols = message.get("payload", {}).get("symbols", [])

            if msg_type == "subscribe":
                for symbol in symbols:
                    symbol = symbol.upper()
                    manager.subscribe_symbol(websocket, symbol)
                    snapshot = engine.book(symbol).depth_snapshot(settings.book_depth_levels)
                    await websocket.send_text(
                        json.dumps({"type": "book_snapshot", "payload": {"symbol": symbol, **snapshot}})
                    )
            elif msg_type == "unsubscribe":
                for symbol in symbols:
                    manager.unsubscribe_symbol(websocket, symbol.upper())
            elif msg_type == "subscribe_risk" and can_view_risk:
                # Silently ignored for everyone else: the push is only a
                # "refetch" nudge, and the REST endpoint enforces access anyway.
                manager.subscribe_risk(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
