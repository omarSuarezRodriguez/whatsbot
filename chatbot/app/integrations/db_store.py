"""
DB-backed data store for the chatbot engine (replaces Google Sheets).

Single source of truth = SaaS database (PostgreSQL/SQLite), scoped by the
active ``business_id`` resolved from :mod:`chatbot.business_context`.

The chatbot services (order/menu/user/reservation/blocked) call this object
through the same method surface the legacy Sheets client exposed, so their
code stays intact while all reads/writes go to the multi-tenant DB.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _active_business_id() -> str:
    from config.settings import DEFAULT_BUSINESS_ID

    try:
        from chatbot.business_context import get_active_business_id

        bid = get_active_business_id()
    except Exception:  # pragma: no cover - defensive
        bid = None
    return (bid or DEFAULT_BUSINESS_ID or "default").strip() or "default"


def _new_order_id() -> str:
    return f"ORD-{uuid.uuid4().hex[:8].upper()}"


class DBStore:
    """Multi-tenant DB store with a Sheets-compatible method surface."""

    # ----------------------------------------------------------------- MENU
    def get_menu(self) -> List[Dict[str, Any]]:
        from infrastructure.database import session_scope
        from services import menu_service as menu_svc

        bid = _active_business_id()
        with session_scope() as db:
            rows = menu_svc.list_menu_items(db, bid, available_only=False)
            return [
                {
                    "id": item.external_id or str(item.id),
                    "nombre": item.nombre,
                    "precio": float(item.precio),
                    "categoria": item.categoria,
                    "disponible": bool(item.disponible),
                }
                for item in rows
            ]

    # ---------------------------------------------------------------- USERS
    def get_user(self, wa_id: str) -> Dict[str, Any]:
        from infrastructure.database import session_scope
        from services import customer_service as cust_svc

        bid = _active_business_id()
        with session_scope() as db:
            customer = cust_svc.get_customer_by_wa_id(db, bid, wa_id)
            if not customer:
                return {"wa_id": wa_id, "name": "", "address": "", "blocked": False}
            return {
                "wa_id": customer.wa_id,
                "name": customer.name or "",
                "address": customer.address or "",
                "blocked": bool(customer.blocked),
                "last_order_items": customer.last_order_items,
            }

    def upsert_user(
        self,
        wa_id: str,
        name: str = "",
        address: str = "",
        last_order_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        from infrastructure.database import session_scope
        from services import customer_service as cust_svc

        bid = _active_business_id()
        with session_scope() as db:
            cust_svc.upsert_from_chat(
                db,
                bid,
                wa_id=wa_id,
                name=name,
                address=address,
                last_order_items=last_order_items,
            )

    def get_last_order(self, wa_id: str) -> Optional[Dict[str, Any]]:
        from infrastructure.database import session_scope
        from services import customer_service as cust_svc

        bid = _active_business_id()
        with session_scope() as db:
            customer = cust_svc.get_customer_by_wa_id(db, bid, wa_id)
            if customer and customer.last_order_items:
                return {"items": customer.last_order_items}
        return None

    def get_blocked_wa_ids(self) -> Set[str]:
        from infrastructure.database import session_scope
        from models.customer import Customer

        bid = _active_business_id()
        with session_scope() as db:
            rows = (
                db.query(Customer.wa_id)
                .filter(Customer.business_id == bid, Customer.blocked.is_(True))
                .all()
            )
            return {row[0] for row in rows if row[0]}

    def set_user_blocked(self, wa_id: str, blocked: bool) -> bool:
        from infrastructure.database import session_scope
        from services import customer_service as cust_svc

        bid = _active_business_id()
        try:
            with session_scope() as db:
                customer = cust_svc.get_customer_by_wa_id(db, bid, wa_id)
                if customer is None:
                    customer = cust_svc.create_customer(
                        db, bid, wa_id=wa_id, blocked=blocked
                    )
                else:
                    customer.blocked = blocked
            return True
        except Exception:
            logger.exception("set_user_blocked failed for %s", wa_id)
            return False

    def refresh_users_cache(self) -> None:
        # DB is always live; nothing to refresh.
        return None

    # --------------------------------------------------------------- ORDERS
    def create_order(
        self,
        wa_id: str,
        items: List[Dict[str, Any]],
        total: float,
        status: str = "pending",
        customer_name: str = "",
        address: str = "",
        delivery_type: str = "",
    ) -> str:
        from infrastructure.database import session_scope
        from services import customer_service as cust_svc
        from services import order_service as order_svc

        bid = _active_business_id()
        with session_scope() as db:
            order_id = _new_order_id()
            # Avoid the (rare) collision within the same business.
            for _ in range(5):
                if order_svc.get_order(db, bid, order_id) is None:
                    break
                order_id = _new_order_id()
            order_svc.create_order(
                db,
                bid,
                order_id=order_id,
                wa_id=wa_id,
                items=items if isinstance(items, list) else [],
                total=float(total or 0),
                status=status,
                customer_name=customer_name,
                address=address,
                delivery_type=delivery_type,
            )
            cust_svc.upsert_from_chat(
                db,
                bid,
                wa_id=wa_id,
                name=customer_name,
                address=address,
                last_order_items=items if isinstance(items, list) else [],
            )
            return order_id

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        from infrastructure.database import session_scope
        from services import order_service as order_svc

        bid = _active_business_id()
        with session_scope() as db:
            row = order_svc.get_order(db, bid, (order_id or "").upper().strip())
            if not row:
                return None
            return _order_to_dict(row)

    def update_order_status(self, order_id: str, status: str) -> bool:
        from infrastructure.database import session_scope
        from services import order_service as order_svc

        bid = _active_business_id()
        try:
            with session_scope() as db:
                row = order_svc.get_order(db, bid, (order_id or "").upper().strip())
                if not row:
                    return False
                order_svc.update_order_status(db, row, status)
            return True
        except Exception:
            logger.exception("update_order_status failed for %s", order_id)
            return False

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        from infrastructure.database import session_scope
        from services import order_service as order_svc

        bid = _active_business_id()
        with session_scope() as db:
            rows = order_svc.list_orders(db, bid, status="pending", limit=200)
            return [_order_to_dict(row) for row in rows]

    # ---------------------------------------------------------- RESERVATIONS
    def create_reservation(
        self,
        wa_id: str,
        personas: int,
        fecha: str,
        hora: str,
    ) -> str:
        from infrastructure.database import session_scope
        from services import reservation_service as res_svc

        bid = _active_business_id()
        with session_scope() as db:
            reservation = res_svc.create_reservation(
                db,
                bid,
                wa_id=wa_id,
                personas=personas,
                fecha=fecha,
                hora=hora,
            )
            return reservation.reservation_id

    # ------------------------------------------------------------------ OPS
    def cache_status(self) -> Dict[str, Any]:
        return {"store": "database", "sheets_connected": False}

    def warm_up_cache(self) -> None:
        return None


def _order_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "order_id": row.order_id,
        "wa_id": row.wa_id,
        "status": row.status,
        "items": row.items or [],
        "total": float(row.total or 0),
        "customer_name": row.customer_name or "",
        "address": row.address or "",
        "delivery_type": row.delivery_type or "",
    }


_store: Optional[DBStore] = None


def get_db_store() -> DBStore:
    """Process-wide singleton store (stateless; safe to share)."""
    global _store
    if _store is None:
        _store = DBStore()
    return _store
