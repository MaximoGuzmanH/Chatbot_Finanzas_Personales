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

            monto_raw = get_entity(tracker, "monto") or tracker.get_slot("monto")
            categoria = get_entity(tracker, "categoria") or tracker.get_slot("categoria")
            fecha_raw = get_entity(tracker, "fecha") or tracker.get_slot("fecha")
            medio = get_entity(tracker, "medio") or tracker.get_slot("medio")

            # Validar monto
            if not monto_raw:
                guardar_transaccion({
                    "tipo": "entrada_incompleta",
                    "descripcion": texto_usuario,
                    "timestamp": datetime.now().isoformat()
                })
                dispatcher.utter_message(text="No entendí el monto del gasto. ¿Podrías repetirlo?")
                return []

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido. Inténtalo de nuevo.")
                return []

            # Validar categoría
            if not categoria:
                dispatcher.utter_message(text="¿En qué categoría deseas registrar este gasto?")
                return []

            # Interpretar y estandarizar fecha
            fecha = formatear_fecha(fecha_raw or texto_usuario)

            # Crear objeto de transacción
            transaccion = {
                "tipo": "gasto",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio,
                "descripcion": texto_usuario
            }

            guardar_transaccion(transaccion)
            mes_actual = transaccion.get("mes", "").lower()

            # Verificar alertas activas
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

            # Confirmación al usuario
            respuesta = f"💸 Gasto registrado:\n• Monto: {monto:.2f} soles\n• Categoría: {categoria}"
            if fecha:
                respuesta += f"\n• Fecha: {fecha}"
            if medio:
                respuesta += f"\n• Medio: {medio}"
            respuesta += "\n\n¿Deseas registrar otro gasto o consultar tu saldo?"

            dispatcher.utter_message(text=respuesta)
            return [
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
            monto_raw = get_entity(tracker, "monto") or tracker.get_slot("monto")
            categoria = get_entity(tracker, "categoria") or tracker.get_slot("categoria")
            fecha = get_entity(tracker, "fecha") or tracker.get_slot("fecha")
            medio = get_entity(tracker, "medio") or tracker.get_slot("medio")

            if not monto_raw:
                dispatcher.utter_message(text="No entendí el monto del ingreso. ¿Podrías repetirlo?")
                return []

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido. Inténtalo de nuevo.")
                return []

            if not categoria:
                dispatcher.utter_message(text="¿Cuál es la categoría de este ingreso?")
                return []

            if fecha and len(fecha.split("/")) == 2:
                fecha += f"/{datetime.now().year}"

            transaccion = {
                "tipo": "ingreso",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio
            }

            guardar_transaccion(transaccion)

            respuesta = f"Tu ingreso de {monto} soles por {categoria} ha sido registrado."
            if fecha:
                respuesta += f" Fecha: {fecha}."
            respuesta += " ¿Te gustaría consultar tu saldo o registrar otro ingreso?"

            dispatcher.utter_message(text=respuesta)
            return [
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
        from actions.transacciones_io import cargar_transacciones
        from actions import formatear_fecha

        transacciones = cargar_transacciones(filtrar_activos=True)
        periodo = get_entity(tracker, "periodo")

        # Filtrar solo ingresos y gastos
        transacciones_filtradas = [
            t for t in transacciones if t.get("tipo") in ["ingreso", "gasto"]
        ]

        # Si se menciona un periodo, filtrar por 'mes' o por contenido de la fecha
        if periodo:
            periodo = periodo.lower()
            transacciones_filtradas = [
                t for t in transacciones_filtradas
                if periodo in t.get("fecha", "").lower() or periodo == t.get("mes", "").lower()
            ]

        if not transacciones_filtradas:
            if periodo:
                dispatcher.utter_message(text=f"No se encontraron movimientos registrados para el periodo {periodo}.")
            else:
                dispatcher.utter_message(text="No se encontraron transacciones registradas.")
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

            mensaje += f"- {tipo}: {monto} soles en {categoria}"
            if fecha:
                mensaje += f" el {formatear_fecha(fecha)}"
            if medio:
                mensaje += f" con {medio}"
            mensaje += "\n"

        mensaje += "\n¿Deseas registrar algo nuevo o consultar tu resumen mensual?"
        dispatcher.utter_message(text=mensaje)

        return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

from collections import Counter, defaultdict

class ActionAnalizarGastos(Action):
    def name(self) -> Text:
        return "action_analizar_gastos"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        from collections import Counter

        def obtener_mes_actual_nombre():
            return datetime.now().strftime("%B").lower()

        transacciones = cargar_transacciones()
        texto_usuario = tracker.latest_message.get("text", "").lower()
        periodo = get_entity(tracker, "periodo")
        categoria = get_entity(tracker, "categoria")

        if not periodo and "este mes" in texto_usuario:
            periodo = obtener_mes_actual_nombre()

        # Filtrar solo gastos válidos
        gastos = [
            t for t in transacciones
            if t.get("tipo") == "gasto" and t.get("monto") and t.get("categoria")
        ]

        if not gastos:
            dispatcher.utter_message(text="No se han registrado gastos aún. ¿Deseas ingresar uno?")
            return []

        # Filtrar por periodo si se indica
        if periodo:
            gastos = [
                g for g in gastos
                if periodo in g.get("fecha", "").lower() or periodo == g.get("mes", "").lower()
            ]

        if not gastos:
            dispatcher.utter_message(text=f"No se encontraron gastos para el periodo {periodo}.")
            return []

        # Si preguntó por una categoría específica
        if categoria:
            gastos_categoria = [
                g for g in gastos if categoria.lower() in g.get("categoria", "").lower()
            ]
            total_categoria = sum(float(g["monto"]) for g in gastos_categoria)

            if not gastos_categoria:
                dispatcher.utter_message(text=f"No se encontraron gastos en la categoría '{categoria}'.")
            else:
                dispatcher.utter_message(
                    text=f"Has gastado un total de {total_categoria:.2f} soles en la categoría '{categoria}'."
                )

            dispatcher.utter_message(text="¿Te gustaría consultar otra categoría o revisar tu resumen mensual?")
            return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

        # Agrupar por categoría y calcular totales
        conteo_categorias = Counter(g.get("categoria", "Desconocida") for g in gastos)
        top_categorias = conteo_categorias.most_common(3)
        total_gasto = sum(float(g.get("monto", 0)) for g in gastos)

        respuesta = "🧾 Análisis de tus hábitos de consumo"
        if periodo:
            respuesta += f" durante {periodo}"
        respuesta += ":\n\n"

        respuesta += "📊 Categorías más frecuentes:\n"
        for cat, freq in top_categorias:
            respuesta += f"• {cat}: {freq} registro(s)\n"

        respuesta += f"\n💸 Total gastado: {total_gasto:.2f} soles"

        # Detalle de transacciones (máximo 5 más recientes)
        respuesta += "\n\n📋 Ejemplos recientes:\n"
        for g in sorted(gastos, key=lambda x: x.get("fecha", ""), reverse=True)[:5]:
            fecha = g.get("fecha", "sin fecha")
            monto = g.get("monto", 0)
            cat = g.get("categoria", "desconocida")
            respuesta += f"- {cat}: {monto} soles ({fecha})\n"

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
            transacciones = cargar_transacciones()
            texto_usuario = tracker.latest_message.get("text", "").lower()

            # Detectar tipo: ingreso o gasto
            if "ingreso" in texto_usuario or "ingresos" in texto_usuario:
                tipo = "ingreso"
            else:
                tipo = "gasto"

            # Detectar los meses
            texto_normalizado = texto_usuario
            for sep in [" y ", " o ", " vs ", " versus ", " entre ", "contra", "comparar "]:
                texto_normalizado = texto_normalizado.replace(sep, " y ")

            posibles_meses = [
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
            ]
            meses_detectados = [mes for mes in posibles_meses if mes in texto_normalizado]
            meses_detectados = list(dict.fromkeys(meses_detectados))  # quitar duplicados

            if len(meses_detectados) != 2:
                dispatcher.utter_message(text="Por favor, indícame dos meses diferentes para comparar. Ejemplo: 'febrero y marzo'.")
                return []

            mes1, mes2 = meses_detectados
            total = defaultdict(float)

            for t in transacciones:
                if t.get("tipo") != tipo:
                    continue
                if t.get("mes") == mes1:
                    total[mes1] += float(t.get("monto", 0))
                elif t.get("mes") == mes2:
                    total[mes2] += float(t.get("monto", 0))

            valor1 = total.get(mes1, 0)
            valor2 = total.get(mes2, 0)

            if valor1 == 0 and valor2 == 0:
                dispatcher.utter_message(text=f"No se encontraron {tipo}s para {mes1} ni para {mes2}.")
                return []

            # Mensaje comparativo
            msg = f"📊 Comparativa de {tipo}s:\n"
            msg += f"- {mes1.capitalize()}: {valor1:.2f} soles\n"
            msg += f"- {mes2.capitalize()}: {valor2:.2f} soles\n"

            if valor1 > valor2:
                msg += f"⬅️ En {mes1} tuviste más {tipo}s que en {mes2}."
            elif valor2 > valor1:
                msg += f"➡️ En {mes2} tuviste más {tipo}s que en {mes1}."
            else:
                msg += f"✅ Tus {tipo}s fueron iguales en ambos meses."

            dispatcher.utter_message(text=msg)
            dispatcher.utter_message(text="¿Deseas analizar tus hábitos o configurar un presupuesto para este mes?")
            return []

        except Exception as e:
            print(f"[ERROR] Fallo en action_comparar_meses: {e}")
            dispatcher.utter_message(text="Ocurrió un error al comparar los meses.")
            return []

from dateparser import parse as parse_fecha_relativa

class ActionConsultarInformacionFinanciera(Action):
    def name(self) -> Text:
        return "action_consultar_informacion_financiera"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        transacciones = cargar_transacciones()
        tipo = get_entity(tracker, "tipo")
        categoria = get_entity(tracker, "categoria")
        medio = get_entity(tracker, "medio")
        fecha_raw = get_entity(tracker, "fecha")
        periodo = get_entity(tracker, "periodo")

        # Interpretar fechas como "lunes pasado"
        fecha = None
        if fecha_raw:
            try:
                fecha_parseada = parse_fecha_relativa(fecha_raw)
                fecha = fecha_parseada.strftime("%d/%m/%Y") if fecha_parseada else fecha_raw
            except:
                fecha = fecha_raw

        # Aplicar filtros
        resultados = []
        for t in transacciones:
            if tipo and t.get("tipo") != tipo:
                continue
            if medio and t.get("medio") != medio:
                continue
            if categoria and categoria.lower() not in t.get("categoria", "").lower():
                continue
            if periodo and periodo.lower() not in t.get("fecha", "").lower():
                continue
            if fecha and fecha not in t.get("fecha", ""):
                continue
            resultados.append(t)

        total = sum(t["monto"] for t in resultados)

        # Generar mensaje
        if categoria:
            msg = f"Tu gasto total en la categoría {categoria} es de {total:.2f} soles."
        elif tipo:
            msg = f"Tu {tipo} total es de {total:.2f} soles."
        elif periodo or fecha or medio:
            msg = f"📊 Resumen filtrado:\n"
            msg += f"- Total: {total:.2f} soles"
        else:
            msg = f"📊 Resumen general:\n"
            msg += f"- Ingresos totales: {sum(t['monto'] for t in transacciones if t['tipo'] == 'ingreso'):.2f} soles\n"
            msg += f"- Gastos totales: {sum(t['monto'] for t in transacciones if t['tipo'] == 'gasto'):.2f} soles"

        dispatcher.utter_message(text=msg)
        return [SlotSet("sugerencia_pendiente", "action_analizar_gastos")]

class ActionEntradaNoEntendida(Action):
    def name(self) -> Text:
        return "action_entrada_no_entendida"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            texto = tracker.latest_message.get("text", "")
            entidades_detectadas = [e.get("entity") for e in tracker.latest_message.get("entities", [])]

            if entidades_detectadas:
                mensaje = (
                    f"No logré entender completamente tu mensaje: \"{texto}\".\n"
                    f"Detecté estas entidades: {', '.join(entidades_detectadas)}.\n"
                    f"¿Podrías darme más contexto o reformularlo?"
                )
            else:
                mensaje = (
                    f"No entendí bien tu mensaje: \"{texto}\".\n"
                    f"¿Podrías reformularlo o especificar mejor qué deseas hacer?"
                )

            guardar_transaccion({
                "tipo": "entrada_no_entendida",
                "descripcion": texto,
                "timestamp": datetime.now().isoformat()
            })

            dispatcher.utter_message(text=mensaje)
            dispatcher.utter_message(text="Puedes preguntarme por tus gastos, ingresos, historial o configuración de alertas.")
            return []

        except Exception as e:
            print(f"[ERROR] Fallo en action_entrada_no_entendida: {e}")
            dispatcher.utter_message(text="Ocurrió un error procesando tu mensaje. Por favor, intenta nuevamente.")
            return []

from actions.alertas_io import guardar_alerta

class ActionResetearCategoriaGastos(Action):
    def name(self) -> Text:
        return "action_resetear_categoria_gastos"

    def run(self, dispatcher, tracker, domain):
        categoria = get_entity(tracker, "categoria")
        periodo = get_entity(tracker, "periodo")

        # Preguntar por la categoría si falta
        if not categoria:
            dispatcher.utter_message(text="¿Qué categoría deseas reiniciar?")
            return []

        # Preguntar por el periodo si falta
        if not periodo:
            dispatcher.utter_message(text=f"¿Para qué periodo deseas reiniciar los datos de gasto en {categoria}?")
            return []

        # Registrar en alertas.json una nueva alerta con monto 0 para ese periodo
        try:
            guardar_alerta({
                "categoria": categoria,
                "periodo": periodo,
                "monto": 0.0
            })

            dispatcher.utter_message(
                text=f"He reiniciado los datos de gasto en {categoria} para {periodo}. "
                     f"¿Deseas hacer otro cambio o consultar tu configuración?"
            )
        except Exception as e:
            print(f"[ERROR] No se pudo guardar el reinicio de categoría: {e}")
            dispatcher.utter_message(text="Ocurrió un error al reiniciar la categoría. Intenta nuevamente.")

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

        # Verificar si ya existe una alerta activa con la misma clave
        alertas = cargar_alertas()
        ya_existe = any(
            a["categoria"].lower() == categoria.lower() and a["periodo"].lower() == periodo
            for a in alertas
        )

        if ya_existe:
            dispatcher.utter_message(text=f"Ya existe una alerta activa para *{categoria}* en *{periodo}*. Usa 'modificar' si deseas actualizarla.")
            return []

        nueva_alerta = {
            "categoria": categoria,
            "monto": monto_float,
            "periodo": periodo
        }

        guardar_alerta(nueva_alerta)

        dispatcher.utter_message(
            text=f"✅ Se ha creado una alerta de *{monto_float} soles* para *{categoria}* en *{periodo}*."
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

        # Validación de campos clave
        if not categoria or not monto or not periodo:
            dispatcher.utter_message(text="Para modificar una configuración necesito la categoría, el monto y el mes con año.")
            return []

        # Parseo de monto
        try:
            monto_float = parse_monto(monto)
        except Exception:
            dispatcher.utter_message(text="El monto proporcionado no es válido.")
            return []

        if monto_float <= 0:
            dispatcher.utter_message(text="El monto debe ser mayor a cero para configurar una alerta.")
            return []

        # Estandarizar periodo
        periodo = periodo.lower().strip()

        # Crear nueva configuración única
        nueva_alerta = [{
            "categoria": categoria,
            "monto": monto_float,
            "periodo": periodo
        }]

        # Guardar nueva configuración sobrescribiendo las anteriores
        guardar_todas_las_alertas(nueva_alerta)

        mensaje = f"🔁 Tu presupuesto para *{categoria}* en *{periodo}* ha sido actualizado a *{monto_float} soles*."
        mensaje += " Puedes seguir modificando otras categorías si lo deseas."

        dispatcher.utter_message(text=mensaje)
        return []

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

        condiciones = {
            "categoria": categoria.lower(),
            "periodo": periodo.lower().strip()
        }

        eliminar_alerta_logicamente(condiciones)

        dispatcher.utter_message(
            text=f"🗑️ Se ha eliminado la alerta configurada para *{categoria}* en *{periodo}*."
        )

        return []

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
            dispatcher.utter_message(text="Perfecto, procedo con eso.")
            return [
                FollowupAction(sugerencia),
                SlotSet("sugerencia_pendiente", None),
                SlotSet("categoria", None),
                SlotSet("monto", None),
                SlotSet("fecha", None),
                SlotSet("medio", None),
                SlotSet("periodo", None)
            ]
        dispatcher.utter_message(text="No entendí a qué te refieres. ¿Podrías repetirlo?")
        return []
    
class ActionBienvenida(Action):
    def name(self) -> Text:
        return "action_bienvenida"

    def run(self, dispatcher, tracker, domain):
        hoy = datetime.now().strftime("%B").lower()
        mensaje = (
            f"¡Hola! Bienvenido 👋\n\n"
            f"Hoy es {hoy.capitalize()} y estoy listo para ayudarte con tus finanzas.\n"
            f"Puedo ayudarte a:\n"
            f"• Registrar ingresos y gastos\n"
            f"• Ver tu historial o saldo\n"
            f"• Configurar alertas\n"
            f"• Comparar tus gastos entre meses\n"
            f"Ejemplo: 'Muéstrame mis gastos de {hoy}'\n"
            f"¿Qué deseas hacer hoy?"
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
