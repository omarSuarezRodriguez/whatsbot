# Matriz mínima de nodos (estado actual)

Fuente: `flows/restaurant_flow.json`  
Fecha: 2026-07-27  
Leyenda OK: `[ ]` pendiente · `[x]` verificado

## Globals (valen en casi cualquier nodo)

| Input | Destino | Notas |
|-------|---------|--------|
| `inicio` / `hola` | `home.home_node` | Con carrito activo → abandon-confirm (salvo bypass) |
| `cancelar` | `home.home_node` | Bypass abandon |
| `productos` | `productos.productos_node` | |
| `pedido` | `order.order_start_node` | Si hay pedido activo → `order_review_node` |
| `ayuda` | `ayuda.ayuda_node` | |
| `reserva` | `reserva.reserva_start_node` | Fuera del MVP pedido |

Abandon-confirm (si sales con carrito): `Continuar` / `Cancelar`.

---

## `home.home_node`

**UI:** botones  
**Action:** ninguna

| # | Entrada / Input | Esperado | OK |
|---|-----------------|----------|----|
| E1 | primer mensaje / `hola` / `inicio` | muestra home + botones | [ ] |
| S1 | `productos` / 📖 Ver menú | `productos.productos_node` | [ ] |
| S2 | `pedido` / 🍽️ Hacer pedido | `order.order_start_node` | [ ] |
| S3 | `ayuda` | `ayuda.ayuda_node` | [ ] |
| S4 | `inicio` | `home.home_node` (re-show) | [ ] |
| F1 | basura | fallback + botones Inicio / Ayuda | [ ] |

**Callejón:** no  
**Mejorar luego:** solo Ver menú si mapa kiosko; list+buttons en fallback

---

## `productos.productos_node`

**UI:** lista `categories` (+ JSON declara fallback_buttons — riesgo list+buttons)  
**Action entry:** `show_productos`  
**Flags:** `list_navigation`, `intercept_products`, target → `productos_category_node`

| # | Entrada / Input | Esperado | OK |
|---|-----------------|----------|----|
| E1 | desde home Ver menú | lista categorías | [ ] |
| E2 | global `productos` | igual | [ ] |
| S1 | lista / `__cat__X` / título cat | `productos_category_node` + `selected_category` | [ ] |
| S2 | `inicio` | `home.home_node` | [ ] |
| S3 | `pedido` | `order.order_start_node` | [ ] |
| S4 | `ayuda` | `ayuda.ayuda_node` | [ ] |
| S5 | texto con producto (intercept) | redirige como `pedido` + parsea texto | [ ] |
| F1 | basura | fallback; ideal quedarse en productos | [ ] |
| N1 | `__next__` / `__prev__` | cambia `list_page`, re-show | [ ] |

**Callejón:** no (si lista o `inicio` funcionan)  
**Mejorar luego:** sin fila Volver; hint `inicio` en body; no mezclar botones con lista

---

## `productos.productos_category_node`

**UI:** lista `category_products`  
**Action:** `show_category_products`  
**Flags:** `list_navigation`, `intercept_products`, `suppress_navigation`

| # | Entrada / Input | Esperado | OK |
|---|-----------------|----------|----|
| E1 | desde productos (categoría) | lista productos de esa cat | [ ] |
| S1 | tap producto / intercept nombre | → flujo `pedido` + parse (hoy **no** hay `order_qty_node`) | [ ] |
| S2 | `inicio` | `home.home_node` | [ ] |
| S3 | `pedido` | `order.order_start_node` | [ ] |
| S4 | `ayuda` | `ayuda.ayuda_node` | [ ] |
| F1 | basura | fallback + hint inicio | [ ] |
| N1 | `__next__` / `__prev__` | paginación | [ ] |

**Callejón riesgo:** sin fila “Categorías”; escape = `inicio` / globals  
**Gap vs mapa ideal:** falta `order_qty_node`

---

## `order.order_start_node`

**UI:** free_text  
**Action:** `capture_order`

| # | Input / outcome | Esperado | OK |
|---|-----------------|----------|----|
| E1 | home pedido / intercept / empty_cart | pide escribir pedido | [ ] |
| T1 | `success` | `order.order_review_node` + cart | [ ] |
| T2 | `partial` | `order.order_clarify_node` | [ ] |
| T3 | `ambiguous` | `order.order_disambiguate_node` | [ ] |
| T4 | all unknown | outcome null; se queda; mensaje unknown | [ ] |
| T5 | vacío / sin items | empty message; se queda | [ ] |
| F1 | no reconoce | fallback | [ ] |

**Globals** siguen activos (inicio, productos, …) con abandon si hay cart

---

## `order.order_review_node`

**UI:** botones Confirmar / Modificar  
**Action show:** `show_cart` · **input:** `handle_order_confirmation`

| # | Input / outcome | Esperado | OK |
|---|-----------------|----------|----|
| E1 | success capture | muestra carrito + botones | [ ] |
| T1 | carrito vacío → `empty_cart` | `order.order_start_node` | [ ] |
| T2 | confirmar / sí → `confirmed` | `order.order_delivery_node` | [ ] |
| T3 | modificar / no → `rejected` | `order.order_modify_node` | [ ] |
| F1 | basura | fallback (sí/no); outcome null | [ ] |

**Gap mapa ideal:** no existe botón `➕ Añadir más`

---

## `order.order_modify_node`

