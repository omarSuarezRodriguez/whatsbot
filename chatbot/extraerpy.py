#!/usr/bin/env python3
"""
extraerpy.py

Recorre la carpeta donde se encuentra este script, busca todos los archivos
.py (excepto __init__.py) y los copia a una carpeta llamada "archivospy",
conservando exactamente la misma estructura de directorios.

Ejemplo:

proyecto/
│
├── extraerpy.py
├── main.py
├── utils/
│   ├── helper.py
│   └── __init__.py
└── app/
    ├── api.py
    └── models/
        └── user.py

Resultado:

archivospy/
├── main.py
├── utils/
│   └── helper.py
└── app/
    ├── api.py
    └── models/
        └── user.py
"""

from pathlib import Path
import shutil

# Carpeta donde está este script
RAIZ = Path(__file__).resolve().parent

# Carpeta destino
DESTINO = RAIZ / "archivospy"

# Crear carpeta destino
DESTINO.mkdir(exist_ok=True)

# Recorrer todos los .py
for archivo in RAIZ.rglob("*.py"):
    # Ignorar la carpeta de salida
    if DESTINO in archivo.parents:
        continue

    # Ignorar este script
    if archivo.name == "extraerpy.py":
        continue

    # Ignorar __init__.py
    if archivo.name == "__init__.py":
        continue

    # Ruta relativa respecto a la raíz
    ruta_relativa = archivo.relative_to(RAIZ)

    # Ruta destino conservando estructura
    archivo_destino = DESTINO / ruta_relativa

    # Crear carpetas necesarias
    archivo_destino.parent.mkdir(parents=True, exist_ok=True)

    # Copiar archivo
    shutil.copy2(archivo, archivo_destino)

    print(f"Copiado: {ruta_relativa}")

print("\nProceso terminado.")
print(f"Los archivos fueron copiados a: {DESTINO}")