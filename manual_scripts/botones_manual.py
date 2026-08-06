import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from twilio.rest import Client

load_dotenv()

# ============================================================
# CONFIGURACIÓN
# ============================================================

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM = os.getenv("TWILIO_WHATSAPP_FROM")

# Tu número de pruebas
TO = "whatsapp:+35699155990"


# ============================================================
# MODIFICA SOLO ESTA PARTE PARA HACER PRUEBAS
# ============================================================

TEXTO = "¿Qué te parece esta nueva función?"

BOTONES = [
    
    
    
    {
        "title": "🔥 Sivcxv",
        "id": "increiblead"
    },
    {
        "title": "🔥 Sifsdf",
        "id": "increiblesdf"
    },
    {
        "title": "👍 No",
        "id": "esta_bien"
    }
]


# ============================================================
# 1. CREAR CONTENIDO TEMPORAL
# ============================================================

url = "https://content.twilio.com/v1/Content"

contenido = {
    "friendly_name": "prueba_temporal_botones",
    "language": "es",
    "types": {
        "twilio/quick-reply": {
            "body": TEXTO,
            "actions": BOTONES
        }
    }
}

respuesta = requests.post(
    url,
    json=contenido,
    auth=HTTPBasicAuth(ACCOUNT_SID, AUTH_TOKEN)
)

if respuesta.status_code != 201:
    print("❌ Error creando los botones")
    print(respuesta.status_code)
    print(respuesta.text)
    exit()

content_sid = respuesta.json()["sid"]

print("✅ Botones creados temporalmente")
print("Content SID:", content_sid)


# ============================================================
# 2. ENVIAR A WHATSAPP
# ============================================================

client = Client(ACCOUNT_SID, AUTH_TOKEN)

mensaje = client.messages.create(
    from_=FROM,
    to=TO,
    content_sid=content_sid
)

print("✅ Mensaje enviado")
print("Message SID:", mensaje.sid)
print("Estado:", mensaje.status)


# ============================================================
# 3. BORRAR EL CONTENIDO DE TWILIO
# ============================================================

delete_url = f"https://content.twilio.com/v1/Content/{content_sid}"

respuesta_delete = requests.delete(
    delete_url,
    auth=HTTPBasicAuth(ACCOUNT_SID, AUTH_TOKEN)
)

if respuesta_delete.status_code == 204:
    print("🗑️ Contenido temporal eliminado de Twilio")
else:
    print("⚠️ No se pudo eliminar el contenido")
    print(respuesta_delete.status_code)
    print(respuesta_delete.text)