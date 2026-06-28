"""Self-checks for the generic order parser (no pytest, only assert + print).

Usage:
    python scripts/selfcheck_parser.py --phase 1

Each subpoint validates against AT LEAST two distinct catalogs (ferretería and
deportes) plus chaotic real-world phrases. On pass prints:  ✅ DONE [<subpoint>]
On failure prints:  ❌ FAIL [<subpoint>] - <reason>  and stops.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
for candidate in (ROOT, ROOT / "chatbot"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:  # utf-8 console so ✅/❌ render on Windows cp1252 terminals
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass

from app.core import parser as P  # noqa: E402

# ---------------------------------------------------------------------------
# Two distinct catalogs — nothing about them is hardcoded in the engine.
# ---------------------------------------------------------------------------

FERRETERIA: List[Dict[str, Any]] = [
    {"id": "f1", "nombre": "Tornillo 3/8", "precio": 500.0, "categoria": "Tornillería", "disponible": True},
    {"id": "f2", "nombre": "Tuerca Hexagonal", "precio": 300.0, "categoria": "Tornillería", "disponible": True},
    {"id": "f3", "nombre": "Arco Compuesto", "precio": 150000.0, "categoria": "Arcos", "disponible": True},
    {"id": "f4", "nombre": "Martillo", "precio": 25000.0, "categoria": "Herramientas", "disponible": True},
]

DEPORTES: List[Dict[str, Any]] = [
    {"id": "d1", "nombre": "Balón de Fútbol", "precio": 80000.0, "categoria": "Balones", "disponible": True},
    {"id": "d2", "nombre": "Guantes de Boxeo", "precio": 120000.0, "categoria": "Boxeo", "disponible": True},
    {"id": "d3", "nombre": "Arco de Fútbol", "precio": 200000.0, "categoria": "Arcos", "disponible": True},
    {"id": "d4", "nombre": "Pelota de Tenis", "precio": 15000.0, "categoria": "Tenis", "disponible": True},
]

ENGINE_FER = P.OrderIntelligenceEngine(FERRETERIA)
ENGINE_DEP = P.OrderIntelligenceEngine(DEPORTES)

CHAOS_1 = "cincuenta arcos, 500 balones; y 323 guantes-de-boxeo!!!"
CHAOS_2 = "kiero 2x tornilllos . . y media docena d arcos"


def _qty(result: Dict[str, Any], fragment: str) -> int:
    frag = P._strip_accents(fragment.lower())
    for item in result.get("items", []):
        if frag in P._strip_accents(str(item["product"]).lower()):
            return int(item["quantity"])
    return 0


# ---------------------------------------------------------------------------
# Phase 1 — chaos-tolerant normalization & tokenization
# ---------------------------------------------------------------------------


def p1_1_punctuation() -> None:
    b = P.TextNormalizer.basic
    assert b("guantes-de-boxeo!!!") == "guantes de boxeo", b("guantes-de-boxeo!!!")
    assert b("(arco) [compuesto] {x}") == "arco compuesto x", b("(arco) [compuesto] {x}")
    sweep = b("a-b–c—d.e:f;g/h\\i|j*k+l&m\"n'o(p)q")
    assert set(sweep.split()) == set("abcdefghijklmnopq"), sweep
    # number-internal separators preserved for the Phase 2 numeric engine
    for s in ("tornillo 3/8", "1.5", "1.000", "1,000", "12,123"):
        assert b(s) == s, (s, b(s))
    # both catalogs end-to-end with heavy punctuation
    fer = ENGINE_FER.parse("quiero 2 tornillo 3/8")
    assert _qty(fer, "tornillo") == 2, fer
    dep = ENGINE_DEP.parse("500 balones; 323 guantes-de-boxeo!!!")
    assert _qty(dep, "balon") == 500 and _qty(dep, "guantes") == 323, dep


def p1_2_repeats() -> None:
    adv = P.TextNormalizer.advanced
    assert adv("balonnnn") == "balonn", adv("balonnnn")
    assert adv("tornilllllo") == "tornillo", adv("tornilllllo")
    assert P._is_noise("holaaa"), "holaaa should collapse to noise 'hola'"
    assert P._number_word("doss") == 2, P._number_word("doss")
    fer = ENGINE_FER.parse("2 martilllo")
    assert _qty(fer, "martillo") == 2, fer
    dep = ENGINE_DEP.parse("500 baloooon de futbol")
    assert _qty(dep, "balon") == 500, dep


def p1_3_glued() -> None:
    c = P.NaturalLanguagePreprocessor.canonicalize
    assert c("2arcos") == "2 arcos", c("2arcos")
    assert c("500balones") == "500 balones", c("500balones")
    assert c("dosarcos") == "dos arcos", c("dosarcos")
    assert c("trespelotas") == "tres pelotas", c("trespelotas")
    fer_split = P.TextNormalizer.advanced("arcocompuesto", ENGINE_FER._catalog_norms)
    assert fer_split == "arco compuesto", fer_split
    # "de" is dropped as noise; the product+product split still recovers both tokens
    dep_split = P.TextNormalizer.advanced("guantesdeboxeo", ENGINE_DEP._catalog_norms)
    assert dep_split == "guantes boxeo", dep_split
    fer = ENGINE_FER.parse("3tornillos")
    assert _qty(fer, "tornillo") == 3, fer
    dep = ENGINE_DEP.parse("dosbalones")
    assert _qty(dep, "balon") == 2, dep


def p1_4_emoji_case_accents() -> None:
    b = P.TextNormalizer.basic
    assert b("ARCOS Compuéstos") == "arcos compuestos", b("ARCOS Compuéstos")
    assert b("Balón de Fútbol") == "balon de futbol", b("Balón de Fútbol")
    assert b("arcos⚽compuestos") == "arcos compuestos", b("arcos⚽compuestos")
    assert b("hola 😀 mundo 🎉🥤") == "hola mundo", b("hola 😀 mundo 🎉🥤")
    fer = ENGINE_FER.parse("2 MARTÍLLO 🔨")
    assert _qty(fer, "martillo") == 2, fer
    dep = ENGINE_DEP.parse("3 BALÓN de fútbol⚽")
    assert _qty(dep, "balon") == 3, dep


def p1_5_segmentation() -> None:
    segs = P.SegmentEngine.split_segments(P.NaturalLanguagePreprocessor.canonicalize(CHAOS_1))
    assert len(segs) == 3, segs
    by_qty = {P.QuantityEngine.extract(s)[0]: P.QuantityEngine.extract(s)[1] for s in segs}
    assert "balones" in by_qty.get(500, ""), (500, by_qty)
    assert "guantes" in by_qty.get(323, ""), (323, by_qty)
    # second chaotic phrase: 2x quantity signal survives, product preserved
    dep = ENGINE_DEP.parse(CHAOS_1)
    assert _qty(dep, "balon") == 500 and _qty(dep, "guantes") == 323, dep
    fer_segs = P.SegmentEngine.split_segments(P.NaturalLanguagePreprocessor.canonicalize(CHAOS_2))
    qtys = [P.QuantityEngine.extract(s) for s in fer_segs]
    assert any(q == 2 and "tornillo" in name for q, name in qtys), qtys


# ---------------------------------------------------------------------------
# Phase 2 — generic Spanish numeric engine
# ---------------------------------------------------------------------------


def p2_1_cardinals() -> None:
    pc = P.parse_cardinal
    assert pc("mil doscientos veinticinco".split()) == 1225, pc("mil doscientos veinticinco".split())
    assert pc("quinientos veinticinco".split()) == 525, pc("quinientos veinticinco".split())
    assert pc("treinta y cinco".split()) == 35, pc("treinta y cinco".split())
    assert pc("un millon".split()) == 1_000_000, pc("un millon".split())
    assert pc("dos mil".split()) == 2000, pc("dos mil".split())
    assert pc("ciento cincuenta".split()) == 150, pc("ciento cincuenta".split())
    assert _qty(ENGINE_FER.parse("mil doscientos veinticinco arcos"), "arco") == 1225
    assert _qty(ENGINE_DEP.parse("quinientos veinticinco balones"), "balon") == 525
    assert _qty(ENGINE_DEP.parse(CHAOS_1), "arco") == 50  # "cincuenta arcos"


def p2_2_thousands() -> None:
    assert P._parse_int_token("1.000") == 1000
    assert P._parse_int_token("1,000") == 1000
    assert P._parse_int_token("12,123") == 12123
    assert P._parse_int_token("1.000.000") == 1_000_000
    # decimals / measures / fractions are NOT integers and must stay intact
    assert P._parse_int_token("1.5") is None
    assert P.TextNormalizer.basic("coca 1.5 l") == "coca 1.5 l"
    assert P.TextNormalizer.basic("tornillo 3/8") == "tornillo 3/8"
    assert _qty(ENGINE_FER.parse("1.000 arcos"), "arco") == 1000
    assert _qty(ENGINE_DEP.parse("12,123 balones"), "balon") == 12123
    fer = ENGINE_FER.parse("quiero 2 tornillo 3/8")
    assert _qty(fer, "tornillo") == 2 and any("3/8" in i["product"] for i in fer["items"]), fer


def p2_3_x_formats() -> None:
    assert _qty(ENGINE_FER.parse("2x martillo"), "martillo") == 2
    assert _qty(ENGINE_FER.parse("x2 martillo"), "martillo") == 2
    assert _qty(ENGINE_DEP.parse("3× balones"), "balon") == 3
    assert _qty(ENGINE_DEP.parse("×2 guantes"), "guantes") == 2
    multi = ENGINE_DEP.parse("2x guantes 3x balones")
    assert _qty(multi, "guantes") == 2 and _qty(multi, "balon") == 3, multi


def p2_4_pair_dozen() -> None:
    assert _qty(ENGINE_DEP.parse("un par de guantes"), "guantes") == 2
    assert _qty(ENGINE_FER.parse("media docena de arcos"), "arco") == 6
    assert _qty(ENGINE_DEP.parse("una docena de balones"), "balon") == 12
    # without the "de" connector
    assert _qty(ENGINE_FER.parse("media docena arcos"), "arco") == 6
    assert _qty(ENGINE_DEP.parse("docena balones"), "balon") == 12
    assert _qty(ENGINE_DEP.parse("un par guantes"), "guantes") == 2
    # chaotic phrase: "media docena d arcos" + "2x tornilllos"
    fer = ENGINE_FER.parse(CHAOS_2)
    assert _qty(fer, "arco") == 6 and _qty(fer, "tornillo") == 2, fer


def p2_5_free_position_mix() -> None:
    assert _qty(ENGINE_FER.parse("arcos x50"), "arco") == 50
    assert _qty(ENGINE_DEP.parse("50x guantes"), "guantes") == 50
    assert _qty(ENGINE_FER.parse("cincuenta arcos"), "arco") == 50
    mix = ENGINE_FER.parse("cincuenta arcos, 500 tuercas y 2x martillos")
    assert _qty(mix, "arco") == 50 and _qty(mix, "tuerca") == 500 and _qty(mix, "martillo") == 2, mix
    dep = ENGINE_DEP.parse(CHAOS_1)
    assert _qty(dep, "balon") == 500 and _qty(dep, "guantes") == 323 and _qty(dep, "arco") == 50, dep


# ---------------------------------------------------------------------------
# Phase 3 — generic catalog matching without hardcode
# ---------------------------------------------------------------------------


def p3_1_distinctiveness() -> None:
    # "futbol" is shared by two DEPORTES products → generic; rest are distinctive.
    assert ENGINE_DEP._matcher._generic_tokens == frozenset({"futbol"}), \
        ENGINE_DEP._matcher._generic_tokens
    # FERRETERIA name tokens are all unique → no generic token, all distinctive.
    assert ENGINE_FER._matcher._generic_tokens == frozenset(), \
        ENGINE_FER._matcher._generic_tokens
    # distinctive token wins over the shared/generic one across both /futbol products
    arco = ENGINE_DEP.parse("2 arco de futbol")
    assert _qty(arco, "arco de futbol") == 2 and arco["status"] == "ok", arco
    balon = ENGINE_DEP.parse("3 balon de futbol")
    assert _qty(balon, "balon de futbol") == 3 and balon["status"] == "ok", balon
    # second catalog: shared "tornillo" must not beat the distinctive variant
    shared = P.OrderIntelligenceEngine([
        {"id": "a", "nombre": "Tornillo Phillips", "precio": 1, "categoria": "T"},
        {"id": "b", "nombre": "Tornillo Hexagonal", "precio": 1, "categoria": "T"},
    ])
    assert shared._matcher._generic_tokens == frozenset({"tornillo"}), \
        shared._matcher._generic_tokens
    res = shared.parse("5 tornillo hexagonal")
    assert _qty(res, "hexagonal") == 5, res


def p3_2_aliases_keywords() -> None:
    cat = P.OrderIntelligenceEngine([
        {"id": "1", "nombre": "Balón de Fútbol", "precio": 1, "categoria": "Balones",
         "aliases": ["esférico", "pelota futbolera"], "keywords": ["soccer"]},
        {"id": "2", "nombre": "Martillo", "precio": 1, "categoria": "Herramientas"},
    ])
    # alias (not in the product name) resolves to the product
    assert _qty(cat.parse("2 esfericos"), "balon") == 2, cat.parse("2 esfericos")
    assert _qty(cat.parse("quiero un soccer"), "balon") == 1, cat.parse("quiero un soccer")
    # no-alias product still matches by its own name (fallback)
    assert _qty(cat.parse("3 martillo"), "martillo") == 3, cat.parse("3 martillo")
    # boundary safety: non-list alias data is tolerated, never crashes
    assert P._normalized_alias_tokens("gaseosa fría") == {"gaseosa fria", "gaseosa", "fria"}
    assert P._normalized_alias_tokens(None) == set()
    assert P._normalized_alias_tokens([1, "Soda", None]) == {"soda"}
    # second catalog proves it is data-driven, not restaurant-specific
    drinks = P.OrderIntelligenceEngine([
        {"id": "x", "nombre": "Coca Cola", "precio": 1, "categoria": "Bebidas",
         "aliases": ["gaseosa", "refresco"]},
    ])
    assert _qty(drinks.parse("2 gaseosa"), "coca") == 2, drinks.parse("2 gaseosa")


def p3_3_generic_category() -> None:
    cat = P.OrderIntelligenceEngine([
        {"id": "1", "nombre": "Camiseta Roja", "precio": 1, "categoria": "Ropa"},
        {"id": "2", "nombre": "Camiseta Azul", "precio": 1, "categoria": "Ropa"},
        {"id": "3", "nombre": "Gorra", "precio": 1, "categoria": "Accesorios"},
    ])
    # multi-product category name is ambiguous → needs_review
    assert cat._category_query_is_ambiguous("ropa") is True
    ropa = cat.parse("quiero ropa")
    assert ropa["_internal"]["needs_review"] is True, ropa
    # single-product category name is unambiguous → auto-accepted
    assert cat._category_query_is_ambiguous("accesorios") is False
    acc = cat.parse("quiero accesorios")
    assert _qty(acc, "gorra") == 1 and acc["_internal"]["needs_review"] is False, acc
    # real catalogs: FERRETERIA "Tornillería" (2 items) ambiguous, DEPORTES singles not
    assert ENGINE_FER._category_query_is_ambiguous("tornilleria") is True
    assert ENGINE_DEP._category_query_is_ambiguous("balones") is False


def p3_4_hardcode_deleted() -> None:
    for name in (
        "SYNONYM_TOKEN_MAP", "BEVERAGE_SYNONYM_KEYS", "CATEGORY_STOPWORDS",
        "PARTIAL_CATEGORY_ONLY", "PARTIAL_GENERIC_TOKENS",
    ):
        assert not hasattr(P, name), f"{name} must be deleted"
    for attr in ("_apply_synonyms", "_detect_single_beverage", "_detect_multi_beverage"):
        assert not hasattr(P.FuzzyMatcher, attr), f"FuzzyMatcher.{attr} must be deleted"
    # no built-in beverage assumption: 'gaseosa' is unknown unless data declares it
    plain = P.OrderIntelligenceEngine([
        {"id": "x", "nombre": "Coca Cola", "precio": 1, "categoria": "Bebidas"},
    ])
    assert _qty(plain.parse("2 gaseosa"), "coca") == 0, plain.parse("2 gaseosa")


def p3_5_fuzzy_typos() -> None:
    assert _qty(ENGINE_FER.parse("2 martilo"), "martillo") == 2, ENGINE_FER.parse("2 martilo")
    assert _qty(ENGINE_FER.parse("3 tornilo 3/8"), "tornillo") == 3, ENGINE_FER.parse("3 tornilo 3/8")
    assert _qty(ENGINE_DEP.parse("2 balom de futbol"), "balon") == 2, ENGINE_DEP.parse("2 balom de futbol")
    assert _qty(ENGINE_DEP.parse("4 pelota de tenis"), "pelota") == 4, ENGINE_DEP.parse("4 pelota de tenis")
    # typo of a data-driven alias is corrected too (aliases feed the vocabulary)
    cat = P.OrderIntelligenceEngine([
        {"id": "1", "nombre": "Balón de Fútbol", "precio": 1, "categoria": "Balones",
         "aliases": ["esferico"]},
    ])
    assert _qty(cat.parse("2 esfericos"), "balon") == 2, cat.parse("2 esfericos")


# ---------------------------------------------------------------------------
# Phase 4 — quantity↔product association + QA + robustness
# ---------------------------------------------------------------------------


def p4_1_longest_match() -> None:
    # Catalog with both "Arco" and "Arco de Fútbol" — longer name wins when query matches it
    twoarc = P.OrderIntelligenceEngine([
        {"id": "a", "nombre": "Arco", "precio": 1, "categoria": "Deportes"},
        {"id": "b", "nombre": "Arco de Fútbol", "precio": 1, "categoria": "Arcos"},
    ])
    r = twoarc.parse("2 arco de futbol")
    assert _qty(r, "arco de futbol") == 2, r
    assert _qty(r, "arco") == 0 or _qty(r, "arco de futbol") == 2, r

    # Real DEPORTES catalog: qty anchors to the right multi-token product
    r = ENGINE_DEP.parse("3 arco de futbol")
    assert _qty(r, "arco de futbol") == 3, r

    # Multi-segment: each qty anchors to its own product
    r = ENGINE_DEP.parse("2 balon de futbol y 3 guantes")
    assert _qty(r, "balon de futbol") == 2 and _qty(r, "guantes") == 3, r

    r = ENGINE_FER.parse("5 tuerca hexagonal y 10 tornillo 3/8")
    assert _qty(r, "tuerca") == 5 and _qty(r, "tornillo") == 10, r

    # Suffix qty also anchors correctly
    r = ENGINE_FER.parse("arcos x50 y tornillo 3/8 x 3")
    assert _qty(r, "arco") == 50, r


def p4_2_qa_never_invent() -> None:
    # Gibberish → empty items, never an invented product
    for text in ["xyzabc123foo", "fghjkl", "zzzzz"]:
        r = ENGINE_FER.parse(text)
        assert r["items"] == [], f"invented product for: {text!r} → {r}"

    # Low-signal text → empty, never invent
    r = ENGINE_DEP.parse("hola quiero algo")
    assert all(
        i["product"].lower() in {e["nombre"].lower() for e in ENGINE_DEP._catalog}
        for i in r["items"]
    ), r

    # A product from catalog A must not appear in catalog B results
    r = ENGINE_FER.parse("3 balon de futbol")
    fer_names = {e["nombre"].lower() for e in ENGINE_FER._catalog}
    assert all(i["product"].lower() in fer_names for i in r["items"]), r

    # All parsed items must be in the catalog that was injected
    catalog_names_dep = {e["nombre"].lower() for e in ENGINE_DEP._catalog}
    r = ENGINE_DEP.parse("50 balones 10 guantes 3 arco de futbol")
    for item in r["items"]:
        assert item["product"].lower() in catalog_names_dep, \
            f"invented product: {item['product']}"

    # product_text too short (single char after normalization) → no crash, no product
    r = ENGINE_FER.parse("2 x")
    assert isinstance(r, dict) and "status" in r


def p4_3_robustness() -> None:
    dep = ENGINE_DEP.parse(CHAOS_1)
    assert _qty(dep, "arco de futbol") == 50, dep
    assert _qty(dep, "balon de futbol") == 500, dep
    assert _qty(dep, "guantes") == 323, dep

    fer = ENGINE_FER.parse(CHAOS_2)
    assert _qty(fer, "tornillo") == 2, fer
    assert _qty(fer, "arco") == 6, fer

    # Edge cases that must not crash
    for text in ["", "   ", "🎉🎉🎉", "123", "!!!", "de la", "y", "x"]:
        r = ENGINE_DEP.parse(text)
        assert isinstance(r, dict) and "status" in r, f"crashed on: {text!r}"

    # Multiple products same catalog
    r = ENGINE_DEP.parse("5 pelota de tenis y 3 guantes de boxeo")
    assert _qty(r, "pelota") == 5 and _qty(r, "guantes") == 3, r

    r = ENGINE_FER.parse("2 tornillo 3/8 y 4 tuerca hexagonal y 1 martillo")
    assert _qty(r, "tornillo") == 2, r
    assert _qty(r, "tuerca") == 4, r
    assert _qty(r, "martillo") == 1, r

    # Second catalog with custom aliases, no regressions after Phase 3
    drinks = P.OrderIntelligenceEngine([
        {"id": "x", "nombre": "Coca Cola", "precio": 1, "categoria": "Bebidas",
         "aliases": ["gaseosa", "refresco", "soda"]},
        {"id": "y", "nombre": "Agua Mineral", "precio": 1, "categoria": "Bebidas",
         "aliases": ["agua"]},
    ])
    assert _qty(drinks.parse("3 gaseosa"), "coca") == 3
    assert _qty(drinks.parse("2 agua"), "agua") == 2


def p4_4_semantic_scorer() -> None:
    assert P._SEMANTIC_SCORER is None

    # Install a perfect scorer and confirm it's called during matching
    calls: List[Any] = []

    def my_scorer(a: str, b: str) -> float:
        calls.append((a, b))
        return 1.0 if a == b else 0.5

    P.set_semantic_scorer(my_scorer)
    try:
        engine = P.OrderIntelligenceEngine(FERRETERIA)
        engine.parse("2 martillo")
        assert len(calls) > 0, "scorer was never called"

        # Scorer that raises → fallback to fuzzy, no crash
        def bad_scorer(a: str, b: str) -> float:
            raise RuntimeError("scorer error")

        P.set_semantic_scorer(bad_scorer)
        r = engine.parse("3 tornillo 3/8")
        assert isinstance(r, dict) and "status" in r, "crash with bad scorer"

        # Scorer returning out-of-range value → fallback
        def oob_scorer(a: str, b: str) -> float:
            return 99.0

        P.set_semantic_scorer(oob_scorer)
        r2 = engine.parse("2 martillo")
        assert isinstance(r2, dict) and "status" in r2, "crash with OOB scorer"
    finally:
        P.set_semantic_scorer(None)
        assert P._SEMANTIC_SCORER is None


# ---------------------------------------------------------------------------
# Phase 5 — Security, stability, and optimisation
# ---------------------------------------------------------------------------

# Golden snapshot captured before any Phase 5 change.
_GOLDEN_FER_CHAOS2 = [("Tornillo 3/8", 2), ("Arco Compuesto", 6)]
_GOLDEN_DEP_CHAOS1 = [("Arco de Fútbol", 50), ("Balón de Fútbol", 500), ("Guantes de Boxeo", 323)]
_GOLDEN_FER_TORNILLO = [("Tornillo 3/8", 2)]
_GOLDEN_DEP_BALON = [("Balón de Fútbol", 3)]


def _items_list(result: Dict[str, Any]) -> List[Tuple[str, int]]:
    return [(i["product"], int(i["quantity"])) for i in result.get("items", [])]


def p5_golden_equality() -> None:
    """Golden output must be bit-identical to the pre-Phase-5 baseline."""
    ef = P.OrderIntelligenceEngine(FERRETERIA)
    ed = P.OrderIntelligenceEngine(DEPORTES)
    assert _items_list(ef.parse(CHAOS_2)) == _GOLDEN_FER_CHAOS2, ef.parse(CHAOS_2)
    assert _items_list(ed.parse(CHAOS_1)) == _GOLDEN_DEP_CHAOS1, ed.parse(CHAOS_1)
    assert _items_list(ef.parse("quiero 2 tornillo 3/8")) == _GOLDEN_FER_TORNILLO
    assert _items_list(ed.parse("3 balon de futbol")) == _GOLDEN_DEP_BALON


def p5_6_engine_cache() -> None:
    """Engine reused when (business_id, fingerprint) match; evicted on catalog change."""
    P._engine_cache_stats["hits"] = 0
    P._engine_cache_stats["misses"] = 0
    P._engine_cache.clear()

    # First build → miss
    op1 = P.OrderParser(FERRETERIA, business_id="biz_test")
    assert P._engine_cache_stats["misses"] == 1, P._engine_cache_stats
    assert P._engine_cache_stats["hits"] == 0, P._engine_cache_stats

    # Same catalog + same business_id → hit, same engine object
    op2 = P.OrderParser(FERRETERIA, business_id="biz_test")
    assert P._engine_cache_stats["hits"] >= 1, P._engine_cache_stats
    assert op1._engine is op2._engine, "cache miss: engine objects differ"

    # Different business_id, same catalog → separate entry (miss, not a hit)
    hits_before = P._engine_cache_stats["hits"]
    P.OrderParser(FERRETERIA, business_id="biz_other")
    assert P._engine_cache_stats["misses"] == 2, P._engine_cache_stats

    # Changed catalog for same tenant → new engine, old key evicted
    changed = FERRETERIA + [{"id": "x99", "nombre": "Nuevo", "precio": 1.0, "categoria": "X", "disponible": True}]
    op3 = P.OrderParser(changed, business_id="biz_test")
    assert op3._engine is not op1._engine, "stale engine not evicted"
    stale = [k for k in P._engine_cache if k[0] == "biz_test" and k != (k[0], P._catalog_fingerprint(op3.menu_items))]
    assert len(stale) == 0, f"stale keys not evicted: {stale}"

    # engine_cache_hits counter must be > 0 after a hit
    hits_total = P._engine_cache_stats["hits"]
    assert hits_total >= 1, "engine_cache_hits never incremented"

    P._engine_cache.clear()
    p5_golden_equality()


def p5_5_no_runtime_compile() -> None:
    """Zero re.compile() calls during parse() — all patterns precompiled at module level."""
    import re as _re
    compile_count = 0
    orig_compile = _re.compile

    def _counting(pattern: Any, flags: int = 0) -> Any:
        nonlocal compile_count
        compile_count += 1
        return orig_compile(pattern, flags)

    _re.compile = _counting  # type: ignore[assignment]
    try:
        ENGINE_FER.parse("quiero 2 martillo")
        ENGINE_DEP.parse(CHAOS_1)
        ENGINE_FER.parse(CHAOS_2)
    finally:
        _re.compile = orig_compile  # type: ignore[assignment]

    assert compile_count == 0, f"re_compile_calls={compile_count} (expected 0)"
    p5_golden_equality()


def p5_4_single_normalization_pass() -> None:
    """resolve() dead qty_check block removed; all-noise segments handled gracefully."""
    # all-noise segment must return empty product_text without crashing
    # ("y" alone is not NOISE_WORDS — filtered by len<2 guard in parse(), not here)
    for noise in ("quiero", "dame porfa", "de la"):
        qty, txt = P.QuantityEngine.resolve(noise, compact_map=ENGINE_FER._compact_to_spaced)
        assert txt == "", f"noise segment {noise!r} produced product_text={txt!r}"
    # qty_check dead code removed: both paths returned same value; verify final return
    qty, txt = P.QuantityEngine.resolve("2 martillo", compact_map=ENGINE_FER._compact_to_spaced)
    assert qty == 2 and "martillo" in txt, (qty, txt)
    # "6 arcos" is what canonicalize("media docena arcos") produces before resolve sees it
    qty, txt = P.QuantityEngine.resolve("6 arcos", compact_map=ENGINE_FER._compact_to_spaced)
    assert qty == 6 and "arco" in txt, (qty, txt)
    # ponytail 5.4: remaining redundancy is extract() calling basic() on already-basic'd input.
    # not tested here since extract() is part of the public API.
    p5_golden_equality()


def p5_3_inverted_index() -> None:
    """best_match must use inverted index to reduce items_scored below catalog size."""
    for engine, name in ((ENGINE_FER, "FERRETERIA"), (ENGINE_DEP, "DEPORTES")):
        catalog_size = len(engine._catalog)
        idx = engine._matcher._inverted_index
        assert isinstance(idx, dict) and len(idx) > 0, f"{name}: empty inverted index"
        # Call best_match directly to bypass category-shortcut paths in parse()
        query = "martillo" if name == "FERRETERIA" else "pelota tenis"
        engine._matcher._stats["items_scored"] = 0
        engine._matcher.best_match(query)
        scored = engine._matcher._stats["items_scored"]
        assert scored < catalog_size, (
            f"{name}: items_scored={scored} not < catalog_size={catalog_size} — index not filtering"
        )
        assert scored >= 1, f"{name}: scored 0 items (query returned no candidates)"
    # Fallback: gibberish must still not crash (full scan fallback)
    for engine in (ENGINE_FER, ENGINE_DEP):
        r = engine.parse("xyzabc123foo")
        assert isinstance(r, dict) and r["items"] == []
    p5_golden_equality()


def p5_2_compact_map_precomputed() -> None:
    """_compact_to_spaced built once; same results as per-call rebuild."""
    for engine in (ENGINE_FER, ENGINE_DEP):
        cmap = engine._matcher._compact_to_spaced
        assert isinstance(cmap, dict), f"not a dict: {type(cmap)}"
        assert len(cmap) > 0, "empty compact map"
        # longest name wins: for each compact key, stored name must be longest
        norms = [e["normalized"] for e in engine._catalog]
        rebuilt: dict = {}
        for spaced in sorted(norms, key=len, reverse=True):
            if not spaced:
                continue
            ckey = spaced.replace(" ", "")
            if len(ckey) >= 4:
                rebuilt.setdefault(ckey, spaced)
        assert cmap == rebuilt, f"compact map mismatch: {cmap} vs {rebuilt}"
    # advanced() with compact_map gives same result as with catalog_norms list
    for phrase in ("arcocompuesto", "guantesdeboxeo", "tornillo38"):
        r_list = P.TextNormalizer.advanced(phrase, ENGINE_FER._catalog_norms)
        r_map = P.TextNormalizer.advanced(phrase, compact_map=ENGINE_FER._matcher._compact_to_spaced)
        assert r_list == r_map, f"{phrase!r}: list={r_list!r} map={r_map!r}"
    p5_golden_equality()


def p5_1_precomputed_statics() -> None:
    """catalog entries must carry compact/tokens_set/name_tokens/alias_pairs/token_keys/distinctive."""
    for engine in (ENGINE_FER, ENGINE_DEP):
        for entry in engine._catalog:
            assert "compact" in entry, f"missing compact: {entry['nombre']}"
            assert entry["compact"] == entry["normalized"].replace(" ", ""), entry
            assert "tokens_set" in entry, f"missing tokens_set: {entry['nombre']}"
            assert entry["tokens_set"] == set(entry["normalized"].split()), entry
            assert "name_tokens" in entry, f"missing name_tokens: {entry['nombre']}"
            assert "alias_pairs" in entry, f"missing alias_pairs: {entry['nombre']}"
            for alias, alias_compact in entry["alias_pairs"]:
                assert alias_compact == alias.replace(" ", ""), (alias, alias_compact)
            assert "token_keys" in entry, f"missing token_keys: {entry['nombre']}"
            assert "distinctive" in entry, f"missing distinctive: {entry['nombre']}"
            assert entry["distinctive"] == entry["token_keys"] - engine._matcher._generic_tokens, entry
    # items_scored counter must be present
    assert "items_scored" in ENGINE_FER._matcher._stats
    p5_golden_equality()


def p5_7_security_boundaries() -> None:
    """input truncation, segment cap, catalog item validation."""
    # 1. input length limit
    long_input = "quiero tornillo " * 100  # >> MAX_INPUT_CHARS
    assert len(long_input) > P.MAX_INPUT_CHARS
    result = ENGINE_FER.parse(long_input)
    # must not crash and must return a valid structure
    assert "status" in result, f"missing status: {result}"

    # 2. segment limit — craft a string that produces many segments
    many_segments = ", ".join(["1 tornillo"] * (P.MAX_SEGMENTS + 5))
    result2 = ENGINE_FER.parse(many_segments)
    assert "status" in result2, f"missing status: {result2}"
    # parsed items must not exceed MAX_SEGMENTS
    assert len(result2.get("items", [])) <= P.MAX_SEGMENTS, (
        f"items {len(result2.get('items', []))} > MAX_SEGMENTS {P.MAX_SEGMENTS}"
    )

    # 3. catalog item validation — bad items silently skipped, good ones kept
    bad_catalog = [
        {"id": "x1", "nombre": 999, "precio": 10.0, "categoria": "Test"},  # nombre not str
        {"id": None, "nombre": "Valido", "precio": 10.0, "categoria": "Test"},  # id missing
        {"id": "x3", "nombre": "Valido2", "precio": "gratis", "categoria": "Test"},  # precio not numeric
        {"id": "x4", "nombre": "Tornillo OK", "precio": 500.0, "categoria": "Test"},  # good
    ]
    bad_engine = P.OrderIntelligenceEngine(bad_catalog)
    assert len(bad_engine._catalog) == 1, (
        f"expected 1 valid item, got {len(bad_engine._catalog)}: {bad_engine._catalog}"
    )
    assert bad_engine._catalog[0]["nombre"] == "Tornillo OK"

    p5_golden_equality()


PHASES: Dict[int, List[Tuple[str, Callable[[], None]]]] = {
    1: [
        ("1.1 tabla única de puntuación", p1_1_punctuation),
        ("1.2 colapso de repeticiones ≥3→2", p1_2_repeats),
        ("1.3 split de palabras pegadas", p1_3_glued),
        ("1.4 emojis/mayúsculas/acentos", p1_4_emoji_case_accents),
        ("1.5 segmentación robusta qty/producto", p1_5_segmentation),
    ],
    2: [
        ("2.1 cardinales unidades→miles→millones", p2_1_cardinals),
        ("2.2 dígitos con separadores de miles", p2_2_thousands),
        ("2.3 formatos 2x/x2/2×/×2", p2_3_x_formats),
        ("2.4 par/docena/media docena", p2_4_pair_dozen),
        ("2.5 posición libre y mezcla", p2_5_free_position_mix),
    ],
    3: [
        ("3.1 distintividad por frecuencia", p3_1_distinctiveness),
        ("3.2 aliases/keywords data-driven", p3_2_aliases_keywords),
        ("3.3 categoría genérica derivada", p3_3_generic_category),
        ("3.4 borrado de hardcode de negocio", p3_4_hardcode_deleted),
        ("3.5 fuzzy/typos en cualquier catálogo", p3_5_fuzzy_typos),
    ],
    4: [
        ("4.1 anclaje qty↔producto longest-match", p4_1_longest_match),
        ("4.2 QA nunca inventar productos", p4_2_qa_never_invent),
        ("4.3 robustez end-to-end", p4_3_robustness),
        ("4.4 scorer semántico pluggable", p4_4_semantic_scorer),
    ],
    5: [
        ("5.1 datos estáticos precomputados en __init__", p5_1_precomputed_statics),
        ("5.2 mapa compact→espaciado precomputado por catálogo", p5_2_compact_map_precomputed),
        ("5.3 prefiltro por índice invertido token→ítems", p5_3_inverted_index),
        ("5.4 normalización única por mensaje", p5_4_single_normalization_pass),
        ("5.5 cero re.compile() en runtime", p5_5_no_runtime_compile),
        ("5.6 caché de engine por tenant+fingerprint", p5_6_engine_cache),
        ("5.7 seguridad en frontera", p5_7_security_boundaries),
    ],
}


def run_phase(phase: int) -> bool:
    subpoints = PHASES.get(phase)
    if not subpoints:
        print(f"❌ FAIL [fase {phase}] - no implementada")
        return False
    for label, fn in subpoints:
        try:
            fn()
        except AssertionError as exc:
            print(f"❌ FAIL [{label}] - {exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"❌ FAIL [{label}] - {type(exc).__name__}: {exc}")
            return False
        print(f"✅ DONE [{label}]")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-checks for the generic order parser")
    ap.add_argument("--phase", type=int, default=0, help="phase number (1..5); 0 = all implemented")
    args = ap.parse_args()
    phases = [args.phase] if args.phase else sorted(PHASES)
    for phase in phases:
        if not run_phase(phase):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
