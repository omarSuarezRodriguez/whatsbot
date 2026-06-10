# Guía de edición desde WhatsBot (para el dueño)

Esta guía explica cómo configurar tu negocio **desde la app móvil WhatsBot**, sin tocar código ni archivos del servidor.

---

## 1. Entrar a la app

1. Abre **WhatsBot** en tu teléfono (Android o iPhone).
2. En **ID del negocio** escribe el código que te dio quien instaló el sistema (normalmente `default` si solo tienes un local).
3. Escribe tu **PIN del dueño** (lo configura el administrador en el servidor — no es tu contraseña de WhatsApp).
4. Pulsa **Entrar**.

Verás la lista de chats: son las mismas conversaciones que llegan al número del bot en WhatsApp.

---

## 2. Responder a clientes

1. Toca un chat de la lista.
2. Lee los mensajes (la pantalla se actualiza sola cada pocos segundos).
3. Escribe abajo y pulsa el botón verde de enviar.
4. El cliente recibe tu mensaje por WhatsApp, como si fuera el bot.

**Tip:** La pantalla imita WhatsApp a propósito para que te resulte familiar.

---

## 3. Aprobar o rechazar pedidos

Cuando un cliente confirma un pedido, puede aparecer una **barra amarilla** arriba del chat:

- **Aprobar** — el bot avisa al cliente que el pedido fue confirmado.
- **Rechazar** — el bot informa que no se pudo aceptar.

También puedes seguir confirmando por tu WhatsApp personal (número admin), como antes.

---

## 4. Editar el menú

**Ruta:** Ajustes (icono engranaje) → **Menú**

| Acción | Cómo |
|--------|------|
| Ver productos | Lista con nombre, categoría y precio |
| Editar | Toca un producto o el icono lápiz |
| Agregar | Botón **+** abajo a la derecha |
| Quitar | Icono papelera |
| Guardar | Icono disquete arriba a la derecha |

**¿Qué pasa al guardar?**  
Los productos se guardan en la base de datos de tu negocio. La **próxima vez** que un cliente pida ver el menú por WhatsApp, el bot mostrará los nombres y precios nuevos. No hace falta reiniciar nada.

**Ejemplo:** Cambias "Pizza margarita" de $25.000 a $28.000 y guardas. Un cliente que escriba *menu* verá $28.000.

---

## 5. Editar intents (palabras clave)

**Ruta:** Ajustes → **Intents**

Los *intents* son las frases y palabras que hacen que el bot entienda qué quiere el cliente.

| Intent | Para qué sirve |
|--------|----------------|
| `menu` | Ver carta / precios |
| `pedido` | Empezar un pedido |
| `reservar` | Reservar mesa |
| `inicio` / `cancelar` | Volver al inicio |

En cada tarjeta puedes editar:

- **Frases** — una por línea. Ejemplo: `quiero la carta`, `qué tienen de comer`.
- **Palabras clave** — separadas por coma. Ejemplo: `menu, carta, catalogo`.

Pulsa **Guardar** (disquete) cuando termines.

**Ejemplo:** Tus clientes dicen "pásame la lista" en vez de "menu". Agrega esa frase al intent `menu` y guarda. El bot reconocerá la frase nueva de inmediato.

---

## 6. Editar mensajes del bot

**Ruta:** Ajustes → **Mensajes**

Aquí cambias los textos que el bot envía automáticamente:

| Mensaje | Cuándo lo ve el cliente |
|---------|-------------------------|
| Bienvenida | Al saludar / iniciar conversación |
| Mensaje vacío | Si manda algo que el bot no entiende |
| Inicio de pedido | Cuando elige hacer pedido |
| Pedido registrado | Después de confirmar un pedido |
| Error genérico | Si algo falla |

1. Toca el mensaje que quieres cambiar.
2. Edita el texto (puedes usar *negrita* con asteriscos, como en WhatsApp).
3. Pulsa **Aceptar** y luego **Guardar** (disquete).

**Ejemplo:** Cambias la bienvenida a:  
*"¡Hola! Bienvenido a La Esquina. Escribe menu, pedido o reservar."*  
Guardas. El **siguiente** cliente que escriba recibirá ese texto.

---

## 7. Resumen rápido

| Quiero… | Dónde en la app |
|---------|-----------------|
| Ver chats | Pantalla principal |
| Responder | Abrir chat → escribir abajo |
| Confirmar pedido | Barra amarilla en el chat |
| Cambiar precios / productos | Ajustes → Menú |
| Que el bot entienda otras frases | Ajustes → Intents |
| Cambiar textos automáticos | Ajustes → Mensajes |
| Salir | Ajustes → Cerrar sesión |

---

## 8. Lo que NO debes hacer

- No edites archivos Python (`config/prompts.py`, etc.) — eso es solo para desarrolladores.
- No compartas tu PIN del dueño.
- No uses una página web para administrar el bot: **solo esta app móvil**.

---

## 9. Problemas frecuentes

| Problema | Solución |
|----------|----------|
| "Error de conexión" | Verifica que el servidor esté encendido y que la URL en `api_config.dart` sea correcta para tu red |
| No aparecen chats | Un cliente debe escribir primero al número del bot por WhatsApp |
| Los cambios no se ven | Asegúrate de pulsar **Guardar**; el bot usa la config nueva en el **próximo** mensaje |
| PIN incorrecto | Pide al administrador revisar `WHATSBOT_OWNER_PIN` en el servidor |

Para soporte técnico (instalación, URL, ngrok), consulta `docs/FLUTTER_APP.md`.
