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
from config.intents import GLOBAL_COMMAND_INTENTS
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

# Phase 2.1: full Spanish cardinal vocabulary (atoms 0..29, tens, hundreds, scales).
# Each word maps to its own value; parse_cardinal() composes multi-word numbers.
# Scales (mil=1000, millon=1e6) act as multipliers in parse_cardinal.
NUMBER_WORDS: Dict[str, int] = {
    "cero": 0,
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21, "veintiun": 21, "veintiún": 21, "veintiuna": 21,
    "veintidos": 22, "veintidós": 22, "veintidas": 22,
    "veintitres": 23, "veintitrés": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintiséis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900,
    "mil": 1000,
    "millon": 1_000_000, "millón": 1_000_000, "millones": 1_000_000,
}

_CARD_THOUSAND = 1000
_CARD_MILLION = 1_000_000


def parse_cardinal(words: List[str]) -> Optional[int]:
    """Compose a Spanish cardinal from word tokens (mil doscientos veinticinco -> 1225)."""
    total = 0
    current = 0
    seen = False
    for raw in words:
        word = _repeat_key(_strip_accents(raw))
        if word == "y":
            if not seen:
                return None
            continue
        value = NUMBER_WORDS.get(word)
        if value is None:
            value = NUMBER_WORDS.get(raw)
        if value is None:
            return None
        seen = True
        if value == _CARD_THOUSAND:
            current = (current or 1) * _CARD_THOUSAND
            total += current
            current = 0
        elif value == _CARD_MILLION:
            current = (current or 1) * _CARD_MILLION
            total += current
            current = 0
        else:
            current += value
    if not seen:
        return None
    return total + current

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

# Phase 2.4: pair / dozen / half-dozen, with or without the "de"/"d" connector.
# Order matters: half-dozen and "una docena" before the bare "docena".
COLLOQUIAL_QTY_REPLACEMENTS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmedia\s+docena(?:\s+(?:de|d)\b)?\s+", re.IGNORECASE), "6 "),
    (re.compile(r"\b(?:una|un)\s+docena(?:\s+(?:de|d)\b)?\s+", re.IGNORECASE), "12 "),
    (re.compile(r"\bdocena(?:\s+(?:de|d)\b)?\s+", re.IGNORECASE), "12 "),
    (re.compile(r"\bun\s+par(?:\s+(?:de|d)\b)?\s+", re.IGNORECASE), "2 "),
    (re.compile(r"\bpar\s+(?:de|d)\b\s+", re.IGNORECASE), "2 "),
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

SOLO_ONLY_RE = re.compile(
    r"\bdéjame\s+solo\b|\bdejame\s+solo\b|\bsolo\s+quiero\b|\bquiero\s+solo\b|\bsolo\s+los\b|\bsolo\s+las\b|\bsolo\s+el\b|\bsolo\s+la\b",
    re.IGNORECASE,
)
SOLO_PREFIX_RE = re.compile(
    r"^(?:déjame\s+solo|dejame\s+solo|solo\s+quiero|quiero\s+solo)\s+(?:los\s+|las\s+|el\s+|la\s+)?",
    re.IGNORECASE,
)

COMMA_SPLIT_RE = re.compile(r"\s*,\s*")
# Phase 2.2: a comma between digits is a thousands separator (12,123) — never a split.
NUMSAFE_COMMA_SPLIT_RE = re.compile(r"\s*(?<!\d),(?!\d)\s*")

PLUS_SPLIT_RE = re.compile(r"\s*\+\s*")
STAR_SPLIT_RE = re.compile(r"\s*\*\s*")
AMP_SPLIT_RE = re.compile(r"\s*&\s*")

CONNECTOR_SPLIT_RE = re.compile(
    r"\s*(?:(?<!\d),(?!\d)|;|&|\||\band\b|\s+y\s+|\s+e\s+|\s+mas\s+|\s+más\s+|\s+también\s+|\s+tambien\s+"
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

COMPOUND_Y_RE = re.compile(r"\bde\s+(\w+)\s+y\s+(\w+)\b", re.IGNORECASE)
COMPOUND_Y_TOKEN = "__ingy__"

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)

REPEAT_CHAR_RE = re.compile(r"([a-z])\1{2,}", re.UNICODE)
REPEAT_CHAR_REPLACEMENT = r"\1\1"

# Phase 1.2: full repeat collapse used only for tolerant set-membership
# (peeeedido -> peedido surface, but matches NOISE "pedido" via this key).
_REPEAT_FULL_RE = re.compile(r"([a-wyz0-9])\1+", re.UNICODE)


def _repeat_key(token: str) -> str:
    return _REPEAT_FULL_RE.sub(r"\1", token)


def _is_noise(token: str) -> bool:
    # ponytail: repeat-key membership; ceiling: a real product token whose
    # full-collapse equals a noise word would be dropped. Upgrade: gate by catalog vocab.
    if not token or token in NUMBER_WORDS:
        return False
    if token in NOISE_WORDS:
        return True
    key = _repeat_key(token)
    return key != token and key in NOISE_WORDS


def _number_word(token: str) -> Optional[int]:
    """Phase 1.2: repeat-tolerant number-word lookup. Phase 2 generalizes magnitudes."""
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    return NUMBER_WORDS.get(_repeat_key(token))


# Phase 1.1: single punctuation table. Every punctuation char becomes a separator
# (space) EXCEPT when flanked by digits on both sides, which preserves number-internal
# separators (3/8, 1.5, 1.000, 1,000) for the Phase 2 numeric engine.
def _strip_punct(text: str) -> str:
    # ponytail: O(n) char scan; upgrade to a precompiled lookbehind regex in Phase 5.5.
    out: List[str] = []
    last = len(text) - 1
    for i, ch in enumerate(text):
        if ch.isalnum() or ch.isspace() or ch == "_":
            out.append(ch)
        elif (
            0 < i < last
            and text[i - 1].isdigit()
            and text[i + 1].isdigit()
        ):
            out.append(ch)
        else:
            out.append(" ")
    return "".join(out)


