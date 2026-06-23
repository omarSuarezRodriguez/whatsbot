# Cambiar el flujo del chatbot

Guía breve para modificar **el orden** de los pasos y **el contenido** de lo que ve el usuario.

---

## Qué archivo tocar según el cambio

| Quieres cambiar… | Archivo |
|------------------|---------|
| Textos de cada paso, opciones del menú, comandos globales | `flows/restaurant_flow.json` |
| A qué paso va después de una respuesta (sí/no, domicilio, etc.) | `chatbot/app/core/flow_engine.py` |
| Mensajes de error, vacío, bienvenida alternativa | `config/prompts.py` |
| Texto del menú de productos | Base de datos (`menu_items`) o app Flutter |
| Prompts por negocio (multi-tenant) | BD `business_prompts` o API `PUT /whatsbot/business/prompts` |

Para la mayoría de cambios de flujo y textos fijos, basta **`restaurant_flow.json`**. Si cambias **cuándo** salta de un paso a otro, toca también **`flow_engine.py`**.

---

## 1. Editar el flujo en JSON

Archivo: `flows/restaurant_flow.json`

### Estructura de un nodo

```json
"order_start": {
  "flow": "order",
  "message": "Texto que ve el usuario al entrar al paso",
  "message_after_action": "Texto extra después de ejecutar la acción",
  "input_mode": "free_text",
  "action": "capture_order",
  "action_on_input": "handle_order_confirmation",
  "options": {
    "pedido": "order_start",
    "menu": "menu_node"
  }
}
```

| Campo | Para qué sirve |
|-------|----------------|
| `message` | Texto principal al **entrar** al nodo |
| `message_after_action` | Texto que se añade **después** de la acción (ej. “¿Confirmamos?”) |
| `options` | Palabra exacta del usuario → id del **siguiente nodo** |
| `action` | Lógica Python que procesa input o prepara datos |
| `action_on_input` | Acción al recibir texto libre (confirmaciones) |
| `flow` | Estado interno: `idle`, `order`, `reservation` |

### Comandos globales (desde cualquier paso)

En `meta.global_commands`:

```json
"global_commands": {
  "menu": "menu_node",
  "pedido": "order_start",
  "reservar": "reservation_start",
  "inicio": "start",
  "cancelar": "start"
}
```

### Cambiar el orden de los pasos

1. Identifica el nodo actual (ej. `order_review`).
2. Mira qué **destino** tiene hoy:
   - en `options` del JSON, o
   - en `flow_engine.py` (acciones que devuelven `"order_delivery"`, `"order_modify"`, etc.).
3. Cambia el destino al nodo que quieras.
4. Ajusta `message` / `message_after_action` del nodo destino.

**Ejemplo:** saltar dirección y ir directo a guardar pedido → en `_action_handle_order_confirmation`, cambiar el destino tras confirmar de `"order_delivery"` a `"order_saved"` (solo si la lógica lo permite).

### Cambiar solo el contenido (sin cambiar orden)

Edita `message`, `message_secondary` o `message_after_action` en el nodo correspondiente.

Placeholders disponibles en plantillas:

| Placeholder | Se reemplaza por |
|-------------|------------------|
| `{{welcome_line}}` | Saludo personalizado con nombre |
| `{{address_prompt}}` | Pregunta de dirección (con dirección guardada si existe) |
| `{{restaurant_name}}` | Nombre del negocio |

---

## 2. Editar transiciones en el motor

Archivo: `chatbot/app/core/flow_engine.py`

Algunos saltos **no están** en el JSON; los define el código en métodos `_action_*`:

| Acción | Transiciones típicas |
|--------|----------------------|
| `capture_order` | → `order_review` |
| `handle_order_confirmation` | sí → `order_delivery`, no → `order_modify` |
| `capture_delivery_type` | domicilio → `order_address`, recoger → `order_saved` o `order_customer_name` |
| `capture_persons` | → `reservation_date` |
| `capture_date` | → `reservation_time` |
| `capture_time` | → `reservation_review` |
| `handle_reservation_confirmation` | sí → `reservation_saved`, no → `reservation_start` |

Para **nuevo paso** en el flujo:

1. Añade el nodo en `restaurant_flow.json`.
2. Si necesita lógica nueva, registra la acción en `_actions` (dict del `__init__`) e implementa `_action_tu_accion`.
3. Haz que el paso anterior apunte a tu nodo (JSON `options` o `return "...", "tu_nodo"` en una acción).

Textos hardcodeados en el motor (abandono de pedido, repetir pedido, fallbacks) también viven aquí; cámbialos si quieres unificar todo en JSON.

---

## 3. Fallbacks y mensajes fuera del flujo

Archivo: `config/prompts.py`

Usado cuando no hay negocio activo o como respaldo. Incluye claves como `empty_body_hint`, `error_generic`, `node_order_start_message`, etc.

Si editas textos en JSON **y** existen claves `node_*` en `prompts.py`, el JSON manda en runtime del flujo; `prompts.py` sigue siendo relevante para gateway y BD vacía.

---

## 4. Aplicar cambios

1. Guarda los archivos editados.
2. **Reinicia el proceso del bot** (API/worker). El JSON se carga al arrancar (`FlowEngine._load_flow()`). No hay hot-reload expuesto en producción.
3. Opcional: variable `FLOWS_PATH` en `.env` si usas otro archivo JSON distinto de `flows/restaurant_flow.json`.
4. Prueba el flujo completo: inicio → pedido → confirmación → domicilio → guardado (y lo mismo para reserva).

---

## 5. Checklist rápido

- [ ] ¿Solo cambiaste textos? → `restaurant_flow.json` (y `config/prompts.py` si aplica)
- [ ] ¿Cambiaste a qué paso va después de sí/no o de un dato? → `flow_engine.py` + JSON
- [ ] ¿Añadiste un paso nuevo? → nodo en JSON + acción en `flow_engine.py`
- [ ] ¿Cambiaste el menú de platos? → BD / Flutter, no el JSON del flujo
- [ ] ¿Multi-negocio? → revisa también `business_prompts` en BD
- [ ] Reiniciaste el servicio tras guardar

---

## Mapa de referencia (flujo actual)

```
start → menu_node | order_start | reservation_start

order_start → order_review → order_delivery → order_address → order_customer_name → order_saved
                    └→ order_modify ────────────────┘

reservation_start → reservation_date → reservation_time → reservation_review → reservation_saved
```

Comandos globales en cualquier momento: `menu`, `pedido`, `reservar`, `inicio`, `cancelar`.

---

## Migración en curso (formato por estados)

El motor acepta **dos formatos** de `restaurant_flow.json`:

| Formato | Estructura |
|---------|------------|
| **Legacy (actual)** | `"nodes": { "start": { ... }, ... }` |
| **Por estados (objetivo)** | `"states": { "idle": { "nodes": { ... } }, "order": { ... } }` |

En runtime ambos se normalizan al mismo mapa plano de nodos. Las transiciones declarativas (`transitions` por outcome) se activarán al migrar el JSON en la Fase 2; hasta entonces los saltos siguen en `flow_engine.py` (`return "...", "order_review"`).

**Validar el JSON antes de desplegar:**

```bash
python scripts/validate_flow.py
```

Comprueba que `options` y `global_commands` apuntan a nodos existentes y, si hay `transitions`, que los destinos y outcomes son coherentes.
