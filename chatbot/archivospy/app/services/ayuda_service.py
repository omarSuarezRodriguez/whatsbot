from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


class AyudaService:
    def __init__(self, store: "DBStore") -> None:
        self.sheets = store  # attr name kept for internal compatibility

    def save_ayuda(
        self,
        wa_id: str,
        personas: int,
        ayuda_date: date,
        ayuda_time: time,
    ) -> str:
        return self.sheets.create_reservation(
            wa_id=wa_id,
            personas=personas,
            fecha=ayuda_date.strftime("%d/%m/%Y"),
            hora=ayuda_time.strftime("%H:%M"),
        )

    @staticmethod
    def format_summary(personas: int, ayuda_date: date, ayuda_time: time) -> str:
        return (
            f"Personas: *{personas}*\n"
            f"Fecha: *{ayuda_date.strftime('%d/%m/%Y')}*\n"
            f"Hora: *{ayuda_time.strftime('%H:%M')}*"
        )
