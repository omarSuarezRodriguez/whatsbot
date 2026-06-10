from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.integrations.google_sheets import GoogleSheetsClient


class UserService:
    def __init__(self, sheets: GoogleSheetsClient) -> None:
        self.sheets = sheets

    def touch(self, wa_id: str, name: str = "") -> None:
        self.sheets.upsert_user(wa_id=wa_id, name=name)

    def get_profile(self, wa_id: str) -> Dict[str, Any]:
        return self.sheets.get_user(wa_id)

    def save_name(self, wa_id: str, name: str) -> None:
        profile = self.get_profile(wa_id)
        self.sheets.upsert_user(
            wa_id=wa_id,
            name=name,
            address=profile.get("address", ""),
            last_order_items=profile.get("last_order_items"),
        )

    def save_address(self, wa_id: str, address: str) -> None:
        profile = self.get_profile(wa_id)
        self.sheets.upsert_user(
            wa_id=wa_id,
            name=profile.get("name", ""),
            address=address,
            last_order_items=profile.get("last_order_items"),
        )

    def get_last_order_items(self, wa_id: str) -> Optional[List[Dict[str, Any]]]:
        last = self.sheets.get_last_order(wa_id)
        if not last:
            return None
        return last.get("items")

    def display_name(self, wa_id: str, fallback: str = "") -> str:
        profile = self.get_profile(wa_id)
        return profile.get("name") or fallback
