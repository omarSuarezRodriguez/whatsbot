# Cambiar el flujo del chatbot

Guía breve para modificar **el orden** de los pasos y **el contenido** de lo que ve el usuario.

---

## Qué archivo tocar según el cambio

| Quieres cambiar… | Archivo |
|------------------|---------|
| Textos de cada paso, opciones del menú, comandos globales | `flows/restaurant_flow.json` |
| A qué paso va después de una respuesta (sí/no, domicilio, etc.) | `flows/restaurant_flow.json` (`transitions`) |
| Lógica de negocio (parsear pedido, validar fecha, guardar) | `chatbot/app/core/flow_engine.py` (`_action_*`) |
| Mensajes de error, vacío, bienvenida alternativa | `config/prompts.py` |
| Texto del menú de productos | Base de datos (`menu_items`) o app Flutter |
| Prompts por negocio (multi-tenant) | BD `business_prompts` o API `PUT /whatsbot/business/prompts` |

Para cambios de flujo y textos fijos, basta **`restaurant_flow.json`**. Python solo devuelve **outcomes** (`confirmed`, `domicilio`, `success`…); el JSON decide el siguiente nodo.

---

## 1. Editar el flujo en JSON

Archivo: `flows/restaurant_flow.json`

### Estructura por estados

```json
"states": {
  "idle": { "initial": "start", "nodes": { ... } },
  "order": { "initial": "order_start", "nodes": { ... } },
  "reservation": { "initial": "reservation_start", "nodes": { ... } }
}
```

Referencias cruzadas entre estados: `"idle.start"`, `"order.order_review"`, `"reservation.reservation_start"`.

### Estructura de un nodo

```json
"order_review": {
  "action": "show_cart",
  "message_after_action": "¿Confirmamos tu pedido?",
  "input_mode": "free_text",
  "action_on_input": "handle_order_confirmation",
  "transitions": {
    "confirmed": "order_delivery",
    "rejected": "order_modify",
    "empty_cart": "order_start",
    "invalid": null
  },
  "options": {
    "menu": "menu_node"
  }
}
```

| Campo | Para qué sirve |
|-------|----------------|
| `message` | Texto principal al **entrar** al nodo |
| `message_after_action` | Texto que se añade **después** de la acción (ej. “¿Confirmamos?”) |
| `options` | Palabra exacta del usuario → id del **siguiente nodo** |
| `transitions` | Outcome de la acción → siguiente nodo (`null` = quedarse) |
| `action` | Lógica Python que procesa input o prepara datos |
| `action_on_input` | Acción al recibir texto libre (confirmaciones) |

### Comandos globales (desde cualquier paso)

En `meta.global_commands` (refs `estado.nodo`):

```json
"global_commands": {
  "menu": "idle.menu_node",
  "pedido": "order.order_start",
  "reservar": "reservation.reservation_start",
  "inicio": "idle.start",
  "cancelar": "idle.start"
}
```

### Cambiar el orden de los pasos

1. Identifica el nodo actual (ej. `order_review`).
2. Edita `transitions` del nodo según el outcome de la acción.
3. Ajusta `message` / `message_after_action` del nodo destino si hace falta.

**Ejemplo:** saltar dirección y ir directo a guardar pedido → en `order_review`, cambiar `"confirmed": "order_delivery"` por `"confirmed": "order_saved"` (solo si la lógica lo permite).

### Cambiar solo el contenido (sin cambiar orden)

Edita `message`, `message_secondary` o `message_after_action` en el nodo correspondiente.

Placeholders disponibles en plantillas:

| Placeholder | Se reemplaza por |
|-------------|------------------|
| `{{welcome_line}}` | Saludo personalizado con nombre |
| `{{address_prompt}}` | Pregunta de dirección (con dirección guardada si existe) |
| `{{restaurant_name}}` | Nombre del negocio |

---

## 2. Transiciones en JSON

Las transiciones viven en `transitions` de cada nodo. Python devuelve **outcomes**, no nombres de nodo.

