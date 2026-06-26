validación hecha el 26/06/2026

IMPORTANTE: EJECUTAR DESDE /pruebas y ejecutar 
py validar_motor_python.py



PS C:\Users\Usuario\Desktop\whatsbot\pruebas> py validar_motor_python.py

==============================
AUDITORÍA DEL MOTOR
==============================

[PASS] Motor interpreta JSON
[PASS] Sin estados hardcodeados
[PASS] Sin nodos hardcodeados
[PASS] Sin referencias hardcodeadas
[PASS] Sin comandos hardcodeados fuera de deuda documentada
[PASS] Registro de acciones consistente
[PASS] Resolución de referencias centralizada     
[PASS] Resolución de transiciones centralizada    
[PASS] Separación Action / Transition
[PASS] Sin lógica de negocio
[PASS] Sin copy UX
[PASS] Sin persistencia directa
[PASS] Sin acceso SQL
[PASS] Sin mutación directa del estado
[PASS] StateManager como única fuente del estado  
[PASS] Services como única lógica de negocio      
[PASS] Parser desacoplado
[PASS] Carga única del JSON
[PASS] Sin duplicación de navegación
[PASS] Multi-tenant respetado
[PASS] Gateway como único entrypoint
[PASS] Sin dependencias circulares
[PASS] Métodos dentro del tamaño permitido        
[PASS] Complejidad ciclomática aceptable
[PASS] Sin código muerto
[PASS] Sin TODO/FIXME críticos
[PASS] Sin imports prohibidos
[PASS] Sin dependencias de implementación
[PASS] Cobertura del registro de acciones
[PASS] Todas las acciones implementadas
[PASS] Acciones sin efectos colaterales indebidos 

------------------------------
INFOS:
  - Registro simétrico: 15 acciones.
  - Mutaciones vía state_manager: set_step, patch_data, reset.
  - Persistencia delegada a Services.
  - json.load centralizado en línea 75.
  - Cobertura registro: 100% (15/15).
  - 15 acciones con implementación.

------------------------------
WARNINGS:
  - chatbot\app\core\flow_engine.py:214 referencia hardcodeada 'idle.start' (fallback permitido condeuda).
  - chatbot\app\core\flow_engine.py:266 deuda de routing conocida: command == "pedido" and self._has_active_order(state)
  - chatbot\app\core\flow_engine.py:272 deuda de routing conocida: command == "inicio" and self._has_active_order(state)
  - chatbot\app\core\flow_engine.py:277 deuda de routing conocida: command == "cancelar"
  - chatbot\app\core\flow_engine.py:288 deuda de routing conocida: command == "inicio"
  - chatbot\app\core\flow_engine.py:293 deuda de routing conocida: command in {"menu", "pedido", "reservar"} and target_step != current_step and not (command == "pedido" and self._has_active_order(state))
  - chatbot\app\core\flow_engine.py:430 deuda de routing conocida: intent_command and intent_command in self.global_commands and not intent.get("has_products")
  - chatbot\app\core\flow_engine.py:452 deuda de routing conocida: not intent_command and intent.get("has_products") and node.get("intercept_products")
  - chatbot\app\core\flow_engine.py:514 deuda de routing conocida: intent_command in {"pedido", "menu", "reservar"} and is_confirmation(text)

==============================
RESULTADO FINAL
==============================

[PASS] Motor interpreta JSON
[PASS] Sin estados hardcodeados
[PASS] Sin nodos hardcodeados
[PASS] Sin referencias hardcodeadas
[PASS] Sin comandos hardcodeados fuera de deuda documentada
[PASS] Registro de acciones consistente
[PASS] Resolución de referencias centralizada     
[PASS] Resolución de transiciones centralizada    
[PASS] Separación Action / Transition
[PASS] Sin lógica de negocio
[PASS] Sin copy UX
[PASS] Sin persistencia directa
[PASS] Sin acceso SQL
[PASS] Sin mutación directa del estado
[PASS] StateManager como única fuente del estado  
[PASS] Services como única lógica de negocio      
[PASS] Parser desacoplado
[PASS] Carga única del JSON
[PASS] Sin duplicación de navegación
[PASS] Multi-tenant respetado
[PASS] Gateway como único entrypoint
[PASS] Sin dependencias circulares
[PASS] Métodos dentro del tamaño permitido        
[PASS] Complejidad ciclomática aceptable
[PASS] Sin código muerto
[PASS] Sin TODO/FIXME críticos
[PASS] Sin imports prohibidos
[PASS] Sin dependencias de implementación
[PASS] Cobertura del registro de acciones
[PASS] Todas las acciones implementadas
[PASS] Acciones sin efectos colaterales indebidos 

[OK] Auditoría completada correctamente.

Cobertura:          100%
Pruebas ejecutadas: 31
Pruebas superadas:  31
Warnings:           9
Errores:            0