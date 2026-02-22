from __future__ import annotations

import json
from typing import Any


def sync_exchange_state(storage: Any, client: Any, logger: Any) -> tuple[int, int]:
    synced_positions = 0
    synced_orders = 0

    try:
        open_orders = client.fetch_open_orders()
    except Exception as exc:
        logger.warning(f"State sync: failed to fetch open orders: {exc}")
        open_orders = []

    try:
        positions = client.fetch_positions()
    except NotImplementedError:
        logger.warning("State sync: fetch_positions is not supported, using empty list")
        positions = []
    except Exception as exc:
        logger.warning(f"State sync: failed to fetch positions: {exc}")
        positions = []

    order_ids: list[str] = []
    for order in open_orders or []:
        order_id = str(order.get("id") or "")
        if not order_id:
            continue

        symbol = str(order.get("symbol") or "")
        status = str(order.get("status") or "open")
        storage.insert_order(
            ts=str(order.get("timestamp") or order.get("datetime") or ""),
            symbol=symbol,
            kind=str(order.get("type") or "unknown"),
            order_id=order_id,
            status=status,
            meta_json=json.dumps(order),
        )
        order_ids.append(order_id)

    storage.delete_open_orders_not_in(order_ids)
    synced_orders = len(order_ids)

    symbols: list[str] = []
    for pos in positions or []:
        symbol = str(pos.get("symbol") or "")
        if not symbol:
            continue

        contracts = float(pos.get("contracts") or pos.get("positionAmt") or pos.get("size") or 0.0)
        if contracts == 0:
            continue

        side = str(pos.get("side") or ("long" if contracts > 0 else "short")).lower()
        amount = abs(contracts)
        entry_price = float(pos.get("entryPrice") or pos.get("entry_price") or pos.get("markPrice") or 0.0)
        unrealized = float(pos.get("unrealizedPnl") or pos.get("unrealized_pnl") or 0.0)

        storage.upsert_position(
            symbol=symbol,
            side=side,
            amount=amount,
            entry_price=entry_price,
            unrealized_pnl=unrealized,
            status="open",
            meta_json=json.dumps(pos),
        )
        symbols.append(symbol)

    storage.delete_positions_not_in(symbols)
    synced_positions = len(symbols)

    logger.info(f"State sync complete: {synced_positions} positions, {synced_orders} open orders")
    return synced_positions, synced_orders
