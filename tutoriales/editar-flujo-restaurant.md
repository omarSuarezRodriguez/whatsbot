# Manual de operación: editar el flujo conversacional

Guía práctica para modificar `flows/restaurant_flow.json` sin tocar Python, de forma segura.

---

## Archivo que editas

| Qué | Dónde |
|-----|-------|
| Flujo conversacional | `flows/restaurant_flow.json` |
| Validador (solo lectura) | `scripts/validate_flow.py` |
| Motor que ejecuta el flujo | `chatbot/app/core/flow_engine.py` |

El bot **no** usa nodos planos legacy. Todo vive bajo `states`.

---

## Anatomía del JSON

```json
{
  "meta": { ... },
  "states": {
    "idle":     { "initial": "start", "nodes": { ... } },
    "order":    { "initial": "order_start", "nodes": { ... } },
    "reservation": { "initial": "reservation_start", "nodes": { ... } }
  }
}
```

### `meta`

- **`global_commands`**: atajos que funcionan desde casi cualquier nodo (`menu`, `pedido`, `reservar`, `inicio`, `cancelar`). Valores con formato `estado.nodo` (ej. `order.order_start`).
- **`cancel_message`**, **`navigation_hint`**: textos globales del bot.

### Cada `state`

- **`initial`**: primer nodo al entrar al estado.
- **`nodes`**: pasos del flujo. Cada clave es un **nombre de nodo único en todo el archivo** (el motor los aplana en un solo diccionario).

### Campos habituales de un nodo

| Campo | Para qué sirve |
|-------|----------------|
| `message` | Texto que ve el usuario al llegar al nodo |
| `message_after_action` | Texto extra después de ejecutar la acción |
| `message_secondary` | Segundo mensaje (con `dual_message`) |
| `input_mode`: `"free_text"` | El usuario escribe texto libre; dispara acción |
| `action` | Acción Python al **entrar** al nodo (si no está esperando input) |
| `action_on_input` | Acción Python cuando el usuario responde (prioridad sobre `action` en input) |
| `transitions` | Mapa `outcome → destino` tras la acción |
| `options` | Mapa `palabra_clave → nodo` (navegación manual del usuario) |
| `flow` | (Opcional) Sobrescribe el estado activo del usuario (ej. volver a `idle`) |
| `fallback` | Mensaje si no entiende la respuesta |
| `suppress_navigation` | Oculta el hint de navegación al pie |

---

## Flujo de trabajo seguro (siempre igual)

1. **Copia de respaldo** del JSON (o commit en git).
2. **Edita** solo lo necesario (un nodo o un bloque de transiciones).
3. **Valida** antes de desplegar:

   ```bash
   python scripts/validate_flow.py
   ```

   Debe terminar en `Resultado: 0 errores`.

4. **Reinicia el bot** (o el contenedor Docker) para que cargue el JSON nuevo. El motor lee el archivo al arrancar; no hay hot-reload en producción.

5. **Prueba manual** el camino que tocaste: pedido completo, reserva completa, y al menos un salto con `menu` / `inicio` desde mitad de flujo.

---

## Cómo funcionan las transiciones (concepto clave)

Python **no elige el siguiente nodo**. Solo devuelve un **outcome** (string). El JSON decide el destino.

```
Usuario escribe → acción Python → (mensaje, "confirmed")
                                        ↓
                         transitions.confirmed en el JSON → "order_delivery"
```

- **`null` en `transitions`**: no hay salto; el usuario **se queda** en el mismo nodo (útil para `invalid`, errores de parseo, o mostrar carrito sin avanzar).
- **Outcome ausente o `None` desde Python**: mismo efecto que `null` — no hay transición.

Tres formas de mover al usuario:

| Mecanismo | Quién lo dispara | Formato del destino |
|-----------|------------------|---------------------|
| `transitions` | Resultado de una acción | Nombre de nodo o `estado.nodo` |
| `options` | Palabra exacta del usuario | **Solo nombre de nodo** (ej. `menu_node`) |
| `global_commands` | Comandos globales (`meta`) | `estado.nodo` (ej. `idle.start`) |

---

## Referencias entre nodos (refs)

### Dentro del mismo estado

Usa el nombre corto del nodo:

```json
"success": "order_review"
```

### Entre estados distintos

Usa formato calificado `estado.nodo`:

```json
"success": "idle.start"
"empty_cart": "order.order_start"
"incomplete": "reservation.reservation_start"
```

### En `options` (mismo estado u otro)

Siempre el **nombre del nodo** (sin prefijo de estado), porque el nombre es único globalmente:

```json
"options": {
  "menu": "menu_node",
  "pedido": "order_start"
}
```

`menu_node` vive en `idle`; `order_start` en `order`. Funciona porque no hay dos nodos con el mismo nombre.

### Regla de oro

