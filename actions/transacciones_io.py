import json
import os
from datetime import datetime

# Ruta absoluta al archivo transacciones.json
RUTA_ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transacciones.json")

def cargar_transacciones():
    if not os.path.exists(RUTA_ARCHIVO):
        return []
    try:
        with open(RUTA_ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Si el archivo está vacío o mal formado, retornamos una lista vacía
        return []

def guardar_transaccion(transaccion):
    transacciones = cargar_transacciones()

    # Fecha en formato actual
    ahora = datetime.now()

    # Si no se proporciona fecha, se usa la actual
    fecha_str = transaccion.get("fecha")
    if not fecha_str:
        fecha_str = ahora.strftime("%d/%m/%Y")
        transaccion["fecha"] = fecha_str

    # Intentar extraer día, mes y año de la fecha
    try:
        # Soporta fechas tipo '5 de marzo', '05/03/2024', etc.
        if "de" in fecha_str:
            partes = fecha_str.lower().split(" de ")
            dia = int(partes[0])
            mes = partes[1]
            año = ahora.year  # Asumimos año actual
        else:
            dia, mes_num, año = map(int, fecha_str.split("/"))
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                     "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            mes = meses[mes_num - 1]
    except Exception as e:
        print(f"[WARN] No se pudo procesar fecha '{fecha_str}', usando fecha actual. Error: {e}")
        dia = ahora.day
        mes = ahora.strftime("%B").lower()
        año = ahora.year

    # Agregar campos adicionales
    transaccion["dia"] = dia
    transaccion["mes"] = mes
    transaccion["año"] = año
    transaccion["timestamp"] = ahora.isoformat()

    transacciones.append(transaccion)
    with open(RUTA_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(transacciones, f, ensure_ascii=False, indent=2)