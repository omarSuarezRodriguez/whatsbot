validación hecha el 26/06/2026

IMPORTANTE: EJECUTAR DESDE /pruebas y ejecutar py validar_json.py


PS C:\Users\Usuario\Desktop\whatsbot\pruebas> py validar_json.py

==============================================================
AUDITORIA DEL FLUJO
Archivo: restaurant_flow.json
==============================================================

[PASS] Estados definidos
[PASS] initial válido
[PASS] Nodos alcanzables
[PASS] Estados alcanzables
[PASS] Referencias válidas
[PASS] Options válidas
[PASS] Transitions válidas
[PASS] Global commands válidos
[PASS] Active order command targets
[PASS] Cobertura del flujo
[PASS] Simulación completa
[PASS] Caminos completos
[PASS] Nodos terminales
[PASS] Estados terminales
[PASS] Ciclos controlados
[PASS] Self-loops válidos
[PASS] Sin caminos muertos
[PASS] Sin estados aislados
[PASS] Sin nodos huérfanos
[PASS] Sin duplicidad lógica

--------------------------------------------------------------
ESTADISTICAS
--------------------------------------------------------------
  Estados:              4
  Nodos:                14
  Referencias totales:  59  (validas: 59)
  Transitions:          34
  Options:              30

  Estados alcanzables:  4/4  (100%)
  Nodos alcanzables:    14/14  (100%)
  Cobertura del flujo:  100%

--------------------------------------------------------------
WARNINGS:
  - 'menu.menu_node': opción 'menu' apunta al mismo nodo (self-loop). self_loop_behavior=None.
  - Nodos con lógica idéntica (action+options+transitions): 'order.order_start_node', 'order.order_modify_node'

--------------------------------------------------------------
INFOS:
  - 'home.home_node': opción 'buenas' apunta al mismo nodo (self-loop). self_loop_behavior='fallback'.
  - 'home.home_node': opción 'hey' apunta al mismo nodo (self-loop). self_loop_behavior='fallback'.
  - 'order.order_start_node': transition 'empty_cart' = null (el nodo permanece en su posicion).
  - 'order.order_review_node': transition 'success' = null (el nodo permanece ensu posicion).
  - 'order.order_review_node': transition 'invalid' = null (el nodo permanece ensu posicion).
  - 'order.order_modify_node': transition 'empty_cart' = null (el nodo permaneceen su posicion).
  - 'order.order_delivery_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'order.order_address_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'order.order_customer_name_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'reservation.reservation_start_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'reservation.reservation_date_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'reservation.reservation_time_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - 'reservation.reservation_review_node': transition 'success' = null (el nodo permanece en su posicion).
  - 'reservation.reservation_review_node': transition 'invalid' = null (el nodo permanece en su posicion).
  - home_node -> (loop->home_node)
  - home_node -> menu_node -> (loop->home_node)
  - home_node -> menu_node -> (loop->menu_node)
  - home_node -> menu_node -> order_start_node -> (loop->menu_node)
  - home_node -> menu_node -> order_start_node -> order_review_node -> (loop->menu_node)
  - home_node -> menu_node -> order_start_node -> order_review_node -> order_delivery_node -> (loop->menu_node)
  - home_node -> menu_node -> order_start_node -> order_review_node -> order_delivery_node -> order_address_node -> (loop->menu_node)
  - home_node -> menu_node -> order_start_node -> order_review_node -> order_delivery_node -> order_address_node -> order_customer_name_node -> (loop->menu_node)
  - Bucle conversacional principal (14 nodos). Todos los caminos regresan a puntos de entrada globales. Correcto.
  - 'home.home_node': self-loop intencional (options: ['buenas', 'hey']) con self_loop_behavior='fallback'.
  - 'menu.menu_node': self-loop detectado (options: ['menu']) pero tiene otras salidas.

==============================================================
RESULTADO FINAL
==============================================================

[OK] Auditoria completada correctamente.

Cobertura:          100%
Pruebas ejecutadas: 20
Pruebas superadas:  20
Warnings:           2
Errores:            0