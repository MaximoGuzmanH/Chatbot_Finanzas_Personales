import json
import os
from datetime import datetime
from typing import Dict, Any


RUTA_ALERTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alertas.json")

def cargar_alertas():
    if not os.path.exists(RUTA_ALERTAS):
        return []
    try:
        with open(RUTA_ALERTAS, "r", encoding="utf-8") as f:
            alertas = json.load(f)
            return [a for a in alertas if a.get("status", 1) == 1]
    except json.JSONDecodeError:
        return []

def guardar_alerta(alerta):
    alertas = cargar_alertas()
    alerta["timestamp"] = datetime.now().isoformat()
    alerta["status"] = 1
    alertas.append(alerta)
    with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
        json.dump(alertas, f, ensure_ascii=False, indent=2)

def eliminar_alerta_logicamente(condiciones):
    alertas = cargar_alertas()
    modificada = False
    for alerta in alertas:
        if all(alerta.get(k) == v for k, v in condiciones.items()) and alerta.get("status", 1) == 1:
            alerta["status"] = 0
            alerta["timestamp_modificacion"] = datetime.now().isoformat()
            modificada = True
            break
    if modificada:
        with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
            json.dump(alertas, f, ensure_ascii=False, indent=2)

def cargar_alertas(filtrar_activos=True):
    if not os.path.exists(RUTA_ALERTAS):
        return []
    try:
        with open(RUTA_ALERTAS, "r", encoding="utf-8") as f:
            alertas = json.load(f)
            if filtrar_activos:
                alertas = [a for a in alertas if a.get("status", 1) == 1]
            return alertas
    except json.JSONDecodeError:
        return []

def guardar_todas_las_alertas(nuevas_alertas):
    """
    Reemplaza todas las alertas activas por un nuevo conjunto de alertas.
    Las anteriores se marcan como inactivas (status = 0).
    """
    ahora = datetime.now()
    if os.path.exists(RUTA_ALERTAS):
        try:
            with open(RUTA_ALERTAS, "r", encoding="utf-8") as f:
                alertas = json.load(f)
        except json.JSONDecodeError:
            alertas = []
    else:
        alertas = []

    # Desactivar todas las alertas activas
    for alerta in alertas:
        if alerta.get("status", 1) == 1:
            alerta["status"] = 0
            alerta["timestamp_modificacion"] = ahora.isoformat()

    # Agregar nuevas alertas activas
    for nueva in nuevas_alertas:
        nueva_alerta = {
            "categoria": nueva["categoria"],
            "monto": nueva["monto"],
            "periodo": nueva["periodo"],
            "status": 1,
            "timestamp": ahora.isoformat()
        }
        alertas.append(nueva_alerta)

    # Guardar
    with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
        json.dump(alertas, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Se sobrescribieron las alertas activas con {len(nuevas_alertas)} nuevas.")

def actualizar_alerta_existente(condiciones: Dict[str, str], nueva_alerta: Dict[str, Any]) -> bool:
    """
    Desactiva la alerta que coincida con las condiciones y añade la nueva alerta.
    Retorna True si se modificó una alerta, False si no existía.
    """
    ahora = datetime.now().isoformat()

    if os.path.exists(RUTA_ALERTAS):
        try:
            with open(RUTA_ALERTAS, "r", encoding="utf-8") as f:
                alertas = json.load(f)
        except json.JSONDecodeError:
            alertas = []
    else:
        alertas = []

    modificada = False
    for alerta in alertas:
        if (alerta.get("categoria", "").lower() == condiciones["categoria"].lower()
                and alerta.get("periodo", "").lower() == condiciones["periodo"].lower()
                and alerta.get("status", 1) == 1):
            alerta["status"] = 0
            alerta["timestamp_modificacion"] = ahora
            modificada = True

    if modificada:
        nueva_alerta["status"] = 1
        nueva_alerta["timestamp"] = ahora
        alertas.append(nueva_alerta)

        with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
            json.dump(alertas, f, ensure_ascii=False, indent=2)

    return modificada