> **Cada nombre de nodo debe ser único en todo el JSON.** No crees dos `start` en estados distintos; usa prefijos (`order_start`, `reservation_start`).

---

## Agregar un nuevo nodo (paso a paso)

Ejemplo: insertar un paso `order_tip` entre confirmación y tipo de entrega.

### 1. Elige el estado

Nodos de pedido → dentro de `states.order.nodes`.

### 2. Crea el nodo con nombre único

```json
"order_tip": {
  "message": "¿Deseas dejar propina? Responde *sí* o *no*.",
  "input_mode": "free_text",
  "options": {
    "si": "order_delivery",
    "no": "order_delivery",
    "menu": "menu_node"
  }
}
```

Si solo usas `options` (sin acción Python), **no necesitas** `transitions`.

### 3. Conecta el nodo anterior

En `order_review`, cambia solo la transición que te interesa:

```json
"confirmed": "order_tip"
```

(en lugar de `"order_delivery"`).

### 4. Añade salida desde el nodo nuevo

Ya hecho en el ejemplo: `options` hacia `order_delivery`.

### 5. Valida y prueba

```bash
python scripts/validate_flow.py
```

Recorre: pedido → confirmar → nuevo paso → domicilio/recoger → fin.

---

## Modificar un flujo existente (order o reservation)

### Solo mensajes

Cambia `message`, `message_after_action` o `fallback`. **No requiere** tocar transiciones ni validador.

### Cambiar el orden de pasos

1. Identifica el nodo que **emite** el salto (`transitions` o `options` del nodo previo).
2. Cambia **solo** el valor destino (ej. `"success": "reservation_time"` → `"reservation_review"`).
3. Valida refs: el destino debe existir como clave en algún `states.*.nodes`.

### Añadir una opción de menú en un paso

En el nodo actual, agrega a `options`:

```json
"inicio": "start"
```

(`start` es el nodo inicial de `idle`).

### Saltar a otro estado al terminar

En el nodo final del subflujo:

```json
"flow": "idle",
"transitions": {
  "success": "idle.start"
}
```

`flow` actualiza el estado interno del usuario; la transición lo lleva al nodo correcto.

---

## Cambiar transiciones sin afectar otros estados

Los estados están aislados en el JSON, pero comparten **nombres de nodo** en el mapa global. Para no romper nada:

1. **Edita transiciones solo del nodo que dispara la acción** — no copies bloques enteros de `transitions` a otros nodos.
2. **No renombres nodos** sin buscar referencias: busca el nombre en todo el archivo (`order_review`, `menu_node`, etc.).
3. **Cambios cross-state**: usa siempre `estado.nodo` en `transitions` y `global_commands` para evitar ambigüedad.
4. Tras el cambio, ejecuta el validador: detecta destinos inexistentes y outcomes faltantes **en ese nodo**, no en todo el grafo.

Ejemplo seguro — redirigir rechazo de reserva a fecha en lugar de reiniciar:

Solo en `reservation_review`:

```json
"rejected": "reservation_date"
```

El resto de `reservation` queda intacto si `reservation_date` ya existe.

---

## Outcomes: contrato fijo Python ↔ JSON

Si un nodo tiene `action` o `action_on_input`, sus `transitions` deben declarar **todos** los outcomes que esa acción puede devolver. El validador lo exige.

### Tabla de acciones y outcomes permitidos

| Acción | Outcomes que debes mapear en `transitions` |
|--------|---------------------------------------------|
| `welcome_customer` | `success` |
| `show_menu` | `success` |
| `show_cart` | `success`, `empty_cart` |
| `capture_order` | `success`, `empty_cart` |
| `handle_order_confirmation` | `confirmed`, `rejected`, `invalid` |
| `capture_delivery_type` | `domicilio`, `recoger_has_name`, `recoger_no_name`, `invalid` |
| `capture_address` | `success_has_name`, `success_no_name`, `invalid` |
| `capture_customer_name` | `success`, `invalid` |
| `save_order` | `success`, `empty_cart` |
| `capture_persons` | `success`, `invalid` |
| `capture_date` | `success`, `invalid` |
| `capture_time` | `success`, `missing_date`, `invalid` |
| `show_reservation_summary` | `success`, `incomplete` |
| `handle_reservation_confirmation` | `confirmed`, `rejected`, `incomplete`, `invalid` |
| `save_reservation` | `success`, `incomplete` |

### Patrones típicos de destino

| Outcome | Uso habitual | Destino típico |
|---------|--------------|----------------|
| `success` | Dato guardado, seguir | Siguiente nodo del flujo |
| `null` | Error leve, reintentar en sitio | `null` |
| `invalid` | No entendió confirmación | `null` |
| `empty_cart` | Carrito vacío | Reinicio del pedido o `null` |
| `confirmed` / `rejected` | Sí / no explícito | Avanzar o rama de modificación |
| `incomplete` | Faltan datos | Nodo que recolecta lo que falta |

