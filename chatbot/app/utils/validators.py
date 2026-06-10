import re
import unicodedata
from datetime import date, datetime, time
from typing import Optional, Tuple

import app.config  # noqa: F401 — final_system en sys.path
from config.intents import GREETING_PHRASES


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    cleaned = _strip_accents(text.strip().lower())
    return " ".join(cleaned.split())


def is_global_command(text: str) -> bool:
    return normalize_text(text) in {
        "menu",
        "pedido",
        "reservar",
        "inicio",
        "cancelar",
    }


def is_greeting(text: str) -> bool:
    cleaned = normalize_text(text)
    if cleaned in GREETING_PHRASES:
        return True
    if any(cleaned.startswith(phrase) for phrase in GREETING_PHRASES if len(phrase) > 4):
        return True
    return any(phrase in cleaned for phrase in GREETING_PHRASES)


def parse_delivery_type(text: str) -> Optional[str]:
    cleaned = normalize_text(text)
    if cleaned in {"1", "domicilio", "delivery", "a domicilio", "envio", "envío"}:
        return "domicilio"
    if cleaned in {
        "2",
        "recoger",
        "recojo",
        "pickup",
        "tienda",
        "en tienda",
        "pasar por",
        "pasar a recoger",
    }:
        return "recoger"
    if "domicilio" in cleaned or "envio" in cleaned or "envío" in cleaned:
        return "domicilio"
    if "recog" in cleaned or "tienda" in cleaned:
        return "recoger"
    return None


def is_admin_confirm(text: str) -> bool:
    cleaned = normalize_text(text)
    if cleaned.startswith("confirmar"):
        return True
    if "listo" in cleaned and ("pedido" in cleaned or "ord-" in cleaned):
        return True
    return cleaned in {"confirmar", "confirmado", "confirmo", "ok confirmar"}


def extract_admin_order_id(text: str) -> Optional[str]:
    cleaned = normalize_text(text)
    match = re.search(r"(ord-[a-f0-9]{8})", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    parts = cleaned.split()
    for part in parts:
        if part.upper().startswith("ORD-"):
            return part.upper()
    return None


def parse_admin_block_command(text: str) -> Optional[Tuple[str, str]]:
    """Parse blockoff:+57... or blockon:+57... admin commands."""
    cleaned = (text or "").strip()
    match = re.match(r"^(blockoff|blockon):(.+)$", cleaned, re.IGNORECASE)
    if not match:
        return None
    cmd = match.group(1).lower()
    phone = match.group(2).strip()
    action = "unblock" if cmd == "blockoff" else "block"
    return action, phone


def parse_persons(text: str) -> Optional[int]:
    cleaned = normalize_text(text)
    match = re.search(r"(\d+)", cleaned)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 30:
            return value

    words = {
        "una": 1,
        "uno": 1,
        "un": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
    }
    for word, qty in words.items():
        if word in cleaned.split():
            return qty
    return None


def parse_date(text: str) -> Optional[date]:
    cleaned = normalize_text(text)
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
            if parsed >= date.today():
                return parsed
        except ValueError:
            continue

    match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", cleaned)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = match.group(3)
        if year:
            year_int = int(year)
            if year_int < 100:
                year_int += 2000
        else:
            year_int = date.today().year
        try:
            parsed = date(year_int, month, day)
            if parsed >= date.today():
                return parsed
        except ValueError:
            return None
    return None


def parse_time(text: str) -> Optional[time]:
    cleaned = normalize_text(text).replace("hrs", "").replace("hr", "").strip()
    formats = ["%H:%M", "%H.%M", "%I:%M %p", "%I:%M%p"]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue

    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def is_confirmation(text: str) -> bool:
    cleaned = normalize_text(text)
    if cleaned in {
        "si",
        "sí",
        "confirmo",
        "confirmar",
        "ok",
        "dale",
        "correcto",
        "yes",
        "va",
        "claro",
        "simon",
        "simón",
        "perfecto",
        "esta bien",
        "está bien",
        "de acuerdo",
        "listo",
        "hecho",
        "sale",
        "orale",
        "órale",
        "arre",
    }:
        return True
    if cleaned.startswith("si ") or cleaned.startswith("ok "):
        return True
    prefix = re.match(
        r"^(?:si|sí|ok|dale|perfecto|esta bien|está bien|claro|va|listo|hecho|sale|"
        r"de acuerdo|correcto|orale|órale|arre)\b",
        cleaned,
    )
    if prefix:
        tail = cleaned[prefix.end() :].strip()
        if not tail or len(tail.split()) <= 3:
            return True
    return False


def is_rejection(text: str) -> bool:
    cleaned = normalize_text(text)
    if cleaned in {
        "no",
        "nop",
        "cancelar",
        "cambiar",
        "modificar",
        "mejor no",
        "nel",
        "nope",
        "negativo",
    }:
        return True
    return cleaned.startswith("no ") or cleaned.startswith("mejor no")


def validate_reservation_slot(
    reservation_date: date,
    reservation_time: time,
) -> Tuple[bool, str]:
    if reservation_date == date.today():
        now = datetime.now().time()
        if reservation_time <= now:
            return False, "La hora debe ser posterior a la hora actual."
    return True, ""
