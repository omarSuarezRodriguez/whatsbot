# ARCHITECTURE_LAW.md

Este archivo es la ley de arquitectura del proyecto. Su objetivo es impedir que cambios incrementales rompan la separacion central del sistema:

```text
JSON = mapa conversacional
Python = motor de ejecucion
Services = negocio
StateManager = estado conversacional
business_scope = aislamiento multi-tenant
```

## Politica de solo lectura

Este archivo es un contrato de solo lectura para tareas normales de implementacion.

Su funcion principal es ser leido, obedecido y usado como criterio de revision. No debe ser editado para acomodar una feature, bugfix, refactor, ajuste de tests o cambio de flujo.

Regla estricta:

```text
ARCHITECTURE_LAW.md se lee; no se modifica.
```

Solo puede cambiarse cuando el usuario pida explicitamente una de estas cosas:

- "modifica ARCHITECTURE_LAW.md"
- "actualiza la ley de arquitectura"
- "cambia las reglas de arquitectura"
- "propongo cambiar la arquitectura"
- "revisa y mejora ARCHITECTURE_LAW.md"

Incluso cuando exista autorizacion explicita, el cambio debe tratarse como una decision de gobernanza, no como parte accidental de una implementacion.

Los tests existentes tampoco deben modificarse como parte de tareas normales para hacer pasar una implementacion.

Solo pueden cambiarse cuando el usuario pida explicitamente una de estas cosas:

- "modifica los tests"
- "actualiza los tests"
- "cambia las expectativas de los tests"
- "agrega tests para este cambio"
- "corrige tests rotos"

Si un cambio rompe tests existentes, no se deben editar los tests para ocultar el problema. Primero se debe asumir que el codigo nuevo rompio un contrato y corregir la implementacion.

Si una tarea requiere violar este documento, no se debe modificar la ley para hacer pasar el cambio. Se debe detener la implementacion y explicar:

1. Que regla se rompe.
2. Por que el cambio la rompe.
3. Que alternativa mantiene la arquitectura.
4. Si no hay alternativa, que decision arquitectonica se necesita.

## Decision central

La arquitectura oficial del bot es:

```text
Twilio
  -> FastAPI webhook
  -> gateway.py
  -> business_scope
  -> FlowEngine
  -> StateManager
  -> Services
  -> DB
```

La regla principal es:

```text
El flujo se configura.
El motor orquesta.
El estado lo administra StateManager.
El negocio vive en Services.
El tenant siempre viene por business_scope.
```

## Invariantes

Estas reglas no son preferencias. Son invariantes del sistema.

### 1. El JSON es el mapa

El JSON define:

- estados
- nodos
- opciones
- transiciones
- comandos globales
- mensajes del flujo
- fallbacks
- outcomes esperados

Python no debe duplicar ese mapa.

Prohibido:

- hardcodear rutas conversacionales en Python
- decidir destinos con `if step == "..."`
- duplicar transiciones fuera del JSON
- crear un segundo mapa en config, BD o codigo
- usar `GLOBAL_COMMAND_ROUTES` como routing runtime paralelo

Permitido:

- cargar JSON
- validar JSON
- resolver referencias del JSON
- ejecutar acciones declaradas por el JSON
- renderizar templates declarados por el JSON

### 2. Python es el motor

`FlowEngine` es un motor de ejecucion, no el negocio.

Debe:

- leer el estado actual
- leer el nodo actual
- ejecutar la accion registrada
- recibir `(mensaje, outcome)`
- resolver la transicion declarada en JSON
- componer la respuesta final

No debe:

- contener reglas especificas por tenant
- contener decisiones de negocio profundas
- escribir directamente en BD
- importar modelos o sesiones de persistencia
- tener copy largo de experiencia de usuario
- convertirse en un conjunto de casos especiales por nodo

### 3. Las acciones son delgadas

Una accion `_action_*` debe ser una capa de orquestacion.

Puede:

- leer datos del `StateManager`
- llamar un Service
- guardar datos conversacionales con `StateManager`
- devolver `(mensaje, outcome)`

No debe:

- contener calculos complejos de negocio
- contener persistencia directa
- validar reglas de dominio complejas si pueden vivir en Services
- crear rutas nuevas por fuera del JSON

### 4. Services contienen negocio

La logica de negocio vive en Services.

Ejemplos:

- pedidos
- menu
- reservas
- usuarios
- clientes
- admin
- notificaciones
- persistencia
- validaciones de dominio

Si una mejora agrega capacidad de negocio, debe agregarse en Services o en una capa de dominio equivalente, no en el motor.

### 5. StateManager controla el estado conversacional

Solo `StateManager` puede mutar:

- `flow`
- `step`
- `data`
- carrito temporal
- reserva temporal
- flags conversacionales
- confirmaciones pendientes

Los datos duraderos pertenecen a BD mediante Services.

Prohibido:

- mutar `state["step"]` fuera de `StateManager`
- mutar `state["flow"]` fuera de `StateManager`
- mutar `state["data"]` directamente fuera de `StateManager`

### 6. Multi-tenant siempre

Todo acceso a datos de negocio debe estar bajo `business_scope` o recibir `business_id` de forma explicita y validada.

Prohibido:

- asumir un unico restaurante
- usar `if business_id == "..."`
- crear comportamiento especial por tenant dentro de `FlowEngine`
- leer configuracion global si existe configuracion por tenant
- resolver menu, prompts, intents, admin o pedidos sin contexto de negocio

