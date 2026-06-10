from __future__ import annotations

from datetime import date, time
from typing import Tuple

from app.integrations.google_sheets import GoogleSheetsClient


class ReservationService:
    def __init__(self, sheets: GoogleSheetsClient) -> None:
        self.sheets = sheets

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
