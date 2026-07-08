# Arquitectura del Motor Conversacional


| Nivel | Concepto | En mi código | Ejemplo |
|-------|----------|--------------|----------|

| 1 | **Chatbot** | Todo el sistema | Kiresoft WhatsApp Bot |

| 2 | **Flow (Módulo)** | Agrupa una funcionalidad | `home`, `productos`, `order`, `ayuda` | (states, contenedor/contiene los estados, ejemplo HOME, PRODUCTOS, ORDER, y dentro de cada estado de esos, están los nodos como los del punto 3)

| 3 | **Nodo (Estado)** | Estado conversacional actual dentro de un Flow | `home_node`, `order_start_node`, `order_review_node`, `order_address_node` |

| 4 | **Action** | Función que ejecuta el estado | `welcome_customer`, `capture_order`, `show_cart`, `capture_address`, `save_order` |

| 5 | **Outcome** | Resultado devuelto por la Action | `success`, `partial`, `confirmed`, `invalid`, `domicilio` |

| 6 | **Transition** | Regla del JSON que decide el siguiente estado | `success → order_review_node`, `confirmed → order_delivery_node` |

---

## Ejemplo de una conversación

| Concepto | Valor |
|----------|-------|
| **Chatbot** | Kiresoft |
| **Flow** | `order` |
| **Nodo (Estado)** | `order_review_node` |
| **Action** | `show_cart` |
| **Outcome** | `confirmed` |
| **Transition** | `confirmed → order_delivery_node` |

---

## Modelo mental

```text
🤖 Chatbot
│
├── 📦 Flow (Módulo)
│
├── 🚪 Nodo (Estado)
│
├── ⚙️ Action
│
├── 📤 Outcome
│
└── 🔀 Transition
        ↓
   Siguiente Nodo (Estado)
```

---

## Ejemplo completo

```text
🤖 Chatbot
│
└── 📦 Flow: ORDER
      │
      └── 🚪 Estado: order_review_node
            │
            └── ⚙️ Action: show_cart
                  │
                  └── 📤 Outcome: confirmed
                        │
                        └── 🔀 Transition
                              │
                              ▼
                      🚪 Estado: order_delivery_node
```

> **Regla mental:** El usuario siempre está dentro de un **Flow** (módulo), ubicado en un **Nodo** (estado). Ese nodo ejecuta una **Action**, la Action devuelve un **Outcome**, y el JSON utiliza ese Outcome para decidir la **Transition** hacia el siguiente Nodo (estado).




Chatbot
│
└── states (contenedor)
      │
      ├── Estado HOME
      │      └── home_node
      │
      ├── Estado PRODUCTOS
      │      └── productos_node
      │
      ├── Estado ORDER
      │      ├── order_start_node
      │      ├── order_review_node
      │      ├── order_modify_node
      │      ├── ...
      │
      └── Estado AYUDA
             ├── ayuda_start_node
             └── ...




"El estado HOME es el módulo o contexto general, y home_node es el estado conversacional concreto."






> ## Modelo mental del motor
>
> Aunque el JSON utiliza la clave `states`, en esta arquitectura **`states` funciona como un contenedor de módulos (Flows)**.
>
> Cada Flow agrupa una funcionalidad del chatbot (`home`, `productos`, `order`, `ayuda`).
>
> Los **estados conversacionales reales** son los **nodos** (`home_node`, `order_start_node`, `order_review_node`, etc.), ya que son los que el motor guarda en `step` y entre los que navega mediante las transiciones del JSON.
>
> En otras palabras:
>
> ```text
> Chatbot
> │
> ├── states (agrupador de Flows)
> │     │
> │     ├── home
> │     │     └── home_node
> │     │
> │     ├── productos
> │     │     └── productos_node
> │     │
> │     ├── order
> │     │     ├── order_start_node
> │     │     ├── order_review_node
> │     │     └── ...
> │     │
> │     └── ayuda
> │           ├── ayuda_start_node
> │           └── ...
> ```
>
> **Regla para recordar:**
>
> - `states` → Agrupa los Flows (módulos).
> - `Flow` → Módulo funcional del chatbot.
> - `Nodo` → Estado conversacional real.
> - `Action` → Lógica que ejecuta el estado.
> - `Outcome` → Resultado de la Action.
> - `Transition` → Decide el siguiente nodo.



Varias palabras parecían significar lo mismo.

Por ejemplo:

states
flow
step
node

Y tú pensabas:

"¿Cuál de todos es el estado?"

Resultó que:

states → contenedor del JSON.
flow → módulo.
step → nodo actual.
node → estado conversacional.

Ahí estaba el verdadero "rompecabezas".


