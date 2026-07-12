## Pendientes ##

# Principios del Motor y del Producto

## 1. Arquitectura

* JSON define el mapa conversacional.
* Python es únicamente el motor de ejecución.
* La lógica de negocio vive exclusivamente en Services.
* El estado solo se modifica mediante StateManager.
* Todo debe respetar `ARCHITECTURE_LAW.md`.

## 2. Multi-tenant

* El motor nunca debe contener reglas específicas de un cliente.
* Todo comportamiento de negocio debe derivarse del catálogo y la configuración del tenant.
* Agregar un nuevo negocio no debe requerir modificar el motor.

## 3. Parser

* Debe comprender pedidos cortos, largos y caóticos.
* La longitud del mensaje no debe afectar el procesamiento.
* Debe tolerar errores ortográficos, puntuación, emojis, mayúsculas, acentos y orden libre.
* Debe procesar el mensaje completo antes de decidir el resultado.
* Nunca debe descartar un pedido completo porque una parte falle.

## 4. Recuperación ante errores

* Todo producto reconocido debe conservarse.
* Lo no reconocido debe enviarse a `unknown/needs_review`.
* El bot debe pedir aclaraciones sin perder el carrito.
* Nunca debe reiniciar el flujo innecesariamente.

## 5. Conversación

* El usuario nunca debe sentir que "perdió" la conversación.
* El contexto debe mantenerse mientras sea válido.
* El bot debe responder de forma natural y coherente.

## 6. Rendimiento

* El trabajo repetido debe eliminarse.
* Reutilizar estructuras cuando sea posible.
* Evitar consultas, parseos y cálculos innecesarios.
* Cada optimización debe mantener exactamente el mismo comportamiento funcional.

## 7. Robustez

* Nunca inventar productos.
* Nunca perder información válida.
* Ante la duda, preguntar.
* El sistema debe degradarse de forma elegante, no fallar completamente.

## 8. Escalabilidad

* El rendimiento debe mantenerse con catálogos grandes.
* Debe soportar pedidos con decenas de productos.
* Debe soportar miles de productos por catálogo.
* Debe soportar múltiples negocios simultáneamente.

## 9. Calidad

* Cambios mínimos e incrementales.
* Reducir deuda técnica en cada mejora.
* Preferir eliminar código antes que añadirlo.
* Sin duplicación.
* Sin hardcode de negocio.

## 10. Objetivo final

Construir un motor conversacional genérico, rápido, resiliente y mantenible, capaz de interpretar pedidos naturales de cualquier negocio sin modificar el código del motor.




## Principios del Engine
El engine nunca conoce un negocio.
El engine solo conoce algoritmos.
Todo negocio se describe mediante datos.
El catálogo es la única fuente de conocimiento del negocio.
Nunca se hardcodean productos, categorías o marcas.
Toda nueva funcionalidad debe generalizar una categoría de problemas, no resolver un caso concreto.
El motor debe degradarse elegantemente: nunca perder información válida.
Si existen productos reconocidos, nunca se descarta el pedido completo.
Todo cambio debe respetar ARCHITECTURE_LAW.md.

## Principios del Parser
Debe funcionar con cualquier catálogo.
Debe soportar mensajes de cualquier longitud.
Debe ser tolerante a errores humanos.
Debe procesar el mensaje completo antes de decidir.
Debe devolver la mayor cantidad de información útil posible.

## Principios del SaaS
Agregar un cliente nunca requiere modificar el motor.
Cambiar un catálogo nunca requiere modificar el motor.
Cambiar un flujo nunca requiere modificar el motor.
Todo es configurable mediante datos.







## Flujo para lanzar el sistema 

1. Pulir el flujo (saludo, menú, textos y experiencia del usuario).
2. Completar funcionalidades (flujos pendientes e integraciones necesarias).
3. Pulir la aplicación (UI, validaciones y corrección de bugs).
4. Pruebas end-to-end (probar el flujo completo de principio a fin).
5. Preparar la demo (datos de prueba y presentación del sistema).
6. Presentar el producto (mostrar el funcionamiento completo).

# Después:

- Requerimientos no funcionales (seguridad, rendimiento, monitoreo, etc.).
- Nuevas funcionalidades (categorías, pagos, reportes, etc.).







- TECH-DEBT: Migrar show_productos de menú textual dinámico a lista interactiva nativa de WhatsApp, manteniendo fallback textual.



🟢 Prioridad baja (P3)

Externalizar todos los textos hardcodeados de los servicios (AdminService, ReservationService, etc.) a un sistema centralizado de UX/JSON.







Hoy tu flujo ya aprovecha varias capacidades:

✅ Mensajes
✅ Botones
✅ Listas
✅ Estado de la conversación
✅ Parser inteligente
✅ Carrito
✅ Reservas

Y todavía puedes agregar:

💳 Pagos

📍 Compartir ubicación

📷 Recibir imágenes
(por ejemplo comprobantes)

📄 Documentos
(facturas, menús PDF)

🔔 Plantillas
(avisar que el pedido va en camino)

📦 Estados del pedido

👨‍💼 Transferir a un asesor humano