**UI:** free_text  
**Action:** `capture_order` (sobre cart)

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | desde review Modificar | pide agregar/quitar/cambiar | [ ] |
| T1 | `success` | `order_review_node` | [ ] |
| T2 | `partial` | `order_clarify_node` | [ ] |
| T3 | `ambiguous` | `order_disambiguate_node` | [ ] |
| F1 | no entiende | fallback; se queda | [ ] |

---

## `order.order_clarify_node`

**UI:** free_text  
**Action input:** `handle_order_clarification`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | partial desde start/modify | pide aclarar unknown | [ ] |
| T1 | `partial_resolved` | `order_review_node` | [ ] |
| F1 | no reconoce / omitir (según motor) | fallback o avanza | [ ] |

**Nota:** solo `partial_resolved` en JSON; otras ramas internas del action auditar en motor

---

## `order.order_disambiguate_node`

**UI:** free_text  
**Action input:** `handle_order_disambiguation`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | ambiguous | lista candidatos | [ ] |
| T1 | `disambiguated` | `order_review_node` | [ ] |
| F1 | basura | fallback; se queda | [ ] |

---

## `order.order_delivery_node`

**UI:** botones Domicilio / Recoger  
**Action:** `capture_delivery_type`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | confirm review | pregunta entrega | [ ] |
| T1 | `domicilio` | `order_address_node` | [ ] |
| T2 | `recoger_has_name` | `order_saved_node` | [ ] |
| T3 | `recoger_no_name` | `order_customer_name_node` | [ ] |
| F1 | basura | fallback; se queda | [ ] |

---

## `order.order_address_node`

**UI:** botones Confirmar / Modificar  
**Action:** `handle_address_confirmation`  
**Msg:** muestra `{{saved_address}}`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | domicilio | muestra dirección guardada | [ ] |
| T1 | `confirm_address` + nombre → `confirmed_has_name` | `order_saved_node` | [ ] |
| T2 | `confirm_address` sin nombre → `confirmed_no_name` | `order_customer_name_node` | [ ] |
| T3 | `edit_address` → `edit` | `order_address_edit_node` | [ ] |
| F1 | basura | fallback | [ ] |

**Riesgo audit:** primera visita sin dirección (mensaje vacío / confirmar vacío) — probar a propósito

---

## `order.order_address_edit_node`

**UI:** free_text  
**Action:** `capture_address`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | Modificar dirección | pide escribir dirección | [ ] |
| T1 | texto OK → `confirm` | `order_address_confirm_node` + guarda address | [ ] |
| F1 | vacío / inválido | se queda (fallback / address_invalid) | [ ] |

---

## `order.order_address_confirm_node`

**UI:** botones Confirmar / Modificar  
**Action:** `handle_new_address_confirmation`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | tras edit | muestra `{{delivery_address}}` | [ ] |
| T1 | `confirm_new_address` + nombre | `order_saved_node` | [ ] |
| T2 | `confirm_new_address` sin nombre | `order_customer_name_node` | [ ] |
| T3 | `edit_new_address` | `order_address_edit_node` | [ ] |
| F1 | basura | fallback | [ ] |

---

## `order.order_customer_name_node`

**UI:** free_text  
**Action:** `capture_customer_name`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | recoger/domicilio sin nombre | pide nombre | [ ] |
| T1 | nombre ≥ 2 → `success` | `order_saved_node` | [ ] |
| F1 | corto / vacío | se queda (fallback) | [ ] |

---

## `order.order_saved_node`

**UI:** resultado action (sin botones)  
**Action:** `save_order`

| # | outcome | Esperado | OK |
|---|---------|----------|----|
| E1 | fin camino feliz | guarda pedido + mensaje success | [ ] |
| T1 | `success` → `null` | fin (terminal) | [ ] |
| T2 | `empty_cart` | `order_start_node` | [ ] |
| G1 | luego `inicio` / `productos` | globals | [ ] |

**Callejón terminal:** OK (es el fin)

---

## `ayuda.ayuda_node`

**UI:** solo texto  
**Options / transitions:** ninguna en JSON

| # | Input | Esperado | OK |
|---|---------|----------|----|
| E1 | ayuda | mensaje “asesor contactará” | [ ] |
| F1 | basura | fallback: escribe *inicio* | [ ] |
| G1 | `inicio` | home (global) | [ ] |

**Callejón suave:** sin botones; escape = escribir `inicio`

---

## Reserva (fuera MVP pedido — documentar, auditar después)

### `reserva.reserva_start_node`
| outcome | destino | OK |
|---------|---------|----|
| `success` | `reserva_date_node` | [ ] |
| inválido | se queda | [ ] |

### `reserva.reserva_date_node`
| `success` → `reserva_time_node` | [ ] |

### `reserva.reserva_time_node`
| `success` → `reserva_review_node` | [ ] |
| `missing_date` → `reserva_date_node` | [ ] |

### `reserva.reserva_review_node`
| `confirmed` → `reserva_saved_node` | [ ] |
| `rejected` / `incomplete` → `reserva_start_node` | [ ] |

### `reserva.reserva_saved_node`
| `success` → `home.home_node` | [ ] |
| `incomplete` → `reserva_start_node` | [ ] |

---

## Orden sugerido de mejora (uno por uno)

1. `home_node`
2. `productos_node`
3. `productos_category_node`
4. `order_start_node` → review → delivery → saved (camino feliz)
5. address / name
6. clarify / disambiguate / modify
7. ayuda / reserva (después)

## No existe aún (mapa ideal)

- `order_qty_node`
- Review: `➕ Añadir más`
- Filas lista `__cats__` / `__home__`