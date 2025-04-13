from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
from actions.transacciones_io import guardar_transaccion, cargar_transacciones
from rasa_sdk.events import SlotSet
import json
import os
from datetime import datetime
from collections import Counter, defaultdict

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
            monto_raw = get_entity(tracker, "monto")
            categoria = get_entity(tracker, "categoria")
            fecha = get_entity(tracker, "fecha")
            medio = get_entity(tracker, "medio")

            if not monto_raw:
                guardar_transaccion({
                    "tipo": "entrada_incompleta",
                    "descripcion": tracker.latest_message.get("text", ""),
                    "timestamp": datetime.now().isoformat()
                })
                dispatcher.utter_message(text="No entendí el monto...")
                return []

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido. Inténtalo de nuevo.")
                return []

            if not categoria:
                dispatcher.utter_message(text="¿En qué categoría deseas registrar este gasto?")
                return []

            # ✅ Agregar año automáticamente si falta
            if fecha and len(fecha.split("/")) == 2:
                fecha += f"/{datetime.now().year}"

            transaccion = {
                "tipo": "gasto",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio
            }

            guardar_transaccion(transaccion)

            respuesta = f"He registrado tu gasto de {monto} soles en {categoria}."
            if fecha:
                respuesta += f" Fecha: {fecha}."
            respuesta += " ¿Deseas registrar otro gasto o consultar tu saldo?"

            dispatcher.utter_message(text=respuesta)
            return [SlotSet("sugerencia_pendiente", "action_consultar_saldo")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_registrar_gasto: {e}")
            dispatcher.utter_message(text="Ocurrió un error al registrar tu gasto. Por favor, intenta nuevamente.")
            return []

class ActionRegistrarIngreso(Action):
    def name(self) -> Text:
        return "action_registrar_ingreso"

    def run(self, dispatcher, tracker, domain):
        try:
            monto_raw = get_entity(tracker, "monto")
            categoria = get_entity(tracker, "categoria")
            fecha = get_entity(tracker, "fecha")
            medio = get_entity(tracker, "medio")

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

            # ✅ Agregar el año actual si falta en la fecha (por ejemplo: "3/enero")
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

            respuesta = f"Tu ingreso de {monto_raw} soles por {categoria} ha sido registrado."
            if fecha:
                respuesta += f" Fecha: {fecha}."
            respuesta += " ¿Te gustaría consultar tu saldo o registrar otro ingreso?"

            dispatcher.utter_message(text=respuesta)
            return [SlotSet("sugerencia_pendiente", "action_consultar_saldo")]

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
        transacciones = cargar_transacciones()

        # Solo incluir ingresos y gastos válidos
        transacciones_filtradas = [
            t for t in transacciones
            if t.get("tipo") in ["ingreso", "gasto"]
        ]

        if not transacciones_filtradas:
            historial = "No tienes ingresos ni gastos registrados aún."
        else:
            historial = ""
            for t in transacciones_filtradas:
                tipo = t.get("tipo", "transacción")
                monto = t.get("monto", "¿?")
                categoria = t.get("categoria", "")
                fecha = t.get("fecha", "")
                medio = t.get("medio", "")

                linea = f"{tipo}: {monto} soles en {categoria}"
                if fecha:
                    linea += f" el {formatear_fecha(fecha)}"
                if tipo == "gasto" and medio:
                    linea += f" con {medio}"

                historial += "- " + linea + "\n"

        dispatcher.utter_message(text=f"Estas son tus transacciones registradas:\n{historial.strip()}")
        dispatcher.utter_message(text="¿Deseas exportar esta información o registrar algo nuevo?")
        return []

class ActionConsultarGasto(Action):
    def name(self) -> Text:
        return "action_consultar_gasto"

    def run(self, dispatcher, tracker, domain):
        try:
            transacciones = cargar_transacciones()
            periodo = tracker.get_slot("periodo")
            medio = next(tracker.get_latest_entity_values("medio"), None)

            # Filtrado por periodo si está disponible
            if periodo:
                transacciones = [
                    t for t in transacciones
                    if t.get("periodo", "").lower() == periodo.lower()
                ]

            # Filtrado por medio si también se menciona
            if medio:
                transacciones = [
                    t for t in transacciones
                    if t.get("medio") == medio
                ]

            # Filtrar solo gastos
            gastos = [t for t in transacciones if t["tipo"] == "gasto"]
            total = sum(float(t["monto"]) for t in gastos)

            if total == 0:
                if periodo:
                    msg = f"No se encontraron gastos registrados en {periodo}. ¿Te gustaría registrar uno ahora?"
                else:
                    msg = "No se han registrado gastos aún. ¿Te gustaría registrar uno ahora?"
                dispatcher.utter_message(text=msg)
                return []
            else:
                if periodo:
                    msg = f"Tu gasto total en {periodo} es de {total:.2f} soles. ¿Quieres ver tu saldo o analizar tus hábitos de consumo?"
                else:
                    msg = f"Tu gasto total registrado es de {total:.2f} soles. ¿Quieres ver tu saldo o analizar tus hábitos de consumo?"
                dispatcher.utter_message(text=msg)
                return [SlotSet("sugerencia_pendiente", "action_analizar_o_clasificar_gastos")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_consultar_gasto: {e}")
            dispatcher.utter_message(text="Ocurrió un error al consultar tus gastos.")
            return []

class ActionExportarInformacion(Action):
    def name(self) -> Text:
        return "action_exportar_informacion"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        transacciones = cargar_transacciones()

        if not transacciones:
            dispatcher.utter_message(text="No tienes transacciones registradas para exportar.")
            dispatcher.utter_message(text="¿Deseas registrar un gasto o ingreso ahora?")
            return []

        dispatcher.utter_message(text="Estas son tus transacciones registradas:")

        for transaccion in transacciones:
            tipo = transaccion.get("tipo", "Desconocido")
            monto = transaccion.get("monto", "???")
            categoria = transaccion.get("categoria", "???")
            fecha = transaccion.get("fecha", "")
            medio = transaccion.get("medio", "")
            timestamp = transaccion.get("timestamp", "")

            mensaje = f"- {tipo}: {monto} soles en {categoria}"
            if fecha:
                linea += f" el {formatear_fecha(fecha)}"
            if medio:
                mensaje += f" con {medio}"
            if timestamp:
                mensaje += f" (registrado el {timestamp})"

            dispatcher.utter_message(text=mensaje)

        dispatcher.utter_message(text="¿Deseas exportar nuevamente más adelante o ver tu resumen mensual?")
        return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

from collections import Counter, defaultdict
import datetime

class ActionAnalizarOClasificarGastos(Action):
    def name(self) -> Text:
        return "action_analizar_o_clasificar_gastos"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        def obtener_mes_actual_num():
            return datetime.now().strftime("%m")

        transacciones = cargar_transacciones()
        texto_usuario = tracker.latest_message.get("text", "").lower()
        periodo = get_entity(tracker, "periodo")
        categoria_preguntada = get_entity(tracker, "categoria")

        if not periodo and "este mes" in texto_usuario:
            periodo = obtener_mes_actual_num()

        gastos = [
            t for t in transacciones
            if t.get("tipo") == "gasto" and t.get("monto") and t.get("categoria")
        ]

        if not gastos:
            dispatcher.utter_message(text="No se han registrado gastos aún. ¿Deseas ingresar uno?")
            return []

        if categoria_preguntada:
            total_categoria = sum(
                float(t.get("monto", 0))
                for t in gastos
                if t.get("categoria", "").lower() == categoria_preguntada.lower()
            )
            if total_categoria == 0:
                dispatcher.utter_message(text=f"No se encontraron gastos en la categoría {categoria_preguntada}.")
            else:
                dispatcher.utter_message(text=f"Has gastado {total_categoria:.2f} soles en {categoria_preguntada}.")
            dispatcher.utter_message(text="¿Te gustaría consultar otra categoría o revisar tu resumen mensual?")
            return [SlotSet("sugerencia_pendiente", "action_consultar_resumen_mensual")]

        if periodo:
            gastos = [
                g for g in gastos
                if periodo in g.get("fecha", "").lower()
            ]

        conteo = Counter(t.get("categoria", "Desconocida") for t in gastos)
        top_categorias = conteo.most_common(3)

        if not top_categorias:
            dispatcher.utter_message(text=f"No se encontraron gastos en el periodo indicado.")
            return []

        respuesta = "He analizado tus hábitos de consumo"
        if periodo:
            respuesta += f" durante el periodo de {periodo}"
        respuesta += ". Estas son tus categorías más frecuentes:\n"

        for cat, freq in top_categorias:
            respuesta += f"• {cat}: {freq} registro(s)\n"

        dispatcher.utter_message(text=respuesta.strip())
        dispatcher.utter_message(text="¿Te gustaría comparar meses o configurar una alerta?")
        return [SlotSet("sugerencia_pendiente", "action_comparar_meses")]

class ActionClasificarGasto(Action):
    def name(self) -> Text:
        return "action_clasificar_gasto"

    def run(self, dispatcher, tracker, domain):
        try:
            monto_raw = get_entity(tracker, "monto")
            categoria = get_entity(tracker, "categoria")
            fecha = get_entity(tracker, "fecha")
            medio = get_entity(tracker, "medio")

            if not monto_raw or not categoria:
                dispatcher.utter_message(text="Necesito el monto y la categoría para clasificar este gasto.")
                return []

            monto = parse_monto(monto_raw)
            if monto == 0.0:
                dispatcher.utter_message(text="El monto ingresado no es válido.")
                return []

            transaccion = {
                "tipo": "gasto",
                "monto": monto,
                "categoria": categoria,
                "fecha": fecha,
                "medio": medio,
                "timestamp": datetime.now().isoformat()
            }

            guardar_transaccion(transaccion)
            respuesta = f"Gasto de {monto} soles clasificado como {categoria}."
            if fecha:
                respuesta += f" Fecha: {fecha}."
            if medio:
                respuesta += f" Medio: {medio}."
            respuesta += " ¿Deseas clasificar otro gasto o consultar tu historial?"

            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            print(f"[ERROR] Clasificar gasto: {e}")
            dispatcher.utter_message(text="Ocurrió un error al clasificar el gasto.")
        return []

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

from datetime import datetime
from collections import defaultdict

class ActionCompararMeses(Action):
    def name(self) -> Text:
        return "action_comparar_meses"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            transacciones = cargar_transacciones()
            texto_usuario = tracker.latest_message.get("text", "").lower()
            periodo = get_entity(tracker, "periodo")

            meses_detectados = []
            if periodo and "y" in periodo:
                meses_detectados = [m.strip() for m in periodo.lower().split("y")]
            else:
                for sep in [" y ", " versus ", " vs ", " entre ", "contra", "comparar "]:
                    texto_usuario = texto_usuario.replace(sep, " y ")
                posibles_meses = [
                    "enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
                ]
                for mes in posibles_meses:
                    if mes in texto_usuario:
                        meses_detectados.append(mes)

            meses_detectados = list(dict.fromkeys(meses_detectados))

            if len(meses_detectados) != 2:
                dispatcher.utter_message(text="Por favor, indícame dos meses diferentes para comparar. Ejemplo: 'febrero y marzo'.")
                return []

            mes1, mes2 = meses_detectados
            gastos = defaultdict(float)

            nombre_a_numero = {
                "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
            }

            for t in transacciones:
                if t.get("tipo") != "gasto":
                    continue

                fecha = t.get("fecha", "").strip().lower()
                if not fecha or "/" not in fecha:
                    continue

                partes = fecha.split("/")
                if len(partes) < 2:
                    continue

                mes_fecha = partes[1].strip()

                monto = float(t.get("monto", 0))

                if mes_fecha == mes1:
                    gastos[mes1] += monto
                elif mes_fecha == mes2:
                    gastos[mes2] += monto


            g1 = gastos.get(mes1, 0)
            g2 = gastos.get(mes2, 0)

            if g1 == 0 and g2 == 0:
                msg = f"No se encontraron gastos para {mes1} ni para {mes2}."
            else:
                msg = f"📊 Comparativa de gastos:\n- {mes1.capitalize()}: {g1:.2f} soles\n- {mes2.capitalize()}: {g2:.2f} soles\n"
                diferencia = g2 - g1
                if diferencia > 0:
                    msg += f"➡️ En {mes2} gastaste {diferencia:.2f} soles más que en {mes1}."
                elif diferencia < 0:
                    msg += f"⬅️ En {mes2} gastaste {-diferencia:.2f} soles menos que en {mes1}."
                else:
                    msg += f"✅ Tus gastos en ambos meses fueron iguales."

            dispatcher.utter_message(text=msg)
            dispatcher.utter_message(text="¿Deseas analizar tus hábitos o configurar un presupuesto para este mes?")
            return []

        except Exception as e:
            print(f"[ERROR] Fallo en action_comparar_meses: {e}")
            dispatcher.utter_message(text="Ocurrió un error al comparar los meses.")
            return []

class ActionConsultarIngreso(Action):
    def name(self) -> Text:
        return "action_consultar_ingreso"

    def run(self, dispatcher, tracker, domain):
        transacciones = cargar_transacciones()
        total = sum(t["monto"] for t in transacciones if t["tipo"] == "ingreso")

        if total == 0:
            msg = "No se han registrado ingresos aún. ¿Deseas registrar uno ahora?"
        else:
            msg = f"Tu ingreso total registrado es de {total:.2f} soles. ¿Te gustaría ver tu saldo o consultar tus gastos?"
        dispatcher.utter_message(text=msg)
        return []

class ActionConsultarResumenMensual(Action):
    def name(self) -> Text:
        return "action_consultar_resumen_mensual"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            transacciones = cargar_transacciones()
            ingresos = 0.0
            gastos = 0.0

            # Obtener mes actual como número (ej. '04') y como nombre (abril)
            hoy = datetime.now()
            mes_actual_num = hoy.strftime("%m")
            mes_actual_nombre = hoy.strftime("%B").lower()

            resumen = []
            for t in transacciones:
                tipo = t.get("tipo", "").lower()
                if tipo not in ["ingreso", "gasto"]:
                    continue

                fecha = t.get("fecha", "")
                if fecha:
                    partes = fecha.split("/")
                    if len(partes) >= 2 and partes[1].lower() == mes_actual_nombre:
                        resumen.append(t)
                        monto = float(t.get("monto", 0))
                        if tipo == "ingreso":
                            ingresos += monto
                        elif tipo == "gasto":
                            gastos += monto

            if not resumen:
                dispatcher.utter_message(text="No se encontraron transacciones registradas este mes.")
                return []

            detalles = ""
            for t in resumen:
                tipo = t.get("tipo", "transacción").capitalize()
                monto = t.get("monto", 0)
                categoria = t.get("categoria", "categoría no especificada")
                fecha = t.get("fecha", "")
                medio = t.get("medio", "")

                linea = f"{tipo}: {monto} soles en {categoria}"
                if fecha:
                    linea += f" el {formatear_fecha(fecha)}"
                if tipo.lower() == "gasto" and medio:
                    linea += f" con {medio}"

                detalles += "- " + linea + "\n"

            mensaje = (
                f"📊 Resumen de {mes_actual_nombre.capitalize()}:\n"
                f"- Total de ingresos: {ingresos:.2f} soles\n"
                f"- Total de gastos: {gastos:.2f} soles\n"
                f"🔍 Detalles:\n{detalles.strip()}"
            )

            dispatcher.utter_message(text=mensaje)
            dispatcher.utter_message(text="¿Deseas comparar este mes con otro, o registrar una nueva transacción?")
            return [SlotSet("sugerencia_pendiente", "action_comparar_meses")]

        except Exception as e:
            print(f"[ERROR] Fallo en action_consultar_resumen_mensual: {e}")
            dispatcher.utter_message(text="Hubo un error al generar el resumen mensual.")
            return []

presupuestos_alertas = {}

class ActionEntradaNoEntendida(Action):
    def name(self) -> Text:
        return "action_entrada_no_entendida"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        texto = tracker.latest_message.get("text", "")
        entidades_detectadas = [e['entity'] for e in tracker.latest_message.get("entities", [])]

        if entidades_detectadas:
            mensaje = f"No logré entender completamente tu mensaje: \"{texto}\". Detecté estas entidades: {', '.join(entidades_detectadas)}. ¿Podrías ser más específico?"
        else:
            mensaje = f"No entendí bien tu mensaje: \"{texto}\". ¿Podrías reformularlo, por favor?"

        guardar_transaccion({
            "tipo": "entrada_no_entendida",
            "descripcion": texto,
            "timestamp": datetime.now().isoformat()
        })

        dispatcher.utter_message(text=mensaje)
        dispatcher.utter_message(text="¿Deseas registrar un gasto o consultar tu saldo?")
        return []

class ActionResetearCategoriaGastos(Action):
    def name(self) -> Text:
        return "action_resetear_categoria_gastos"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        from actions.transacciones_io import guardar_transaccion

        guardar_transaccion({
            "tipo": "sistema",
            "descripcion": "Categorías de gastos reseteadas."
        })

        dispatcher.utter_message(text="He reseteado tus categorías de gastos.")
        return []

class ActionGestionarPresupuestoOAlerta(Action):
    def name(self) -> Text:
        return "action_gestionar_presupuesto_o_alerta"

    def run(self, dispatcher, tracker, domain):
        categoria = get_entity(tracker, "categoria")
        monto = get_entity(tracker, "monto")
        periodo = get_entity(tracker, "periodo")

        if not categoria or not monto:
            dispatcher.utter_message(text="Necesito una categoría y un monto para configurar el presupuesto o alerta.")
            return []

        try:
            monto_float = parse_monto(monto)
        except:
            dispatcher.utter_message(text="El monto proporcionado no es válido.")
            return []

        clave = f"{categoria.lower()}_{periodo.lower()}" if periodo else categoria.lower()
        presupuestos_alertas[clave] = monto_float

        # Guardar como transacción
        guardar_transaccion({
            "tipo": "alerta",
            "categoria": categoria,
            "monto": monto_float,
            "periodo": periodo
        })

        mensaje = f"Configurado: {monto_float} soles en {categoria}."
        if periodo:
            mensaje += f" Periodo: {periodo}."
        mensaje += " ¿Deseas configurar otra alerta o consultar tu configuración actual?"
        
        dispatcher.utter_message(text=mensaje)
        return []
    
class ActionConsultarConfiguracion(Action):
    def name(self) -> Text:
        return "action_consultar_configuracion"

    def run(self, dispatcher, tracker, domain):
        try:
            transacciones = cargar_transacciones()
            configuraciones = [t for t in transacciones if t.get("tipo") in ["configuracion", "alerta"]]

            if not configuraciones:
                dispatcher.utter_message(text="No tienes configuraciones activas.")
                dispatcher.utter_message(text="¿Deseas agregar una nueva alerta o presupuesto?")
                return []

            mensaje = "Estas son tus configuraciones activas:\n"
            for config in configuraciones:
                categoria = config.get("categoria", "desconocida").capitalize()
                monto = config.get("monto", "¿?")
                periodo = config.get("periodo", "")
                mensaje += f"• {categoria}: {monto} soles"
                if periodo:
                    mensaje += f" para {periodo}"
                if config.get("timestamp"):
                    mensaje += f" (registrado: {config['timestamp']})"
                mensaje += "\n"

            dispatcher.utter_message(text=mensaje.strip())
            dispatcher.utter_message(text="¿Deseas modificar o eliminar alguna de estas configuraciones?")
            return []

        except Exception as e:
            print(f"[ERROR] Consultar configuración: {e}")
            dispatcher.utter_message(text="Ocurrió un error al consultar tus configuraciones.")
            return []

class ActionEliminarConfiguracion(Action):
    def name(self) -> Text:
        return "action_eliminar_configuracion"

    def run(self, dispatcher, tracker, domain):
        categoria = get_entity(tracker, "categoria")
        if not categoria:
            dispatcher.utter_message(text="No especificaste qué categoría deseas eliminar.")
            return []

        if categoria in presupuestos_alertas:
            del presupuestos_alertas[categoria]
            guardar_transaccion({
                "tipo": "eliminacion_configuracion",
                "categoria": categoria,
                "timestamp": datetime.now().isoformat()
            })
            mensaje = f"La configuración para '{categoria}' ha sido eliminada."
        else:
            mensaje = f"No encontré una configuración para la categoría '{categoria}'."

        dispatcher.utter_message(text=mensaje)
        dispatcher.utter_message(text="¿Deseas agregar una nueva configuración o consultar las existentes?")
        return []
    
from rasa_sdk.events import FollowupAction

class ActionFollowSuggestion(Action):
    def name(self) -> Text:
        return "action_follow_suggestion"

    def run(self, dispatcher, tracker, domain):
        sugerencia = tracker.get_slot("sugerencia_pendiente")
        if sugerencia:
            dispatcher.utter_message(text="Perfecto, procedo con eso.")
            return [FollowupAction(sugerencia)]
        dispatcher.utter_message(text="No entendí a qué te refieres. ¿Podrías repetirlo?")
        return []