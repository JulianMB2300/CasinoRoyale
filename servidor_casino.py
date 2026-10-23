import asyncio
import json
import os
import random
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()
salas = {}

DISTRIBUCION_RONDAS = [5, 4, 4, 4, 4, 5]


def nuevo_mazo():
    palos = ["Corazones", "Diamantes", "Tréboles", "Picas"]
    mazo = [
        {"palo": palo, "nominal": valor, "es_mona": False}
        for palo in palos
        for valor in range(1, 14)
    ]
    mazo.append({"palo": "Especial", "nominal": 15, "es_mona": True})
    random.shuffle(mazo)
    return mazo


def mensaje(tipo, datos=None):
    return json.dumps({"tipo": tipo, "datos": datos or {}}, ensure_ascii=False)


async def enviar_a_jugadores(sala, tipo, datos=None):
    payload = mensaje(tipo, datos)
    desconectados = []
    for clave in ("jugador1", "jugador2"):
        ws = sala.get(clave)
        if ws is not None:
            try:
                await ws.send_text(payload)
            except Exception:
                desconectados.append(clave)
    for clave in desconectados:
        sala[clave] = None


def repartir_manos(sala, ronda):
    cantidad = DISTRIBUCION_RONDAS[ronda - 1]
    mazo = sala["mazo"]
    # No reutilizar cartas ni producir manos desiguales si el mazo se agotó.
    if len(mazo) < cantidad * 2:
        raise ValueError("No quedan suficientes cartas para repartir esta ronda.")
    mano1 = [mazo.pop() for _ in range(cantidad)]
    mano2 = [mazo.pop() for _ in range(cantidad)]
    return mano1, mano2


