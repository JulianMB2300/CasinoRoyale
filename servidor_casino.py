import asyncio
import json
import os
import random
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

# Diccionario para almacenar las salas activas y los clientes conectados
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
                        "nombre": sala_id
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
                        
                        # Notificar al jugador 2 que se unió
                        await websocket.send_text(json.dumps({
                            "tipo": "UNIDO_SALA",
                            "datos": {"sala_id": sala_id, "id_jugador": 2}
                        }))
                        
                        # Iniciar la partida para ambos creando un mazo y barajando cartas iniciales
                        palo_list = ['Corazones', 'Diamantes', 'Tréboles', 'Picas']
                        deck = []
                        for p in palo_list:
                            for v in range(1, 14):
                                deck.append({"palo": p, "nominal": v, "es_mona": False})
                        deck.append({"palo": 'Especial', "nominal": 15, "es_mona": True})
                        random.shuffle(deck)
                        
                        carta_mesa = [deck.pop()]
                        m1 = [deck.pop() for _ in range(5)]
                        m2 = [deck.pop() for _ in range(5)]
                        
                        payload_partida = {
                            "mesa_inicial": carta_mesa,
                            "mano_j1": m1,
                            "mano_j2": m2
                        }
                        
                        # Enviar a jugador 1 y jugador 2
                        await salas[sala_id]["jugador1"].send_text(json.dumps({
                            "tipo": "INICIAR_PARTIDA",
                            "datos": payload_partida
                        }))
                        await salas[sala_id]["jugador2"].send_text(json.dumps({
                            "tipo": "INICIAR_PARTIDA",
                            "datos": payload_partida
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "tipo": "ERROR",
                            "datos": {"mensaje": "Sala no encontrada o llena"}
                        }))

                elif tipo == "ACCION_JUEGO":
                    if sala_actual and sala_actual in salas:
                        s = salas[sala_actual]
                        # Reenviar la acción a TODOS los jugadores de la sala para mantener sincronización perfecta
                        for cliente_ws in [s["jugador1"], s["jugador2"]]:
                            if cliente_ws:
                                await cliente_ws.send_text(json.dumps({
                                    "tipo": "ACCION_JUEGO",
                                    "datos": datos
                                }))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        if sala_actual and sala_actual in salas:
            del salas[sala_actual]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("servidor_casino:app", host="0.0.0.0", port=port)