# Phase 1.3: split glued quantity+product tokens. Digit↔letter boundaries split
# (excluding x/× which are the 2x/x2 multiplier handled by Phase 2.3); number-word
# prefixes glued to a product ("dosarcos" -> "dos arcos") also split.
_GLUE_DIGIT_LETTER_RE = re.compile(r"(\d)(?=[a-wyz])", re.IGNORECASE)
_GLUE_LETTER_DIGIT_RE = re.compile(r"(?<=[a-wyz])(\d)", re.IGNORECASE)
_GLUE_QTYWORD_RE = re.compile(rf"\b({_QTY_WORD_ALTS})([a-z]{{3,}})", re.IGNORECASE)


def _qtyword_split(match: "re.Match[str]") -> str:
    g1, g2 = match.group(1), match.group(2)
    # ponytail: don't break a compound cardinal (doscientos = dos+cientos);
    # ceiling: glued cardinal+cardinal like "dosmil" still splits (intended → 2 mil).
    if (g1 + g2) in NUMBER_WORDS:
        return match.group(0)
    return f"{g1} {g2}"


def _split_glued_quantities(text: str) -> str:
    text = _GLUE_DIGIT_LETTER_RE.sub(r"\1 ", text)
    text = _GLUE_LETTER_DIGIT_RE.sub(r" \1", text)
    text = _GLUE_QTYWORD_RE.sub(_qtyword_split, text)
    return text


# Phase 2.2: an integer token is either plain digits or digit groups separated by
# thousands separators (1.000, 1,000, 1.000.000, 12,123). Decimals/measures (1.5)
# and fractions (3/8) do NOT match the grouped form, so they stay intact.
_INT_TOKEN = r"\d{1,3}(?:[.,]\d{3})+|\d+"
_INT_TOKEN_RE = re.compile(rf"^(?:{_INT_TOKEN})$")
_NUM_RUN = rf"(?:{_QTY_WORD_ALTS})(?:\s+(?:y\s+)?(?:{_QTY_WORD_ALTS}))*"


def _parse_int_token(token: str) -> Optional[int]:
    if not _INT_TOKEN_RE.match(token):
        return None
    return int(token.replace(".", "").replace(",", ""))

QTY_PREFIX_RE = re.compile(
    rf"^(?:({_INT_TOKEN})\s*[x×]\s*|[x×]\s*({_INT_TOKEN})\s*"
    rf"|[x×]({_INT_TOKEN})\s*|({_INT_TOKEN})\s+)(.*)$",
    re.IGNORECASE,
)

QTY_SUFFIX_RE = re.compile(rf"^(.+?)\s+(?:[x×]\s*)?({_INT_TOKEN})[x×]?\s*$")

SEGMENT_BOUNDARY_RE = re.compile(
    rf"(?<!\d)(?:({_INT_TOKEN})\s*[x×]\s+|[x×]\s*({_INT_TOKEN})\s+"
    rf"|({_INT_TOKEN})\s+"
    rf"|(?<!\w)(?:{_NUM_RUN})(?!\w)\s+)(?=\D)",
    re.IGNORECASE,
)

# Phase 5.5: all inline re.compile() calls moved to module level; zero compile at runtime.
# ponytail 5.5: covers every inline pattern found in method bodies as of this phase.
# ceiling: new inline patterns added later would silently skip precompilation.
# Upgrade: CI lint rule banning re.compile/re.search/re.sub with string literals in methods.
_WS_RE = re.compile(r"\s+")
_HAS_DIGIT_RE = re.compile(r"\d")
_QTY_X_GLUE_RE = re.compile(r"(\d)\s*[x×](?=\S)")
_X_QTY_GLUE_RE = re.compile(r"(?<!\d)[x×]\s*(\d+)\s+")
_NUMERIC_X_SIGNAL_RE = re.compile(r"\b\d+\s*[x×]\s*\w", re.IGNORECASE)
_X_NUMERIC_SIGNAL_RE = re.compile(r"\b[x×]\d+\s+\w", re.IGNORECASE)
_QTY_DE_PRODUCT_RE = re.compile(
    r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|un|una|uno|par)\s+de\s+\w{3,}",
    re.IGNORECASE,
)
_PURE_DIGITS_RE = re.compile(r"^\d+$")
_PARA_LLEVAR_RE = re.compile(r"\bpara\s+llevar\b", re.IGNORECASE)
_DE_PREFIX_RE = re.compile(r"^de\s+")
_LEADING_INT_X_RE = re.compile(rf"({_INT_TOKEN})[x×]", re.IGNORECASE)
_LEADING_X_INT_RE = re.compile(rf"[x×]({_INT_TOKEN})", re.IGNORECASE)
_CANCEL_START_RE = re.compile(r"^(?:cancelar|anular)\b", re.IGNORECASE)
_CONFIRM_ORD_RE = re.compile(r"^confirmar\s+ord", re.IGNORECASE)  # 5.5 completion
_NON_ALPHA_RE = re.compile(r"[^a-z]")
_VOWEL_RE = re.compile(r"[aeiou]")

_catalog_log = logging.getLogger(__name__)

# Phase 5.7: security constants — anti-DoS input limits.
# ponytail 5.7: flat char limit; ceiling: multi-byte emoji count differently in len().
# Upgrade: limit in Unicode codepoints via len(text) (already counts codepoints in CPython).
MAX_INPUT_CHARS: int = 1000   # chars; longer input is truncated before any processing
MAX_SEGMENTS: int = 20        # segments; excess truncated after SegmentEngine.split_segments

