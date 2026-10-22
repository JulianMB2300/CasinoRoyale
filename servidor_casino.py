import asyncio
import json
import random
import websockets
from supabase import create_client, Client

# ==========================================
# CONFIGURACIÓN DE SUPABASE (Tus credenciales)
# ==========================================
SUPABASE_URL = "https://gywyghqttyvvgzpcyoms.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5d3lnaHF0dHl2dmd6cGN5b21zIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI2OTI4ODIsImV4cCI6MjEwODI2ODg4Mn0.bvmYqAgBIQi2NYntOekELCU4Vbt1KX7n4_15SBYNYfI"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# GESTOR DE SALAS Y CONEXIONES (LOBBY)
# ==========================================
CLIENTES_CONECTADOS = {}  # {websocket: user_data}
SALAS_JUEGO = {}           # {sala_id: datos_sala}

async def registrar_usuario_db(user_id, username):
    """Verifica o crea el perfil del usuario en Supabase de forma segura."""
    try:
        res = supabase.table('perfiles').select('*').eq('id', str(user_id)).execute()
        if not res.data:
            nueva_cuenta = {
                'id': str(user_id),
                'username': username,
                'fichas': 10000,
                'nivel': 1,
                'victorias': 0,
                'derrotas': 0
            }
            supabase.table('perfiles').insert(nueva_cuenta).execute()
            return nueva_cuenta
        return res.data[0]
    except Exception as e:
        print(f"⚠️ Error accediendo a Supabase: {e}")
        return {
            'id': str(user_id),
            'username': username,
            'fichas': 10000,
            'nivel': 1,
            'victorias': 0,
            'derrotas': 0
        }

# ==========================================
# MANEJADOR PRINCIPAL DE WEBSOCKETS
# ==========================================
async def manejador_conexion(websocket):
    print(f"🔌 Nueva conexión establecida desde {websocket.remote_address}")
    CLIENTES_CONECTADOS[websocket] = None

    try:
        async for mensaje in websocket:
            datos = json.loads(mensaje)
            tipo = datos.get('tipo')
            payload = datos.get('datos', {})

            if tipo == 'LOGIN':
                username = payload.get('username', 'Jugador')
                user_id = payload.get('user_id', str(hash(username)))
                
                perfil = await registrar_usuario_db(user_id, username)
                CLIENTES_CONECTADOS[websocket] = perfil

                respuesta = {
                    'tipo': 'LOGIN_EXITOSO',
                    'datos': {
                        'perfil': perfil,
                        'salas_disponibles': list(SALAS_JUEGO.keys())
                    }
                }
                await websocket.send(json.dumps(respuesta))
                print(f"✅ Usuario autenticado en Supabase: {username} ({perfil.get('fichas', 0)} 🪙)")

            elif tipo == 'CREAR_SALA':
                nombre_sala = f"Mesa de {CLIENTES_CONECTADOS[websocket]['username']}"
                sala_id = f"sala_{random.randint(1000, 9999)}"
                
                SALAS_JUEGO[sala_id] = {
                    'nombre': nombre_sala,
                    'host': websocket,
                    'jugadores': [CLIENTES_CONECTADOS[websocket]],
                    'estado': 'esperando'
                }

                respuesta = {
                    'tipo': 'SALA_CREADA',
                    'datos': {'sala_id': sala_id, 'nombre': nombre_sala}
                }
                await websocket.send(json.dumps(respuesta))
                print(f"🎲 Sala creada: {sala_id}")

    except websockets.exceptions.ConnectionClosedError:
        print("⚠️ Un cliente se desconectó repentinamente.")
    finally:
        if websocket in CLIENTES_CONECTADOS:
            del CLIENTES_CONECTADOS[websocket]

# ==========================================
# ARRANQUE DEL SERVIDOR EN LA NUBE O LOCAL
# ==========================================
async def main():
    import os
    PUERTO = int(os.environ.get("PORT", 8080))
    async with websockets.serve(manejador_conexion, "0.0.0.0", PUERTO):
        print(f"🚀 Servidor de Casino Master corriendo en puerto {PUERTO}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())