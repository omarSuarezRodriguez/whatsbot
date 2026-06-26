validación hecha el 26/06/2026

IMPORTANTE: EJECUTAR DESDE LA RAIZ DEL PROYECTO 
py validar_arquitectura.py



PS C:\Users\Usuario\Desktop\whatsbot> py validar_arquitectura.py

==============================================================
AUDITORIA ARQUITECTONICA
==============================================================

[PASS] JSON mapa — forma (flows\restaurant_flow.json)
[PASS] JSON mapa — contrato nodos (flows\restaurant_flow.json)
[PASS] JSON mapa — nodos únicos (flows\restaurant_flow.json)
[PASS] JSON mapa — referencias (flows\restaurant_flow.json)
[PASS] JSON mapa — transiciones/acciones (flows\restaurant_flow.json)
[PASS] Python core — acciones registradas
[PASS] Python core — motor no es mapa
[PASS] Python core — sin copy UX
[PASS] Python core — frontera Services
[PASS] JSON mapa — comandos globales en JSON
[PASS] JSON mapa — carga centralizada
[PASS] Multi-tenant — sin tenants hardcodeados
[PASS] Multi-tenant — gateway usa business_scope
[PASS] StateManager — ownership del estado
[PASS] Gobernanza — ARCHITECTURE_LAW.md
[PASS] Gobernanza — tests

Validación arquitectónica — información:

- flows\restaurant_flow.json define estados: home, menu, order, reservation      
- flows\restaurant_flow.json order.order_start_node transitions.empty_cart sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_review_node transitions.success sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_review_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_modify_node transitions.empty_cart sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_delivery_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_address_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json order.order_customer_name_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json reservation.reservation_start_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json reservation.reservation_date_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json reservation.reservation_time_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo o dinámico.
- flows\restaurant_flow.json reservation.reservation_review_node transitions.success sin outcome literal estático en las acciones del nodo; puede ser defensivo odinámico.
- flows\restaurant_flow.json reservation.reservation_review_node transitions.invalid sin outcome literal estático en las acciones del nodo; puede ser defensivo odinámico.
- services/business_config_loader.py referencia GLOBAL_COMMAND_ROUTES como semilla/config (no es routing runtime del motor).
- services/business_service.py referencia GLOBAL_COMMAND_ROUTES como semilla/config (no es routing runtime del motor).

Validación arquitectónica — advertencias:

- flows\restaurant_flow.json order.order_saved_node.flow='home' difiere del estado contenedor 'order' (FlowEngine inyecta flow=order al normalizar).
- flows\restaurant_flow.json reservation.reservation_saved_node.flow='home' difiere del estado contenedor 'reservation' (FlowEngine inyecta flow=reservation al normalizar).
- chatbot\app\core\flow_engine.py:249 deuda de routing conocida: command == "pedido" and self._has_active_order(state)
- chatbot\app\core\flow_engine.py:255 deuda de routing conocida: command == "inicio" and self._has_active_order(state)
- chatbot\app\core\flow_engine.py:260 deuda de routing conocida: command == "cancelar"
- chatbot\app\core\flow_engine.py:271 deuda de routing conocida: command == "inicio"
- chatbot\app\core\flow_engine.py:276 deuda de routing conocida: command in {"menu", "pedido", "reservar"} and target_step != current_step and not (command == "pedido" and self._has_active_order(state))
- chatbot\app\core\flow_engine.py:399 deuda de routing conocida: intent_command in {"pedido", "menu", "reservar"} and is_confirmation(text)
- chatbot\app\core\flow_engine.py:401 deuda de routing conocida: intent_command and intent_command in self.global_commands and not intent.get("has_products")
- chatbot\app\core\flow_engine.py:412 deuda de routing conocida: not intent_command and intent.get("has_products") and node.get("intercept_products")

==============================================================
RESULTADO FINAL
==============================================================

[PASS] JSON mapa — forma (flows\restaurant_flow.json)
[PASS] JSON mapa — contrato nodos (flows\restaurant_flow.json)
[PASS] JSON mapa — nodos únicos (flows\restaurant_flow.json)
[PASS] JSON mapa — referencias (flows\restaurant_flow.json)
[PASS] JSON mapa — transiciones/acciones (flows\restaurant_flow.json)
[PASS] Python core — acciones registradas
[PASS] Python core — motor no es mapa
[PASS] Python core — sin copy UX
[PASS] Python core — frontera Services
[PASS] JSON mapa — comandos globales en JSON
[PASS] JSON mapa — carga centralizada
[PASS] Multi-tenant — sin tenants hardcodeados
[PASS] Multi-tenant — gateway usa business_scope
[PASS] StateManager — ownership del estado
[PASS] Gobernanza — ARCHITECTURE_LAW.md
[PASS] Gobernanza — tests

[OK] Auditoria completada correctamente.

Cobertura arquitectónica: 100%
Pruebas ejecutadas:        16
Pruebas superadas:         16
Warnings:                  10
Errores:                   0