async def iniciar_partida(sala, revancha=False):
    sala["mazo"] = nuevo_mazo()
    sala["ronda"] = 1
    sala["turno"] = sala["primer_jugador"]
    sala["rondas_solicitadas"] = set()
    sala["partida_finalizada"] = False
    sala["mesa_inicial"] = [sala["mazo"].pop()]
    mano1, mano2 = repartir_manos(sala, 1)
    payload = {
        "mesa_inicial": sala["mesa_inicial"],
        "mano_j1": mano1,
        "mano_j2": mano2,
        "ronda": 1,
        "turno_inicial": sala["turno"],
        "primer_jugador": sala["primer_jugador"],
        "revancha": revancha,
    }
    await enviar_a_jugadores(sala, "INICIAR_PARTIDA", payload)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Casino Master Server is running"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    username = "Jugador"
    sala_actual = None

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                mensaje_recibido = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_text(mensaje("ERROR", {"mensaje": "Mensaje JSON inválido"}))
                continue

            tipo = mensaje_recibido.get("tipo")
            datos = mensaje_recibido.get("datos") or {}

            if tipo == "LOGIN":
                username = datos.get("username", "Jugador")
                perfil = {"username": username, "fichas": 10000}
                await websocket.send_text(mensaje("LOGIN_EXITOSO", {"perfil": perfil}))

            elif tipo == "CREAR_SALA":
                # Evitar colisiones de ID de sala.
                sala_id = f"sala_{random.randint(1000, 9999)}"
                while sala_id in salas:
                    sala_id = f"sala_{random.randint(1000, 9999)}"

                sala_actual = sala_id
                salas[sala_id] = {
                    "jugador1": websocket,
                    "jugador2": None,
                    "nombres": {1: username, 2: None},
                    "nombre": sala_id,
                    "turno": 1,
                    "primer_jugador": 1,
                    "ronda": 1,
                    "distribucion": DISTRIBUCION_RONDAS[:],
                    "mazo": [],
                    "rondas_solicitadas": set(),
                    "partida_finalizada": False,
                    "lock": asyncio.Lock(),
                }
                await websocket.send_text(mensaje("SALA_CREADA", {
                    "sala_id": sala_id,
                    "nombre": sala_id,
                    "id_jugador": 1,
                }))

            elif tipo == "UNIR_SALA":
                sala_id = datos.get("sala_id")
                sala = salas.get(sala_id)
                if sala and sala["jugador2"] is None and sala["jugador1"] is not websocket:
                    sala_actual = sala_id
                    sala["jugador2"] = websocket
                    sala["nombres"][2] = username
                    await websocket.send_text(mensaje("UNIDO_SALA", {
                        "sala_id": sala_id,
                        "id_jugador": 2,
                    }))
                    async with sala["lock"]:
                        await iniciar_partida(sala, revancha=False)
                else:
                    await websocket.send_text(mensaje("ERROR", {
                        "mensaje": "Sala no encontrada o llena"
                    }))

            elif tipo == "ACCION_JUEGO":
                sala = salas.get(sala_actual) if sala_actual else None
                if not sala:
                    await websocket.send_text(mensaje("ERROR", {"mensaje": "No estás en una sala"}))
                    continue

                async with sala["lock"]:
                    id_emisor = 1 if websocket is sala["jugador1"] else (
                        2 if websocket is sala["jugador2"] else None
                    )
                    if id_emisor is None:
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "No perteneces a esta sala"}))
                    elif sala["partida_finalizada"]:
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "La partida ya terminó"}))
                    elif sala["turno"] != id_emisor:
                        await websocket.send_text(mensaje("ERROR_TURNO", {"mensaje": "No es tu turno"}))
                    else:
                        # El servidor es autoridad del turno; solo avanza tras aceptar una acción.
                        sala["turno"] = 2 if sala["turno"] == 1 else 1
                        datos_confirmados = dict(datos)
                        datos_confirmados["nuevo_turno"] = sala["turno"]
                        datos_confirmados["id_jugador_accion"] = id_emisor
                        await enviar_a_jugadores(sala, "ACCION_JUEGO", datos_confirmados)

            elif tipo == "REPARTIR_RONDA":
                sala = salas.get(sala_actual) if sala_actual else None
                if not sala:
                    await websocket.send_text(mensaje("ERROR", {"mensaje": "No estás en una sala"}))
                    continue

                async with sala["lock"]:
                    id_emisor = 1 if websocket is sala["jugador1"] else (
                        2 if websocket is sala["jugador2"] else None
                    )
                    try:
                        ronda_nueva = int(datos.get("ronda", 0))
                    except (TypeError, ValueError):
                        ronda_nueva = 0

                    # Solo aceptar la siguiente ronda, una sola vez por partida.
                    if id_emisor != sala["primer_jugador"] and id_emisor != (
                        2 if sala["primer_jugador"] == 1 else 1
                    ):
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "Jugador no válido"}))
                    elif sala["partida_finalizada"]:
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "La partida ya terminó"}))
                    elif ronda_nueva != sala["ronda"] + 1 or ronda_nueva > len(DISTRIBUCION_RONDAS):
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "Número de ronda inválido"}))
                    elif ronda_nueva in sala["rondas_solicitadas"]:
                        # Idempotencia: si el otro cliente solicita el mismo reparto, no repartir de nuevo.
                        await websocket.send_text(mensaje("NUEVA_RONDA", {
                            "ronda": ronda_nueva,
                            "ya_repartida": True,
                        }))
                    else:
                        try:
                            mano1, mano2 = repartir_manos(sala, ronda_nueva)
                        except ValueError as exc:
                            await websocket.send_text(mensaje("ERROR", {"mensaje": str(exc)}))
                            continue

                        sala["ronda"] = ronda_nueva
                        sala["rondas_solicitadas"].add(ronda_nueva)
                        payload_ronda = {
                            "ronda": ronda_nueva,
                            "mano_j1": mano1,
                            "mano_j2": mano2,
                            "turno_inicial": sala["turno"],
                        }
                        await enviar_a_jugadores(sala, "NUEVA_RONDA", payload_ronda)

            elif tipo in ("REVANCHA_REQUEST", "SOLICITAR_REVANCHA"):
                sala = salas.get(sala_actual) if sala_actual else None
                if not sala:
                    await websocket.send_text(mensaje("ERROR", {"mensaje": "No estás en una sala"}))
                    continue

                async with sala["lock"]:
                    if sala["jugador1"] is None or sala["jugador2"] is None:
                        await websocket.send_text(mensaje("ERROR", {"mensaje": "Falta un jugador para la revancha"}))
                    else:
                        # Solo iniciar una revancha cuando la partida anterior terminó.
                        if not sala["partida_finalizada"]:
                            await websocket.send_text(mensaje("ERROR", {
                                "mensaje": "La partida todavía no ha terminado"
                            }))
                        else:
                            sala["primer_jugador"] = 2 if sala["primer_jugador"] == 1 else 1
                            await iniciar_partida(sala, revancha=True)

            elif tipo == "FINALIZAR_PARTIDA":
                sala = salas.get(sala_actual) if sala_actual else None
                if not sala:
                    continue
                async with sala["lock"]:
                    sala["partida_finalizada"] = True
                    await enviar_a_jugadores(sala, "FINALIZAR_PARTIDA", datos)

    except WebSocketDisconnect:
        if sala_actual and sala_actual in salas:
            sala = salas[sala_actual]
            async with sala["lock"]:
                if sala.get("jugador1") is websocket:
                    sala["jugador1"] = None
                if sala.get("jugador2") is websocket:
                    sala["jugador2"] = None
                # Mantener la sala para permitir reconexión/diagnóstico.
                if sala["jugador1"] is None and sala["jugador2"] is None:
                    del salas[sala_actual]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("servidor_casino:app", host="0.0.0.0", port=port)