Si un tenant necesita flujo distinto, la solucion correcta es configuracion de flujo por tenant. No se permite resolverlo con condicionales dentro del motor.

### 7. Gateway unico

Todo mensaje de WhatsApp debe pasar por `gateway.py`.

La API puede:

- recibir webhook
- resolver tenant
- persistir auditoria
- llamar gateway
- responder a Twilio

La API no debe:

- reimplementar el parser conversacional
- reimplementar el motor
- modificar estado conversacional directamente
- decidir rutas del flujo
- saltarse bloqueos o reglas de admin/cliente

### 8. Una fuente de verdad por responsabilidad

La navegacion vive en JSON.

Los comandos globales runtime viven en `meta.global_commands`.

El copy del flujo vive en JSON.

El copy configurable del gateway vive en BD.

Los defaults de `config/*` son semillas, no fuente runtime si ya existe configuracion en BD.

No se debe crear la misma decision en dos lugares distintos.

### 9. Cambios incrementales son permitidos si respetan capas

Una mejora incremental es valida cuando agrega comportamiento dentro de la capa correcta.

Una mejora incremental no debe modificar `ARCHITECTURE_LAW.md` ni cambiar tests existentes salvo autorizacion explicita del usuario. Los tests son contrato; no son material de ajuste para que el cambio parezca correcto.

Ejemplos validos:

- helper nuevo en un Service
- mejora del parser sin cambiar routing
- nuevo endpoint que respeta `business_id`
- nueva validacion de dominio en Services
- nuevo campo de BD usado por Services
- nuevo copy en JSON
- nueva transicion declarada en JSON
- nueva accion delgada registrada y validada
- tests nuevos o modificados solo si el usuario lo pidio explicitamente

Ejemplos invalidos:

- nueva ruta decidida con `if current_step == "..."`
- nuevo tenant resuelto con `if business_id == "..."`
- nuevo copy largo hardcodeado en `FlowEngine`
- persistencia directa desde `FlowEngine`
- estado mutado sin `StateManager`
- cambiar tests para que acepten una regresion
- borrar assertions existentes sin autorizacion explicita
- modificar snapshots, fixtures o expectativas para esconder un fallo

### 10. Deuda aceptada no debe crecer

Estas limitaciones existen y deben tratarse como deuda conocida:

- flujo JSON global
- acciones restaurante-specific dentro de `FlowEngine`
- parser grande de pedidos en `core`
- admin WhatsApp legacy global
- estado conversacional en archivo JSON local
- prompts duplicados entre JSON, config y BD
- nombres legacy como `restaurant`, `sheets` y `RESTAURANT_NAME`

Cuando se toque una zona con deuda, el cambio debe:

- reducir la deuda, o
- dejarla igual, o
- documentar explicitamente por que no puede reducirla todavia

Nunca debe ampliarla silenciosamente.

## Proceso obligatorio para cambios

Antes de implementar:

1. Leer este archivo.
2. Identificar que capas toca el cambio.
3. Confirmar si el cambio es incremental o arquitectonico.
4. Si es arquitectonico, pedir aprobacion antes de implementarlo.
5. Si requiere cambiar tests, confirmar que el usuario lo pidio explicitamente.

Despues de implementar:

```bash
python scripts/validate_flow.py
python scripts/validate_architecture.py
pytest
```

El validador puede bloquear cambios en este archivo o en tests. Las variables de autorizacion del validador solo pueden usarse cuando el usuario pidio explicitamente cambiar la ley o cambiar tests. No deben usarse para saltarse una regla durante una implementacion normal.

Si algun comando falla, no se debe esconder el fallo. Se debe reportar:

- comando ejecutado
- resultado
- causa probable
- correccion aplicada o pendiente

## Checklist de revision

Antes de aceptar un cambio, responder:

- La navegacion sigue en JSON?
- Python sigue siendo motor y no mapa?
- El negocio sigue en Services?
- El estado se muta solo por `StateManager`?
- El cambio respeta multi-tenant?
- No hay `if business_id == ...`?
- No hay rutas paralelas fuera del JSON?
- No hay copy largo de flujo en Python?
- Los comandos globales vienen de `meta.global_commands`?
- Las acciones nuevas son delgadas?
- Los outcomes tienen transiciones declaradas?
- No se modificaron tests salvo solicitud explicita?
- Se ejecutaron validadores y tests?

## Instruccion para asistentes AI y Cursor

Cuando trabajes en este repo:

1. No modifiques este archivo salvo solicitud explicita del usuario.
2. No modifiques tests existentes salvo solicitud explicita del usuario.
3. No hagas cambios que contradigan este archivo.
4. Si el usuario pide algo ambiguo, elige la opcion que preserve esta arquitectura.
5. Si una implementacion obvia rompe una regla, detente y explica la alternativa.
6. Al final de cambios relevantes, ejecuta validadores y tests.
7. Si no puedes ejecutar validadores, dilo claramente.

Prompt recomendado para tareas futuras:

```text
Antes de implementar, lee ARCHITECTURE_LAW.md.
No modifiques ARCHITECTURE_LAW.md.
No modifiques tests existentes salvo que yo lo pida explicitamente.
Implementa el cambio respetando:
JSON = mapa,
Python = motor,
Services = negocio,
StateManager = estado,
business_scope = tenant.

Al final ejecuta:
python scripts/validate_flow.py
python scripts/validate_architecture.py
pytest

Si alguna regla arquitectonica se rompe, no fuerces el cambio.
Explica que regla se rompe y propone una alternativa.
```
