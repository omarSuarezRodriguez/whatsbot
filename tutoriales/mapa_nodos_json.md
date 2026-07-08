# MAPA DE NODOS — restaurant_flow.json

## FLUJOS PRINCIPALES

HOME
PRODUCTOS
ORDER
AYUDA


# FLOW: HOME

## home_node
│
├── Action:
│   welcome_customer
│
├── Entradas directas:
│   productos
│   pedido
│   ayuda
│   buenas
│   hey
│
└── Destinos:
    productos → productos.productos_node
    pedido    → order.order_start_node
    ayuda     → ayuda.ayuda_start_node
    buenas    → permanece en home_node
    hey       → permanece en home_node
    otro      → fallback y permanece


# FLOW: PRODUCTOS

## productos_node
│
├── Action:
│   show_productos
│
├── Entradas directas:
│   pedido
│   ayuda
│   inicio
│   hola
│   buenas
│   hey
│   productos
│
└── Destinos:
    pedido    → order.order_start_node
    ayuda     → ayuda.ayuda_start_node
    inicio    → home.home_node
    hola      → home.home_node
    buenas    → home.home_node
    hey       → home.home_node
    productos → permanece en productos_node


# FLOW: ORDER

## order_start_node
│
├── Action:
│   capture_order
│
├── Outcomes:
│   success
│   empty_cart
│   partial
│   ambiguous
│
└── Destinos:
    success    → order_review_node
    empty_cart → permanece
    partial    → order_clarify_node
    ambiguous  → order_disambiguate_node


## order_review_node
│
├── Action al entrar:
│   show_cart
│
├── Action al responder:
│   handle_order_confirmation
│
├── Outcomes:
│   success
│   empty_cart
│   confirmed
│   rejected
│   invalid
│
└── Destinos:
    success    → permanece
    empty_cart → order_start_node
    confirmed  → order_delivery_node
    rejected   → order_modify_node
    invalid    → permanece


## order_modify_node
│
├── Action:
│   capture_order
│
├── Outcomes:
│   success
│   empty_cart
│   partial
│   ambiguous
│
└── Destinos:
    success    → order_review_node
    empty_cart → permanece
    partial    → order_clarify_node
    ambiguous  → order_disambiguate_node


## order_clarify_node
│
├── Action al responder:
│   handle_order_clarification
│
├── Outcomes:
│   partial_resolved
│   partial_retry
│   skip
│
└── Destinos:
    partial_resolved → order_review_node
    partial_retry    → permanece
    skip             → permanece


## order_disambiguate_node
│
├── Action al responder:
│   handle_order_disambiguation
│
├── Outcomes:
│   disambiguated
│   disambiguate_next
│   invalid_choice
│
└── Destinos:
    disambiguated    → order_review_node
    disambiguate_next → permanece
    invalid_choice   → permanece


## order_delivery_node
│
├── Action:
│   capture_delivery_type
│
├── Outcomes:
│   domicilio
│   recoger_has_name
│   recoger_no_name
│   invalid
│
└── Destinos:
    domicilio         → order_address_node
    recoger_has_name  → order_saved_node
    recoger_no_name   → order_customer_name_node
    invalid           → permanece


## order_address_node
│
├── Action:
│   capture_address
│
├── Outcomes:
│   success_has_name
│   success_no_name
│   invalid
│
└── Destinos:
    success_has_name → order_saved_node
    success_no_name  → order_customer_name_node
    invalid          → permanece


## order_customer_name_node
│
├── Action:
│   capture_customer_name
│
├── Outcomes:
│   success
│   invalid
│
└── Destinos:
    success → order_saved_node
    invalid → permanece


## order_saved_node
│
├── Action:
│   save_order
│
├── Outcomes:
│   success
│   empty_cart
│
└── Destinos:
    success    → permanece
    empty_cart → order_start_node


# FLOW: AYUDA

## ayuda_start_node
│
├── Action:
│   capture_persons
│
├── Outcomes:
│   success
│   invalid
│
└── Destinos:
    success → ayuda_date_node
    invalid → permanece


## ayuda_date_node
│
├── Action:
│   capture_date
│
├── Outcomes:
│   success
│   invalid
│
└── Destinos:
    success → ayuda_time_node
    invalid → permanece


## ayuda_time_node
│
├── Action:
│   capture_time
│
├── Outcomes:
│   success
│   missing_date
│   invalid
│
└── Destinos:
    success      → ayuda_review_node
    missing_date → ayuda_date_node
    invalid      → permanece


## ayuda_review_node
│
├── Action al entrar:
│   show_ayuda_summary
│
├── Action al responder:
│   handle_ayuda_confirmation
│
├── Outcomes:
│   success
│   incomplete
│   confirmed
│   rejected
│   invalid
│
└── Destinos:
    success    → permanece
    incomplete → ayuda_start_node
    confirmed  → ayuda_saved_node
    rejected   → ayuda_start_node
    invalid    → permanece


## ayuda_saved_node
│
├── Action:
│   save_ayuda
│
├── Outcomes:
│   success
│   incomplete
│
└── Destinos:
    success    → home.home_node
    incomplete → ayuda_start_node














    CHATBOT
│
├── HOME
│   └── home_node
│       ├── productos ───────────────▶ PRODUCTOS
│       ├── pedido ──────────────────▶ ORDER
│       └── ayuda ───────────────────▶ AYUDA
│
├── PRODUCTOS
│   └── productos_node
│       ├── pedido ──────────────────▶ ORDER
│       ├── ayuda ───────────────────▶ AYUDA
│       └── inicio ──────────────────▶ HOME
│
├── ORDER
│
│   order_start_node
│       │
│       ├── success ────────────────▶ order_review_node
│       ├── partial ────────────────▶ order_clarify_node ───┐
│       └── ambiguous ──────────────▶ order_disambiguate_node│
│                                                              │
│                         ◀────────────────────────────────────┘
│
│   order_review_node
│       ├── confirmed ──────────────▶ order_delivery_node
│       ├── rejected ───────────────▶ order_modify_node
│       │                                │
│       │                                └──▶ order_review_node
│       │
│       ▼
│   order_delivery_node
│       ├── domicilio ──────────────▶ order_address_node
│       │                                │
│       │                                ├── tiene nombre ───┐
│       │                                └── sin nombre ─────┼──▶
│       │                                                     │
│       ├── recoger + nombre ─────────────────────────────────┤
│       └── recoger sin nombre ─────▶ customer_name_node ─────┤
│                                                             ▼
│                                                    order_saved_node
│
└── AYUDA
    │
    ayuda_start_node
        ↓
    ayuda_date_node
        ↓
    ayuda_time_node
        ↓
    ayuda_review_node
        ├── confirmed ──────────────▶ ayuda_saved_node ───▶ HOME
        └── rejected/incomplete ────▶ ayuda_start_node