| Acción | Outcomes |
|--------|----------|
| `welcome_customer`, `show_menu`, `show_cart`, `show_reservation_summary` | `success` o quedarse (`null`) |
| `capture_order` | `success`, `empty_cart` |
| `handle_order_confirmation` | `confirmed`, `rejected`, `invalid` |
| `capture_delivery_type` | `domicilio`, `recoger_has_name`, `recoger_no_name`, `invalid` |
| `capture_address` | `success_has_name`, `success_no_name`, `invalid` |
| `capture_customer_name` | `success`, `invalid` |
| `save_order` | `success` → `idle.start`, `empty_cart` → `order.order_start` |
| `capture_persons` | `success`, `invalid` |
| `capture_date` | `success`, `invalid` |
| `capture_time` | `success`, `missing_date`, `invalid` |
| `handle_reservation_confirmation` | `confirmed`, `rejected`, `incomplete`, `invalid` |
| `save_reservation` | `success` → `idle.start`, `incomplete` → `reservation.reservation_start` |

Para **nuevo paso** en el flujo:

1. Añade el nodo en `restaurant_flow.json` dentro del `state` correcto.
2. Define `transitions` con los outcomes que devuelve la acción.
3. Si necesita lógica nueva, registra la acción en `_actions` e implementa `_action_tu_accion` devolviendo outcomes (no nombres de nodo).
4. Haz que el paso anterior apunte a tu nodo vía `transitions` o `options`.

Textos hardcodeados en el motor (abandono de pedido, repetir pedido, fallbacks) siguen en `flow_engine.py`; cámbialos ahí si quieres unificar todo en JSON.

---

## 3. Fallbacks y mensajes fuera del flujo

Archivo: `config/prompts.py`

Usado cuando no hay negocio activo o como respaldo. Incluye claves como `empty_body_hint`, `error_generic`, `node_order_start_message`, etc.

Si editas textos en JSON **y** existen claves `node_*` en `prompts.py`, el JSON manda en runtime del flujo; `prompts.py` sigue siendo relevante para gateway y BD vacía.

---

## 4. Aplicar cambios

1. Guarda los archivos editados.
2. Valida el JSON: `python scripts/validate_flow.py`
3. **Reinicia el proceso del bot** (API/worker). El JSON se carga al arrancar (`FlowEngine._load_flow()`). No hay hot-reload expuesto en producción.
4. Opcional: variable `FLOWS_PATH` en `.env` si usas otro archivo JSON distinto de `flows/restaurant_flow.json`.
5. Prueba el flujo completo: inicio → pedido → confirmación → domicilio → guardado (y lo mismo para reserva).

---

## 5. Checklist rápido

- [ ] ¿Solo cambiaste textos? → `restaurant_flow.json` (y `config/prompts.py` si aplica)
- [ ] ¿Cambiaste a qué paso va después de sí/no o de un dato? → `transitions` en JSON
- [ ] ¿Añadiste un paso nuevo? → nodo + `transitions` en JSON + acción en `flow_engine.py`
- [ ] ¿Cambiaste el menú de platos? → BD / Flutter, no el JSON del flujo
- [ ] ¿Multi-negocio? → revisa también `business_prompts` en BD
- [ ] Ejecutaste `python scripts/validate_flow.py` sin errores
- [ ] Reiniciaste el servicio tras guardar

---

## Mapa de referencia (flujo actual)

```
idle: start, menu_node

order:
  order_start        →(success)→ order_review
  order_review       →(confirmed)→ order_delivery | (rejected)→ order_modify | (empty_cart)→ order_start
  order_modify       →(success)→ order_review
  order_delivery     →(domicilio)→ order_address | (recoger_has_name)→ order_saved | (recoger_no_name)→ order_customer_name
  order_address      →(success_has_name)→ order_saved | (success_no_name)→ order_customer_name
  order_customer_name→(success)→ order_saved
  order_saved        →(success)→ idle.start

reservation:
  reservation_start  →(success)→ reservation_date
  reservation_date   →(success)→ reservation_time
  reservation_time   →(success)→ reservation_review | (missing_date)→ reservation_date
  reservation_review →(confirmed)→ reservation_saved | (rejected|incomplete)→ reservation_start
  reservation_saved  →(success)→ idle.start
```

Comandos globales en cualquier momento: `menu`, `pedido`, `reservar`, `inicio`, `cancelar`.