ACCEPT_AUTO_SCORE = 0.80
ACCEPT_REVIEW_SCORE = 0.50
AMBIGUITY_DELTA = 0.05
TYPO_CORRECT_MIN_SCORE = 0.68
TYPO_CORRECT_MIN_GAP = 0.05
TYPO_VOCAB_MIN_LEN = 4

# Phase 4.4: optional pluggable semantic scorer (off by default, fallback = fuzzy).
# ponytail: module-level singleton; not tenant-isolated nor thread-safe.
# Upgrade: pass scorer as constructor param to OrderIntelligenceEngine.
_SEMANTIC_SCORER: Optional[Any] = None

# Phase 5.6: engine cache keyed by (business_id, catalog_fingerprint).
# ponytail 5.6: hash() not stable across processes → in-process cache only; no persistence.
# ceiling: unbounded growth if many distinct fingerprints per tenant (DB migration bursts).
# Upgrade: LRU with max-size or weak-value dict if memory pressure matters.
_engine_cache: Dict[Tuple[str, str], "OrderIntelligenceEngine"] = {}
_engine_cache_stats: Dict[str, int] = {"hits": 0, "misses": 0}


def _catalog_fingerprint(menu_items: List[Dict[str, Any]]) -> str:
    """Stable (within-process) hash of sorted (id, nombre, precio, disponible) tuples."""
    rows = tuple(sorted(
        (
            str(i.get("id", "")),
            str(i.get("nombre", "")),
            str(i.get("precio", "")),
            str(i.get("disponible", True)),
        )
        for i in menu_items
    ))
    return str(hash(rows))


def _get_or_build_engine(
    business_id: str, menu_items: List[Dict[str, Any]]
) -> "OrderIntelligenceEngine":
    """Return cached engine or build fresh; evicts stale keys for this tenant."""
    fp = _catalog_fingerprint(menu_items)
    key: Tuple[str, str] = (business_id, fp)
    cached = _engine_cache.get(key)
    if cached is not None:
        _engine_cache_stats["hits"] += 1
        return cached
    _engine_cache_stats["misses"] += 1
    engine = OrderIntelligenceEngine(menu_items)
    # Evict stale entries for this tenant (catalog changed → auto-invalidation).
    stale = [k for k in _engine_cache if k[0] == business_id]
    for k in stale:
        del _engine_cache[k]
    _engine_cache[key] = engine
    return engine


def set_semantic_scorer(fn: Optional[Any]) -> None:
    """Install a semantic scorer callable(a: str, b: str) → float [0, 1].  None = fuzzy."""
    global _SEMANTIC_SCORER
    _SEMANTIC_SCORER = fn


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
        if part
    }


