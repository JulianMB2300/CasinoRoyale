import asyncio
import json
import random
import websockets

PALOS_MAP = {
    'Corazones': 'hearts',
    'Diamantes': 'diamonds',
    'Tréboles': 'clubs',
    'Picas': 'spades'
}

class Carta:
    def __init__(self, palo, nominal, es_mona=False):
        self.palo = palo
        self.nominal = nominal
        self.es_mona = es_mona

    def to_dict(self):
        return {'palo': self.palo, 'nominal': self.nominal, 'es_mona': self.es_mona}

class Mazo:
    def __init__(self):
        self.cartas = []
        self.reiniciar_y_mezclar()

    def reiniciar_y_mezclar(self):
        self.cartas = []
        for palo in ['Corazones', 'Diamantes', 'Tréboles', 'Picas']:
            for val in range(1, 14):
                self.cartas.append(Carta(palo, val))
        self.cartas.append(Carta('Especial', 15, es_mona=True))
        random.shuffle(self.cartas)

    def robar(self):
        return self.cartas.pop() if self.cartas else None

# Almacenamiento global de salas y conexiones
SALAS = {}
JUGADORES = {}

async def manejar_conexion(websocket):
    username = "Jugador"
    try:
        async for mensaje in websocket:
            data = json.loads(mensaje)
        tipo = data.get("tipo")
        datos = data.get("datos", {})

        if tipo == "ACCION_JUEGO":
            # Buscar en qué sala está este websocket y reenviar la jugada al otro jugador
            for s_id, info in SALAS.items():
                if websocket in info["jugadores"]:
                    for ws in info["jugadores"]:
                        if ws != websocket:
                            await ws.send(json.dumps(data))
                    break

            if tipo == "LOGIN":
                username = datos.get("username", "Jugador")
                JUGADORES[websocket] = username
                perfil = {"username": username, "fichas": 10000}
                await websocket.send(json.dumps({
                    "tipo": "LOGIN_EXITOSO",
                    "datos": {"perfil": perfil}
                }))

            elif tipo == "CREAR_SALA":
                sala_id = f"sala_{random.randint(1000, 9999)}"
                SALAS[sala_id] = {
                    "id": sala_id,
                    "creador": websocket,
                    "jugadores": [websocket],
                    "estado": "ESPERANDO"
                }
                await websocket.send(json.dumps({
                    "tipo": "SALA_CREADA",
                    "datos": {"sala_id": sala_id, "nombre": f"Mesa de {username}"}
                }))

            elif tipo == "UNIR_SALA":
                sala_id = datos.get("sala_id")
                if sala_id in SALAS and len(SALAS[sala_id]["jugadores"]) < 2:
                    SALAS[sala_id]["jugadores"].append(websocket)
                    SALAS[sala_id]["estado"] = "LLENA"

                    # 1. Notificar a ambos jugadores que la sala ya está lista
                    for idx, ws in enumerate(SALAS[sala_id]["jugadores"]):
                        await ws.send(json.dumps({
                            "tipo": "UNIDO_SALA",
                            "datos": {"sala_id": sala_id, "id_jugador": idx + 1}
                        }))

                    # 2. Generar partida inicial y sincronizar a ambos
                    mazo = Mazo()
                    carta_inicial = mazo.robar()
                    mano_j1 = [mazo.robar().to_dict() for _ in range(5)]
                    mano_j2 = [mazo.robar().to_dict() for _ in range(5)]

                    payload_inicio = {
                        "tipo": "INICIAR_PARTIDA",
                        "datos": {
                            "sala_id": sala_id,
                            "mesa_inicial": [carta_inicial.to_dict()],
                            "mano_j1": mano_j1,
                            "mano_j2": mano_j2
                        }
                    }

                    for ws in SALAS[sala_id]["jugadores"]:
                        await ws.send(json.dumps(payload_inicio))
                else:
                    await websocket.send(json.dumps({
                        "tipo": "ERROR_SALA",
                        "datos": {"mensaje": "La sala no existe o está llena"}
                    }))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in JUGADORES:
            del JUGADORES[websocket]

async def main():
    import os
    port = int(os.environ.get("PORT", 8080))
    async with websockets.serve(manejar_conexion, "0.0.0.0", port):
        print(f"🚀 Servidor Casino Master escuchando en el puerto {port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())