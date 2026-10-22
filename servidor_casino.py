import asyncio
import json
import os
import random
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

salas = {}

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
                mensaje = json.loads(raw_message)
                tipo = mensaje.get("tipo")
                datos = mensaje.get("datos", {})

                if tipo == "LOGIN":
                    username = datos.get("username", "Jugador")
                    perfil = {"username": username, "fichas": 10000}
                    await websocket.send_text(json.dumps({
                        "tipo": "LOGIN_EXITOSO",
                        "datos": {"perfil": perfil}
                    }))

                elif tipo == "CREAR_SALA":
                    sala_id = f"sala_{random.randint(1000, 9999)}"
                    sala_actual = sala_id
                    salas[sala_id] = {
                        "jugador1": websocket,
                        "jugador2": None,
                        "nombre": sala_id,
                        "turno": 1,
                        "ronda": 1,
                        "distribucion": [5, 4, 4, 4, 4, 5],
                        "mazo": []
                    }
                    await websocket.send_text(json.dumps({
                        "tipo": "SALA_CREADA",
                        "datos": {"sala_id": sala_id, "nombre": sala_id}
                    }))

                elif tipo == "UNIR_SALA":
                    sala_id = datos.get("sala_id")
                    if sala_id in salas and salas[sala_id]["jugador2"] is None:
                        sala_actual = sala_id
                        salas[sala_id]["jugador2"] = websocket
                        
                        await websocket.send_text(json.dumps({
                            "tipo": "UNIDO_SALA",
                            "datos": {"sala_id": sala_id, "id_jugador": 2}
                        }))
                        
                        # Crear mazo inicial
                        s = salas[sala_id]
                        palo_list = ['Corazones', 'Diamantes', 'Tréboles', 'Picas']
                        deck = []
                        for p in palo_list:
                            for v in range(1, 14):
                                deck.append({"palo": p, "nominal": v, "es_mona": False})
                        deck.append({"palo": 'Especial', "nominal": 15, "es_mona": True})
                        random.shuffle(deck)
                        s["mazo"] = deck
                        
                        carta_mesa = [s["mazo"].pop()]
                        cant = s["distribucion"][0]
                        m1 = [s["mazo"].pop() for _ in range(cant)]
                        m2 = [s["mazo"].pop() for _ in range(cant)]
                        
                        payload_partida = {
                            "mesa_inicial": carta_mesa,
                            "mano_j1": m1,
                            "mano_j2": m2,
                            "ronda": 1
                        }
                        
                        await s["jugador1"].send_text(json.dumps({"tipo": "INICIAR_PARTIDA", "datos": payload_partida}))
                        await s["jugador2"].send_text(json.dumps({"tipo": "INICIAR_PARTIDA", "datos": payload_partida}))
                    else:
                        await websocket.send_text(json.dumps({
                            "tipo": "ERROR",
                            "datos": {"mensaje": "Sala no encontrada o llena"}
                        }))

                elif tipo == "ACCION_JUEGO":
                    if sala_actual and sala_actual in salas:
                        s = salas[sala_actual]
                        es_jugador_1 = (websocket == s["jugador1"])
                        id_emisor = 1 if es_jugador_1 else 2
                        
                        # Validar estrictamente el turno actual en el servidor
                        if s.get("turno", 1) == id_emisor:
                            # Cambiar de turno oficialmente
                            s["turno"] = 2 if s["turno"] == 1 else 1
                            datos["nuevo_turno"] = s["turno"]
                            
                            # Enviar la acción confirmada a AMBOS jugadores para mantener sincronización perfecta
                            mensaje_respuesta = json.dumps({
                                "tipo": "ACCION_JUEGO",
                                "datos": datos
                            })
                            await s["jugador1"].send_text(mensaje_respuesta)
                            if s["jugador2"]:
                                await s["jugador2"].send_text(mensaje_respuesta)
                        else:
                            await websocket.send_text(json.dumps({
                                "tipo": "ERROR_TURNO",
                                "datos": {"mensaje": "No es tu turno"}
                            }))

                elif tipo == "REPARTIR_RONDA":
                    if sala_actual and sala_actual in salas:
                        s = salas[sala_actual]
                        ronda_nueva = datos.get("ronda")
                        if ronda_nueva <= len(s["distribucion"]):
                            cant = s["distribucion"][ronda_nueva - 1]
                            m1 = [s["mazo"].pop() for _ in range(min(cant, len(s["mazo"])))]
                            m2 = [s["mazo"].pop() for _ in range(min(cant, len(s["mazo"])))]
                            
                            payload_ronda = {
                                "ronda": ronda_nueva,
                                "mano_j1": m1,
                                "mano_j2": m2
                            }
                            await s["jugador1"].send_text(json.dumps({"tipo": "NUEVA_RONDA", "datos": payload_ronda}))
                            if s["jugador2"]:
                                await s["jugador2"].send_text(json.dumps({"tipo": "NUEVA_RONDA", "datos": payload_ronda}))

                elif tipo == "FINALIZAR_PARTIDA":
                    if sala_actual and sala_actual in salas:
                        s = salas[sala_actual]
                        mensaje_fin = json.dumps({"tipo": "FINALIZAR_PARTIDA", "datos": datos})
                        await s["jugador1"].send_text(mensaje_fin)
                        if s["jugador2"]:
                            await s["jugador2"].send_text(mensaje_fin)

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        if sala_actual and sala_actual in salas:
            del salas[sala_actual]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("servidor_casino:app", host="0.0.0.0", port=port)