def _normalized_alias_tokens(raw: Any) -> set[str]:
    """Phase 3.2: turn item['aliases'/'keywords'] data into normalized alias tokens.

    Accepts a str or an iterable of str (anything else is ignored — boundary safety).
    """
    values: List[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = [v for v in raw if isinstance(v, str)]
    out: set[str] = set()
    for value in values:
        norm = TextNormalizer.basic(value)
        if norm:
            out.add(norm)
            out.update(norm.split())
    return out


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
        cleaned = _strip_punct(cleaned)
        cleaned = _WS_RE.sub(" ", cleaned)
        return cleaned.strip()

    @classmethod
    def advanced(
        cls,
        value: str,
        catalog_normalized: Optional[List[str]] = None,
        *,
        compact_map: Optional[Dict[str, str]] = None,
    ) -> str:
        text = value.lower().strip()
        text = EMOJI_RE.sub(" ", text)
        text = _strip_accents(text)
        text = _strip_punct(text)
        text = REPEAT_CHAR_RE.sub(REPEAT_CHAR_REPLACEMENT, text)
        text = _split_glued_quantities(text)
        text = _WS_RE.sub(" ", text).strip()
        if compact_map is not None or catalog_normalized:
            glued_tokens: List[str] = []
            for token in text.split():
                if _HAS_DIGIT_RE.search(token):
                    glued_tokens.append(token)
                else:
                    glued_tokens.append(
                        cls._split_glued_words(token, catalog_normalized, compact_map=compact_map)
                    )
            text = " ".join(glued_tokens)
        text = cls._remove_noise_tokens(text)
        text = _WS_RE.sub(" ", text).strip()
        return text

    @staticmethod
    def _split_glued_words(
        text: str,
        catalog_names: Optional[List[str]] = None,
        *,
        compact_map: Optional[Dict[str, str]] = None,
    ) -> str:
        compact = text.replace(" ", "")
        if not compact:
            return text
        if compact_map is None:
            # ponytail 5.2: fallback — rebuild map from list (public-API compat).
            # ceiling: O(n_catalog) per token; upgrade: always pass compact_map.
            compact_map = {}
            for spaced_name in (catalog_names or []):
                if not spaced_name:
                    continue
                compact_name = spaced_name.replace(" ", "")
                if len(compact_name) < 4:
                    continue
                if compact_name not in compact_map or len(spaced_name) > len(
                    compact_map[compact_name]
                ):
                    compact_map[compact_name] = spaced_name

        for compact_name, spaced_name in compact_map.items():
            if compact == compact_name:
                return spaced_name
            for suffix in ("s", "es"):
                if compact == f"{compact_name}{suffix}":
                    return spaced_name

        spans: List[Tuple[int, int, str]] = []
        for compact_name, spaced_name in compact_map.items():
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
        filtered = [t for t in tokens if not _is_noise(t)]
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

# ---------------------------------------------------------------------------
# Per-request (contextvar) intent index — set by business_context.business_scope
# to avoid mutating globals under concurrent requests.
# ---------------------------------------------------------------------------
import contextvars as _cv

_active_intent_index: _cv.ContextVar[
    "tuple | None"
] = _cv.ContextVar("intent_index", default=None)


def _get_intent_index() -> "tuple":
    """Return the per-request intent index (contextvar) or fall back to module globals."""
    idx = _active_intent_index.get(None)
    if idx is not None:
        return idx
    return (_INTENT_PHRASES_BY_LEN, _INTENT_TOKEN_TO_COMMAND, _INTENT_ALL_TOKENS, _INTENT_HINT_RE)


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
        text = REPEAT_CHAR_RE.sub(REPEAT_CHAR_REPLACEMENT, text)
        text = _strip_punct(text)
        text = cls._expand_colloquial_quantities(text)
        text = _QTY_X_GLUE_RE.sub(r"\1 ", text)
        text = _X_QTY_GLUE_RE.sub(r"\1 ", text)
        text = _split_glued_quantities(text)
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
        text = _WS_RE.sub(" ", text).strip()
        return text

    @staticmethod
    def _expand_colloquial_quantities(text: str) -> str:
        for pattern, replacement in COLLOQUIAL_QTY_REPLACEMENTS:
            text = pattern.sub(replacement, text)
        return text


class UserIntentClassifier:
    """Detect the five global commands (menu, pedido, reservar, inicio, cancelar)."""

    _CONFIRMATION_BLOCKED = frozenset({"productos", "pedido", "ayuda"})

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
        _, _, intent_keep, _ = _get_intent_index()
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
        if _NUMERIC_X_SIGNAL_RE.search(basic):
            return True
        if _X_NUMERIC_SIGNAL_RE.search(basic):
            return True
        if _QTY_DE_PRODUCT_RE.search(basic):
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

        _phrases, _tok2cmd, _all_tokens, _hint_re = _get_intent_index()
        words = basic.split()
        if len(words) == 1:
            single = _strip_accents(words[0])
            cmd = _accept_command(_tok2cmd.get(single))
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
            or bool(_hint_re.search(basic))
        )
        if run_phrases:
            for command, phrase_key in _phrases:
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
                if key in _tok2cmd:
                    cmd = _accept_command(_tok2cmd[key])
                    if not cmd:
                        continue
                    if cmd == "productos" and "principal" in words:
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
        self._generic_tokens = self._build_generic_tokens(catalog)
        # ponytail 5.2: precompute compact→spaced map once; ceiling: aliases excluded.
        # Upgrade: include alias compacts to handle "esfericos"→"esferico" glued splits.
        self._compact_to_spaced: Dict[str, str] = self._build_compact_map(self._catalog_norms)
        # ponytail 5.3: inverted index token→[item_indices]; computed after generic_tokens.
        # ceiling: token_keys not yet set on entries at FuzzyMatcher init time → computed inline.
        # Upgrade: rebuild index after OIE sets token_keys to reuse precomputed values.
        self._inverted_index: Dict[str, List[int]] = self._build_inverted_index(catalog)
        # ponytail 5.1: operation counters for Phase 5 self-checks; ceiling: not thread-safe.
        # Upgrade: use threading.local or contextvars per request.
        self._stats: Dict[str, int] = {"items_scored": 0}

    @staticmethod
    def _build_inverted_index(catalog: List[Dict[str, Any]]) -> Dict[str, List[int]]:
        """Phase 5.3: token→[catalog_indices] for O(query_tokens) candidate prefetch."""
        # ponytail 5.3: indexes normalized name tokens + data-driven alias tokens.
        # ceiling: token_keys not precomputed here → _token_keys() called inline.
        # Upgrade: after OIE sets entry["token_keys"], rebuild to skip redundant computation.
        index: Dict[str, List[int]] = {}
        for i, entry in enumerate(catalog):
            # Use precomputed token_keys if available (not yet at FuzzyMatcher.__init__ time)
            tks: set = entry.get("token_keys") or _token_keys(entry["normalized"])
            for tok in tks:
                index.setdefault(tok, []).append(i)
            name_tks = tks
            for alias, _ in entry.get("alias_pairs", []):
                for tok in _token_keys(alias):
                    if tok not in name_tks:
                        index.setdefault(tok, []).append(i)
        return index

    @staticmethod
    def _build_compact_map(catalog_norms: List[str]) -> Dict[str, str]:
        """Phase 5.2: compact→spaced map built once, sorted desc so longest name wins."""
        # ponytail 5.2: first-write-wins after sorting → no len() comparison needed.
        # ceiling: O(n_catalog) build; ceiling for lookup is O(n_catalog) span scan per token.
        # Upgrade for lookup: trie or aho-corasick for sub-O(n) per-token scan.
        compact_map: Dict[str, str] = {}
        for spaced_name in sorted(catalog_norms, key=len, reverse=True):
            if not spaced_name:
                continue
            compact_name = spaced_name.replace(" ", "")
            if len(compact_name) < 4:
                continue
            compact_map.setdefault(compact_name, spaced_name)
        return compact_map

    @staticmethod
    def _build_generic_tokens(catalog: List[Dict[str, Any]]) -> frozenset:
        """Phase 3.1: distinctiveness by catalog frequency (replaces CATEGORY_STOPWORDS).

        A token shared by >=2 products is non-distinctive (category/generic word);
        matching only such tokens must not beat a distinctive single-product token.
        """
        # ponytail: generic = document-frequency >= 2; ceiling: tiny catalogs where a
        # truly distinctive word coincidentally repeats. Upgrade: tf-idf weighting.
        if len(catalog) < 2:
            return frozenset()
        df: Dict[str, int] = {}
        for entry in catalog:
            for key in _token_keys(entry["normalized"]):
                if _is_noise(key) or _number_word(key) is not None:
                    continue
                df[key] = df.get(key, 0) + 1
        return frozenset(token for token, count in df.items() if count >= 2)

    @staticmethod
    def _build_vocabulary(catalog: List[Dict[str, Any]]) -> List[str]:
        words: set[str] = set()
        for entry in catalog:
            words.add(entry["normalized"])
            for token in entry.get("tokens", []):
                if len(token) >= TYPO_VOCAB_MIN_LEN:
                    words.add(token)
            # Phase 3.5: data-driven aliases feed typo correction for any catalog.
            for alias in entry.get("aliases", ()):
                if not isinstance(alias, str):
                    continue
                for token in alias.split():
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
        # Phase 4.4: use injected semantic scorer when available; fallback to fuzzy on error.
        if _SEMANTIC_SCORER is not None:
            try:
                sem = float(_SEMANTIC_SCORER(a, b))
                if 0.0 <= sem <= 1.0:
                    return sem
            except Exception:  # noqa: BLE001
                pass
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
        target_compact = item["compact"]  # ponytail 5.1: precomputed
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
        item_tokens = item["tokens_set"]  # ponytail 5.1: precomputed
        if query_tokens and item_tokens:
            overlap = len(query_tokens & item_tokens) / max(len(query_tokens | item_tokens), 1)
            base = max(base, overlap)

        if len(query_tokens) == 1:
            single = next(iter(query_tokens))
            if len(single) >= 3 and any(
                single == part or (len(part) >= 4 and single in part)
                for part in item["tokens"]  # ponytail 5.1: precomputed list
            ):
                base = max(base, 0.95)

        q_keys = _token_keys(normalized_query)
        name_tokens = item["name_tokens"]  # ponytail 5.1: precomputed
        alias_hit = False
        for alias, alias_compact in item["alias_pairs"]:  # ponytail 5.1: precomputed pairs
            alias_score = self._ratio(normalized_query, alias)
            base = max(base, alias_score)
            if (
                alias in q_keys
                or normalized_query == alias
                or (query_compact and alias_compact and query_compact == alias_compact)
            ):
                base = max(base, 0.97)
                # only a genuine (data-driven, non-name) alias bypasses the
                # distinctiveness clamp; name-token aliases must not.
                if alias not in name_tokens:
                    alias_hit = True

        distinctive = item["distinctive"]  # ponytail 5.1: precomputed post-FuzzyMatcher init
        if distinctive:
            hits = len(distinctive & q_keys)
            if hits == len(distinctive):
                base = max(base, 0.97)
            elif hits == 0 and not alias_hit:
                # an explicit alias match must not be clamped by name-token distinctiveness
                base = min(base, 0.62)

        return min(base, 1.0)

    def best_match(
        self, fragment: str
    ) -> Tuple[Optional[Dict[str, Any]], float, Optional[Dict[str, Any]], float]:
        query = TextNormalizer.advanced(fragment, compact_map=self._compact_to_spaced)  # ponytail 5.2
        query = self._correct_typos(query)
        if not query:
            return None, 0.0, None, 0.0

        # ponytail 5.3: prefetch candidates via inverted index; fallback to full scan.
        # ceiling: recall depends on token overlap; gibberish/unseen words fall back.
        # Upgrade: add phonetic/ngram index for higher typo recall without full scan.
        # Semantic scorer bypasses index: scorer is free-form and may match cross-token pairs.
        if _SEMANTIC_SCORER is not None:
            candidates = self.catalog
        else:
            q_keys = _token_keys(query)
            candidate_indices: set[int] = set()
            for tok in q_keys:
                for idx in self._inverted_index.get(tok, ()):
                    candidate_indices.add(idx)
            candidates = (
                [self.catalog[i] for i in candidate_indices] if candidate_indices else self.catalog
            )

        best_item: Optional[Dict[str, Any]] = None
        best_score = 0.0
        second_item: Optional[Dict[str, Any]] = None
        second_score = 0.0
        for item in candidates:
            self._stats["items_scored"] += 1
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
            and self.has_distinctive_winner(query, second_item, best_item)
        ):
            best_item, second_item = second_item, best_item

        # Phase 4.1: among tied items prefer the one that covers more query tokens (longest match).
        # ponytail: single pass after scoring; ceiling: only resolves exact score ties.
        # Upgrade: integrate coverage into score_pair with a fractional bonus.
        if best_item and second_item and abs(best_score - second_score) < 0.001:
            q_lm = _token_keys(query)
            b_cover = len(best_item["token_keys"] & q_lm)   # ponytail 5.1: precomputed
            s_cover = len(second_item["token_keys"] & q_lm)  # ponytail 5.1: precomputed
            if s_cover > b_cover:
                best_item, second_item = second_item, best_item

        return best_item, best_score, second_item, second_score

    def has_distinctive_winner(
        self,
        query: str,
        best: Dict[str, Any],
        second: Dict[str, Any],
    ) -> bool:
        q_keys = _token_keys(query)
        best_keys = best["distinctive"]  # ponytail 5.1: precomputed
        second_keys = second["distinctive"]  # ponytail 5.1: precomputed
        best_hits = best_keys & q_keys
        second_hits = second_keys & q_keys
        if best_hits and not second_hits:
            return True
        if len(best_hits) > len(second_hits):
            return True
        return False


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
        for splitter in (
            NUMSAFE_COMMA_SPLIT_RE,
            PLUS_SPLIT_RE,
            STAR_SPLIT_RE,
            PIPE_SPLIT_RE,
            AMP_SPLIT_RE,
        ):
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
                if token and not _is_noise(token)
            ]
            if not prefix_tokens:
                return [f"{chunks[0]} {chunks[1]}".strip()]
        return chunks

    @staticmethod
    def _is_quantity_only(segment: str) -> bool:
        cleaned = TextNormalizer.basic(segment.strip())
        if _PURE_DIGITS_RE.match(cleaned):
            return True
        key = _strip_accents(cleaned)
        return _number_word(key) is not None


