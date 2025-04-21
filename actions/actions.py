from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
from actions.transacciones_io import guardar_transaccion, cargar_transacciones
from rasa_sdk.events import SlotSet
from collections import defaultdict
import json
import os
from datetime import datetime
from collections import Counter, defaultdict
from rasa_sdk.types import DomainDict
from dateparser import parse as parse_fecha_relativa
from actions.transacciones_io import eliminar_transaccion_logicamente
from actions.alertas_io import guardar_alerta
from actions.alertas_io import eliminar_alerta_logicamente
from actions.alertas_io import cargar_alertas
from actions.alertas_io import guardar_todas_las_alertas

def formatear_fecha(fecha: str) -> str:
    try:
        partes = fecha.strip().split("/")
        if len(partes) == 3:
            dia, mes, anio = partes
            meses = {
                "01": "enero", "02": "febrero", "03": "marzo", "04": "abril",
                "05": "mayo", "06": "junio", "07": "julio", "08": "agosto",
                "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre"
            }
            mes_nombre = meses.get(mes.zfill(2), mes)
            return f"{int(dia)} de {mes_nombre} de {anio}"
    except:
        pass
    return fecha

def get_entity(tracker: Tracker, entity_name: str) -> Text:
    entity = next(tracker.get_latest_entity_values(entity_name), None)
    return entity if entity else ""

def parse_monto(monto_raw: str) -> float:
    try:
        monto_limpio = (
            monto_raw.lower()
            .replace("soles", "")
            .replace("sol", "")
            .replace("s/", "")
            .replace("s\\", "")
            .replace("s", "")
            .replace(",", "")
            .strip()
        )
        return float(monto_limpio)
    except Exception as e:
        print(f"[ERROR] No se pudo convertir el monto: '{monto_raw}' → {e}")
        return 0.0

class ActionRegistrarGasto(Action):
    def name(self) -> Text:
        return "action_registrar_gasto"

    def run(self, dispatcher, tracker, domain):
        try:
            texto_usuario = tracker.latest_message.get("text", "").lower()

            # Establecer el tipo en el slot para mantener el contexto
            tipo_actual = tracker.get_slot("tipo") or "gasto"

            monto_raw = get_entity(tracker, "monto") or tracker.get_slot("monto")
            categoria = get_entity(tracker, "categoria") or tracker.get_slot("categoria")
            fecha_raw = get_entity(tracker, "fecha") or tracker.get_slot("fecha")
            medio = get_entity(tracker, "medio") or tracker.get_slot("medio")

            campos_faltantes = []
            if not monto_raw:
                campos_faltantes.append("monto")
            if not categoria:
                campos_faltantes.append("categoría")
            if not medio:
                campos_faltantes.append("medio")

            # Preguntar por los campos faltantes sin guardar aún
            if campos_faltantes:
                mensaje = "Para registrar tu gasto, necesito también:\n"
                for campo in campos_faltantes:
                    if campo == "medio":
                        mensaje += "• ¿Con qué medio realizaste el gasto? (efectivo, débito o crédito)\n"
                    elif campo == "monto":
                        mensaje += "• ¿Cuál fue el monto?\n"
                    elif campo == "categoría":
                        mensaje += "• ¿En qué categoría clasificarías este gasto?\n"

                dispatcher.utter_message(text=mensaje)
                return [
                    SlotSet("tipo", "gasto"),
                    SlotSet("monto", monto_raw),
                    SlotSet("categoria", categoria),
                    SlotSet("fecha", fecha_raw),
                    SlotSet("medio", medio)
                ]

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido. Intenta nuevamente.")
                return []

            # Procesamiento de fecha
            if not fecha_raw:
                fecha_raw = datetime.now().strftime("%d/%m/%Y")
            elif len(fecha_raw.split("/")) == 2:
                fecha_raw += f"/{datetime.now().year}"
            fecha = formatear_fecha(fecha_raw)

            transaccion = {
                "tipo": "gasto",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio
            }

            guardar_transaccion(transaccion)
            mes_actual = transaccion.get("mes", "").lower()

            # Verificar alertas
            alertas = cargar_alertas()
            alertas_activas = [
                a for a in alertas
                if a.get("categoria", "").lower() == categoria.lower()
                and a.get("periodo", "").lower() == mes_actual
            ]

            if alertas_activas:
                limite = float(alertas_activas[0].get("monto", 0))
                transacciones = cargar_transacciones()
                total_categoria = sum(
                    float(t["monto"]) for t in transacciones
                    if t.get("tipo") == "gasto"
                    and t.get("categoria", "").lower() == categoria.lower()
                    and t.get("mes", "").lower() == mes_actual
                )
                if total_categoria > limite:
                    exceso = total_categoria - limite
                    dispatcher.utter_message(
                        text=f"⚠️ Atención: has superado el límite de {limite:.2f} soles en {categoria} para {mes_actual}. "
                             f"Te has excedido por {exceso:.2f} soles."
                    )

            # Confirmación clara
            mensaje = (
                f"💸 Gasto registrado:\n"
                f"• Monto: {monto:.2f} soles\n"
                f"• Categoría: {categoria}\n"
                f"• Fecha: {fecha}\n"
                f"• Medio: {medio}\n\n"
                f"¿Deseas registrar otro gasto o consultar tu saldo?"
            )

            dispatcher.utter_message(text=mensaje)

            return [
                SlotSet("tipo", None),
                SlotSet("sugerencia_pendiente", "action_consultar_saldo"),
                SlotSet("categoria", None),
                SlotSet("monto", None),
                SlotSet("fecha", None),
                SlotSet("medio", None)
            ]

        except Exception as e:
            print(f"[ERROR] Fallo en action_registrar_gasto: {e}")
            dispatcher.utter_message(text="Ocurrió un error al registrar tu gasto. Por favor, intenta nuevamente.")
            return []

