"""Application-level (post-Logon) FIX message handling.

Only NewOrderSingle and MarketDataRequest are implemented -- the two flows
the platform template asks for ("send in market data and/or send in
orders"). OrderCancelRequest and other message types are natural extension
points, left unimplemented rather than faked.
"""

import asyncio
import json

import simplefix
import websockets

from app.config import settings
from app.engine_client import engine_client

SIDE_MAP = {"1": "BUY", "2": "SELL"}
ORD_TYPE_MAP = {"1": "MARKET", "2": "LIMIT"}
ORD_STATUS_MAP = {
    "NEW": "0",
    "PARTIALLY_FILLED": "1",
    "FILLED": "2",
    "CANCELED": "4",
    "REJECTED": "8",
}


async def handle_application_message(session, msg: simplefix.FixMessage) -> None:
    msg_type = msg.get(35).decode()
    if msg_type == "D":
        await _handle_new_order_single(session, msg)
    elif msg_type == "V":
        await _handle_market_data_request(session, msg)


async def _handle_new_order_single(session, msg: simplefix.FixMessage) -> None:
    cl_ord_id = msg.get(11).decode()
    symbol = msg.get(55).decode()
    side = SIDE_MAP.get(msg.get(54).decode(), "BUY")
    ord_type = ORD_TYPE_MAP.get(msg.get(40).decode(), "LIMIT")
    qty = msg.get(38).decode()
    price_raw = msg.get(44)
    price = price_raw.decode() if price_raw else None

    try:
        order = await engine_client.submit_order(
            session.sender_comp_id, symbol=symbol, side=side, order_type=ord_type, qty=qty, price=price
        )
    except Exception as exc:
        await _send_execution_report(
            session,
            cl_ord_id,
            {
                "order_id": "NONE",
                "status": "REJECTED",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "leaves_qty": "0",
                "reject_reason": str(exc),
                "fills": [],
            },
        )
        return

    await _send_execution_report(session, cl_ord_id, order)


async def _send_execution_report(session, cl_ord_id: str, order: dict) -> None:
    fills = order.get("fills") or []
    is_reject = order["status"] == "REJECTED"
    exec_type = "8" if is_reject else {"FILLED": "2", "PARTIALLY_FILLED": "1"}.get(order["status"], "0")

    report = session.new_message("8")
    report.append_pair(37, str(order["order_id"]))  # OrderID
    report.append_pair(11, cl_ord_id)  # ClOrdID
    report.append_pair(17, f"E-{order['order_id']}-{len(fills)}")  # ExecID
    report.append_pair(150, exec_type)  # ExecType
    report.append_pair(39, ORD_STATUS_MAP.get(order["status"], "0"))  # OrdStatus
    report.append_pair(55, order["symbol"])
    report.append_pair(54, "1" if order["side"] == "BUY" else "2")
    report.append_pair(38, str(order["qty"]))
    if order.get("price"):
        report.append_pair(44, str(order["price"]))
    report.append_pair(151, str(order["leaves_qty"]))  # LeavesQty
    report.append_pair(14, str(sum(float(f["qty"]) for f in fills)))  # CumQty
    if fills:
        last = fills[-1]
        report.append_pair(32, str(last["qty"]))  # LastQty
        report.append_pair(31, str(last["price"]))  # LastPx
    if is_reject and order.get("reject_reason"):
        report.append_pair(58, order["reject_reason"])  # Text
    await session.send(report)


async def _handle_market_data_request(session, msg: simplefix.FixMessage) -> None:
    md_req_id = msg.get(262).decode()
    symbol = msg.get(55).decode()
    sub_type = msg.get(263)

    book = await engine_client.get_order_book(symbol)
    await _send_market_data_snapshot(session, md_req_id, book)

    # SubscriptionRequestType 1 = snapshot + ongoing updates.
    if sub_type and sub_type.decode() == "1":
        asyncio.create_task(_relay_incremental_updates(session, md_req_id, symbol))


async def _send_market_data_snapshot(session, md_req_id: str, book: dict) -> None:
    msg = session.new_message("W")  # MarketDataSnapshotFullRefresh
    msg.append_pair(262, md_req_id)
    msg.append_pair(55, book["symbol"])
    entries = [("0", lvl) for lvl in book["bids"]] + [("1", lvl) for lvl in book["asks"]]
    msg.append_pair(268, len(entries))  # NoMDEntries
    for entry_type, lvl in entries:
        msg.append_pair(269, entry_type)  # MDEntryType: 0=Bid, 1=Offer
        msg.append_pair(270, lvl["price"])  # MDEntryPx
        msg.append_pair(271, lvl["qty"])  # MDEntrySize
    await session.send(msg)


async def _relay_incremental_updates(session, md_req_id: str, symbol: str) -> None:
    """Opens our own WS connection to the backend -- the same live feed the
    React GUI uses -- and republishes book updates as FIX
    MarketDataIncrementalRefresh for the life of the FIX session."""
    token = await engine_client.token_for(session.sender_comp_id)
    url = f"{settings.backend_ws_url}?token={token}"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "subscribe", "payload": {"symbols": [symbol]}}))
            async for raw in ws:
                if not session.logged_on:
                    break
                event = json.loads(raw)
                if event.get("type") == "book_snapshot":
                    await _send_incremental_refresh(session, md_req_id, event["payload"])
    except Exception:
        pass  # best-effort relay; a dropped feed doesn't take down the FIX session


async def _send_incremental_refresh(session, md_req_id: str, book: dict) -> None:
    msg = session.new_message("X")  # MarketDataIncrementalRefresh
    msg.append_pair(262, md_req_id)
    entries = [("0", lvl) for lvl in book["bids"]] + [("1", lvl) for lvl in book["asks"]]
    msg.append_pair(268, len(entries))
    for entry_type, lvl in entries:
        msg.append_pair(279, "0")  # MDUpdateAction: this template always sends a full replace, not true deltas
        msg.append_pair(269, entry_type)
        msg.append_pair(55, book["symbol"])
        msg.append_pair(270, lvl["price"])
        msg.append_pair(271, lvl["qty"])
    await session.send(msg)
