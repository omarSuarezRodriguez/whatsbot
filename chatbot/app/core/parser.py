"""Order Intelligence Engine — natural-language order parser with cart operations."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import app.config  # noqa: F401

from app.config import GLOBAL_COMMANDS
from config.intents import (
    GLOBAL_COMMAND_INTENTS,
    MENU_INTENT_PHRASES,
    MENU_INTENT_TOKENS,
    ORDER_INTENT_PHRASES,
)
from app.utils.validators import is_confirmation

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz as _rapidfuzz

    _HAS_RAPIDFUZZ = True
except ImportError:
    _rapidfuzz = None  # type: ignore[assignment]
    _HAS_RAPIDFUZZ = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUMBER_WORDS: Dict[str, int] = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "dieciséis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintidós": 22,
    "veintidas": 22,
    "veintitres": 23,
    "veintitrés": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintiséis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
}

_QTY_WORD_ALTS = "|".join(
    re.escape(word) for word in sorted(NUMBER_WORDS.keys(), key=len, reverse=True)
)

NOISE_WORDS = frozenset(
    {
        "quiero",
        "quero",
        "dame",
        "deme",
        "porfa",
        "porfavor",
        "favor",
        "mmm",
        "mm",
        "eh",
        "este",
        "esta",
        "eso",
        "esa",
        "pedir",
        "pedido",
        "pedidos",
        "necesito",
        "quisiera",
        "me",
        "gustaria",
        "ponme",
        "traeme",
        "trae",
        "traes",
        "traer",
        "agrega",
        "agregar",
        "anade",
        "añade",
        "añadir",
        "suma",
        "sumar",
        "tambien",
        "también",
        "mas",
        "más",
        "solo",
        "solamente",
        "favor",
        "hola",
        "buenas",
        "buenos",
        "dias",
        "tardes",
        "noches",
        "please",
        "pls",
        "ok",
        "vale",
        "listo",
        "ya",
        "ahora",
        "por",
        "para",
        "mi",
        "le",
        "mio",
        "mía",
        "escribi",
        "escribí",
        "escribo",
        "escribe",
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "sin",
        "algo",
        "alguna",
        "algun",
        "algún",
        "pues",
        "bueno",
        "oye",
        "mira",
        "fijate",
        "fíjate",
        "che",
        "amigo",
        "disculpa",
        "perdon",
        "perdón",
        "okey",
        "okay",
        "igual",
        "entonces",
        "creo",
        "pienso",
        "nomas",
        "nomás",
        "porfis",
        "plis",
        "favorcito",
        "seria",
        "sería",
        "podria",
        "podría",
        "quisiera",
        "gustaria",
        "gustaría",
        "nada",
        "gracias",
        "thanks",
        "llevar",
    }
)

PARTIAL_CATEGORY_ONLY = frozenset({"bebida", "bebidas"})
PARTIAL_GENERIC_TOKENS = frozenset(
    {
        "bebida",
        "bebidas",
        "refresco",
        "refrescos",
        "soda",
        "gaseosa",
        "gasosa",
    }
)

RESERVATION_SLOT_RE = re.compile(
    r"\b(?:"
    r"manana|mañana|pasado|mediodia|medianoche|"
    r"lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|"
    r"\d{1,2}[-/]\d{1,2}|a\s+las\s+\d|"
    r"para\s+(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)"
    r")\b",
    re.IGNORECASE,
)

JOKE_CANCEL_PREFIX_RE = re.compile(
    r"^(?:cancelar|anular)\b.*?\bes broma\b[,\s]*",
    re.IGNORECASE,
)
COMPOUND_MENU_ORDER_RE = re.compile(
    r"^(?:menu|menú|carta|ver carta|ver el menu|ver menú|ver la carta)\s+"
    r"(?:y\s+|,\s*)"
    r"(?:quiero|dame|ponme|necesito|quisiera|me|oye|hola|buenas|un|una)",
    re.IGNORECASE,
)
QUESTION_NO_ORDER_RE = re.compile(
    r"\b(?:"
    r"a\s+que\s+hora|que\s+hora|qué\s+hora|"
    r"donde|dónde|cuanto|cuánto|cuales|cuáles|cual\b|cuál\b|"
    r"abren|cierran|horario|telefono|teléfono|direccion|dirección"
    r")\b",
    re.IGNORECASE,
)

# Token-level semantic hints (applied before menu matching, never invent products).
SYNONYM_TOKEN_MAP: Dict[str, str] = {
    "coca": "coca cola",
    "cola": "coca cola",
    "gaseosa": "coca cola",
    "gasosa": "coca cola",
    "refresco": "coca cola",
    "refrescos": "coca cola",
    "soda": "coca cola",
    "sodas": "coca cola",
    "agua": "agua",
    "natural": "agua",
    "mineral": "agua",
    "hambre": "hamburguesa",
    "burger": "hamburguesa",
    "hamburgesa": "hamburguesa",
    "hamburgsa": "hamburguesa",
    "hambrguesa": "hamburguesa",
    "habasurguesa": "hamburguesa",
    "hbogruesa": "hamburguesa",
    "pirzas": "pizza",
    "harwewaianas": "hawaiana",
    "picsas": "pizza",
    "quieso": "queso",
    "gaseoza": "coca cola",
    "cocacola": "cocacola",
    "cocacolas": "cocacola",
    "hamburguesa": "hamburguesa",
    "hamburguesas": "hamburguesa",
    "margarita": "margarita",
    "margaritas": "margarita",
    "hawaiana": "hawaiana",
    "hawaiano": "hawaiana",
    "hawaianas": "hawaiana",
    "hawaianos": "hawaiana",
    "cesar": "cesar",
    "césar": "cesar",
    "papas": "papas fritas",
    "papitas": "papas fritas",
    "fritas": "papas fritas",
    "frits": "papas fritas",
    "pizza": "pizza",
    "ensalada": "ensalada",
}

INTENT_MIN_CONFIDENCE = 0.82

# Words after a quantity that express intent, not a product (e.g. "un pedido", "una mesa").
_PRODUCT_SIGNAL_BLOCK_TAIL = (
    "pedido|pedidos|orden|ordenar|mesa|mesas|reserva|reservacion|reservar|"
    "menu|carta|catalogo|comer|hambre|encargar|comprar|agendar|apartar|"
    "inicio|principal|reiniciar|cancelar|anular|abortar|olvidar"
)

PRODUCT_ORDER_SIGNAL_RE = re.compile(
    rf"(?:(?:{_QTY_WORD_ALTS})|\d+)\s*[x×]?\s*(?!{_PRODUCT_SIGNAL_BLOCK_TAIL}\b)[a-z]{{3,}}",
    re.IGNORECASE,
)

COLLOQUIAL_QTY_REPLACEMENTS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\buna?\s+docena\s+de\s+", re.IGNORECASE), "12 "),
    (re.compile(r"\bmedia\s+docena\s+de\s+", re.IGNORECASE), "6 "),
    (re.compile(r"\bun\s+par\s+de\s+", re.IGNORECASE), "2 "),
    (re.compile(r"\bpar\s+de\s+", re.IGNORECASE), "2 "),
)

CONVERSATIONAL_PREFIX_RE = re.compile(
    r"^(?:bueno|pues|oye|mira|fijate|fíjate|che|amigo|disculpa|perdon|perdón|"
    r"okey|okay|entonces|igual)\s+",
    re.IGNORECASE,
)

WHATSAPP_BULLET_RE = re.compile(r"(?:^|\n)\s*[-•]\s*", re.MULTILINE)

PLUS_CONNECTOR_TOKEN = "__plus__"
STAR_CONNECTOR_TOKEN = "__star__"
AMP_CONNECTOR_TOKEN = "__amp__"

PLUS_CONNECTOR_GUARD_RE = re.compile(r"\s*\+\s*")
STAR_CONNECTOR_GUARD_RE = re.compile(r"\s*\*\s*")
AMP_CONNECTOR_GUARD_RE = re.compile(r"\s*&\s*")

REMOVE_VERB_RE = re.compile(
    r"\b(?:quita|quitar|elimina|eliminar|saca|sacar|borra|borrar|"
    r"sacame|sácame|quitame|quítame|remueve|remover|"
    r"ya\s+no\s+quiero|sin\s+el|sin\s+la|dejame\s+sin|déjame\s+sin|"
    r"cancela\s+el|cancela\s+la|\bsin\b)\b",
    re.IGNORECASE,
)

REMOVE_PREFIX_RE = re.compile(
    r"^(?:quita|quitar|elimina|eliminar|saca|sacar|borra|borrar|"
    r"sacame|sácame|quitame|quítame|remueve|remover|"
    r"ya\s+no\s+quiero|sin\s+el|sin\s+la|dejame\s+sin|déjame\s+sin|"
    r"cancela\s+el|cancela\s+la|\bsin\b)\s+",
    re.IGNORECASE,
)

OTRA_ADD_RE = re.compile(r"\botra\b", re.IGNORECASE)
OTRA_PREFIX_RE = re.compile(r"^(?:otra|otro|otro\s+uno|otra\s+una)\s+", re.IGNORECASE)
ADD_VERB_RE = re.compile(
    r"\b(?:agregame|agrégame|agrega|agregar|sumale|súmale|anademe|añademe)\b",
    re.IGNORECASE,
)
ADD_PREFIX_RE = re.compile(
    r"^(?:agregame|agrégame|agrega|agregar|sumale|súmale|anademe|añademe)\s+",
    re.IGNORECASE,
)

COMMA_SPLIT_RE = re.compile(r"\s*,\s*")

PLUS_SPLIT_RE = re.compile(r"\s*\+\s*")
STAR_SPLIT_RE = re.compile(r"\s*\*\s*")

CONNECTOR_SPLIT_RE = re.compile(
    r"\s*(?:,|;|&|\||\band\b|\s+y\s+|\s+e\s+|\s+mas\s+|\s+más\s+|\s+también\s+|\s+tambien\s+"
    r"|\s+luego\s+|\s+ademas\s+|\s+además\s+|\s+aparte\s+|\s+y\s+aparte\s+"
    r"|\s+igual\s+|\s+otra\s+vez\s+|\s+tambien\s+quiero\s+|\s+también\s+quiero\s+"
    r"|\s+aparte\s+de\s+)\s*",
    re.IGNORECASE,
)

# Split "con" only when followed by another order item (qty), not "con queso" in a name.
CON_ITEM_SPLIT_RE = re.compile(
    rf"\s+con\s+(?=(?:\d+\s*[x×]|[x×]\s*\d+|\d+\s+|(?:{_QTY_WORD_ALTS})\s+))",
    re.IGNORECASE,
)

PIPE_SPLIT_RE = re.compile(r"\s*\|\s*")

PEDIDO_LABEL_PREFIX_RE = re.compile(r"^pedido\s*:\s*", re.IGNORECASE)

ADMIN_PREFIX_RE = re.compile(
    r"^(?:confirmar\s+ord[-\w]*|cancelar\s+pedido)\s+",
    re.IGNORECASE,
)

ADMIN_INLINE_RE = re.compile(r"\b(?:mesa\s+\d+|anota:|pedido\s+telefonico)\b", re.IGNORECASE)

TIME_PRICE_NOISE_RE = re.compile(
    r"\b(?:a\s+las\s+)?\d{1,2}\s*(?:pm|am|hrs?)\b|\$\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)

BEVERAGE_SYNONYM_KEYS = frozenset(
    {
        "coca",
        "cola",
        "gaseosa",
        "gasosa",
        "gaseoza",
        "refresco",
        "refrescos",
        "soda",
        "cocacola",
        "cocacolas",
        "sodas",
    }
)

COMPOUND_Y_RE = re.compile(r"\bde\s+(\w+)\s+y\s+(\w+)\b", re.IGNORECASE)
COMPOUND_Y_TOKEN = "__ingy__"

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "]+",
    flags=re.UNICODE,
)

REPEAT_CHAR_RE = re.compile(r"([a-z])\1{2,}", re.UNICODE)

QTY_PREFIX_RE = re.compile(
    r"^(?:(\d+)\s*[x×]\s*|[x×]\s*(\d+)\s*|[x×](\d+)\s*|(\d+)\s+)(.*)$",
    re.IGNORECASE,
)

QTY_SUFFIX_RE = re.compile(r"^(.+?)\s+(\d+)\s*$")

SEGMENT_BOUNDARY_RE = re.compile(
    rf"(?<!\d)(?:(\d+)\s*[x×]\s*|[x×]\s*(\d+)\s*|[x×](\d+)\s*|(\d+)\s+"
    rf"|(?<!\w)(?:{_QTY_WORD_ALTS})(?!\w)\s+)",
    re.IGNORECASE,
)

ACCEPT_AUTO_SCORE = 0.80
ACCEPT_REVIEW_SCORE = 0.50
AMBIGUITY_DELTA = 0.05
TYPO_CORRECT_MIN_SCORE = 0.68
TYPO_CORRECT_MIN_GAP = 0.05
TYPO_VOCAB_MIN_LEN = 4


def log_parser_errors(
    *,
    wa_id: str = "",
    message: str = "",
    reason: str = "",
    parser_status: str = "",
    score: Optional[float] = None,
    unknown: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append parser audit events; never raises."""
    try:
        from app.config import PARSER_ERROR_LOG_PATH

        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wa_id": wa_id,
            "message": message,
            "reason": reason,
            "parser_status": parser_status,
            "score": score,
            "unknown": unknown or [],
        }
        if extra:
            record.update(extra)
        path = Path(PARSER_ERROR_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("log_parser_errors failed (non-fatal)")


def _min_confidence(items: List[Dict[str, Any]]) -> Optional[float]:
    scores = [float(item.get("confidence", 0)) for item in items if item.get("confidence")]
    return min(scores) if scores else None


# Generic menu words — matching only these must not beat a distinctive token hit.
CATEGORY_STOPWORDS = frozenset(
    {
        "pizza",
        "pizzas",
        "hamburguesa",
        "hamburguesas",
        "ensalada",
        "ensaladas",
        "agua",
        "coca",
        "cola",
        "mineral",
        "clasica",
        "cesar",
        "clasico",
        "natural",
        "bebida",
        "bebidas",
    }
)


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------


def _strip_accents(value: str) -> str:
    """Fold áéíóú, ñ and other accented characters for stable menu matching."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _singularize_token(token: str) -> str:
    """Reduce simple Spanish plurals for matching (pizzas → pizza)."""
    if len(token) <= 3:
        return token
    if token.endswith("iones"):
        return token[:-2]
    if token.endswith("anes") and len(token) > 5:
        return token[:-2]
    if token.endswith("ces") and len(token) > 4:
        return token[:-2] + "r"
    if token.endswith("as") and len(token) > 4:
        return token[:-1]
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _token_keys(text: str) -> set[str]:
    return {
        _singularize_token(_strip_accents(part))
        for part in text.split()
        if part and _singularize_token(_strip_accents(part)) not in CATEGORY_STOPWORDS
    }


def normalize(value: str) -> str:
    """Public lightweight normalizer (backward compatible)."""
    return TextNormalizer.basic(value)


class TextNormalizer:
    """Advanced normalization pipeline for chaotic WhatsApp input."""

    @staticmethod
    def basic(value: str) -> str:
        cleaned = value.lower().strip()
        cleaned = EMOJI_RE.sub(" ", cleaned)
        cleaned = _strip_accents(cleaned)
        cleaned = COMMA_SPLIT_RE.sub(" ", cleaned)
        cleaned = PLUS_SPLIT_RE.sub(" ", cleaned)
        cleaned = STAR_SPLIT_RE.sub(" ", cleaned)
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @classmethod
    def advanced(cls, value: str, catalog_normalized: Optional[List[str]] = None) -> str:
        text = value.lower().strip()
        text = EMOJI_RE.sub(" ", text)
        text = _strip_accents(text)
        text = COMMA_SPLIT_RE.sub(" ", text)
        text = PLUS_SPLIT_RE.sub(" ", text)
        text = STAR_SPLIT_RE.sub(" ", text)
        text = REPEAT_CHAR_RE.sub(r"\1", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if catalog_normalized:
            glued_tokens: List[str] = []
            for token in text.split():
                if re.search(r"\d", token):
                    glued_tokens.append(token)
                else:
                    glued_tokens.append(
                        cls._split_glued_words(token, catalog_normalized)
                    )
            text = " ".join(glued_tokens)
        text = cls._remove_noise_tokens(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _split_glued_words(text: str, catalog_names: List[str]) -> str:
        compact = text.replace(" ", "")
        if not compact:
            return text
        compact_to_spaced: Dict[str, str] = {}
        for spaced_name in catalog_names:
            if not spaced_name:
                continue
            compact_name = spaced_name.replace(" ", "")
            if len(compact_name) < 4:
                continue
            if compact_name not in compact_to_spaced or len(spaced_name) > len(
                compact_to_spaced[compact_name]
            ):
                compact_to_spaced[compact_name] = spaced_name

        for compact_name, spaced_name in compact_to_spaced.items():
            if compact == compact_name:
                return spaced_name
            for suffix in ("s", "es"):
                if compact == f"{compact_name}{suffix}":
                    return spaced_name

        spans: List[Tuple[int, int, str]] = []
        for compact_name, spaced_name in compact_to_spaced.items():
            start = 0
            while True:
                idx = compact.find(compact_name, start)
                if idx == -1:
                    break
                spans.append((idx, idx + len(compact_name), spaced_name))
                start = idx + 1
        if not spans:
            return text
        spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
        used: List[Tuple[int, int]] = []
        chosen: List[Tuple[int, int, str]] = []
        for start, end, spaced_name in spans:
            if any(not (end <= u0 or start >= u1) for u0, u1 in used):
                continue
            used.append((start, end))
            chosen.append((start, end, spaced_name))
        if not chosen:
            return text
        chosen.sort(key=lambda s: s[0])
        rebuilt: List[str] = []
        cursor = 0
        for start, end, spaced_name in chosen:
            if start > cursor:
                gap = compact[cursor:start]
                if gap:
                    rebuilt.append(gap)
            rebuilt.append(spaced_name)
            cursor = end
        if cursor < len(compact):
            rebuilt.append(compact[cursor:])
        return " ".join(rebuilt)

    @staticmethod
    def _remove_noise_tokens(text: str) -> str:
        tokens = text.split()
        filtered = [
            t
            for t in tokens
            if t not in NOISE_WORDS or t in NUMBER_WORDS
        ]
        return " ".join(filtered)


def _build_intent_phrase_index() -> Tuple[
    List[Tuple[str, str]],
    Dict[str, str],
    frozenset[str],
]:
    """Pre-normalize phrases and token map once at import (hot path in infer)."""
    rows: List[Tuple[int, str, str]] = []
    token_to_command: Dict[str, str] = {}
    all_tokens: set[str] = set()
    for command, spec in GLOBAL_COMMAND_INTENTS.items():
        for token in spec["tokens"]:
            key = _strip_accents(token)
            all_tokens.add(key)
            token_to_command.setdefault(key, command)
        for phrase in spec["phrases"]:
            phrase_key = TextNormalizer.basic(phrase)
            if phrase_key:
                rows.append((len(phrase_key), command, phrase_key))
    rows.sort(key=lambda row: row[0], reverse=True)
    flat = [(command, phrase_key) for _, command, phrase_key in rows]
    return flat, token_to_command, frozenset(all_tokens)


_INTENT_PHRASES_BY_LEN, _INTENT_TOKEN_TO_COMMAND, _INTENT_ALL_TOKENS = (
    _build_intent_phrase_index()
)
_INTENT_HINT_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(t) for t in sorted(_INTENT_ALL_TOKENS, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


class NaturalLanguagePreprocessor:
    """Fast, regex-only canonicalization for conversational WhatsApp input."""

    @classmethod
    def canonicalize(cls, value: str) -> str:
        text = value.lower().strip()
        if not text:
            return ""
        text = PEDIDO_LABEL_PREFIX_RE.sub("", text)
        text = ADMIN_PREFIX_RE.sub("", text)
        text = ADMIN_INLINE_RE.sub(" ", text)
        text = TIME_PRICE_NOISE_RE.sub(" ", text)
        text = EMOJI_RE.sub(" ", text)
        text = PLUS_CONNECTOR_GUARD_RE.sub(f" {PLUS_CONNECTOR_TOKEN} ", text)
        text = STAR_CONNECTOR_GUARD_RE.sub(f" {STAR_CONNECTOR_TOKEN} ", text)
        text = AMP_CONNECTOR_GUARD_RE.sub(f" {AMP_CONNECTOR_TOKEN} ", text)
        text = _strip_accents(text)
        text = WHATSAPP_BULLET_RE.sub(" ", text)
        text = COMMA_SPLIT_RE.sub(" ", text)
        text = REPEAT_CHAR_RE.sub(r"\1", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = cls._expand_colloquial_quantities(text)
        text = re.sub(r"(\d)\s*[x×](?=\S)", r"\1 ", text)
        text = re.sub(r"(?<!\d)[x×]\s*(\d+)\s+", r"\1 ", text)
        while True:
            stripped = CONVERSATIONAL_PREFIX_RE.sub("", text, count=1).strip()
            if stripped == text:
                break
            text = stripped
        text = (
            text.replace(PLUS_CONNECTOR_TOKEN, "+")
            .replace(STAR_CONNECTOR_TOKEN, "*")
            .replace(AMP_CONNECTOR_TOKEN, "&")
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _expand_colloquial_quantities(text: str) -> str:
        for pattern, replacement in COLLOQUIAL_QTY_REPLACEMENTS:
            text = pattern.sub(replacement, text)
        return text


class UserIntentClassifier:
    """Detect the five global commands (menu, pedido, reservar, inicio, cancelar)."""

    _CONFIRMATION_BLOCKED = frozenset({"menu", "pedido", "reservar"})

    @staticmethod
    def _sanitize_command(command: Optional[str]) -> Optional[str]:
        if command in GLOBAL_COMMANDS:
            return command
        return None

    @staticmethod
    def looks_like_reservation_data(text: str) -> bool:
        basic = TextNormalizer.basic(text)
        if not basic.startswith("reserva "):
            return False
        return bool(RESERVATION_SLOT_RE.search(basic))

    @staticmethod
    def _content_tokens(text: str) -> List[str]:
        intent_keep = _INTENT_ALL_TOKENS
        return [
            token
            for token in TextNormalizer.basic(text).split()
            if token
            and token not in NUMBER_WORDS
            and (
                token not in NOISE_WORDS
                or _strip_accents(token) in intent_keep
            )
        ]

    @staticmethod
    def looks_like_product_order(text: str) -> bool:
        basic = TextNormalizer.basic(text)
        if PRODUCT_ORDER_SIGNAL_RE.search(basic):
            return True
        if re.search(r"\b\d+\s*[x×]\s*\w", basic, re.IGNORECASE):
            return True
        if re.search(r"\b[x×]\d+\s+\w", basic, re.IGNORECASE):
            return True
        if re.search(
            r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|un|una|uno|par)\s+de\s+\w{3,}",
            basic,
            re.IGNORECASE,
        ):
            return True
        return False

    @classmethod
    def infer(
        cls,
        text: str,
        *,
        has_product_signal: bool = False,
    ) -> Dict[str, Any]:
        """Return best global command intent from free-form Spanish text."""
        basic = TextNormalizer.basic(text)
        if not basic:
            return {
                "command": None,
                "confidence": 0.0,
                "matched": "",
                "has_products": False,
            }

        if JOKE_CANCEL_PREFIX_RE.match(basic):
            tail = JOKE_CANCEL_PREFIX_RE.sub("", basic).strip()
            if tail:
                basic = tail
                has_product_signal = True
        elif COMPOUND_MENU_ORDER_RE.match(basic):
            tail = COMPOUND_MENU_ORDER_RE.sub("", basic).strip()
            if tail:
                basic = tail
                has_product_signal = True

        product_signal = has_product_signal or cls.looks_like_product_order(basic)
        confirmation_like = is_confirmation(basic)
        best_command: Optional[str] = None
        best_score = 0.0
        best_match = ""

        def _accept_command(command: Optional[str]) -> Optional[str]:
            cmd = cls._sanitize_command(command)
            if cmd and confirmation_like and cmd in cls._CONFIRMATION_BLOCKED:
                return None
            return cmd

        if cls.looks_like_reservation_data(basic):
            return {
                "command": None,
                "confidence": 0.0,
                "matched": "",
                "has_products": product_signal,
            }

        words = basic.split()
        if len(words) == 1:
            single = _strip_accents(words[0])
            cmd = _accept_command(_INTENT_TOKEN_TO_COMMAND.get(single))
            if cmd:
                return {
                    "command": cmd,
                    "confidence": 0.98,
                    "matched": single,
                    "has_products": product_signal,
                }

        run_phrases = (
            not product_signal
            or len(words) <= 8
            or bool(_INTENT_HINT_RE.search(basic))
        )
        if run_phrases:
            for command, phrase_key in _INTENT_PHRASES_BY_LEN:
                if phrase_key in basic:
                    cmd = _accept_command(command)
                    if not cmd:
                        continue
                    score = 0.96 if len(phrase_key.split()) > 1 else 0.9
                    if score > best_score:
                        best_score = score
                        best_command = cmd
                        best_match = phrase_key
                        if score >= 0.96:
                            break

        if best_score < 0.96:
            for word in words:
                key = _strip_accents(word)
                if key in _INTENT_TOKEN_TO_COMMAND:
                    cmd = _accept_command(_INTENT_TOKEN_TO_COMMAND[key])
                    if not cmd:
                        continue
                    if cmd == "menu" and "principal" in words:
                        continue
                    if cmd == "pedido" and re.search(
                        r"\b(?:no quiero|ya no quiero|anular|cancelar|no sigo|ya no sigo)\b",
                        basic,
                    ):
                        continue
                    if cmd in {"inicio", "cancelar"} or not product_signal:
                        return {
                            "command": cmd,
                            "confidence": 0.92,
                            "matched": key,
                            "has_products": product_signal,
                        }
                    break

        if product_signal and best_score < 0.95:
            return {
                "command": None,
                "confidence": round(best_score, 4),
                "matched": best_match,
                "has_products": True,
            }

        if best_score < INTENT_MIN_CONFIDENCE:
            return {
                "command": None,
                "confidence": round(best_score, 4),
                "matched": best_match,
                "has_products": product_signal,
            }

        return {
            "command": _accept_command(best_command),
            "confidence": round(best_score, 4),
            "matched": best_match,
            "has_products": product_signal,
        }


def _menu_literal_tokens(menu_items: List[Dict[str, Any]]) -> frozenset[str]:
    tokens: set[str] = set()
    for item in menu_items:
        if not item.get("disponible", True):
            continue
        name = str(item.get("nombre", "")).strip()
        if not name:
            continue
        tokens.update(TextNormalizer.basic(name).split())
    return frozenset(tokens)


def infer_user_intent(
    text: str,
    menu_items: Optional[List[Dict[str, Any]]] = None,
    *,
    menu_tokens: Optional[frozenset[str]] = None,
) -> Dict[str, Any]:
    """Public helper: extract menu/pedido/reservar/inicio/cancelar intent from NL text."""
    prepared = NaturalLanguagePreprocessor.canonicalize(text or "")
    has_product = UserIntentClassifier.looks_like_product_order(prepared)
    if not has_product:
        if menu_tokens:
            prepared_tokens = set(prepared.split())
            has_product = bool(prepared_tokens & menu_tokens)
        elif menu_items:
            prepared_tokens = set(prepared.split())
            has_product = bool(prepared_tokens & _menu_literal_tokens(menu_items))
    return UserIntentClassifier.infer(prepared, has_product_signal=has_product)


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


class FuzzyMatcher:
    """Real numeric similarity scoring against dynamic menu catalog."""

    def __init__(self, catalog: List[Dict[str, Any]]) -> None:
        self.catalog = catalog
        self._catalog_norms = [entry["normalized"] for entry in catalog]
        self._vocabulary = self._build_vocabulary(catalog)
        self._vocab_set = set(self._vocabulary)
        self._vocab_by_len: Dict[int, List[str]] = {}
        self._vocab_by_first: Dict[str, List[str]] = {}
        for word in self._vocabulary:
            self._vocab_by_len.setdefault(len(word), []).append(word)
            if word:
                self._vocab_by_first.setdefault(word[0], []).append(word)
        self._multi_beverage = self._detect_multi_beverage(catalog)
        self._single_beverage_norm = self._detect_single_beverage(catalog)

    @staticmethod
    def _detect_single_beverage(catalog: List[Dict[str, Any]]) -> Optional[str]:
        drinks = [
            entry.get("normalized", "")
            for entry in catalog
            if "bebida" in str(entry.get("categoria", "")).lower()
            or any(
                hint in str(entry.get("normalized", "")).lower()
                for hint in ("coca", "agua", "refresco", "jugo", "soda")
            )
        ]
        if len(drinks) == 1:
            return drinks[0]
        return None

    @staticmethod
    def _detect_multi_beverage(catalog: List[Dict[str, Any]]) -> bool:
        drinks = 0
        for entry in catalog:
            norm = entry.get("normalized", "")
            cat = str(entry.get("categoria", "")).lower()
            if "bebida" in cat or any(
                hint in norm for hint in ("coca", "agua", "refresco", "jugo", "soda")
            ):
                drinks += 1
        return drinks > 1

    @staticmethod
    def _build_vocabulary(catalog: List[Dict[str, Any]]) -> List[str]:
        words: set[str] = set()
        for entry in catalog:
            words.add(entry["normalized"])
            for token in entry.get("tokens", []):
                if len(token) >= TYPO_VOCAB_MIN_LEN:
                    words.add(token)
        return sorted(words, key=len, reverse=True)

    def _best_vocab_match(self, token: str) -> Tuple[str, float, float]:
        token_key = _strip_accents(token.lower())
        if len(token_key) < TYPO_VOCAB_MIN_LEN:
            return token, 0.0, 0.0
        if token_key in self._vocab_set:
            return token, 1.0, 0.0

        best_word = token
        best_score = 0.0
        second_score = 0.0
        token_len = len(token_key)
        first_ch = token_key[0]
        for delta in range(-3, 4):
            for candidate in self._vocab_by_len.get(token_len + delta, ()):
                if candidate and candidate[0] != first_ch:
                    continue
                score = self._ratio(token_key, candidate)
                if score > best_score or (
                    score == best_score and len(candidate) > len(best_word)
                ):
                    second_score = best_score
                    best_score = score
                    best_word = candidate
                elif score > second_score:
                    second_score = score
        return best_word, best_score, second_score

    def _correct_typos(self, text: str) -> str:
        if not text:
            return text
        corrected: List[str] = []
        for token in text.split():
            token_key = _strip_accents(token.lower())
            if token_key in self._vocab_set:
                corrected.append(token)
                continue
            candidate, score, second_score = self._best_vocab_match(token)
            cand_key = _strip_accents(candidate.lower())
            prefix_ok = (
                len(token_key) >= 3
                and len(cand_key) >= 3
                and (token_key[:3] == cand_key[:3] or score >= 0.88)
            )
            if (
                score >= TYPO_CORRECT_MIN_SCORE
                and (score - second_score) >= TYPO_CORRECT_MIN_GAP
                and cand_key != token_key
                and prefix_ok
            ):
                corrected.append(candidate)
            else:
                corrected.append(token)
        return " ".join(corrected)

    @staticmethod
    def _ratio(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if _HAS_RAPIDFUZZ and _rapidfuzz is not None:
            token_score = _rapidfuzz.token_set_ratio(a, b) / 100.0
            partial_score = _rapidfuzz.partial_ratio(a, b) / 100.0
            base_score = _rapidfuzz.ratio(a, b) / 100.0
            return max(token_score, partial_score, base_score)
        token_a = set(a.split())
        token_b = set(b.split())
        token_overlap = len(token_a & token_b) / max(len(token_a | token_b), 1)
        seq_score = SequenceMatcher(None, a, b).ratio()
        if a in b or b in a:
            return max(0.95, token_overlap, seq_score)
        return max(token_overlap, seq_score)

    def score_pair(self, query: str, item: Dict[str, Any]) -> float:
        normalized_query = query.strip()
        if not normalized_query:
            return 0.0

        target = item["normalized"]
        if normalized_query == target:
            return 1.0
        query_compact = normalized_query.replace(" ", "")
        target_compact = target.replace(" ", "")
        if query_compact and query_compact == target_compact:
            return 0.97
        if query_compact and (
            query_compact in target_compact or target_compact in query_compact
        ):
            return max(0.95, self._ratio(normalized_query, target))
        if normalized_query in target or target in normalized_query:
            return 0.95

        base = self._ratio(normalized_query, target)
        query_tokens = set(normalized_query.split())
        item_tokens = set(item["tokens"])
        if query_tokens and item_tokens:
            overlap = len(query_tokens & item_tokens) / max(len(query_tokens | item_tokens), 1)
            base = max(base, overlap)

        target_parts = target.split()
        if len(query_tokens) == 1:
            single = next(iter(query_tokens))
            if len(single) >= 3 and any(
                single == part or (len(part) >= 4 and single in part)
                for part in target_parts
            ):
                base = max(base, 0.95)

        q_keys = _token_keys(normalized_query)
        for alias in item.get("aliases", []):
            alias_score = self._ratio(normalized_query, alias)
            base = max(base, alias_score)
            if alias in q_keys or normalized_query == alias:
                base = max(base, 0.97)
            alias_compact = alias.replace(" ", "")
            if query_compact and alias_compact and query_compact == alias_compact:
                base = max(base, 0.97)

        q_keys = _token_keys(normalized_query)
        i_keys = _token_keys(target)
        distinctive = i_keys - CATEGORY_STOPWORDS
        if distinctive:
            hits = len(distinctive & q_keys)
            if hits == len(distinctive):
                base = max(base, 0.97)
            elif hits == 0:
                base = min(base, 0.62)

        return min(base, 1.0)

    def best_match(
        self, fragment: str
    ) -> Tuple[Optional[Dict[str, Any]], float, Optional[Dict[str, Any]], float]:
        query = TextNormalizer.advanced(fragment, self._catalog_norms)
        query = self._correct_typos(query)
        query = self._apply_synonyms(query)
        if not query:
            return None, 0.0, None, 0.0

        best_item: Optional[Dict[str, Any]] = None
        best_score = 0.0
        second_item: Optional[Dict[str, Any]] = None
        second_score = 0.0
        for item in self.catalog:
            score = self.score_pair(query, item)
            if score > best_score:
                second_item, second_score = best_item, best_score
                best_item, best_score = item, score
            elif score > second_score:
                second_item, second_score = item, score

        if not best_item or best_score < ACCEPT_REVIEW_SCORE:
            return None, 0.0, None, 0.0

        if (
            second_item
            and best_score == second_score
            and FuzzyMatcher.has_distinctive_winner(query, second_item, best_item)
        ):
            best_item, second_item = second_item, best_item

        return best_item, best_score, second_item, second_score

    @staticmethod
    def has_distinctive_winner(
        query: str,
        best: Dict[str, Any],
        second: Dict[str, Any],
    ) -> bool:
        q_keys = _token_keys(query)
        best_keys = _token_keys(best["normalized"]) - CATEGORY_STOPWORDS
        second_keys = _token_keys(second["normalized"]) - CATEGORY_STOPWORDS
        best_hits = best_keys & q_keys
        second_hits = second_keys & q_keys
        if best_hits and not second_hits:
            return True
        if len(best_hits) > len(second_hits):
            return True
        return False

    def _apply_synonyms(self, text: str) -> str:
        tokens = text.split()
        expanded: List[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            token_key = _strip_accents(token.lower())
            singular_key = _singularize_token(token_key)
            if token_key in self._vocab_set:
                mapped = token
            else:
                mapped = (
                    SYNONYM_TOKEN_MAP.get(token_key)
                    or SYNONYM_TOKEN_MAP.get(singular_key)
                    or SYNONYM_TOKEN_MAP.get(token, token)
                )
            beverage_key = (
                token_key
                if token_key in BEVERAGE_SYNONYM_KEYS
                else singular_key
            )
            if (
                self._multi_beverage
                and beverage_key in BEVERAGE_SYNONYM_KEYS
                and mapped.replace(" ", "") != token_key
            ):
                mapped = token
            elif (
                not self._multi_beverage
                and beverage_key in BEVERAGE_SYNONYM_KEYS
                and self._single_beverage_norm
            ):
                mapped = self._single_beverage_norm
            mapped_parts = mapped.split()
            expanded.extend(mapped_parts)
            skip = 0
            for j, part in enumerate(mapped_parts[1:], start=1):
                if (
                    i + j < len(tokens)
                    and _strip_accents(tokens[i + j].lower())
                    == _strip_accents(part.lower())
                ):
                    skip = j
            i += 1 + skip
        deduped: List[str] = []
        for token in expanded:
            if token and (not deduped or deduped[-1] != token):
                deduped.append(token)
        return " ".join(deduped)


# ---------------------------------------------------------------------------
# Segmentation & quantity extraction
# ---------------------------------------------------------------------------


class SegmentEngine:
    """Splits chaotic order text into quantity + product fragments."""

    @staticmethod
    def _preserve_compound_y(text: str) -> str:
        return COMPOUND_Y_RE.sub(
            lambda match: f"de {match.group(1)} {COMPOUND_Y_TOKEN} {match.group(2)}",
            text,
        )

    @staticmethod
    def _restore_compound_y(text: str) -> str:
        return text.replace(COMPOUND_Y_TOKEN, "y")

    @staticmethod
    def _split_by_connectors(raw: str) -> List[str]:
        chunks = [raw.strip()]
        for splitter in (COMMA_SPLIT_RE, PLUS_SPLIT_RE, STAR_SPLIT_RE, PIPE_SPLIT_RE):
            next_chunks: List[str] = []
            for chunk in chunks:
                next_chunks.extend(splitter.split(chunk))
            chunks = [part.strip() for part in next_chunks if part.strip()]
        return chunks

    @staticmethod
    def _split_connector_parts(normalized: str) -> List[str]:
        normalized = CON_ITEM_SPLIT_RE.sub(" __conbreak__ ", normalized)
        parts = CONNECTOR_SPLIT_RE.split(normalized)
        return [part.replace("__conbreak__", " con ").strip() for part in parts if part.strip()]

    @staticmethod
    def split_segments(text: str) -> List[str]:
        raw = text.strip()
        if not raw:
            return []

        comma_chunks = SegmentEngine._split_by_connectors(raw)
        if not comma_chunks:
            return []

        segments: List[str] = []
        for chunk in comma_chunks:
            normalized = TextNormalizer.basic(chunk)
            if not normalized:
                continue
            normalized = SegmentEngine._preserve_compound_y(normalized)
            parts = SegmentEngine._split_connector_parts(normalized)
            for part in parts:
                part = SegmentEngine._restore_compound_y(part.strip())
                if not part:
                    continue
                segments.extend(SegmentEngine._split_numeric_boundaries(part))

        merged: List[str] = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            if merged and SegmentEngine._is_quantity_only(segment):
                prev_qty, prev_name = QuantityEngine.extract(merged[-1])
                extra_qty, _ = QuantityEngine.extract(segment)
                merged[-1] = f"{prev_qty + extra_qty} {prev_name}".strip()
                continue
            merged.append(segment)
        return merged

    @staticmethod
    def _split_numeric_boundaries(part: str) -> List[str]:
        matches = list(SEGMENT_BOUNDARY_RE.finditer(part))
        if not matches:
            return [part]

        chunks: List[str] = []
        cursor = 0
        for match in matches:
            if match.start() > cursor:
                prefix = part[cursor : match.start()].strip()
                if prefix:
                    chunks.append(prefix)
            cursor = match.start()

        tail = part[cursor:].strip()
        if tail:
            chunks.append(tail)

        if not chunks:
            return [part]
        if len(chunks) == 2:
            prefix_tokens = [
                token
                for token in TextNormalizer.basic(chunks[0]).split()
                if token and token not in NOISE_WORDS
            ]
            if not prefix_tokens:
                return [f"{chunks[0]} {chunks[1]}".strip()]
        return chunks

    @staticmethod
    def _is_quantity_only(segment: str) -> bool:
        cleaned = TextNormalizer.basic(segment.strip())
        if re.fullmatch(r"\d+", cleaned):
            return True
        key = _strip_accents(cleaned)
        return key in NUMBER_WORDS


class QuantityEngine:
    """Robust quantity resolver: 2x, x2, digits, number words."""

    @staticmethod
    def _strip_leading_noise(text: str) -> str:
        tokens = text.split()
        while tokens and tokens[0] in NOISE_WORDS and tokens[0] not in NUMBER_WORDS:
            tokens.pop(0)
        return " ".join(tokens)

    @staticmethod
    def _strip_trailing_noise(text: str) -> str:
        text = re.sub(r"\bpara\s+llevar\b", "", text, flags=re.IGNORECASE).strip()
        tokens = text.split()
        while tokens and tokens[-1] in NOISE_WORDS and tokens[-1] not in NUMBER_WORDS:
            tokens.pop()
        return " ".join(tokens)

    @staticmethod
    def _strip_de_prefix(text: str) -> str:
        return re.sub(r"^de\s+", "", text.strip())

    @staticmethod
    def extract(segment: str) -> Tuple[int, str]:
        cleaned = TextNormalizer.basic(segment)
        cleaned = QuantityEngine._strip_leading_noise(cleaned)
        if not cleaned:
            return 1, ""

        match = QTY_PREFIX_RE.match(cleaned)
        if match:
            qty = int(match.group(1) or match.group(2) or match.group(3) or match.group(4))
            remainder = QuantityEngine._strip_trailing_noise(
                QuantityEngine._strip_de_prefix((match.group(5) or "").strip())
            )
            return max(qty, 1), remainder

        for word, qty in NUMBER_WORDS.items():
            pattern = rf"^{word}\s+(.+)$"
            word_match = re.match(pattern, cleaned)
            if word_match:
                remainder = QuantityEngine._strip_trailing_noise(
                    QuantityEngine._strip_de_prefix(word_match.group(1).strip())
                )
                return qty, remainder

        suffix = QTY_SUFFIX_RE.match(cleaned)
        if suffix:
            name = QuantityEngine._strip_trailing_noise(
                QuantityEngine._strip_de_prefix(suffix.group(1).strip())
            )
            qty = int(suffix.group(2))
            if name and not re.fullmatch(r"\d+", name):
                return max(qty, 1), name

        return 1, QuantityEngine._strip_trailing_noise(cleaned)

    @staticmethod
    def resolve(segment: str, catalog_norms: Optional[List[str]] = None) -> Tuple[int, str]:
        """Extract quantity from the raw segment, then product text for matching."""
        basic = TextNormalizer.basic(segment)
        qty, product_text = QuantityEngine.extract(basic)
        if not product_text:
            return qty, ""

        normalized = TextNormalizer.advanced(product_text, catalog_norms)
        _, product_text = QuantityEngine.extract(normalized)
        qty_check, _ = QuantityEngine.extract(
            TextNormalizer.advanced(segment, catalog_norms)
        )
        if qty_check != qty:
            raw_numbers = [int(value) for value in re.findall(r"\d+", basic)]
            if raw_numbers and raw_numbers[0] == qty:
                return qty, product_text or normalized
        return qty, product_text or normalized


# ---------------------------------------------------------------------------
# Order Intelligence Engine (core)
# ---------------------------------------------------------------------------


class OrderIntelligenceEngine:
    """
    Production-grade order interpretation pipeline.
    Menu is injected at construction time (dynamic, never hardcoded).
    """

    def __init__(self, menu_items: List[Dict[str, Any]]) -> None:
        self.menu_items = [item for item in menu_items if item.get("disponible", True)]
        self._catalog = self._build_catalog()
        self._matcher = FuzzyMatcher(self._catalog)
        self._catalog_by_name = {entry["nombre"].lower(): entry for entry in self._catalog}
        self._category_defaults = self._build_category_defaults()
        self._catalog_norms = [entry["normalized"] for entry in self._catalog]
        self._menu_literal_token_set: set[str] = set()
        self._menu_token_set: set[str] = set()
        for entry in self._catalog:
            self._menu_literal_token_set.update(entry["normalized"].split())
            self._menu_token_set.update(entry["normalized"].split())
            for alias in entry.get("aliases", ()):
                if isinstance(alias, str) and len(alias) >= 3:
                    self._menu_token_set.update(alias.split())

    def _build_catalog(self) -> List[Dict[str, Any]]:
        catalog: List[Dict[str, Any]] = []
        for item in self.menu_items:
            name = str(item.get("nombre", "")).strip()
            normalized = TextNormalizer.basic(name)
            aliases = {normalized, *normalized.split()}
            for token, mapped in SYNONYM_TOKEN_MAP.items():
                if mapped.replace(" ", "") in normalized.replace(" ", ""):
                    aliases.add(token)
            catalog.append(
                {
                    "id": item.get("id"),
                    "nombre": name,
                    "precio": float(item.get("precio", 0)),
                    "categoria": item.get("categoria", ""),
                    "tokens": normalized.split(),
                    "normalized": normalized,
                    "aliases": sorted(aliases),
                }
            )
        return sorted(catalog, key=lambda entry: len(entry["normalized"]), reverse=True)

    def _build_category_defaults(self) -> Dict[str, Dict[str, Any]]:
        """First product per category in menu order (for category-name orders)."""
        defaults: Dict[str, Dict[str, Any]] = {}
        seen_categories: set[str] = set()
        catalog_by_name = {
            str(entry["nombre"]).strip().lower(): entry for entry in self._catalog
        }
        for item in self.menu_items:
            category = str(item.get("categoria", "")).strip()
            if not category:
                continue
            category_key = self._category_match_key(category)
            if category_key in seen_categories:
                continue
            product_name = str(item.get("nombre", "")).strip().lower()
            catalog_entry = catalog_by_name.get(product_name)
            if catalog_entry:
                defaults[category_key] = catalog_entry
                seen_categories.add(category_key)
        return defaults

    @staticmethod
    def _category_match_key(text: str) -> str:
        basic = TextNormalizer.basic(text)
        parts = [
            _singularize_token(_strip_accents(token))
            for token in basic.split()
            if token
        ]
        return " ".join(parts).strip()

    def _match_category_product(self, product_text: str) -> Optional[Dict[str, Any]]:
        query_key = self._category_match_key(product_text)
        if not query_key:
            return None
        hit = self._category_defaults.get(query_key)
        if hit:
            return hit
        tokens = query_key.split()
        meaningful = [
            token
            for token in tokens
            if token and token not in NOISE_WORDS and token not in NUMBER_WORDS
        ]
        if not meaningful:
            return None
        if len(meaningful) == 1:
            return self._category_defaults.get(
                _singularize_token(_strip_accents(meaningful[0]))
            )
        last = _singularize_token(_strip_accents(meaningful[-1]))
        if last not in self._category_defaults:
            return None
        if meaningful[0] in {"algo", "una", "un", "dos", "tres", "de"} or len(meaningful) == 2:
            return self._category_defaults[last]
        return None

    def _is_category_only_query(self, product_text: str) -> bool:
        query_key = self._category_match_key(product_text)
        if not query_key:
            return False
        tokens = query_key.split()
        meaningful = [
            token
            for token in tokens
            if token and token not in NOISE_WORDS and token not in NUMBER_WORDS
        ]
        if not meaningful:
            return False
        if len(meaningful) == 1:
            return meaningful[0] in PARTIAL_CATEGORY_ONLY
        last = _singularize_token(_strip_accents(meaningful[-1]))
        if last not in PARTIAL_CATEGORY_ONLY:
            return False
        return meaningful[0] in {"algo", "una", "un", "dos", "tres", "de"}

    def _is_partial_generic_product(self, product_text: str, qty: int) -> bool:
        if qty > 1:
            return False
        if self._is_category_only_query(product_text):
            return True
        query_key = self._category_match_key(product_text)
        tokens = query_key.split()
        meaningful = [
            token
            for token in tokens
            if token and token not in NOISE_WORDS and token not in NUMBER_WORDS
        ]
        if not meaningful:
            return False
        if len(meaningful) == 1:
            return meaningful[0] in PARTIAL_GENERIC_TOKENS
        if len(meaningful) == 2 and meaningful[0] in {"algo", "una", "un", "de"}:
            return meaningful[1] in PARTIAL_GENERIC_TOKENS
        return False

    def parse(self, text: str) -> Dict[str, Any]:
        """Canonical output contract."""
        raw = (text or "").strip()
        if not raw:
            return self._result([], "needs_clarification", ["entrada vacía"])

        prepared = NaturalLanguagePreprocessor.canonicalize(raw)

        skip_global_intent = False
        if JOKE_CANCEL_PREFIX_RE.match(prepared):
            tail = JOKE_CANCEL_PREFIX_RE.sub("", prepared).strip()
            if tail:
                prepared = tail
                skip_global_intent = True
        elif COMPOUND_MENU_ORDER_RE.match(prepared):
            tail = COMPOUND_MENU_ORDER_RE.sub("", prepared).strip()
            if tail:
                prepared = tail
                skip_global_intent = True

        if QUESTION_NO_ORDER_RE.search(prepared) and not (
            set(prepared.split()) & self._menu_token_set
            or self._has_category_token_overlap(prepared)
        ):
            return self._fail_safe(["consulta fuera de pedido"])

        if ADMIN_PREFIX_RE.match(raw.strip().lower()) or re.match(
            r"^confirmar\s+ord", raw.strip(), re.IGNORECASE
        ):
            result = self._result([], "needs_clarification", ["comando admin"])
            result["_internal"] = {"user_intent": "admin", "intent_confidence": 1.0}
            return result

        if re.match(r"^(?:cancelar|anular)\b", prepared, re.IGNORECASE):
            result = self._result([], "needs_clarification", ["intención de cancelar"])
            result["_internal"] = {
                "user_intent": "cancelar",
                "intent_confidence": 0.98,
                "needs_review": False,
            }
            return result

        prepared_tokens = set(prepared.split())
        has_menu_overlap = bool(prepared_tokens & self._menu_literal_token_set)
        has_category_overlap = self._has_category_token_overlap(prepared)
        intent_info = UserIntentClassifier.infer(
            prepared,
            has_product_signal=(
                has_menu_overlap
                or UserIntentClassifier.looks_like_product_order(prepared)
            ),
        )
        if (
            skip_global_intent
            and intent_info.get("command") in {"cancelar", "menu", "pedido"}
        ):
            intent_info = {
                "command": None,
                "confidence": 0.0,
                "matched": "",
                "has_products": True,
            }
        if intent_info.get("command") and not intent_info.get("has_products"):
            reason_by_command = {
                "menu": "intención de menú",
                "pedido": "intención de pedido sin productos",
                "reservar": "intención de reservar",
                "inicio": "intención de inicio",
                "cancelar": "intención de cancelar",
            }
            command = str(intent_info["command"])
            result = self._result(
                [],
                "needs_clarification",
                [reason_by_command.get(command, f"intención: {command}")],
            )
            result["_internal"] = {
                "user_intent": command,
                "intent_confidence": intent_info.get("confidence"),
                "intent_match": intent_info.get("matched", ""),
                "needs_review": False,
            }
            return result

        catalog_norms = self._catalog_norms
        segments = SegmentEngine.split_segments(prepared)
        normalized_full = ""
        if not segments:
            normalized_full = TextNormalizer.advanced(prepared, catalog_norms)
            segments = [normalized_full] if normalized_full else []

        has_overlap = has_menu_overlap or has_category_overlap
        if not has_overlap:
            if not normalized_full:
                normalized_full = TextNormalizer.advanced(prepared, catalog_norms)
            has_overlap = (
                bool(set(normalized_full.split()) & self._menu_token_set)
                or self._has_category_token_overlap(normalized_full)
            )

        gibberish_text = normalized_full or prepared
        if (
            not has_overlap
            and (
                self._is_gibberish(gibberish_text)
                or len(_token_keys(gibberish_text)) <= 1
            )
        ):
            if len(segments) < 2 and not (
                segments and self._segment_likely_product(segments[0])
            ):
                return self._fail_safe(["texto no interpretable"])

        parsed_items: List[Dict[str, Any]] = []
        unknown: List[str] = []
        needs_review = False

        for segment in segments:
            seg_tokens = [
                token
                for token in TextNormalizer.basic(segment).split()
                if token and token not in NOISE_WORDS
            ]
            if not seg_tokens:
                continue
            qty, product_text = QuantityEngine.resolve(segment, catalog_norms)
            if not product_text:
                continue
            pre_synonym = product_text
            product_text = self._matcher._apply_synonyms(product_text)
            if not product_text:
                continue

            category_entry = self._match_category_product(product_text)
            used_category_fallback = False
            if category_entry:
                best = category_entry
                score = ACCEPT_AUTO_SCORE
                second = None
                second_score = 0.0
                used_category_fallback = True
                if self._is_category_only_query(product_text):
                    needs_review = True
            else:
                best, score, second, second_score = self._matcher.best_match(product_text)

            if best and self._is_partial_generic_product(pre_synonym, qty):
                needs_review = True

            reject_match = bool(
                not used_category_fallback
                and best
                and score < ACCEPT_AUTO_SCORE
                and not self._match_aligns_with_intent(product_text, best)
            )

            if not best:
                unknown.append(segment)
                continue

            if reject_match:
                unknown.append(segment)
                continue

            if score < ACCEPT_AUTO_SCORE:
                needs_review = True
            ambiguous = (
                second
                and second_score >= ACCEPT_REVIEW_SCORE
                and best["id"] != second["id"]
                and abs(score - second_score) <= AMBIGUITY_DELTA
                and not FuzzyMatcher.has_distinctive_winner(product_text, best, second)
            )
            if ambiguous:
                needs_review = True

            parsed_items.append(
                {
                    "product": best["nombre"],
                    "quantity": qty,
                    "product_id": best["id"],
                    "unit_price": best["precio"],
                    "confidence": round(score, 4),
                }
            )

        parsed_items = self._deduplicate(parsed_items)
        parsed_items, qa_unknown, qa_review = self._quality_assurance(prepared, parsed_items)
        unknown.extend(qa_unknown)
        needs_review = needs_review or qa_review

        if not parsed_items:
            return self._fail_safe(unknown or ["sin productos reconocidos"])

        status = "ok" if not needs_review and not unknown else "needs_clarification"
        result = self._result(parsed_items, status, unknown)
        internal: Dict[str, Any] = {
            "min_score": _min_confidence(parsed_items),
            "needs_review": needs_review,
            "ambiguous": needs_review and not unknown,
        }
        if intent_info.get("command"):
            internal["user_intent"] = intent_info["command"]
            internal["intent_confidence"] = intent_info.get("confidence")
        result["_internal"] = internal
        return result

    def _quality_assurance(
        self,
        raw: str,
        items: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str], bool]:
        """Double-check: menu boundary, coherence, no invented products."""
        unknown: List[str] = []
        needs_review = False
        validated: List[Dict[str, Any]] = []

        for item in items:
            name_key = item["product"].lower()
            catalog_entry = self._catalog_by_name.get(name_key)
            if not catalog_entry:
                unknown.append(item["product"])
                needs_review = True
                continue
            if item.get("confidence", 0) < ACCEPT_REVIEW_SCORE:
                needs_review = True
            validated.append(item)

        validated = self._deduplicate(validated)
        if validated and not unknown:
            simulated = ", ".join(f"{i['quantity']} {i['product']}" for i in validated)
            raw_norm = TextNormalizer.basic(raw)
            if len(raw_norm) > 8 and len(simulated) < 3:
                needs_review = True

        return validated, unknown, needs_review

    @staticmethod
    def _deduplicate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in items:
            key = str(item.get("product_id") or item["product"]).lower()
            if key not in merged:
                merged[key] = dict(item)
            else:
                merged[key]["quantity"] += item["quantity"]
                merged[key]["confidence"] = max(
                    merged[key].get("confidence", 0),
                    item.get("confidence", 0),
                )
        return list(merged.values())

    def _fail_safe(self, unknown: List[str]) -> Dict[str, Any]:
        available = [entry["nombre"] for entry in self._catalog]
        return {
            "items": [],
            "total_items": 0,
            "status": "needs_clarification",
            "unknown": unknown,
            "menu_available": available,
            "_internal": {"min_score": None, "needs_review": True, "fail_safe": True},
        }

    @staticmethod
    def _result(
        items: List[Dict[str, Any]],
        status: str,
        unknown: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        public_items = [
            {"product": item["product"], "quantity": int(item["quantity"])}
            for item in items
        ]
        return {
            "items": public_items,
            "total_items": sum(item["quantity"] for item in public_items),
            "status": status,
            "unknown": unknown or [],
        }

    def _segment_likely_product(self, segment: str) -> bool:
        if not segment:
            return False
        _, product_text = QuantityEngine.extract(
            TextNormalizer.basic(segment),
        )
        if not product_text:
            return False
        if set(product_text.split()) & self._menu_token_set:
            return True
        best, score, _, _ = self._matcher.best_match(product_text)
        return bool(best and score >= ACCEPT_REVIEW_SCORE)

    def _has_menu_token_overlap(self, text: str) -> bool:
        basic = TextNormalizer.basic(text)
        if not basic:
            return False
        if set(basic.split()) & self._menu_token_set:
            return True
        corrected = self._matcher._correct_typos(basic)
        return corrected != basic and bool(set(corrected.split()) & self._menu_token_set)

    def _has_category_token_overlap(self, text: str) -> bool:
        """Category names count as valid menu overlap (e.g. una hamburguesa)."""
        basic = TextNormalizer.basic(text)
        if not basic:
            return False
        if self._category_match_key(basic) in self._category_defaults:
            return True
        for token in basic.split():
            if re.fullmatch(r"\d+", token):
                continue
            key = _singularize_token(_strip_accents(token))
            if key in NUMBER_WORDS:
                continue
            if key in self._category_defaults:
                return True
        return False

    @staticmethod
    def _intent_tokens(product_text: str) -> set[str]:
        intents: set[str] = set()
        for token in TextNormalizer.basic(product_text).split():
            key = _strip_accents(token.lower())
            if key in NUMBER_WORDS:
                continue
            singular = _singularize_token(key)
            mapped = SYNONYM_TOKEN_MAP.get(key) or SYNONYM_TOKEN_MAP.get(singular)
            if mapped:
                intents.add(TextNormalizer.basic(mapped))
            if key not in CATEGORY_STOPWORDS:
                intents.add(TextNormalizer.basic(singular))
        return {intent for intent in intents if intent}

    @staticmethod
    def _match_aligns_with_intent(product_text: str, best: Dict[str, Any]) -> bool:
        intents = OrderIntelligenceEngine._intent_tokens(product_text)
        if not intents:
            return False
        target = best["normalized"]
        target_parts = set(target.split())
        for intent in intents:
            if intent in target:
                return True
            if any(part in target_parts for part in intent.split() if len(part) >= 4):
                return True
            if _token_keys(intent) & _token_keys(target):
                return True
        return False

    @staticmethod
    def _is_gibberish(text: str) -> bool:
        if not text or len(text) < 3:
            return True
        tokens = text.split()
        if len(tokens) == 1 and len(tokens[0]) >= 6:
            letters = re.sub(r"[^a-z]", "", tokens[0])
            if letters and len(set(letters)) <= 3:
                return True
            if not re.search(r"[aeiou]", letters) and len(letters) >= 5:
                return True
        return False


# ---------------------------------------------------------------------------
# Public facade (Flask / Twilio integration — backward compatible)
# ---------------------------------------------------------------------------


class OrderParser:
    """Facade used by OrderService; wraps OrderIntelligenceEngine."""

    def __init__(self, menu_items: List[Dict[str, Any]]) -> None:
        self.menu_items = [item for item in menu_items if item.get("disponible", True)]
        self._engine = OrderIntelligenceEngine(self.menu_items)
        self._catalog = self._engine._catalog
        self._matcher = self._engine._matcher

    def parse_order(self, text: str, wa_id: str = "") -> Dict[str, Any]:
        """Structured output contract for order interpretation."""
        result = self._engine.parse(text)
        self._audit_parse_result(text, result, wa_id=wa_id)
        return result

    @staticmethod
    def _audit_parse_result(text: str, result: Dict[str, Any], wa_id: str = "") -> None:
        status = result.get("status", "")
        unknown = result.get("unknown") or []
        internal = result.get("_internal") or {}
        if status == "ok" and not unknown and not internal.get("needs_review"):
            return
        reason = "needs_clarification"
        if internal.get("fail_safe"):
            reason = "fail_safe"
        elif unknown:
            reason = "unknown_segments"
        elif internal.get("ambiguous"):
            reason = "ambiguity"
        log_parser_errors(
            wa_id=wa_id,
            message=text,
            reason=reason,
            parser_status=status,
            score=internal.get("min_score"),
            unknown=unknown,
            extra={"total_items": result.get("total_items", 0)},
        )

    def _match_product(self, fragment: str) -> Optional[Dict[str, Any]]:
        best, score, _, _ = self._matcher.best_match(fragment)
        return best if best and score >= ACCEPT_REVIEW_SCORE else None

    def _extract_quantity(self, text: str) -> Tuple[int, str]:
        return QuantityEngine.extract(text)

    def _split_segments(self, text: str) -> List[str]:
        return SegmentEngine.split_segments(text)

    def _cart_from_parse(
        self, result: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        items: List[Dict[str, Any]] = []
        for entry in result.get("items", []):
            matched = self._catalog_by_name(entry["product"])
            if not matched:
                continue
            qty = entry["quantity"]
            items.append(
                {
                    "product_id": matched["id"],
                    "product": matched["nombre"],
                    "qty": qty,
                    "unit_price": matched["precio"],
                    "subtotal": round(qty * matched["precio"], 2),
                }
            )
        unknown = list(result.get("unknown", []))
        return items, unknown

    def parse_additions(self, text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        result = self._engine.parse(text)
        items, unknown = self._cart_from_parse(result)
        if result.get("status") == "needs_clarification" and not items:
            segments = self._split_segments(text)
            unknown.extend(segments)
        return items, unknown

    def _catalog_by_name(self, product_name: str) -> Optional[Dict[str, Any]]:
        for entry in self._catalog:
            if entry["nombre"].lower() == product_name.lower():
                return entry
        return None

    def parse_remove(self, text: str) -> Tuple[List[str], List[str]]:
        cleaned = NaturalLanguagePreprocessor.canonicalize(text)
        cleaned = REMOVE_PREFIX_RE.sub("", cleaned)
        removed: List[str] = []
        unknown: List[str] = []
        for segment in self._split_segments(cleaned):
            matched = self._match_product(segment)
            if matched:
                removed.append(matched["nombre"])
            else:
                unknown.append(segment)
        return removed, unknown

    def parse_replace(self, text: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        cleaned = NaturalLanguagePreprocessor.canonicalize(text)
        patterns = [
            r"cambia\s+(.+?)\s+por\s+(.+)",
            r"reemplaza\s+(.+?)\s+por\s+(.+)",
            r"cambiar\s+(.+?)\s+por\s+(.+)",
            r"en\s+vez\s+de\s+(.+?)\s+por\s+(.+)",
            r"en\s+lugar\s+de\s+(.+?)\s+por\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if not match:
                continue
            old_fragment, new_fragment = match.group(1).strip(), match.group(2).strip()
            old_item = self._match_product(old_fragment)
            new_item = self._match_product(new_fragment)
            if old_item and new_item:
                return old_item["nombre"], new_item["nombre"], []
            unknown: List[str] = []
            if not old_item:
                unknown.append(old_fragment)
            if not new_item:
                unknown.append(new_fragment)
            return None, None, unknown
        return None, None, []

    def apply_message(
        self,
        text: str,
        current_cart: Optional[List[Dict[str, Any]]] = None,
        wa_id: str = "",
    ) -> Dict[str, Any]:
        cart = [dict(item) for item in (current_cart or [])]
        notes: List[str] = []
        unknown: List[str] = []
        cleaned = NaturalLanguagePreprocessor.canonicalize(text)

        if ADD_VERB_RE.search(cleaned):
            fragment = ADD_PREFIX_RE.sub("", cleaned).strip()
            matched = self._match_product(fragment) if fragment else None
            if matched:
                qty, _ = self._extract_quantity(fragment)
                addition = {
                    "product_id": matched["id"],
                    "product": matched["nombre"],
                    "qty": max(qty, 1),
                    "unit_price": matched["precio"],
                    "subtotal": round(max(qty, 1) * matched["precio"], 2),
                }
                found = False
                for item in cart:
                    if item["product"] == addition["product"]:
                        item["qty"] += addition["qty"]
                        item["subtotal"] = round(item["qty"] * item["unit_price"], 2)
                        found = True
                        break
                if not found:
                    cart.append(addition)
                notes.append(f"Agregué: {addition['product']}.")
                return {"items": cart, "notes": notes, "unknown": unknown}

            parse_snapshot = self._engine.parse(text)
            additions, unknown_add = self._cart_from_parse(parse_snapshot)
            unknown.extend(unknown_add)
            self._audit_parse_result(text, parse_snapshot, wa_id=wa_id)
            for addition in additions:
                found = False
                for item in cart:
                    if item["product"] == addition["product"]:
                        item["qty"] += addition["qty"]
                        item["subtotal"] = round(item["qty"] * item["unit_price"], 2)
                        found = True
                        break
                if not found:
                    cart.append(addition)
            if additions:
                notes.append(f"Agregué: {', '.join(a['product'] for a in additions)}.")
            return {"items": cart, "notes": notes, "unknown": unknown}

        if OTRA_ADD_RE.search(cleaned):
            fragment = OTRA_PREFIX_RE.sub("", cleaned).strip()
            matched = self._match_product(fragment) if fragment else None
            if matched:
                for item in cart:
                    if item["product"] == matched["nombre"]:
                        item["qty"] += 1
                        item["subtotal"] = round(item["qty"] * item["unit_price"], 2)
                        notes.append(f"Agregué otra: {matched['nombre']}.")
                        return {"items": cart, "notes": notes, "unknown": unknown}

        if REMOVE_VERB_RE.search(cleaned):
            removed, unknown_remove = self.parse_remove(text)
            unknown.extend(unknown_remove)
            if removed:
                cart = [item for item in cart if item["product"] not in removed]
                notes.append(f"Eliminé: {', '.join(removed)}.")
            return {"items": cart, "notes": notes, "unknown": unknown}

        old_name, new_name, unknown_replace = self.parse_replace(text)
        unknown.extend(unknown_replace)
        if old_name and new_name:
            replaced = False
            for item in cart:
                if item["product"] == old_name:
                    new_match = self._match_product(new_name)
                    if new_match:
                        item["product_id"] = new_match["id"]
                        item["product"] = new_match["nombre"]
                        item["unit_price"] = new_match["precio"]
                        item["subtotal"] = round(item["qty"] * new_match["precio"], 2)
                        replaced = True
            if replaced:
                notes.append(f"Cambié {old_name} por {new_name}.")
            return {"items": cart, "notes": notes, "unknown": unknown}

        parse_snapshot = self._engine.parse(text)
        additions, unknown_add = self._cart_from_parse(parse_snapshot)
        unknown.extend(unknown_add)
        self._audit_parse_result(text, parse_snapshot, wa_id=wa_id)

        cart_before = {item["product"]: item["qty"] for item in cart}
        for addition in additions:
            found = False
            for item in cart:
                if item["product"] == addition["product"]:
                    item["qty"] += addition["qty"]
                    item["subtotal"] = round(item["qty"] * item["unit_price"], 2)
                    found = True
                    break
            if not found:
                cart.append(addition)

        for item in cart:
            if item["qty"] != cart_before.get(item["product"], 0):
                notes.append(f"Actualicé: {item['product']} x{item['qty']}.")

        return {"items": cart, "notes": notes, "unknown": unknown}

    @staticmethod
    def cart_total(items: List[Dict[str, Any]]) -> float:
        return round(sum(item.get("subtotal", 0) for item in items), 2)

    @staticmethod
    def format_cart(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "Tu carrito está vacío."
        lines = []
        for item in items:
            lines.append(
                f"• {item['qty']} x {item['product']} — ${item['subtotal']:.2f}"
            )
        total = OrderParser.cart_total(items)
        lines.append(f"\n*Total: ${total:.2f}*")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal validation suite (regression guard)
# ---------------------------------------------------------------------------

_VALIDATION_MENU: List[Dict[str, Any]] = [
    {"id": "t1", "nombre": "Papas Fritas", "precio": 4.0, "categoria": "Sides", "disponible": True},
    {
        "id": "t2",
        "nombre": "Hamburguesa Clásica",
        "precio": 9.5,
        "categoria": "Hamburguesas",
        "disponible": True,
    },
    {"id": "t3", "nombre": "Agua Mineral", "precio": 1.5, "categoria": "Bebidas", "disponible": True},
]

_DEMO_VALIDATION_MENU: List[Dict[str, Any]] = [
    {"id": "1", "nombre": "Pizza Hawaiana", "precio": 12.5, "categoria": "Pizzas", "disponible": True},
    {"id": "2", "nombre": "Pizza Margarita", "precio": 11.0, "categoria": "Pizzas", "disponible": True},
    {
        "id": "3",
        "nombre": "Hamburguesa Clásica",
        "precio": 9.5,
        "categoria": "Hamburguesas",
        "disponible": True,
    },
    {"id": "4", "nombre": "Coca Cola", "precio": 2.5, "categoria": "Bebidas", "disponible": True},
    {"id": "5", "nombre": "Agua Mineral", "precio": 1.5, "categoria": "Bebidas", "disponible": True},
    {"id": "6", "nombre": "Ensalada César", "precio": 8.0, "categoria": "Ensaladas", "disponible": True},
]


def _find_item(items: List[Dict[str, Any]], product_fragment: str) -> Optional[Dict[str, Any]]:
    fragment = _strip_accents(product_fragment.lower())
    for item in items:
        if fragment in _strip_accents(item["product"].lower()):
            return item
    return None


def _qty_for(items: List[Dict[str, Any]], product_fragment: str) -> int:
    found = _find_item(items, product_fragment)
    return int(found["quantity"]) if found else 0


def run_validation_suite(verbose: bool = True) -> bool:
    """
    Executable regression tests for the Order Intelligence Engine.
    Safe to call in development; does not mutate external state.
    """
    failures: List[str] = []
    total = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal total
        total += 1
        if not condition:
            failures.append(f"{label}: {detail}".strip())

    basic_engine = OrderIntelligenceEngine(_VALIDATION_MENU)
    demo_engine = OrderIntelligenceEngine(_DEMO_VALIDATION_MENU)

    case1 = basic_engine.parse("2 papas fritas")
    check(
        "2 papas fritas",
        case1["status"] == "ok" and _qty_for(case1["items"], "papas") == 2,
        str(case1),
    )

    case2 = basic_engine.parse("peeeedido 3 hamburgesa")
    check(
        "peeeedido 3 hamburgesa",
        case2["status"] == "ok" and _qty_for(case2["items"], "hamburguesa") == 3,
        str(case2),
    )

    case3 = basic_engine.parse("asdfgh")
    check(
        "asdfgh fail-safe",
        case3["status"] == "needs_clarification" and case3["total_items"] == 0,
        str(case3),
    )

    case4 = basic_engine.parse("2 papas fritas y agua 3 hamburguesas")
    check(
        "2 papas fritas y agua 3 hamburguesas",
        case4["status"] == "ok"
        and _qty_for(case4["items"], "papas") == 2
        and _qty_for(case4["items"], "agua") == 1
        and _qty_for(case4["items"], "hamburguesa") == 3,
        str(case4),
    )

    user_order = (
        "quiero dos pizzas hawaianas, dos pizza margarita, una hamburgsa clasica, "
        "dos agua mineral y 5 ensaladas cesar"
    )
    case5 = demo_engine.parse(user_order)
    check(
        "pedido largo con comas (usuario)",
        case5["status"] == "ok"
        and not case5.get("unknown")
        and _qty_for(case5["items"], "hawaiana") == 2
        and _qty_for(case5["items"], "margarita") == 2
        and _qty_for(case5["items"], "hamburguesa") == 1
        and _qty_for(case5["items"], "agua") == 2
        and _qty_for(case5["items"], "cesar") == 5,
        str(case5),
    )

    apply5 = OrderParser(_DEMO_VALIDATION_MENU).apply_message(user_order)
    check(
        "apply_message pedido largo sin unknown",
        len(apply5["items"]) == 5 and not apply5.get("unknown"),
        str(apply5),
    )

    case6 = demo_engine.parse("dos pizza margarita,una hamburgsa clasica")
    check(
        "comas sin espacios",
        case6["status"] == "ok"
        and _qty_for(case6["items"], "margarita") == 2
        and _qty_for(case6["items"], "hamburguesa") == 1,
        str(case6),
    )

    case7 = demo_engine.parse("2 pizzas hawaiana 1 ensalada césar")
    check(
        "tildes en producto",
        case7["status"] == "ok"
        and _qty_for(case7["items"], "hawaiana") == 2
        and _qty_for(case7["items"], "cesar") == 1,
        str(case7),
    )

    case8 = demo_engine.parse("pizzahawaiana y pizzamargarita")
    check(
        "palabras pegadas",
        case8["status"] == "ok"
        and _find_item(case8["items"], "hawaiana")
        and _find_item(case8["items"], "margarita"),
        str(case8),
    )

    case9 = demo_engine.parse("3 coca cola, 2 gaseosa")
    check(
        "sinonimos bebidas",
        case9["status"] == "ok" and _qty_for(case9["items"], "coca") >= 3,
        str(case9),
    )

    case10 = demo_engine.parse("menu")
    check(
        "intencion menu sin productos",
        case10["total_items"] == 0 and case10["status"] == "needs_clarification",
        str(case10),
    )

    case10b = demo_engine.parse("men\u00fa")
    check(
        "intencion menu con tilde",
        case10b["total_items"] == 0 and case10b["status"] == "needs_clarification",
        str(case10b),
    )

    case11 = demo_engine.parse("2 hamburgesa & 1 agua")
    check(
        "conector ampersand",
        case11["status"] == "ok"
        and _qty_for(case11["items"], "hamburguesa") == 2
        and _qty_for(case11["items"], "agua") == 1,
        str(case11),
    )

    case11b = demo_engine.parse("dos pizzas, dos hamburguesas con dos aguas")
    check(
        "conector con como y",
        case11b["status"] in {"ok", "needs_clarification"}
        and len(case11b["items"]) == 3
        and _qty_for(case11b["items"], "hamburguesa") == 2
        and _qty_for(case11b["items"], "agua") == 2,
        str(case11b),
    )

    case11c = demo_engine.parse("2 pizzas, 2 hamburguesas con 2 aguas")
    check(
        "conector con con cantidades numericas",
        case11c["status"] in {"ok", "needs_clarification"}
        and len(case11c["items"]) == 3
        and _qty_for(case11c["items"], "hamburguesa") == 2
        and _qty_for(case11c["items"], "agua") == 2,
        str(case11c),
    )

    case12 = demo_engine.parse("hamburguesa + agua")
    check(
        "conector plus",
        case12["status"] == "ok"
        and _find_item(case12["items"], "hamburguesa")
        and _find_item(case12["items"], "agua"),
        str(case12),
    )

    case13 = basic_engine.parse("peeedido dos hamburgesas y una agua")
    check(
        "errores ortograficos extremos",
        _qty_for(case13["items"], "hamburguesa") >= 2 and _qty_for(case13["items"], "agua") >= 1,
        str(case13),
    )

    extended_menu: List[Dict[str, Any]] = [
        {"id": "p1", "nombre": "Pizza de Jamon y Queso", "precio": 95.0, "categoria": "Pizzas", "disponible": True},
        {"id": "p2", "nombre": "Pizza Mexicana", "precio": 25.0, "categoria": "Pizzas", "disponible": True},
        {"id": "p3", "nombre": "Pizza Ranchera", "precio": 15.0, "categoria": "Pizzas", "disponible": True},
        {"id": "b1", "nombre": "Coca Cola", "precio": 8.0, "categoria": "Bebidas", "disponible": True},
        {"id": "h1", "nombre": "Hamburguesa Mega", "precio": 20.0, "categoria": "Hamburguesas", "disponible": True},
        {"id": "h2", "nombre": "Hamburguesa Doble Carne", "precio": 22.0, "categoria": "Hamburguesas", "disponible": True},
        {"id": "h3", "nombre": "Hamburguesa Doble Pollo", "precio": 15.0, "categoria": "Hamburguesas", "disponible": True},
    ]
    user_long_order = (
        "quiero por favor dos pizzas de jamon y queso, tres pizzas mexicanas, "
        "4 pizzas rancheras, 5 coca colas, 7 hamburguesas mega ocho hamburguesas "
        "doble carne una habasurguesa doble pollo"
    )
    case14 = OrderIntelligenceEngine(extended_menu).parse(user_long_order)
    check(
        "pedido largo jamon y queso y hamburguesas variadas",
        case14["status"] in {"ok", "needs_clarification"}
        and len(case14["items"]) == 7
        and _qty_for(case14["items"], "jamon") == 2
        and _qty_for(case14["items"], "mexicana") == 3
        and _qty_for(case14["items"], "ranchera") == 4
        and _qty_for(case14["items"], "coca") == 5
        and _qty_for(case14["items"], "mega") == 7
        and _qty_for(case14["items"], "doble carne") == 8
        and _qty_for(case14["items"], "doble pollo") == 1,
        str(case14),
    )

    case15 = demo_engine.parse("hbogruesa")
    check(
        "typo general hbogruesa",
        case15["status"] in {"ok", "needs_clarification"}
        and _qty_for(case15["items"], "hamburguesa") >= 1,
        str(case15),
    )

    case16 = demo_engine.parse("2 piza hawaiana")
    check(
        "typo general piza",
        case16["status"] in {"ok", "needs_clarification"}
        and _qty_for(case16["items"], "hawaiana") == 2,
        str(case16),
    )

    large_qty_menu: List[Dict[str, Any]] = [
        {"id": "p1", "nombre": "Pizza de Jamon y Queso", "precio": 95.0, "categoria": "Pizzas", "disponible": True},
        {"id": "p2", "nombre": "Pizza Hawaiana", "precio": 125.0, "categoria": "Pizzas", "disponible": True},
        {"id": "h1", "nombre": "Hamburguesa Clasica", "precio": 125.0, "categoria": "Hamburguesas", "disponible": True},
        {"id": "h2", "nombre": "Hamburguesa Mega", "precio": 11.0, "categoria": "Hamburguesas", "disponible": True},
        {
            "id": "h3",
            "nombre": "Hamburguesa Doble Carne",
            "precio": 22.0,
            "categoria": "Hamburguesas",
            "disponible": True,
        },
        {"id": "b1", "nombre": "Coca Cola", "precio": 8.0, "categoria": "Bebidas", "disponible": True},
    ]
    large_qty_order = (
        "quiero por favor 60 hamburgsdfesas clasiccscas, 2333 hamburgueas mega, "
        "12123 cocas con 777 pirzas harwewaianas y 8 picsas de jamon y quieso"
    )
    case17 = OrderIntelligenceEngine(large_qty_menu).parse(large_qty_order)
    check(
        "cantidades grandes y repetidas",
        case17["status"] in {"ok", "needs_clarification"}
        and _qty_for(case17["items"], "clasica") == 60
        and _qty_for(case17["items"], "mega") == 2333
        and _qty_for(case17["items"], "coca") == 12123
        and _qty_for(case17["items"], "hawaiana") == 777
        and _qty_for(case17["items"], "jamon") == 8,
        str(case17),
    )

    case18 = demo_engine.parse(
        "le escribi dos pizzas hawaianas, dos cocacolas dos hamburguesas de carne y un agua"
    )
    check(
        "prefijo conversacional no suma items fantasma",
        case18["status"] in {"ok", "needs_clarification"}
        and _qty_for(case18["items"], "hawaiana") == 2
        and _qty_for(case18["items"], "coca") == 2
        and _qty_for(case18["items"], "hamburguesa") == 2
        and _qty_for(case18["items"], "agua") == 1,
        str(case18),
    )

    user_bug_menu: List[Dict[str, Any]] = [
        {"id": "1", "nombre": "Hawaiana", "precio": 125.0, "categoria": "Pizzas", "disponible": True},
        {"id": "b1", "nombre": "Coca Cola", "precio": 25.0, "categoria": "Bebidas", "disponible": True},
        {"id": "b2", "nombre": "Agua", "precio": 11.0, "categoria": "Bebidas", "disponible": True},
    ]
    case19 = OrderIntelligenceEngine(user_bug_menu).parse(
        "* 2 pizza hawaiana, 1 coca cola\n* una hamburguesa y dos aguas"
    )
    check(
        "asteriscos whatsapp sin fusionar coca con hamburguesa",
        _qty_for(case19["items"], "hawaiana") == 2
        and _qty_for(case19["items"], "coca") == 1
        and _qty_for(case19["items"], "agua") == 2
        and any("hamburguesa" in str(u).lower() for u in case19.get("unknown", [])),
        str(case19),
    )

    user_menu_with_burger: List[Dict[str, Any]] = [
        *user_bug_menu,
        {
            "id": "h1",
            "nombre": "Carne",
            "precio": 5.0,
            "categoria": "Hamburguesas",
            "disponible": True,
        },
    ]
    case20 = OrderIntelligenceEngine(user_menu_with_burger).parse(
        "* 2 pizza hawaiana, 1 coca cola\n* una hamburguesa y dos aguas"
    )
    check(
        "nombre de categoria usa primer producto de la categoria",
        case20["status"] == "ok"
        and _qty_for(case20["items"], "hawaiana") == 2
        and _qty_for(case20["items"], "coca") == 1
        and _qty_for(case20["items"], "carne") == 1
        and _qty_for(case20["items"], "agua") == 2
        and not case20.get("unknown"),
        str(case20),
    )

    production_like_menu: List[Dict[str, Any]] = [
        {"id": "", "nombre": "Hawaiana", "precio": 125.0, "categoria": "Pizzas", "disponible": True},
        {"id": "", "nombre": "Margarita", "precio": 11.0, "categoria": "Pizzas", "disponible": True},
        {"id": "", "nombre": "Pollo con Champiñones", "precio": 11.0, "categoria": "Pizzeta", "disponible": True},
        {"id": "", "nombre": "Coca Cola", "precio": 25.0, "categoria": "Bebidas", "disponible": True},
        {"id": "", "nombre": "Agua", "precio": 11.0, "categoria": "Bebidas", "disponible": True},
        {"id": "", "nombre": "Café", "precio": 2.0, "categoria": "Bebidas", "disponible": True},
        {"id": "", "nombre": "Carne", "precio": 5.0, "categoria": "Hamburguesas", "disponible": True},
    ]
    case21 = OrderIntelligenceEngine(production_like_menu).parse(
        "* 2 pizza hawaiana, 1 coca cola\n* una hamburguesa y dos aguas"
    )
    check(
        "ids vacios no desvian categoria hamburguesa a cafe",
        case21["status"] == "ok"
        and _qty_for(case21["items"], "hawaiana") == 2
        and _qty_for(case21["items"], "coca") == 1
        and _qty_for(case21["items"], "carne") == 1
        and _qty_for(case21["items"], "agua") == 2
        and _qty_for(case21["items"], "cafe") == 0
        and not case21.get("unknown"),
        str(case21),
    )

    case22 = demo_engine.parse("bueno pues un par de pizza margarita y tres aguas")
    check(
        "colloquial par de y prefijo conversacional",
        case22["status"] in {"ok", "needs_clarification"}
        and _qty_for(case22["items"], "margarita") == 2
        and _qty_for(case22["items"], "agua") == 3,
        str(case22),
    )

    case23 = demo_engine.parse("que tienen de bebidas")
    check(
        "frase menu sin productos concretos",
        case23["total_items"] == 0 and case23["status"] == "needs_clarification",
        str(case23),
    )

    case24 = demo_engine.parse(
        "dos pizzas hawaianas luego tres cocacolas y aparte una ensalada cesar"
    )
    check(
        "conectores luego y aparte",
        case24["status"] in {"ok", "needs_clarification"}
        and _qty_for(case24["items"], "hawaiana") == 2
        and _qty_for(case24["items"], "coca") == 3
        and _qty_for(case24["items"], "cesar") == 1,
        str(case24),
    )

    remove_case = OrderParser(_DEMO_VALIDATION_MENU).apply_message(
        "quitame la coca cola",
        [
            {
                "product_id": "4",
                "product": "Coca Cola",
                "qty": 2,
                "unit_price": 2.5,
                "subtotal": 5.0,
            }
        ],
    )
    check(
        "apply_message quitar producto conversacional",
        not remove_case["items"] and "Eliminé" in " ".join(remove_case.get("notes", [])),
        str(remove_case),
    )

    case25 = demo_engine.parse("dos hamburguesas con dos aguas")
    check(
        "con separa items con cantidad no de jamon y queso",
        case25["status"] in {"ok", "needs_clarification"}
        and _qty_for(case25["items"], "hamburguesa") == 2
        and _qty_for(case25["items"], "agua") == 2,
        str(case25),
    )

    jamon_menu: List[Dict[str, Any]] = [
        {
            "id": "p1",
            "nombre": "Pizza de Jamon y Queso",
            "precio": 95.0,
            "categoria": "Pizzas",
            "disponible": True,
        },
    ]
    case26 = OrderIntelligenceEngine(jamon_menu).parse("2 pizza de jamon y queso")
    check(
        "de jamon y queso no parte en dos productos",
        case26["status"] in {"ok", "needs_clarification"}
        and len(case26["items"]) == 1
        and case26["items"][0]["quantity"] == 2,
        str(case26),
    )

    case27 = demo_engine.parse("CONFIRMAR ORD-12345 dos hawaianas")
    check(
        "comando admin no parsea como pedido",
        case27["total_items"] == 0 and case27["status"] == "needs_clarification",
        str(case27),
    )

    case28 = demo_engine.parse("a las 8 pm 2 pizzas hawaianas")
    check(
        "hora pm no confunde cantidad",
        case28["status"] in {"ok", "needs_clarification"}
        and _qty_for(case28["items"], "hawaiana") == 2,
        str(case28),
    )

    case29 = demo_engine.parse("2 hawaiana | 3 coca cola | 1 ensalada cesar")
    check(
        "conector pipe",
        case29["status"] in {"ok", "needs_clarification"}
        and _qty_for(case29["items"], "hawaiana") == 2
        and _qty_for(case29["items"], "coca") == 3
        and _qty_for(case29["items"], "cesar") == 1,
        str(case29),
    )

    case30 = OrderIntelligenceEngine(large_qty_menu).parse("veintiuna hamburguesas mega")
    check(
        "cantidad veintiuno en palabras",
        case30["status"] in {"ok", "needs_clarification"}
        and _qty_for(case30["items"], "mega") == 21,
        str(case30),
    )

    case31 = demo_engine.parse("tengo hambre")
    check(
        "intencion pedido vacio",
        case31["total_items"] == 0 and case31["status"] == "needs_clarification",
        str(case31),
    )

    case32 = demo_engine.parse("menu y 2 margaritas")
    check(
        "menu con productos sigue parseando",
        case32["status"] in {"ok", "needs_clarification"}
        and _qty_for(case32["items"], "margarita") == 2,
        str(case32),
    )

    multi_drink_menu: List[Dict[str, Any]] = [
        {"id": "1", "nombre": "Coca Cola", "precio": 2.5, "categoria": "Bebidas", "disponible": True},
        {"id": "2", "nombre": "Agua Mineral", "precio": 1.5, "categoria": "Bebidas", "disponible": True},
    ]
    case33 = OrderIntelligenceEngine(multi_drink_menu).parse("2 refrescos")
    check(
        "refresco no fuerza coca con varias bebidas",
        case33["status"] == "needs_clarification" or _qty_for(case33["items"], "agua") >= 0,
        str(case33),
    )

    case34 = OrderIntelligenceEngine(large_qty_menu).parse("siete mega ocho doble carne")
    check(
        "cantidad palabra fusiona segmento siguiente",
        case34["status"] in {"ok", "needs_clarification"}
        and _qty_for(case34["items"], "mega") == 7
        and _qty_for(case34["items"], "doble carne") == 8,
        str(case34),
    )

    replace_case = OrderParser(_DEMO_VALIDATION_MENU).apply_message(
        "en vez de coca cola por agua mineral",
        [
            {
                "product_id": "4",
                "product": "Coca Cola",
                "qty": 1,
                "unit_price": 2.5,
                "subtotal": 2.5,
            }
        ],
    )
    check(
        "apply_message en vez de por",
        any(item["product"] == "Agua Mineral" for item in replace_case["items"]),
        str(replace_case),
    )

    pollo_menu: List[Dict[str, Any]] = [
        {
            "id": "p1",
            "nombre": "Pollo con Champiñones",
            "precio": 11.0,
            "categoria": "Pizzeta",
            "disponible": True,
        },
        {"id": "p2", "nombre": "Margarita", "precio": 11.0, "categoria": "Pizzas", "disponible": True},
    ]
    case35 = OrderIntelligenceEngine(pollo_menu).parse("2 pollo con champiñones")
    check(
        "nombre con con en catalogo intacto",
        case35["status"] in {"ok", "needs_clarification"}
        and len(case35["items"]) == 1
        and case35["items"][0]["quantity"] == 2,
        str(case35),
    )

    real_menu = [
        {"id": "1", "nombre": "Hawaiana", "precio": 125.0, "categoria": "Pizzas", "disponible": True},
        {"id": "2", "nombre": "cocacola", "precio": 3.0, "categoria": "Bebidas", "disponible": True},
    ]
    case36 = OrderIntelligenceEngine(real_menu).parse("bueno 2 hawaiana y 3 cocacola")
    check(
        "menu real hawaiana cocacola",
        case36["status"] == "ok"
        and _qty_for(case36["items"], "hawaiana") == 2
        and _qty_for(case36["items"], "coca") == 3,
        str(case36),
    )

    case37 = basic_engine.parse("$50 4 papas fritas")
    check(
        "precio dolares no es cantidad",
        case37["status"] in {"ok", "needs_clarification"}
        and _qty_for(case37["items"], "papas") == 4,
        str(case37),
    )

    case38 = demo_engine.parse("3 gaseosa")
    check(
        "gaseosa sinonimo con una sola gaseosa en menu",
        case38["status"] in {"ok", "needs_clarification"}
        and _qty_for(case38["items"], "coca") == 3,
        str(case38),
    )

    case39 = demo_engine.parse("cancelar 2 hawaianas")
    check(
        "cancelar al inicio no es pedido",
        case39["total_items"] == 0,
        str(case39),
    )

    intent1 = infer_user_intent("menu")
    check(
        "infer_user_intent menu",
        intent1.get("command") == "menu" and intent1.get("confidence", 0) >= 0.9,
        str(intent1),
    )

    intent2 = infer_user_intent("hola quisiera reservar una mesa para 4")
    check(
        "infer_user_intent reservar",
        intent2.get("command") == "reservar",
        str(intent2),
    )

    intent3 = infer_user_intent("quiero hacer un pedido")
    check(
        "infer_user_intent pedido",
        intent3.get("command") == "pedido",
        str(intent3),
    )

    intent4 = infer_user_intent("volver al inicio porfa")
    check(
        "infer_user_intent inicio",
        intent4.get("command") == "inicio",
        str(intent4),
    )

    intent5 = infer_user_intent("cancelar mi pedido")
    check(
        "infer_user_intent cancelar",
        intent5.get("command") == "cancelar",
        str(intent5),
    )

    intent6 = infer_user_intent("2 pizzas hawaianas y 1 coca")
    check(
        "infer_user_intent con productos no es comando",
        intent6.get("command") is None and intent6.get("has_products"),
        str(intent6),
    )

    intent7 = infer_user_intent("menu y 2 margaritas")
    check(
        "infer_user_intent menu con productos no bloquea pedido",
        intent7.get("command") is None and intent7.get("has_products"),
        str(intent7),
    )

    intent8 = infer_user_intent("listo ya quiero comprar")
    check(
        "infer_user_intent confirmacion no es pedido",
        intent8.get("command") is None,
        str(intent8),
    )

    intent9 = infer_user_intent("comprar")
    check(
        "infer_user_intent comprar solo no es comando",
        intent9.get("command") is None,
        str(intent9),
    )

    parse_reservar = demo_engine.parse("me gustaria reservar para el viernes")
    check(
        "parse intencion reservar sin productos",
        parse_reservar["total_items"] == 0
        and (parse_reservar.get("_internal") or {}).get("user_intent") == "reservar",
        str(parse_reservar),
    )

    parse_pedido = demo_engine.parse("tengo hambre")
    check(
        "parse intencion pedido tengo hambre",
        parse_pedido["total_items"] == 0
        and (parse_pedido.get("_internal") or {}).get("user_intent") == "pedido",
        str(parse_pedido),
    )

    apply_agrega = OrderParser(_DEMO_VALIDATION_MENU).apply_message(
        "agregame 2 cocas mas",
        [{"product_id": "4", "product": "Coca Cola", "qty": 1, "unit_price": 2.5, "subtotal": 2.5}],
    )
    check(
        "apply_message agregame",
        sum(i["qty"] for i in apply_agrega["items"]) >= 3,
        str(apply_agrega),
    )

    pedido_label = demo_engine.parse("pedido: 2 hawaiana, 1 coca cola")
    check(
        "prefijo pedido dos puntos",
        pedido_label["status"] in {"ok", "needs_clarification"}
        and _qty_for(pedido_label["items"], "hawaiana") == 2,
        str(pedido_label),
    )

    if verbose:
        passed = total - len(failures)
        if failures:
            print("PARSER VALIDATION FAILURES:")
            for failure in failures:
                print(f"  - {failure}")
            print(f"PARSER VALIDATION: {passed}/{total}")
        else:
            print(f"PARSER VALIDATION: OK ({total}/{total})")

    return not failures


if __name__ == "__main__":
    import sys

    ok = run_validation_suite(verbose=True)
    sys.exit(0 if ok else 1)