class ActionRegistrarIngreso(Action):
    def name(self) -> Text:
        return "action_registrar_ingreso"

    def run(self, dispatcher, tracker, domain):
        try:
            texto_usuario = tracker.latest_message.get("text", "").lower()
            tipo_actual = tracker.get_slot("tipo") or "ingreso"

            monto_raw = get_entity(tracker, "monto") or tracker.get_slot("monto")
            categoria = get_entity(tracker, "categoria") or tracker.get_slot("categoria")
            fecha_raw = get_entity(tracker, "fecha") or tracker.get_slot("fecha")
            medio = get_entity(tracker, "medio") or tracker.get_slot("medio")

            campos_faltantes = []
            if not monto_raw:
                campos_faltantes.append("monto")
            if not categoria:
                campos_faltantes.append("categoría")
            if not medio:
                campos_faltantes.append("medio")

            if campos_faltantes:
                mensaje = "Para registrar tu ingreso, necesito también:\n"
                for campo in campos_faltantes:
                    if campo == "medio":
                        mensaje += "• ¿Con qué medio recibiste el ingreso? (efectivo, tarjeta de débito, etc.)\n"
                    elif campo == "monto":
                        mensaje += "• ¿Cuál fue el monto?\n"
                    elif campo == "categoría":
                        mensaje += "• ¿Qué tipo de ingreso fue? (sueldo, venta, etc.)\n"

                dispatcher.utter_message(text=mensaje)
                return [
                    SlotSet("tipo", "ingreso"),
                    SlotSet("monto", monto_raw),
                    SlotSet("categoria", categoria),
                    SlotSet("fecha", fecha_raw),
                    SlotSet("medio", medio)
                ]

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido. Intenta nuevamente.")
                return []

            # Procesamiento de fecha
            if not fecha_raw:
                fecha_raw = datetime.now().strftime("%d/%m/%Y")
            elif len(fecha_raw.split("/")) == 2:
                fecha_raw += f"/{datetime.now().year}"
            fecha = formatear_fecha(fecha_raw)

            transaccion = {
                "tipo": "ingreso",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio
            }

            guardar_transaccion(transaccion)

            mensaje = (
                f"💰 Ingreso registrado:\n"
                f"• Monto: {monto:.2f} soles\n"
                f"• Categoría: {categoria}\n"
                f"• Fecha: {fecha}\n"
                f"• Medio: {medio}\n\n"
                f"¿Deseas registrar otro ingreso o consultar tu saldo?"
            )

            dispatcher.utter_message(text=mensaje)

            return [
                SlotSet("tipo", None),
                SlotSet("sugerencia_pendiente", "action_consultar_saldo"),
                SlotSet("categoria", None),
                SlotSet("monto", None),
                SlotSet("fecha", None),
                SlotSet("medio", None)
            ]

        except Exception as e:
            print(f"[ERROR] Fallo en action_registrar_ingreso: {e}")
            dispatcher.utter_message(text="Ocurrió un error al registrar tu ingreso. Por favor, intenta nuevamente.")
            return []