**Nota:** Varias acciones devuelven `None` (sin outcome) en casos de error de parseo; eso equivale a quedarse en el nodo. No hace falta una clave extra en `transitions` para esos casos.

---

## Agregar un nuevo outcome (cuando sí toca Python)

Solo si la lógica nueva **no** puede expresarse con outcomes existentes.

### Checklist (los tres lugares deben coincidir)

1. **`flow_engine.py`** — La acción devuelve el nuevo string:
   ```python
   return "Mensaje al usuario.", "nuevo_outcome"
   ```
2. **`scripts/validate_flow.py`** — Añade el outcome al set de la acción en `ACTION_OUTCOMES`.
3. **`restaurant_flow.json`** — Mapea en `transitions`:
   ```json
   "nuevo_outcome": "siguiente_nodo"
   ```

Si falta cualquiera de los tres, el validador falla o el bot no avanza.

### Nueva acción completa (caso raro)

Además de lo anterior:

- Registrar la función en el dict `_actions` de `FlowEngine`.
- Implementar `_action_mi_accion`.
- Usar `"action": "mi_accion"` en el nodo JSON.

Para cambios de copy, orden de pasos o ramas con outcomes ya existentes, **no abras Python**.

---

## Errores comunes y cómo evitarlos

### Refs inválidas

**Síntoma:** validador dice `nodo inexistente`.  
**Causa:** typo en nombre, o `estado.nodo` mal escrito.  
**Fix:** busca el nombre exacto en `states.*.nodes` o usa el validador como guía.

### Outcomes faltantes en `transitions`

**Síntoma:** `faltan outcomes [...] para acción`.  
**Causa:** el nodo tiene `action`/`action_on_input` pero no lista todos los outcomes de la tabla.  
**Fix:** añade las claves que faltan (pueden apuntar a `null`).

### Nombres de nodo duplicados

**Síntoma:** comportamiento errático al saltar de estado.  
**Causa:** dos nodos con la misma clave en estados distintos (el último gana al aplanar).  
**Fix:** prefijos por flujo (`order_*`, `reservation_*`).

### Estados huérfanos

**Síntoma:** nodo existe pero nadie llega.  
**Causa:** olvidaste enlazar desde `transitions`, `options` o `global_commands`.  
**Fix:** el validador **no** detecta huérfanos; revisa manualmente desde `initial` de cada state o prueba el chat.

### Loops no deseados

**Síntoma:** el usuario gira en círculo.  
**Causa:** `success` apunta al mismo nodo sin condición de salida, o `options` solo redirigen entre dos nodos.  
**Fix:** usa `null` para errores; asegura al menos un camino hacia un nodo terminal (`order_saved`, `reservation_saved`, `idle.start`).

### JSON inválido

**Síntoma:** el bot no arranca o `json.load` falla.  
**Fix:** coma final, comillas dobles, cerrar llaves. Usa un validador JSON del editor.

### Cambios sin reinicio

**Síntoma:** editaste el archivo pero el bot sigue igual.  
**Fix:** reinicia el proceso/contenedor; el flujo se carga al inicio.

---

## Reglas mínimas de consistencia

1. **Estructura:** solo `meta` + `states`; cada state con `initial` + `nodes`.
2. **Nombres únicos** de nodo en todo el archivo.
3. **Todo nodo con acción** → `transitions` completos según la tabla de outcomes.
4. **Destinos reales:** cada ref en `transitions`, `options` y `global_commands` apunta a un nodo existente.
5. **Cross-state explícito** en `transitions` y `global_commands`: `estado.nodo`.
6. **`null` explícito** para “quedarse aquí” en outcomes de error o revisión.
7. **Validar siempre** con `python scripts/validate_flow.py` antes de desplegar.
8. **Probar** el happy path y al menos un error (`invalid`, carrito vacío, etc.) del flujo tocado.

---

## Mapa rápido del flujo actual

```
idle.start / menu_node
    ├─ pedido → order.order_start → … → order_saved → idle.start
    └─ reservar → reservation.reservation_start → … → reservation_saved → idle.start

order:  order_start → order_review ⇄ order_modify → order_delivery
        → order_address? → order_customer_name? → order_saved

reservation:  reservation_start → reservation_date → reservation_time
              → reservation_review → reservation_saved
```

Comandos globales desde casi cualquier paso: `menu`, `pedido`, `reservar`, `inicio`, `cancelar` (ver `meta.global_commands`).

---

## Resumen en una frase

Edita mensajes y cables (`transitions` / `options`) en `restaurant_flow.json`, respeta el vocabulario de outcomes, valida con el script, reinicia el bot y prueba el camino — Python solo entra si inventas un outcome o acción nueva.
