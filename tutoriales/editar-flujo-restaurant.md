# Editar flujo restaurante

Guía para modificar `flows/restaurant_flow.json` sin romper el bot.

Rutina segura: backup → editar JSON → `python scripts/validate_flow.py` → reiniciar bot → probar en chat.

---

## Arquitectura motor

Migración Fase 1–4 cerrada. Separación fija:

### JSON = mapa

El archivo `flows/restaurant_flow.json` define **qué** dice el bot y **a dónde** va:

| Capa | Rol |
|------|-----|
| `meta` | Textos UX estáticos (abandon, cancel, welcome, prompts de dirección, etc.) y `global_commands` |
| `states` / nodos | `message`, `message_after_action`, `message_secondary`, `fallback` |
| `options` | Atajos por palabra normalizada (`menu` → `menu_node`) |
| `transitions` | Destino según **outcome** de una acción (`confirmed` → `order_delivery`) |
| Flags de nodo | `dual_message`, `self_loop_behavior`, `suppress_repeat_message`, `intercept_products`, `order_greeting_on_greeting` |

El motor **no** inventa copy de negocio: lee plantillas del JSON y las renderiza (`{{welcome_line}}`, etc.).

### Python = motor

`chatbot/app/core/flow_engine.py` ejecuta el pipeline:

```
input → abandon/meta handlers → options → global_commands → intent → action → transition → compose → str
```

Las funciones `_action_*`:

- Devuelven `(mensaje, outcome)` — el mensaje puede ser dinámico (carrito, totales, errores con datos).
- El **outcome** (`success`, `confirmed`, `rejected`, …) lo resuelve el JSON en `transitions`.
- Sin outcome nuevo en Python no hace falta tocar el motor.

Composición de salida en un solo `str`: `message` → resultado de `action` → `message_after_action` → `message_secondary` (si `dual_message`).

### Prohibido en el motor

| Patrón | Por qué |
|--------|---------|
| `step == "start"` (u otro nombre de nodo) en routing | El destino va en `options` / `transitions` |
| `List[str]` / `Reply = Union[...]` como respuesta | `process_message` siempre devuelve `str` |
| `format_menu()` fuera de `_action_show_menu` | El catálogo solo en nodo `menu_node` vía acción `show_menu` |
| Strings UX literales en Python | Van en `meta` o `node.fallback` |
| `return ..., "order_*"` / `"start"` desde `_action_*` | Las acciones devuelven outcomes semánticos, no nombres de nodo |

### Validación

```bash
python scripts/validate_flow.py
```

Comprueba refs, outcomes, claves `meta` (Fase 2/3) y coherencia de flags de nodo. Avisos (no errores) si `dual_message` sin `message_secondary`.

### Idea central

**Python decide lógica y outcome; JSON decide texto estático y siguiente nodo.** Para cambiar solo mensajes o rutas, edita el JSON. Para nueva lógica de negocio, añade o ajusta `_action_*` + `ACTION_OUTCOMES` en el validador + `transitions` en el JSON.