class ActionConsultarSaldo(Action):
    def name(self) -> Text:
        return "action_consultar_saldo"

    def run(self, dispatcher, tracker, domain):
        try:
            transacciones = cargar_transacciones()
            medio = next(tracker.get_latest_entity_values("medio"), None)

            if medio:
                transacciones = [t for t in transacciones if t.get("medio") == medio]

            total_ingresos = sum(float(t["monto"]) for t in transacciones if t["tipo"] == "ingreso")
            total_gastos = sum(float(t["monto"]) for t in transacciones if t["tipo"] == "gasto")
            saldo = total_ingresos - total_gastos

            if total_ingresos == 0 and total_gastos == 0:
                if medio:
                    msg = f"No se han registrado ingresos ni gastos con {medio}. ¿Deseas registrar uno ahora?"
                else:
                    msg = "Aún no se han registrado ingresos ni gastos. ¿Deseas registrar uno ahora?"
                dispatcher.utter_message(text=msg)
                return []
            else:
                if medio:
                    msg = f"Tu saldo actual en {medio} es de {saldo:.2f} soles. ¿Quieres ver tu historial o consultar tus ingresos?"
                else:
                    msg = f"Tu saldo actual es de {saldo:.2f} soles. ¿Quieres ver tu historial o consultar tus ingresos?"
                dispatcher.utter_message(text=msg)
                return [SlotSet("sugerencia_pendiente", "action_ver_historial_completo")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_consultar_saldo: {e}")
            dispatcher.utter_message(text="Ocurrió un error al consultar tu saldo.")
            return []

class ActionVerHistorialCompleto(Action):
    def name(self) -> Text:
        return "action_ver_historial_completo"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            from actions.transacciones_io import cargar_transacciones
            from actions import formatear_fecha

            transacciones = cargar_transacciones(filtrar_activos=True)
            periodo = get_entity(tracker, "periodo")

            transacciones_filtradas = [
                t for t in transacciones if t.get("tipo") in ["ingreso", "gasto"]
            ]

            if periodo:
                periodo = periodo.lower()
                transacciones_filtradas = [
                    t for t in transacciones_filtradas
                    if periodo in str(t.get("fecha", "")).lower() or periodo == str(t.get("mes", "")).lower()
                ]

            if not transacciones_filtradas:
                mensaje = f"No se encontraron movimientos registrados para el periodo {periodo}." if periodo else "No se encontraron transacciones registradas."
                dispatcher.utter_message(text=mensaje)
                return []

            mensaje = "📋 Estas son tus transacciones registradas"
            if periodo:
                mensaje += f" para el periodo {periodo}"
            mensaje += ":\n"

            for t in transacciones_filtradas:
                tipo = t.get("tipo", "transacción")
                monto = t.get("monto", 0)
                categoria = t.get("categoria", "sin categoría")
                fecha = t.get("fecha", "")
                medio = t.get("medio", "")

                linea = f"- {tipo}: {monto:.2f} soles en {categoria}"
                if fecha:
                    try:
                        linea += f" el {formatear_fecha(fecha)}"
                    except Exception:
                        linea += f" el {fecha}"
                if medio:
                    linea += f" con {medio}"
                mensaje += linea + "\n"

            mensaje += "\n¿Deseas registrar algo nuevo o consultar tu resumen mensual?"
            dispatcher.utter_message(text=mensaje)

            return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_ver_historial_completo: {e}")
            dispatcher.utter_message(text="Ocurrió un error al mostrar tu historial. Por favor, intenta nuevamente.")
            return []

from collections import Counter, defaultdict

class ActionAnalizarGastos(Action):
    def name(self) -> Text:
        return "action_analizar_gastos"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        from collections import Counter, defaultdict
        from datetime import datetime
        import re

        transacciones = cargar_transacciones(filtrar_activos=True)
        texto_usuario = tracker.latest_message.get("text", "").lower()

        # 🔍 Extraer entidades
        periodo_raw = get_entity(tracker, "periodo")
        categoria = get_entity(tracker, "categoria")

        # 📆 Normalizar periodo
        periodo = None
        if "este mes" in texto_usuario and not periodo_raw:
            periodo = f"{datetime.now().strftime('%B').lower()} de {datetime.now().year}"
        elif periodo_raw:
            match = re.search(r"([a-záéíóúñ]+)(?:\s+de\s+)?(\d{4})?", periodo_raw.lower())
            if match:
                mes = match.group(1).strip()
                año = match.group(2) or str(datetime.now().year)
                periodo = f"{mes} de {año}"
            else:
                periodo = periodo_raw.strip().lower()

        # 🎯 Filtrar solo gastos válidos
        gastos = [
            t for t in transacciones
            if t.get("tipo") == "gasto" and t.get("monto") and t.get("categoria")
        ]

        if periodo:
            gastos = [g for g in gastos if g.get("periodo", "").lower() == periodo.lower()]

        if not gastos:
            if periodo:
                dispatcher.utter_message(text=f"No se encontraron gastos registrados para el periodo *{periodo}*.")
            else:
                dispatcher.utter_message(text="No se han registrado gastos aún. ¿Deseas ingresar uno?")
            return []

        # ⚠️ Advertencia si hay registros sin categoría
        sin_categoria = [g for g in gastos if not g.get("categoria")]
        if sin_categoria:
            dispatcher.utter_message(
                text=f"⚠️ Se encontraron {len(sin_categoria)} gasto(s) sin categoría. Esto podría afectar el análisis."
            )

        # 📂 Si se indicó categoría específica
        if categoria:
            gastos_categoria = [g for g in gastos if categoria.lower() in g.get("categoria", "").lower()]
            total_categoria = sum(float(g["monto"]) for g in gastos_categoria)

            if not gastos_categoria:
                dispatcher.utter_message(
                    text=f"No se encontraron gastos en la categoría *{categoria}*" +
                         (f" durante *{periodo}*" if periodo else "") + "."
                )
            else:
                dispatcher.utter_message(
                    text=f"Has gastado un total de *{total_categoria:.2f} soles* en *{categoria}*" +
                         (f" durante *{periodo}*" if periodo else "") + "."
                )

            return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

        # 📊 Agrupar por categoría y calcular totales
        categorias_sumadas = defaultdict(float)
        for g in gastos:
            nombre = g.get("categoria", "Sin categoría").strip().lower()
            categorias_sumadas[nombre] += float(g.get("monto", 0))

        total_gasto = sum(categorias_sumadas.values())
        top_categorias = sorted(categorias_sumadas.items(), key=lambda x: x[1], reverse=True)[:3]

        # 🧾 Generar mensaje principal
        respuesta = "🧾 *Análisis de tus hábitos de consumo*"
        if periodo:
            respuesta += f" durante *{periodo}*"
        respuesta += ":\n\n"

        respuesta += "📊 *Categorías con mayor gasto*:\n"
        for cat, total in top_categorias:
            porcentaje = (total / total_gasto) * 100
            respuesta += f"• {cat.title()}: {total:.2f} soles ({porcentaje:.1f}%)\n"

        respuesta += f"\n💸 *Total gastado*: *{total_gasto:.2f} soles*\n"

        # 🧾 Ejemplos recientes (ordenados por fecha)
        def parse_fecha(fecha_str):
            try:
                return datetime.strptime(fecha_str, "%Y-%m-%d")
            except:
                return datetime.min

        recientes = sorted(gastos, key=lambda x: parse_fecha(x.get("fecha", "")), reverse=True)[:5]

        respuesta += "\n📋 *Ejemplos recientes*:\n"
        for g in recientes:
            fecha = g.get("fecha", "sin fecha")
            monto = g.get("monto", 0)
            cat = g.get("categoria", "Sin categoría")
            respuesta += f"- {cat.title()}: {monto:.2f} soles ({fecha})\n"

        respuesta += "\n¿Quieres comparar tus gastos entre meses o configurar una alerta?"
        dispatcher.utter_message(text=respuesta.strip())

        return [SlotSet("sugerencia_pendiente", "action_comparar_meses")]

def extraer_mes(fecha: str) -> str:
    meses = {
        "01": "enero", "02": "febrero", "03": "marzo", "04": "abril",
        "05": "mayo", "06": "junio", "07": "julio", "08": "agosto",
        "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre"
    }
    try:
        partes = fecha.strip().split("/")
        if len(partes) >= 2:
            mes = partes[1].lower().zfill(2)
            if mes in meses:
                return meses[mes]  # si es numérico
            return mes  # si ya está como nombre, lo devolvemos directamente
    except:
        pass
    return ""

class ActionCompararMeses(Action):
    def name(self) -> Text:
        return "action_comparar_meses"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            from datetime import datetime
            transacciones = cargar_transacciones(filtrar_activos=True)
            texto = tracker.latest_message.get("text", "").lower()

            tipo = "ingreso" if "ingreso" in texto or "ingresos" in texto else "gasto"
            año_actual = str(datetime.now().year)

            posibles_meses = [
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
            ]

            # 🔍 Normalizar conectores comunes
            texto_normalizado = texto
            for sep in [" y ", " o ", " vs ", " versus ", " entre ", "contra", "comparar "]:
                texto_normalizado = texto_normalizado.replace(sep, " y ")

            # 📅 Buscar dos periodos explícitos (mes y año)
            matches = re.findall(rf"({'|'.join(posibles_meses)})(?:\s+de)?\s+(\d{{4}})", texto_normalizado)
            if len(matches) == 2:
                periodo1 = f"{matches[0][0]} de {matches[0][1]}"
                periodo2 = f"{matches[1][0]} de {matches[1][1]}"

                if periodo1 == periodo2:
                    dispatcher.utter_message(text="Por favor, proporciona dos periodos diferentes para la comparación.")
                    return []

                total = defaultdict(float)
                for t in transacciones:
                    if t.get("tipo") != tipo:
                        continue
                    if t.get("periodo", "").lower() == periodo1:
                        total[periodo1] += float(t.get("monto", 0))
                    elif t.get("periodo", "").lower() == periodo2:
                        total[periodo2] += float(t.get("monto", 0))

                v1, v2 = total.get(periodo1, 0), total.get(periodo2, 0)
                if v1 == 0 and v2 == 0:
                    dispatcher.utter_message(
                        text=f"No se encontraron {tipo}s registrados para *{periodo1}* ni *{periodo2}*."
                    )
                    return []

                mensaje = f"📊 Comparativa de *{tipo}s*:\n"
                mensaje += f"- {periodo1.capitalize()}: {v1:.2f} soles\n"
                mensaje += f"- {periodo2.capitalize()}: {v2:.2f} soles\n"

                if v1 > v2:
                    mensaje += f"⬅️ En *{periodo1}* tuviste más {tipo}s que en *{periodo2}*."
                elif v2 > v1:
                    mensaje += f"➡️ En *{periodo2}* tuviste más {tipo}s que en *{periodo1}*."
                else:
                    mensaje += f"✅ Tus {tipo}s fueron iguales en ambos periodos."

                dispatcher.utter_message(text=mensaje)
                dispatcher.utter_message(text="¿Quieres configurar un presupuesto o consultar tus ingresos recientes?")
                return [SlotSet("sugerencia_pendiente", "action_crear_configuracion")]

            # 🧠 No hay 2 periodos explícitos → Asumir análisis de todo el año
            elif "en qué mes" in texto:
                totales_por_mes = defaultdict(float)
                for t in transacciones:
                    if t.get("tipo") != tipo:
                        continue
                    mes = t.get("mes", "").lower()
                    año = str(t.get("año"))
                    if mes in posibles_meses and año == año_actual:
                        totales_por_mes[mes] += float(t.get("monto", 0))

                if not totales_por_mes:
                    dispatcher.utter_message(text=f"No se encontraron {tipo}s registrados durante el año {año_actual}.")
                    return []

                mes_max = max(totales_por_mes.items(), key=lambda x: x[1])[0]
                monto_max = totales_por_mes[mes_max]

                mensaje = (
                    f"📅 En el año {año_actual}, el mes con mayor {tipo} fue *{mes_max}* "
                    f"con un total de *{monto_max:.2f} soles*."
                )
                dispatcher.utter_message(text=mensaje)
                dispatcher.utter_message(text="¿Deseas comparar otros periodos o revisar tu historial completo?")
                return [SlotSet("sugerencia_pendiente", "action_ver_historial_completo")]

            else:
                dispatcher.utter_message(
                    text="Por favor, indícame dos periodos válidos con mes y año. Ejemplo: 'marzo de 2024 y abril de 2024'."
                )
                return []

        except Exception as e:
            print(f"[ERROR] Fallo en action_comparar_meses: {e}")
            dispatcher.utter_message(
                text="Ocurrió un error al comparar los meses. Intenta de nuevo usando dos periodos como 'marzo de 2024 y abril de 2024'."
            )
            return []

from dateparser import parse as parse_fecha_relativa

class ActionConsultarInformacionFinanciera(Action):
    def name(self) -> Text:
        return "action_consultar_informacion_financiera"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        from datetime import datetime
        from collections import defaultdict

        transacciones = cargar_transacciones(filtrar_activos=True)
        texto = tracker.latest_message.get("text", "").strip().lower()
        tokens = texto.split()

        tipo = get_entity(tracker, "tipo") or tracker.get_slot("tipo")
        categoria = get_entity(tracker, "categoria") or tracker.get_slot("categoria")
        medio = get_entity(tracker, "medio") or tracker.get_slot("medio")
        fecha_raw = get_entity(tracker, "fecha") or tracker.get_slot("fecha")
        periodo_raw = get_entity(tracker, "periodo") or tracker.get_slot("periodo")

        # 🧠 Verificar si la frase parece ambigua o incompleta
        verbos_clave = [
            "gasté", "gaste", "pagué", "ingresé", "recibí", "consulté", "usé",
            "muestra", "consultar", "ver", "registré", "gané", "cuánto", "invertí"
        ]
        contiene_verbo = any(v in texto for v in verbos_clave)

        if not contiene_verbo and len(tokens) <= 5:
            dispatcher.utter_message(text=f"No logré entender tu intención con: “{texto}”. ¿Podrías reformularlo?")
            return [
                SlotSet("sugerencia_pendiente", "action_ayuda_general"),
                FollowupAction("action_entrada_no_entendida")
            ]

        # 📆 Interpretar fecha relativa como "lunes pasado"
        fecha = None
        if fecha_raw:
            try:
                fecha_parseada = parse_fecha_relativa(fecha_raw)
                fecha = fecha_parseada.strftime("%d/%m/%Y") if fecha_parseada else fecha_raw
            except:
                fecha = fecha_raw

        # 📅 Normalizar periodo
        periodo = None
        if periodo_raw:
            match = re.search(r"([a-záéíóúñ]+)(?:\s+de\s+)?(\d{4})?", periodo_raw.lower())
            if match:
                mes = match.group(1).strip()
                año = match.group(2) or str(datetime.now().year)
                periodo = f"{mes} de {año}"
            else:
                periodo = periodo_raw.strip().lower()

        # 🔍 Filtrar transacciones
        resultados = []
        for t in transacciones:
            if tipo and t.get("tipo") != tipo:
                continue
            if medio and t.get("medio", "").lower() != medio.lower():
                continue
            if categoria and categoria.lower() not in t.get("categoria", "").lower():
                continue
            if periodo and periodo.lower() != t.get("periodo", "").lower():
                continue
            if fecha and fecha not in t.get("fecha", ""):
                continue
            resultados.append(t)

        total = sum(t["monto"] for t in resultados)

        # 🚫 Si no hay resultados
        if not resultados:
            if categoria and periodo:
                dispatcher.utter_message(
                    text=f"No se encontraron {tipo}s registrados en la categoría *{categoria}* durante *{periodo}*."
                )
            elif tipo and periodo:
                dispatcher.utter_message(
                    text=f"No se encontraron {tipo}s registrados durante *{periodo}*."
                )
            elif tipo:
                dispatcher.utter_message(
                    text=f"No se encontraron registros de tipo *{tipo}*."
                )
            else:
                dispatcher.utter_message(text="No se encontraron registros financieros con los criterios proporcionados.")
            return []

        # ✅ Generar respuesta
        if categoria and periodo:
            msg = f"Tu {tipo} total en la categoría *{categoria}* durante *{periodo}* es de *{total:.2f} soles*."
        elif tipo and periodo:
            msg = f"Tu {tipo} total durante *{periodo}* es de *{total:.2f} soles*."
        elif tipo:
            resumen_cat = defaultdict(float)
            for t in resultados:
                resumen_cat[t.get("categoria", "Sin categoría")] += t["monto"]

            msg = f"📊 Tu resumen de *{tipo}s*"
            if periodo:
                msg += f" durante *{periodo}*"
            msg += " por categoría:\n"
            for cat, monto in resumen_cat.items():
                msg += f"- {cat}: {monto:.2f} soles\n"
        elif medio:
            msg = f"Total registrado usando *{medio}*: *{total:.2f} soles*."
        else:
            msg = f"📊 Total filtrado: *{total:.2f} soles*."

        dispatcher.utter_message(text=msg.strip())
        return [SlotSet("sugerencia_pendiente", "action_analizar_gastos")]
        
class ActionEntradaNoEntendida(Action):
    def name(self) -> Text:
        return "action_entrada_no_entendida"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            texto = tracker.latest_message.get("text", "")
            intent = tracker.latest_message.get("intent", {}).get("name", "")
            entidades_detectadas = [e.get("entity") for e in tracker.latest_message.get("entities", [])]

            # ⛔️ Evitar guardar afirmaciones, negaciones o saludos como entradas no entendidas
            if intent not in ["entrada_no_entendida", "nlu_fallback"]:
                dispatcher.utter_message(text="No logré entender completamente tu mensaje. ¿Podrías reformularlo o dar más detalles?")
                return []

            # 🧠 Guardar solo si el intent es realmente no entendido
            guardar_transaccion({
                "tipo": "entrada_no_entendida",
                "descripcion": texto,
                "timestamp": datetime.now().isoformat()
            })

            if entidades_detectadas:
                mensaje = (
                    f"No logré entender completamente tu mensaje: “{texto}”.\n\n"
                    f"📌 Detecté estas entidades: *{', '.join(entidades_detectadas)}*.\n"
                    f"¿Podrías darme más contexto o reformularlo?"
                )
            else:
                mensaje = (
                    f"No logré entender tu mensaje: “{texto}”.\n\n"
                    f"👉 Prueba con frases como:\n"
                    f"- “Registré un gasto de 100 soles en comida”\n"
                    f"- “¿Cuánto ingresé en marzo?”\n"
                    f"- “Configura una alerta de 300 soles para abril”\n"
                )

            dispatcher.utter_message(text=mensaje)
            dispatcher.utter_message(text="Estoy aquí para ayudarte con tus finanzas. ¿Qué te gustaría hacer ahora?")

            return [SlotSet("sugerencia_pendiente", "action_ayuda_general")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_entrada_no_entendida: {e}")
            dispatcher.utter_message(text="Ocurrió un error procesando tu mensaje. Por favor, intenta nuevamente.")
            return []

from actions.alertas_io import guardar_alerta

class ActionResetearCategoriaGastos(Action):
    def name(self) -> Text:
        return "action_resetear_categoria_gastos"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        categoria = get_entity(tracker, "categoria")
        periodo = get_entity(tracker, "periodo")
        texto_usuario = tracker.latest_message.get("text", "").lower()

        if not categoria or not periodo:
            dispatcher.utter_message(text="Necesito la categoría y el mes con año para resetear los gastos.")
            return []

        # Normalizar periodo
        match = re.search(r"([a-záéíóúñ]+)(?:\s+de\s+)?(\d{4})", periodo.lower())
        if not match:
            dispatcher.utter_message(text="El formato del periodo debe ser 'marzo de 2025', por ejemplo.")
            return []

        mes = match.group(1).strip().lower()
        año = int(match.group(2))

        transacciones = cargar_transacciones()
        ahora = datetime.now().isoformat()
        modificadas = 0

        for t in transacciones:
            if (
                t.get("tipo") == "gasto"
                and t.get("categoria", "").lower() == categoria.lower()
                and t.get("mes", "").lower() == mes
                and t.get("año") == año
                and t.get("status", 1) == 1
            ):
                t["status"] = 0
                t["timestamp_modificacion"] = ahora
                modificadas += 1

        # Agregar registro de reinicio
        transacciones.append({
            "tipo": "reinicio",
            "categoria": categoria,
            "mes": mes,
            "año": año,
            "motivo": "reseteo de gastos",
            "timestamp": ahora,
            "status": 1
        })

        # Guardar en transacciones.json
        with open(RUTA_TRANSACCIONES, "w", encoding="utf-8") as f:
            json.dump(transacciones, f, ensure_ascii=False, indent=2)

        if modificadas > 0:
            mensaje = f"🔄 Se han reseteado {modificadas} registros de gasto en *{categoria}* para *{mes} {año}*."
        else:
            mensaje = f"No se encontraron gastos activos en *{categoria}* para *{mes} {año}*, pero el reinicio ha sido registrado."

        dispatcher.utter_message(text=mensaje)
        return []

import actions.alertas_io as alertas_io

class ActionCrearConfiguracion(Action):
    def name(self) -> Text:
        return "action_crear_configuracion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        categoria = get_entity(tracker, "categoria")
        monto = get_entity(tracker, "monto")
        periodo = get_entity(tracker, "periodo")
        texto_usuario = tracker.latest_message.get("text", "").lower()

        if not categoria or not monto or not periodo:
            dispatcher.utter_message(text="Necesito la categoría, el monto y el mes con año para crear una configuración.")
            return []

        try:
            monto_float = parse_monto(monto)
        except Exception:
            dispatcher.utter_message(text="El monto ingresado no es válido.")
            return []

        if monto_float <= 0:
            dispatcher.utter_message(text="El monto debe ser mayor que cero.")
            return []

        periodo = periodo.lower().strip()

        # 🔍 Extraer mes y año del periodo
        match = re.search(r"([a-záéíóúñ]+)(?:\s+de\s+)?(\d{4})", periodo)
        if not match:
            dispatcher.utter_message(text="El formato del periodo debe ser 'abril de 2024', por ejemplo.")
            return []

        mes = match.group(1).strip().lower()
        año = int(match.group(2))
        periodo_normalizado = f"{mes} de {año}"

        # Verificar si ya existe una alerta activa con la misma clave
        alertas = cargar_alertas()
        ya_existe = any(
            a["categoria"].lower() == categoria.lower() and a["periodo"].lower() == periodo_normalizado
            for a in alertas
        )

        if ya_existe:
            dispatcher.utter_message(
                text=f"Ya existe una alerta activa para *{categoria}* en *{periodo_normalizado}*. Usa 'modificar' si deseas actualizarla."
            )
            return []

        nueva_alerta = {
            "categoria": categoria,
            "monto": monto_float,
            "periodo": periodo_normalizado,
            "mes": mes,
            "año": año,
            "timestamp": datetime.now().isoformat(),
            "status": 1
        }

        guardar_alerta(nueva_alerta)

        dispatcher.utter_message(
            text=f"✅ Se ha creado una alerta de *{monto_float} soles* para *{categoria}* en *{periodo_normalizado}*."
        )

        return []
            
class ActionModificarConfiguracion(Action):
    def name(self) -> Text:
        return "action_modificar_configuracion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        categoria = get_entity(tracker, "categoria")
        monto = get_entity(tracker, "monto")
        periodo = get_entity(tracker, "periodo")
        texto_usuario = tracker.latest_message.get("text", "").lower()

        if not categoria or not monto or not periodo:
            dispatcher.utter_message(text="Para modificar una configuración necesito la categoría, el monto y el mes con año.")
            return []

        try:
            monto_float = parse_monto(monto)
        except Exception:
            dispatcher.utter_message(text="El monto proporcionado no es válido.")
            return []

        if monto_float <= 0:
            dispatcher.utter_message(text="El monto debe ser mayor a cero para configurar una alerta.")
            return []

        # Normalizar periodo
        match = re.search(r"([a-záéíóúñ]+)(?:\s+de\s+)?(\d{4})", periodo.lower())
        if not match:
            dispatcher.utter_message(text="El formato del periodo debe ser 'abril de 2024', por ejemplo.")
            return []

        mes = match.group(1).strip().lower()
        año = int(match.group(2))
        periodo_normalizado = f"{mes} de {año}"

        # Buscar alerta existente
        alertas = cargar_alertas()
        alerta_existente = next((
            a for a in alertas
            if a.get("categoria", "").lower() == categoria.lower()
            and a.get("periodo", "").lower() == periodo_normalizado
            and a.get("status", 1) == 1
        ), None)

        if alerta_existente:
            # Guardar información actual y nueva para confirmar modificación
            return [
                SlotSet("categoria", categoria),
                SlotSet("monto", monto_float),
                SlotSet("periodo", periodo_normalizado),
                SlotSet("mes", mes),
                SlotSet("año", año),
                SlotSet("alerta_original", json.dumps(alerta_existente)),
                SlotSet("sugerencia_pendiente", "confirmar_modificacion_alerta")
            ]
        else:
            dispatcher.utter_message(
                text=f"No encontré una alerta activa para *{categoria}* en *{periodo_normalizado}*. ¿Deseas crear una nueva alerta?"
            )
            return [
                SlotSet("categoria", categoria),
                SlotSet("monto", monto_float),
                SlotSet("periodo", periodo_normalizado),
                SlotSet("mes", mes),
                SlotSet("año", año),
                SlotSet("sugerencia_pendiente", "action_crear_configuracion")
            ]

class ActionConfirmarModificacionAlerta(Action):
    def name(self) -> Text:
        return "confirmar_modificacion_alerta"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        categoria = tracker.get_slot("categoria")
        monto = tracker.get_slot("monto")
        periodo = tracker.get_slot("periodo")

        # Verificar si existe alerta activa
        alertas = cargar_alertas()
        alerta_existente = next((
            a for a in alertas
            if a.get("categoria", "").lower() == categoria.lower()
            and a.get("periodo", "").lower() == periodo.lower()
            and a.get("status", 1) == 1
        ), None)

        if not alerta_existente:
            dispatcher.utter_message(text="La alerta a modificar ya no está activa o no existe.")
            return []

        # Preparar mensaje de confirmación
        mensaje = (
            f"Tienes esta alerta activa:\n"
            f"• Categoría: {alerta_existente['categoria']}\n"
            f"• Monto actual: {alerta_existente['monto']:.2f} soles\n"
            f"• Periodo: {alerta_existente['periodo']}\n\n"
            f"¿Deseas actualizarla a:\n"
            f"• Monto nuevo: {monto:.2f} soles?\n\n"
            f"Responde con 'sí' para confirmar o 'no' para cancelar."
        )
        dispatcher.utter_message(text=mensaje)

        return [
            SlotSet("alerta_original", json.dumps(alerta_existente))  # para que luego pueda ser modificada
        ]

class ActionEjecutarModificacionAlerta(Action):
    def name(self) -> Text:
        return "action_ejecutar_modificacion_alerta"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            categoria = tracker.get_slot("categoria")
            monto = tracker.get_slot("monto")
            periodo = tracker.get_slot("periodo")
            alerta_json = tracker.get_slot("alerta_original")

            if not (categoria and monto and periodo and alerta_json):
                dispatcher.utter_message(text="No se pudo completar la modificación porque faltan datos.")
                return []

            alerta_original = json.loads(alerta_json)
            alertas = cargar_alertas()
            ahora = datetime.now()

            # Desactivar la alerta original
            for alerta in alertas:
                if (alerta.get("categoria", "").lower() == alerta_original.get("categoria", "").lower() and
                        alerta.get("periodo", "").lower() == alerta_original.get("periodo", "").lower() and
                        alerta.get("status", 1) == 1):
                    alerta["status"] = 0
                    alerta["timestamp_modificacion"] = ahora.isoformat()

            # Crear nueva alerta
            nueva_alerta = {
                "categoria": categoria,
                "monto": float(monto),
                "periodo": periodo,
                "status": 1,
                "timestamp": ahora.isoformat()
            }
            alertas.append(nueva_alerta)

            # Guardar en archivo
            with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
                json.dump(alertas, f, ensure_ascii=False, indent=2)

            dispatcher.utter_message(
                text=f"✅ Alerta modificada correctamente:\n• Categoría: {categoria}\n"
                     f"• Nuevo monto: {monto} soles\n• Periodo: {periodo}"
            )

            return [
                SlotSet("categoria", None),
                SlotSet("monto", None),
                SlotSet("periodo", None),
                SlotSet("alerta_original", None),
                SlotSet("sugerencia_pendiente", None),
            ]

        except Exception as e:
            print(f"[ERROR] Fallo en action_ejecutar_modificacion_alerta: {e}")
            dispatcher.utter_message(text="Hubo un error al intentar modificar la alerta. Intenta nuevamente.")
            return []

def desactivar_alerta(categoria: str, periodo: str):
    alertas = cargar_alertas()
    for alerta in alertas:
        if alerta["categoria"].lower() == categoria.lower() and alerta["periodo"].lower() == periodo.lower():
            alerta["status"] = 0
    guardar_todas_las_alertas(alertas)

class ActionEliminarConfiguracion(Action):
    def name(self) -> Text:
        return "action_eliminar_configuracion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        categoria = get_entity(tracker, "categoria")
        periodo = get_entity(tracker, "periodo")
        texto_usuario = tracker.latest_message.get("text", "").lower()

        if not categoria or not periodo:
            dispatcher.utter_message(text="Necesito la categoría y el mes con año para eliminar una configuración.")
            return []

        periodo = periodo.lower().strip()
        alertas = cargar_alertas()
        alerta = next((
            a for a in alertas
            if a.get("categoria", "").lower() == categoria.lower()
            and a.get("periodo", "").lower() == periodo
            and a.get("status", 1) == 1
        ), None)

        if not alerta:
            dispatcher.utter_message(text=f"No encontré ninguna alerta activa para *{categoria}* en *{periodo}*.")
            return []

        mensaje = (
            f"🔔 Se encontró esta alerta activa:\n"
            f"• Categoría: {alerta['categoria']}\n"
            f"• Monto: {alerta['monto']:.2f} soles\n"
            f"• Periodo: {alerta['periodo']}\n\n"
            f"¿Estás seguro de que deseas eliminarla?"
        )
        dispatcher.utter_message(text=mensaje)

        return [
            SlotSet("categoria", categoria),
            SlotSet("periodo", periodo),
            SlotSet("sugerencia_pendiente", "confirmar_eliminacion_alerta")
        ]

class ActionConfirmarEliminacionAlerta(Action):
    def name(self) -> Text:
        return "confirmar_eliminacion_alerta"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        intent_confirmacion = tracker.latest_message.get("intent", {}).get("name")
        categoria = tracker.get_slot("categoria")
        periodo = tracker.get_slot("periodo")

        if intent_confirmacion != "affirm":
            dispatcher.utter_message(text="Perfecto, no se ha eliminado la alerta.")
            return [SlotSet("sugerencia_pendiente", None)]

        alertas = cargar_alertas()
        encontrado = False

        for alerta in alertas:
            if alerta.get("categoria", "").lower() == categoria.lower() and alerta.get("periodo", "").lower() == periodo.lower() and alerta.get("status", 1) == 1:
                alerta["status"] = 0
                alerta["timestamp_modificacion"] = datetime.now().isoformat()
                encontrado = True

        if encontrado:
            with open(RUTA_ALERTAS, "w", encoding="utf-8") as f:
                json.dump(alertas, f, ensure_ascii=False, indent=2)

            dispatcher.utter_message(
                text=f"🗑️ La alerta para *{categoria}* en *{periodo}* ha sido eliminada correctamente."
            )
        else:
            dispatcher.utter_message(
                text="No se encontró una alerta activa para eliminar."
            )

        return [
            SlotSet("categoria", None),
            SlotSet("periodo", None),
            SlotSet("sugerencia_pendiente", None)
        ]

class ActionConsultarConfiguracion(Action):
    def name(self) -> Text:
        return "action_consultar_configuracion"

    def run(self, dispatcher, tracker, domain):
        alertas = cargar_alertas()

        if not alertas:
            dispatcher.utter_message(text="No tienes configuraciones de alertas registradas.")
            return []

        # Agrupar por última alerta por categoría + periodo
        ultimas_alertas = {}
        for alerta in sorted(alertas, key=lambda x: x.get("timestamp", ""), reverse=True):
            clave = f"{alerta.get('categoria', '').lower()}_{alerta.get('periodo', '').lower()}"
            if clave not in ultimas_alertas:
                ultimas_alertas[clave] = alerta

        mensaje = "Estas son tus configuraciones activas:\n"
        for alerta in ultimas_alertas.values():
            categoria = alerta.get("categoria", "desconocida").capitalize()
            monto = alerta.get("monto", "?")
            periodo = alerta.get("periodo", "")
            fecha = ""
            if alerta.get("timestamp"):
                try:
                    fecha = datetime.fromisoformat(alerta["timestamp"]).strftime(" (registrado el %d/%m/%Y)")
                except:
                    fecha = ""
            mensaje += f"• {categoria}: {monto} soles"
            if periodo:
                mensaje += f" para {periodo}"
            mensaje += f"{fecha}.\n"

        mensaje += "¿Deseas modificar o eliminar alguna de estas configuraciones?"
        dispatcher.utter_message(text=mensaje)
        return []

class ActionEliminarAlerta(Action):
    def name(self) -> Text:
        return "action_eliminar_alerta"

    def run(self, dispatcher, tracker, domain):
        categoria = get_entity(tracker, "categoria")
        periodo = get_entity(tracker, "periodo")

        if not categoria or not periodo:
            dispatcher.utter_message(text="Necesito saber qué alerta deseas eliminar. Por favor indica la categoría y el mes.")
            return []

        condiciones = {
            "categoria": categoria.lower(),
            "periodo": periodo.lower()
        }

        alertas = cargar_alertas()
        coincidencias = [
            a for a in alertas
            if a["categoria"].lower() == condiciones["categoria"] and a["periodo"].lower() == condiciones["periodo"]
        ]

        if not coincidencias:
            dispatcher.utter_message(text=f"No encontré una alerta configurada para {categoria} en {periodo}.")
            return []

        eliminar_alerta_logicamente(condiciones)

        dispatcher.utter_message(text=f"He eliminado la alerta de {categoria} en {periodo}.")
        return []
    
from rasa_sdk.events import FollowupAction

class ActionFollowSuggestion(Action):
    def name(self) -> Text:
        return "action_follow_suggestion"

    def run(self, dispatcher, tracker, domain):
        sugerencia = tracker.get_slot("sugerencia_pendiente")

        if sugerencia:
            dispatcher.utter_message(text="Perfecto, procedo con tu solicitud.")
            return [
                FollowupAction(sugerencia),
                SlotSet("sugerencia_pendiente", None)
            ]
        
        # Si no hay sugerencia válida
        dispatcher.utter_message(text="No tengo ninguna acción pendiente que ejecutar.")
        return []
    
class ActionBienvenida(Action):
    def name(self) -> Text:
        return "action_bienvenida"

    def run(self, dispatcher, tracker, domain):
        # Diccionario de traducción de meses
        meses_es = {
            "January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
            "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
            "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"
        }

        ahora = datetime.now()
        nombre_mes_en = ahora.strftime("%B")
        nombre_mes_es = meses_es.get(nombre_mes_en, nombre_mes_en).capitalize()
        fecha_formateada = f"{ahora.day} de {nombre_mes_es} de {ahora.year}"

        mensaje = (
            f"¡Hola! Bienvenido 👋\n\n"
            f"Hoy es {fecha_formateada} y estoy listo para ayudarte con tus finanzas.\n"
            f"Puedo ayudarte a:\n"
            f"• Registrar ingresos y gastos\n"
            f"• Ver tu historial o saldo\n"
            f"• Configurar alertas\n"
            f"• Comparar tus gastos entre meses\n"
            f"Ejemplo: 'Muéstrame mis gastos de {nombre_mes_es.lower()}'\n"
            f"¿Qué deseas hacer hoy?"
        )

        dispatcher.utter_message(text=mensaje)
        return []

class ActionAyudaGeneral(Action):
    def name(self) -> Text:
        return "action_ayuda_general"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[EventType]:

        mensaje = (
            "🧭 Aquí tienes algunas cosas que puedo hacer:\n"
            "- Registrar ingresos o gastos\n"
            "- Consultar tu saldo o historial\n"
            "- Configurar o eliminar alertas por categoría\n"
            "- Analizar tus hábitos de gasto\n"
            "- Comparar meses\n\n"
            "Ejemplo: *'Gaste 80 soles en comida con débito el 2 de abril'*"
        )
        dispatcher.utter_message(text=mensaje)
        return []

from rasa_sdk.events import SessionStarted, ActionExecuted, EventType

class ActionSessionStart(Action):
    def name(self) -> Text:
        return "action_session_start"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        # Inicio de sesión estándar
        events = [SessionStarted(), ActionExecuted("action_listen")]

        # Aquí llamamos manualmente a tu acción personalizada de bienvenida
        bienvenida = ActionBienvenida()
        bienvenida.run(dispatcher, tracker, domain)

        return events

class ActionNegacion(Action):
    def name(self) -> Text:
        return "action_negacion"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        sugerencia = tracker.get_slot("sugerencia_pendiente")

        # 🧾 Si había una sugerencia pendiente y se niega, entonces se despide
        if sugerencia:
            dispatcher.utter_message(text="Entendido. ¡Hasta luego! Recuerda que puedes volver cuando lo necesites.")
            return [SlotSet("sugerencia_pendiente", None)]

        # ❓ Si no había sugerencia, responde de forma neutra
        dispatcher.utter_message(text="Está bien, dime si deseas hacer otra consulta o registrar algo.")
        return []
