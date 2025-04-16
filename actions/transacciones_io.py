import json
import os
from datetime import datetime

# Ruta absoluta al archivo transacciones.json
RUTA_ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transacciones.json")

def cargar_transacciones(filtrar_activos=True):
    if not os.path.exists(RUTA_ARCHIVO):
        return []
    try:
        with open(RUTA_ARCHIVO, "r", encoding="utf-8") as f:
            transacciones = json.load(f)
            if filtrar_activos:
                transacciones = [t for t in transacciones if t.get("status", 1) == 1]
            return transacciones
    except json.JSONDecodeError:
        return []

def guardar_transaccion(transaccion):
    transacciones = cargar_transacciones(filtrar_activos=False)

    ahora = datetime.now()

    # Si no se proporciona fecha, se usa la actual
    fecha_str = transaccion.get("fecha")
    if not fecha_str:
        fecha_str = ahora.strftime("%d/%m/%Y")
        transaccion["fecha"] = fecha_str

    try:
        if "de" in fecha_str:
            partes = fecha_str.lower().split(" de ")
            dia = int(partes[0])
            mes = partes[1]
            año = ahora.year
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
    transaccion["status"] = transaccion.get("status", 1)  # 👈 importante aquí

    transacciones.append(transaccion)
    with open(RUTA_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(transacciones, f, ensure_ascii=False, indent=2)
        
def eliminar_transaccion_logicamente(condiciones):
    """
    Marca como inactiva (status = 0) la primera transacción que coincida con las condiciones dadas.

    condiciones: diccionario con los campos clave que deben coincidir. Ejemplo:
        {
            "tipo": "alerta",
            "categoria": "ropa",
            "periodo": "abril"
        }
    """
    transacciones = cargar_transacciones(filtrar_activos=False)  # Trae todas, incluso inactivas
    modificada = False

    for transaccion in transacciones:
        if transaccion.get("status", 1) == 0:
            continue  # Ya está desactivada

        coincide = all(transaccion.get(k) == v for k, v in condiciones.items())
        if coincide:
            transaccion["status"] = 0
            transaccion["timestamp_modificacion"] = datetime.now().isoformat()
            modificada = True
            break

    if modificada:
        with open(RUTA_ARCHIVO, "w", encoding="utf-8") as f:
            json.dump(transacciones, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Transacción eliminada lógicamente: {condiciones}")
    else:
        print(f"[WARN] No se encontró ninguna transacción activa que coincida con: {condiciones}")

