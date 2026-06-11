from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


class ReservationService:
    def __init__(self, store: "DBStore") -> None:
        self.sheets = store  # attr name kept for internal compatibility

    def save_reservation(
        self,
        wa_id: str,
        personas: int,
        reservation_date: date,
        reservation_time: time,
    ) -> str:
        return self.sheets.create_reservation(
            wa_id=wa_id,
            personas=personas,
            fecha=reservation_date.strftime("%d/%m/%Y"),
            hora=reservation_time.strftime("%H:%M"),
        )

    @staticmethod
    def format_summary(personas: int, reservation_date: date, reservation_time: time) -> str:
        return (
            f"Personas: *{personas}*\n"
            f"Fecha: *{reservation_date.strftime('%d/%m/%Y')}*\n"
            f"Hora: *{reservation_time.strftime('%H:%M')}*"
        )