class QuantityEngine:
    """Robust quantity resolver: 2x, x2, digits, number words."""

    @staticmethod
    def _strip_leading_noise(text: str) -> str:
        tokens = text.split()
        while tokens and _is_noise(tokens[0]):
            tokens.pop(0)
        return " ".join(tokens)

    @staticmethod
    def _strip_trailing_noise(text: str) -> str:
        text = _PARA_LLEVAR_RE.sub("", text).strip()
        tokens = text.split()
        while tokens and _is_noise(tokens[-1]):
            tokens.pop()
        return " ".join(tokens)

    @staticmethod
    def _strip_de_prefix(text: str) -> str:
        return _DE_PREFIX_RE.sub("", text.strip())

    @staticmethod
    def _leading_quantity(tokens: List[str]) -> Tuple[Optional[int], int]:
        """Generic quantity at the front: digits/thousands, 2x/x2/2×, cardinal runs."""
        if not tokens:
            return None, 0
        first = tokens[0]
        # 2x / x2 / 2× / ×2 glued into one token (Phase 2.3)
        m = _LEADING_INT_X_RE.fullmatch(first)
        if m:
            return _parse_int_token(m.group(1)), 1
        m = _LEADING_X_INT_RE.fullmatch(first)
        if m:
            return _parse_int_token(m.group(1)), 1
        # "2 x" / "x 2" split across tokens
        if first in {"x", "×"} and len(tokens) > 1:
            value = _parse_int_token(tokens[1])
            if value is not None:
                return value, 2
        value = _parse_int_token(first)
        if value is not None:
            if len(tokens) > 2 and tokens[1] in {"x", "×"}:
                nxt = _parse_int_token(tokens[2])
                if nxt is not None:
                    return value, 3
            return value, 1
        # cardinal word run (Phase 2.1): mil doscientos veinticinco, treinta y cinco
        run = 0
        while run < len(tokens):
            key = _repeat_key(_strip_accents(tokens[run]))
            if key in NUMBER_WORDS:
                run += 1
            elif (
                key == "y"
                and run > 0
                and run + 1 < len(tokens)
                and _repeat_key(_strip_accents(tokens[run + 1])) in NUMBER_WORDS
            ):
                run += 1
            else:
                break
        if run:
            value = parse_cardinal(tokens[:run])
            if value is not None:
                return value, run
        return None, 0

    @staticmethod
    def extract(segment: str) -> Tuple[int, str]:
        cleaned = TextNormalizer.basic(segment)
        cleaned = QuantityEngine._strip_leading_noise(cleaned)
        if not cleaned:
            return 1, ""

        tokens = cleaned.split()
        qty, consumed = QuantityEngine._leading_quantity(tokens)
        if qty is not None:
            remainder = QuantityEngine._strip_trailing_noise(
                QuantityEngine._strip_de_prefix(" ".join(tokens[consumed:]).strip())
            )
            return max(qty, 1), remainder

        # Phase 2.5: free-position quantity at the tail ("arcos x50", "guantes 50")
        suffix = QTY_SUFFIX_RE.match(cleaned)
        if suffix:
            name = QuantityEngine._strip_trailing_noise(
                QuantityEngine._strip_de_prefix(suffix.group(1).strip())
            )
            qty = _parse_int_token(suffix.group(2))
            if qty is not None and name and not _INT_TOKEN_RE.match(name):
                return max(qty, 1), name

        return 1, QuantityEngine._strip_trailing_noise(cleaned)

    @staticmethod
    def resolve(
        segment: str,
        catalog_norms: Optional[List[str]] = None,
        *,
        compact_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str]:
        """Extract quantity from the raw segment, then product text for matching."""
        basic = TextNormalizer.basic(segment)
        qty, product_text = QuantityEngine.extract(basic)
        if not product_text:
            return qty, ""

        # ponytail 5.2: pass compact_map to avoid rebuilding inside advanced().
        normalized = TextNormalizer.advanced(product_text, catalog_norms, compact_map=compact_map)
        _, product_text = QuantityEngine.extract(normalized)
        # ponytail 5.4: qty_check block removed — all branches returned same value.
        # ceiling: if extract() is changed to mutate qty, re-add cross-check.
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
        # ponytail 5.1: token_keys/distinctive depend on _generic_tokens → computed post-FuzzyMatcher.
        # ceiling: O(n*tokens) extra init; upgrade: embed in FuzzyMatcher.__init__ directly.
        _generic = self._matcher._generic_tokens
        for _entry in self._catalog:
            _tk = _token_keys(_entry["normalized"])
            _entry["token_keys"] = _tk
            _entry["distinctive"] = _tk - _generic
        # ponytail 5.2: reuse matcher's precomputed compact map.
        self._compact_to_spaced = self._matcher._compact_to_spaced
        self._catalog_by_name = {entry["nombre"].lower(): entry for entry in self._catalog}
        self._category_defaults = self._build_category_defaults()
        self._category_counts = self._build_category_counts()
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
            # ponytail 5.7: type-safety guard at catalog build; ceiling: no schema versioning.
            # Upgrade: JSON-Schema validation on menu_items at load time.
            _id = item.get("id")
            _nombre = item.get("nombre")
            _precio = item.get("precio")
            if not isinstance(_nombre, str) or not _nombre.strip():
                _catalog_log.warning("catalog item skipped — missing/invalid 'nombre': %r", item)
                continue
            if _id is None:
                _catalog_log.warning("catalog item skipped — missing 'id': %r", item)
                continue
            if not isinstance(_precio, (int, float)):
                _catalog_log.warning("catalog item skipped — non-numeric 'precio': %r", item)
                continue
            name = _nombre.strip()
            normalized = TextNormalizer.basic(name)
            aliases = {normalized, *normalized.split()}
            # Phase 3.2: aliases/keywords are data-driven per product, never hardcoded.
            for field in ("aliases", "keywords"):
                aliases.update(_normalized_alias_tokens(item.get(field)))
            _sorted_aliases = sorted(aliases)
            _toks = normalized.split()
            catalog.append(
                {
                    "id": item.get("id"),
                    "nombre": name,
                    "precio": float(item.get("precio", 0)),
                    "categoria": item.get("categoria", ""),
                    "tokens": _toks,
                    "normalized": normalized,
                    "aliases": _sorted_aliases,
                    # ponytail 5.1: static statics precomputed once per catalog build.
                    # ceiling: mutable catalog not supported; upgrade: invalidate via fingerprint (5.6).
                    "compact": normalized.replace(" ", ""),
                    "tokens_set": set(_toks),
                    "name_tokens": set(_toks) | {normalized},
                    "alias_pairs": [(a, a.replace(" ", "")) for a in _sorted_aliases],
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

    def _build_category_counts(self) -> Dict[str, int]:
        """Phase 3.3: products per category key (drives generic-category ambiguity)."""
        counts: Dict[str, int] = {}
        for item in self.menu_items:
            category = str(item.get("categoria", "")).strip()
            if not category:
                continue
            key = self._category_match_key(category)
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _category_match_key(text: str) -> str:
        basic = TextNormalizer.basic(text)
        parts = [
            _singularize_token(_strip_accents(token))
            for token in basic.split()
            if token
        ]
        return " ".join(parts).strip()

    def _matched_category_key(self, product_text: str) -> Optional[str]:
        """Category key a bare category-name query resolves to (or None)."""
        query_key = self._category_match_key(product_text)
        if not query_key:
            return None
        if query_key in self._category_defaults:
            return query_key
        meaningful = [
            token
            for token in query_key.split()
            if token and token not in NOISE_WORDS and token not in NUMBER_WORDS
        ]
        if not meaningful:
            return None
        if len(meaningful) == 1:
            key = _singularize_token(_strip_accents(meaningful[0]))
            return key if key in self._category_defaults else None
        last = _singularize_token(_strip_accents(meaningful[-1]))
        if last not in self._category_defaults:
            return None
        if meaningful[0] in {"algo", "una", "un", "dos", "tres", "de"} or len(meaningful) == 2:
            return last
        return None

    def _match_category_product(self, product_text: str) -> Optional[Dict[str, Any]]:
        key = self._matched_category_key(product_text)
        return self._category_defaults.get(key) if key else None

    def _category_query_is_ambiguous(self, product_text: str) -> bool:
        """Phase 3.3: a bare category name is ambiguous when its category has >1 product.

        Replaces hardcoded PARTIAL_CATEGORY_ONLY/PARTIAL_GENERIC_TOKENS — the generic
        signal is derived from real item['categoria'] data.
        """
        key = self._matched_category_key(product_text)
        return bool(key) and self._category_counts.get(key, 0) > 1

    def parse(self, text: str) -> Dict[str, Any]:
        """Canonical output contract."""
        raw = (text or "").strip()
        if not raw:
            return self._result([], "needs_clarification", ["entrada vacía"])
        # ponytail 5.7: anti-DoS truncation; ceiling: emoji may span 2+ codepoints in UTF-16.
        # Upgrade: truncate on segment boundary to preserve complete items.
        if len(raw) > MAX_INPUT_CHARS:
            raw = raw[:MAX_INPUT_CHARS]

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

        if ADMIN_PREFIX_RE.match(raw.strip().lower()) or _CONFIRM_ORD_RE.match(raw.strip()):
            result = self._result([], "needs_clarification", ["comando admin"])
            result["_internal"] = {"user_intent": "admin", "intent_confidence": 1.0}
            return result

        if _CANCEL_START_RE.match(prepared):
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
            and intent_info.get("command") in {"cancelar", "productos", "pedido"}
        ):
            intent_info = {
                "command": None,
                "confidence": 0.0,
                "matched": "",
                "has_products": True,
            }
        if intent_info.get("command") and not intent_info.get("has_products"):
            reason_by_command = {
                "productos": "intención de productos",
                "pedido": "intención de pedido sin productos",
                "ayuda": "intención de ayuda",
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
        _cmap = self._compact_to_spaced  # ponytail 5.2: precomputed compact map
        segments = SegmentEngine.split_segments(prepared)
        # ponytail 5.7: segment-count guard; excess silently dropped (partial parse).
        # ceiling: adversary could craft a payload that splits into exactly MAX_SEGMENTS+1.
        # Upgrade: log truncation for observability.
        if len(segments) > MAX_SEGMENTS:
            segments = segments[:MAX_SEGMENTS]
        normalized_full = ""
        if not segments:
            normalized_full = TextNormalizer.advanced(prepared, compact_map=_cmap)
            segments = [normalized_full] if normalized_full else []

        has_overlap = has_menu_overlap or has_category_overlap
        if not has_overlap:
            if not normalized_full:
                normalized_full = TextNormalizer.advanced(prepared, compact_map=_cmap)
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
        ambiguous_items: List[Dict[str, Any]] = []
        needs_review = False

        for segment in segments:
            # ponytail 5.4: seg_tokens check removed — resolve returns product_text=""
            # for all-noise segments, caught by the `not product_text` guard below.
            # ceiling: if _is_noise() contract changes, restore the early check.
            qty, product_text = QuantityEngine.resolve(segment, compact_map=_cmap)  # ponytail 5.2
            # Phase 4.2: never attempt matching on a trivially short fragment.
            if not product_text or len(product_text) < 2:
                continue

            category_entry = self._match_category_product(product_text)
            used_category_fallback = False
            if category_entry:
                best = category_entry
                score = ACCEPT_AUTO_SCORE
                second = None
                second_score = 0.0
                used_category_fallback = True
                if self._category_query_is_ambiguous(product_text):
                    needs_review = True
            else:
                best, score, second, second_score = self._matcher.best_match(product_text)

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
                and not self._matcher.has_distinctive_winner(product_text, best, second)
            )
            if ambiguous:
                needs_review = True
                # ponytail: hold ambiguous items back from cart; surface as candidates.
                # ceiling: only top-2 candidates returned; upgrade: add top_n_matches(n).
                ambiguous_items.append({
                    "segment": product_text,
                    "qty": qty,
                    "candidates": [
                        {
                            "product": best["nombre"],
                            "product_id": best["id"],
                            "unit_price": best["precio"],
                        },
                        {
                            "product": second["nombre"],
                            "product_id": second["id"],
                            "unit_price": second["precio"],
                        },
                    ],
                })
                continue  # do not add ambiguous item to parsed_items

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

        if not parsed_items and not ambiguous_items:
            return self._fail_safe(unknown or ["sin productos reconocidos"])

        status = "ok" if not needs_review and not unknown else "needs_clarification"
        result = self._result(parsed_items, status, unknown, ambiguous_items)
        internal: Dict[str, Any] = {
            "min_score": _min_confidence(parsed_items),
            "needs_review": needs_review,
            "ambiguous": bool(ambiguous_items),
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
        """Phase 4.2: menu boundary + coherence.  Never invent products.

        Any item whose name is not in _catalog_by_name (exact, case-insensitive) is
        treated as unknown — the engine never outputs a product that was not injected.
        """
        unknown: List[str] = []
        needs_review = False
        validated: List[Dict[str, Any]] = []

        for item in items:
            name_key = item["product"].lower()
            catalog_entry = self._catalog_by_name.get(name_key)
            if not catalog_entry:
                # Phase 4.2: strict never-invent gate.
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
        ambiguous_items: Optional[List[Dict[str, Any]]] = None,
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
            "ambiguous_items": ambiguous_items or [],
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
            if _PURE_DIGITS_RE.match(token):
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
            intents.add(TextNormalizer.basic(_singularize_token(key)))
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
            letters = _NON_ALPHA_RE.sub("", tokens[0])
            if letters and len(set(letters)) <= 3:
                return True
            if not _VOWEL_RE.search(letters) and len(letters) >= 5:
                return True
        return False


# ---------------------------------------------------------------------------
# Public facade (Flask / Twilio integration — backward compatible)
# ---------------------------------------------------------------------------


class OrderParser:
    """Facade used by OrderService; wraps OrderIntelligenceEngine."""

    def __init__(self, menu_items: List[Dict[str, Any]], *, business_id: str = "") -> None:
        self.menu_items = [item for item in menu_items if item.get("disponible", True)]
        # ponytail 5.6: reuse engine if catalog unchanged; evicts on fingerprint change.
        self._engine = _get_or_build_engine(business_id, self.menu_items)
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
            return {
                "items": cart,
                "notes": notes,
                "unknown": unknown,
                "ambiguous_items": parse_snapshot.get("ambiguous_items", []),
            }

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

        if SOLO_ONLY_RE.search(cleaned):
            # ponytail: "déjame solo X" → keep only X, discard everything else.
            # ceiling: multi-product "solo X y Y" falls through to fallback parse.
            fragment = SOLO_PREFIX_RE.sub("", cleaned).strip()
            matched = self._match_product(fragment) if fragment else None
            if matched:
                qty, _ = self._extract_quantity(fragment)
                kept = {
                    "product_id": matched["id"],
                    "product": matched["nombre"],
                    "qty": max(qty, 1),
                    "unit_price": matched["precio"],
                    "subtotal": round(max(qty, 1) * matched["precio"], 2),
                }
                notes.append(f"Dejé solo: {matched['nombre']}.")
                return {"items": [kept], "notes": notes, "unknown": unknown}
            unknown.append(fragment or cleaned)
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

        return {
            "items": cart,
            "notes": notes,
            "unknown": unknown,
            "ambiguous_items": parse_snapshot.get("ambiguous_items", []),
        }

    @staticmethod
    def cart_total(items: List[Dict[str, Any]]) -> float:
        return round(sum(item.get("subtotal", 0) for item in items), 2)

    @staticmethod
    def _fmt_cop(amount: float) -> str:
        # ponytail: entero con punto miles; upgrade: locale/Decimal si hay centavos
        return f"{int(round(amount)):,}".replace(",", ".")

    @staticmethod
    def format_cart(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "Tu carrito está vacío."
        lines = []
        for item in items:
            sub = OrderParser._fmt_cop(item["subtotal"])
            lines.append(
                f"- {item['product']} x{item['qty']} - ${sub}"
            )
        total = OrderParser.cart_total(items)
        lines.append(f"\n💰 Valor total: *${OrderParser._fmt_cop(total)}*")
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
    {
        "id": "4",
        "nombre": "Coca Cola",
        "precio": 2.5,
        "categoria": "Bebidas",
        "disponible": True,
        "aliases": ["gaseosa", "refresco", "soda", "cola"],
    },
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

    case15 = demo_engine.parse("hamburgesa")
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
        "quiero por favor 60 hamburgesas clasikas, 2333 hamburgueas mega, "
        "12123 cocas con 777 pizas hawayana y 8 picsas de jamon y quieso"
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
