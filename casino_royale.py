import os
import random
import sys
import threading
import json
import asyncio
import websockets
import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import Image, ImageTk

PALOS_MAP = {
    'Corazones': 'hearts',
    'Diamantes': 'diamonds',
    'Tréboles': 'clubs',
    'Picas': 'spades'
}

NOMBRES_CARTAS = {
    1: 'As', 2: '2', 3: '3', 4: '4', 5: '5', 
    6: '6', 7: '7', 8: '8', 9: '9', 10: '10', 
    11: 'J', 12: 'Q', 13: 'K', 15: 'Mona'
}

class Carta:
    def __init__(self, palo, nominal, es_mona=False):
        self.palo = palo
        self.nominal = nominal  
        self.es_mona = es_mona
        
        if es_mona:
            self.texto = "Mona (15)"
            self.puntos = 3
            self.valores_posibles = [15]
            self.nombre_archivo = "red_joker.png"
        else:
            nombre_val = NOMBRES_CARTAS.get(nominal, str(nominal))
            self.texto = f"{nombre_val} de {palo}"
            
            palo_code = PALOS_MAP.get(palo, '')
            if nominal == 1:
                val_str = "ace"
                self.nombre_archivo = f"{val_str}_of_{palo_code}.png"
            elif nominal in [11, 12, 13]:
                val_str = {11: 'jack', 12: 'queen', 13: 'king'}[nominal]
                self.nombre_archivo = f"{val_str}_of_{palo_code}2.png"
            else:
                self.nombre_archivo = f"{nominal}_of_{palo_code}.png"

            if nominal == 1:
                self.valores_posibles = [1, 14]
            else:
                self.valores_posibles = [nominal]

            if nominal == 10 and palo == 'Diamantes':
                self.puntos = 2  # Brillos
            elif nominal == 2 and palo == 'Picas':
                self.puntos = 1  # Duque
            elif nominal == 1:
                self.puntos = 1  # As
            else:
                self.puntos = 0

    def to_dict(self):
        return {'palo': self.palo, 'nominal': self.nominal, 'es_mona': self.es_mona}

    @staticmethod
    def from_dict(d):
        return Carta(d['palo'], d['nominal'], d['es_mona'])

    def __str__(self):
        return self.texto


class ElementoMesa:
    def __init__(self, cartas, valor_objetivo, bloqueada=False, creador_id=None):
        self.cartas = list(cartas)
        self.valor_objetivo = valor_objetivo
        self.bloqueada = bloqueada
        self.creador_id = creador_id

    def to_dict(self):
        return {
            'cartas': [c.to_dict() for c in self.cartas],
            'valor_objetivo': self.valor_objetivo,
            'bloqueada': self.bloqueada,
            'creador_id': self.creador_id
        }

    @staticmethod
    def from_dict(d):
        cartas = [Carta.from_dict(c) for c in d['cartas']]
        return ElementoMesa(cartas, d['valor_objetivo'], d['bloqueada'], d['creador_id'])


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
        if self.cartas:
            return self.cartas.pop()
        return None


class ClienteCasinoRed:
    def __init__(self, app_ref, host=None, puerto=None):
        self.app = app_ref
        self.uri = "wss://casino-master-wiah.onrender.com/ws"
        self.websocket = None
        self.loop = None
        self.hilo = None
        self.perfil_usuario = None

    def iniciar_conexion(self, username):
        self.hilo = threading.Thread(target=self._correr_loop, args=(username,), daemon=True)
        self.hilo.start()

    def _correr_loop(self, username):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._conectar_y_escuchar(username))

    async def _conectar_y_escuchar(self, username):
        try:
            async with websockets.connect(self.uri, ping_interval=20, ping_timeout=20) as websocket:
                self.websocket = websocket
                print(f"🔗 Conectado al servidor central de Casino Master en {self.uri}")

                mensaje_login = {
                    "tipo": "LOGIN",
                    "datos": {"username": username}
                }
                await websocket.send(json.dumps(mensaje_login))

                try:
                    async for mensaje in websocket:
                        datos = json.loads(mensaje)
                        tipo = datos.get("tipo")
                        payload = datos.get("datos", {})

                        if tipo == "LOGIN_EXITOSO":
                            self.perfil_usuario = payload.get("perfil")
                            self.app.root.after(0, lambda perfil=self.perfil_usuario: self.app.notificar_login_exitoso(perfil))
                        elif tipo == "SALA_CREADA":
                            sala_id = payload.get("sala_id")
                            nombre_sala = payload.get("nombre")
                            self.app.root.after(0, lambda sala_id=sala_id, nombre_sala=nombre_sala: self.app.notificar_sala_creada(sala_id, nombre_sala))
                        elif tipo == "UNIDO_SALA":
                            sala_id = payload.get("sala_id")
                            id_jugador = payload.get("id_jugador", 2)
                            self.app.root.after(0, lambda sala_id=sala_id, id_jugador=id_jugador: self.app.notificar_unido_sala(sala_id, id_jugador))
                        elif tipo == "INICIAR_PARTIDA":
                            self.app.root.after(0, lambda payload=payload: self.app.iniciar_partida_red(payload))
                        elif tipo == "NUEVA_RONDA":
                            self.app.root.after(0, lambda payload=payload: self.app.aplicar_nueva_ronda_red(payload))
                        elif tipo == "ACCION_JUEGO":
                            self.app.root.after(0, lambda payload=payload: self.app.procesar_accion_remota(payload))
                        elif tipo == "FINALIZAR_PARTIDA":
                            self.app.root.after(0, lambda: self.app.finalizar_juego_red())
                except websockets.exceptions.ConnectionClosed:
                    print("⚠️ La conexión con el servidor se cerró.")

        except Exception as e:
            print(f"⚠️ Error de conexión con el servidor WebSocket: {e}")
            self.app.root.after(0, lambda e=e: messagebox.showerror("Error de Red", f"No se pudo conectar al servidor: {e}"))

    def enviar_accion(self, tipo_accion, datos_accion):
        if self.websocket and self.loop:
            mensaje = {"tipo": tipo_accion, "datos": datos_accion}
            asyncio.run_coroutine_threadsafe(self.websocket.send(json.dumps(mensaje)), self.loop)

    def cerrar(self):
        if self.loop and self.websocket:
            try:
                asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
            except:
                pass


class CasinoRoyaleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Casino Master - Tradición Digital")
        
        self.root.attributes('-fullscreen', True)
        self.root.bind("<Escape>", lambda event: self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen')))
        
        self.root.configure(bg="#2d0a0a")

        self.modo_juego = None  
        self.cliente_red = None
        self.mi_id_jugador = 1  
        self.nombre_usuario = "Jugador"
        self.nombres_jugadores = {1: "Jugador 1", 2: "Jugador 2"}
        self.ia_ejecutando = False
        self.mazo = Mazo()
        self.ronda_actual = 1
        self.distribucion_rondas = [5, 4, 4, 4, 4, 5]

        self.turno_jugador = 1
        self.turno_inicial_partida = 1
        self.poseedor_llaves = 1

        self.mano_j1 = []
        self.mano_j2 = []
        
        self.pozo_j1 = []
        self.pozo_j2 = []

        self.mesa = []
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.imagenes_cache = {}
        
        self.ultimo_anuncio_captura = "♠ ¡Partida iniciada en Casino Master! ♦"

        self.mostrar_pantalla_inicio()

    def limpiar_ventana(self):
        for w in self.root.winfo_children():
            w.destroy()

    def mostrar_pantalla_inicio(self):
        if self.cliente_red:
            self.cliente_red.cerrar()
            self.cliente_red = None

        self.limpiar_ventana()

        frame_menu = tk.Frame(self.root, bg="#2d0a0a")
        frame_menu.pack(expand=True)

        lbl_titulo = tk.Label(frame_menu, text="♠ CASINO MASTER ♦", font=("Times New Roman", 38, "bold"), bg="#2d0a0a", fg="#d4af37")
        lbl_titulo.pack(pady=10)

        lbl_subsub = tk.Label(frame_menu, text="Tradicón Digital con WebSockets", font=("Arial", 12, "italic"), bg="#2d0a0a", fg="#00ffcc")
        lbl_subsub.pack(pady=5)

        lbl_sub = tk.Label(frame_menu, text="Selecciona el modo de juego", font=("Arial", 14, "bold"), bg="#2d0a0a", fg="#f5b041")
        lbl_sub.pack(pady=10)

        btn_1v1 = tk.Button(frame_menu, text="👥 Jugador vs Jugador (1v1 Local)", font=("Arial", 13, "bold"), bg="#3d1414", fg="#f5b041", activebackground="#5a1e1e", activeforeground="white", width=32, height=2, bd=2, relief="raised", command=lambda: self.iniciar_juego('1v1'))
        btn_1v1.pack(pady=8)

        btn_ia = tk.Button(frame_menu, text="🤖 Jugador vs IA Competitiva", font=("Arial", 13, "bold"), bg="#3d1414", fg="#f5b041", activebackground="#5a1e1e", activeforeground="white", width=32, height=2, bd=2, relief="raised", command=lambda: self.iniciar_juego('ia'))
        btn_ia.pack(pady=8)

        btn_online = tk.Button(frame_menu, text="🌐 Multijugador Online", font=("Arial", 13, "bold"), bg="#1e3d24", fg="#d4af37", activebackground="#2d6a4f", activeforeground="white", width=32, height=2, bd=2, relief="raised", command=self.configurar_online)
        btn_online.pack(pady=8)

    def configurar_online(self):
        username = simpledialog.askstring("Casino Master - Login", "Ingresa tu apodo (Nickname):", initialvalue="Julian")
        if not username:
            return

        username = username.strip()
        if not username:
            return

        self.nombre_usuario = username
        self.nombres_jugadores[self.mi_id_jugador] = username
        self.modo_juego = 'online'
        self.mi_id_jugador = 1
        self.nombres_jugadores[1] = username
        self.limpiar_ventana()

        frame_lobby = tk.Frame(self.root, bg="#2d0a0a")
        frame_lobby.pack(expand=True)

        tk.Label(frame_lobby, text="🌐 LOBBY DE CASINO MASTER", font=("Times New Roman", 26, "bold"), bg="#2d0a0a", fg="#d4af37").pack(pady=20)
        self.lbl_estado_lobby = tk.Label(frame_lobby, text="Conectando al servidor central...", font=("Arial", 13, "italic"), bg="#2d0a0a", fg="#00ffcc")
        self.lbl_estado_lobby.pack(pady=10)

        self.btn_crear_sala = tk.Button(frame_lobby, text="🎲 Crear Mesa de Juego", font=("Arial", 12, "bold"), bg="#234e35", fg="#d4af37", state="disabled", command=self.crear_sala_online)
        self.btn_crear_sala.pack(pady=8, ipadx=10, ipady=5)

        self.btn_unirse_sala = tk.Button(frame_lobby, text="🔗 Unirse a Mesa por ID", font=("Arial", 12, "bold"), bg="#1e3d24", fg="#d4af37", state="disabled", command=self.unirse_a_sala_prompt)
        self.btn_unirse_sala.pack(pady=8, ipadx=10, ipady=5)

        tk.Button(frame_lobby, text="❌ Volver al Menú", font=("Arial", 12, "bold"), bg="#4a1212", fg="white", command=self.mostrar_pantalla_inicio).pack(pady=10)

        self.cliente_red = ClienteCasinoRed(self)
        self.cliente_red.iniciar_conexion(username)

    def notificar_login_exitoso(self, perfil):
        fichas = perfil.get('fichas', 10000)
        username = perfil.get('username', 'Jugador')
        self.nombre_usuario = str(username).strip() or self.nombre_usuario
        self.nombres_jugadores[self.mi_id_jugador] = self.nombre_usuario
        self.lbl_estado_lobby.config(text=f"✅ ¡Conectado como {self.nombre_usuario}!\n🪙 Fichas: {fichas}")
        self.btn_crear_sala.config(state="normal")
        self.btn_unirse_sala.config(state="normal")

    def crear_sala_online(self):
        if self.cliente_red:
            self.mi_id_jugador = 1
            self.cliente_red.enviar_accion("CREAR_SALA", {"username": self.nombre_usuario})
            self.lbl_estado_lobby.config(text="🎲 Creando sala en el servidor...")

    def unirse_a_sala_prompt(self):
        sala_id = simpledialog.askstring("Unirse a Mesa", "Ingresa el ID de la sala (ej. sala_1234):")
        if sala_id and self.cliente_red:
            self.mi_id_jugador = 2
            self.cliente_red.enviar_accion("UNIR_SALA", {"sala_id": sala_id, "username": self.nombre_usuario})
            self.lbl_estado_lobby.config(text=f"Conectándose a la sala {sala_id}...")

    def notificar_sala_creada(self, sala_id, nombre_sala):
        messagebox.showinfo("Mesa Creada", f"¡Mesa creada con éxito!\n\nID DE SALA: {sala_id}\n\nComparte este código con tu amigo para jugar.")
        self.lbl_estado_lobby.config(text=f"🎲 Sala creada: {sala_id}\nEsperando a que se una el segundo jugador...")

    def notificar_unido_sala(self, sala_id, id_jugador):
        self.mi_id_jugador = id_jugador
        self.lbl_estado_lobby.config(text=f"✅ Unido a la sala {sala_id}. ¡Iniciando partida en breve!")

    def iniciar_partida_red(self, payload):
        datos = payload.get("datos", payload)

        # Los nombres deben venir del servidor para que ambos clientes
        # vean los apodos reales de los dos jugadores.
        nombres = datos.get("nombres_jugadores", {})
        if isinstance(nombres, dict):
            for clave, valor in nombres.items():
                try:
                    id_nombre = int(clave)
                except (TypeError, ValueError):
                    continue
                if id_nombre in (1, 2) and valor:
                    self.nombres_jugadores[id_nombre] = str(valor)

        nombre_j1 = datos.get("nombre_j1") or datos.get("jugador1_nombre")
        nombre_j2 = datos.get("nombre_j2") or datos.get("jugador2_nombre")
        if nombre_j1:
            self.nombres_jugadores[1] = str(nombre_j1)
        if nombre_j2:
            self.nombres_jugadores[2] = str(nombre_j2)

        # El nombre propio ingresado en el login es una alternativa segura
        # si el servidor todavía no envía el nombre de ese puesto.
        if self.mi_id_jugador in (1, 2):
            self.nombres_jugadores[self.mi_id_jugador] = self.nombre_usuario

        mesa = datos.get("mesa_inicial", [])
        m_j1 = datos.get("mano_j1", [])
        m_j2 = datos.get("mano_j2", [])
        self.ronda_actual = datos.get("ronda", 1)

        self.modo_juego = 'online'
        self.limpiar_ventana()
        self.crear_interfaz_juego()

        self.mesa = [ElementoMesa([Carta.from_dict(c)], c['nominal']) for c in mesa]
        self.mano_j1 = [Carta.from_dict(c) for c in m_j1]
        self.mano_j2 = [Carta.from_dict(c) for c in m_j2]
        self.pozo_j1 = []
        self.pozo_j2 = []
        self.poseedor_llaves = 1
        self.ultimo_anuncio_captura = "♠ ¡Partida iniciada! ♦"

        # El servidor puede indicar quién abre la partida. Si no lo hace,
        # alternamos entre 1 y 2 en cada revancha en ambos clientes.
        turno_inicial = datos.get("turno_inicial", datos.get("turno_jugador"))
        if turno_inicial not in (1, 2):
            turno_inicial = self.turno_inicial_partida
        self.turno_jugador = turno_inicial
        self.turno_inicial_partida = 2 if turno_inicial == 1 else 1
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.ia_ejecutando = False

        self.lbl_seleccion.config(text=f"¡Partida iniciada! Eres el Jugador {self.mi_id_jugador}")
        self.actualizar_vista()

    def aplicar_nueva_ronda_red(self, payload):
        datos = payload.get("datos", payload)
        self.ronda_actual = datos.get("ronda", self.ronda_actual)
        m_j1 = datos.get("mano_j1", [])
        m_j2 = datos.get("mano_j2", [])

        self.mano_j1 = [Carta.from_dict(c) for c in m_j1]
        self.mano_j2 = [Carta.from_dict(c) for c in m_j2]
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.ia_ejecutando = False
        turno_servidor = datos.get("turno_inicial", datos.get("turno_jugador"))
        if turno_servidor in (1, 2):
            self.turno_jugador = turno_servidor
        self.actualizar_vista()

    def procesar_accion_remota(self, payload):
        tipo_accion = payload.get("tipo_accion")
        jugador_id = payload.get("jugador_id")
        
        if jugador_id == self.mi_id_jugador:
            return # Ignorar eco propio

        mano_oponente = self.mano_j1 if jugador_id == 1 else self.mano_j2
        pozo_oponente = self.pozo_j1 if jugador_id == 1 else self.pozo_j2

        if tipo_accion == "LANZAR":
            carta = Carta.from_dict(payload.get("carta"))
            for c in list(mano_oponente):
                if c.nominal == carta.nominal and c.palo == carta.palo:
                    mano_oponente.remove(c)
                    break
            self.mesa.append(ElementoMesa([carta], carta.nominal))
            self.fusionar_pilas_mesa()
            self.ultimo_anuncio_captura = f"🃏 {self.obtener_nombre_jugador(jugador_id)} soltó {carta}"

        elif tipo_accion == "SUMAR":
            carta = Carta.from_dict(payload.get("carta"))
            indices = payload.get("indices_mesa")
            nuevo_objetivo = payload.get("nuevo_objetivo")
            
            for c in list(mano_oponente):
                if c.nominal == carta.nominal and c.palo == carta.palo:
                    mano_oponente.remove(c)
                    break
            
            cartas_combinadas = [carta]
            for idx in sorted(indices, reverse=True):
                elem = self.mesa.pop(idx)
                cartas_combinadas.extend(elem.cartas)

            self.mesa.append(ElementoMesa(cartas_combinadas, nuevo_objetivo, bloqueada=False, creador_id=jugador_id))
            self.fusionar_pilas_mesa()
            self.ultimo_anuncio_captura = f"➕ {self.obtener_nombre_jugador(jugador_id)} formó {nuevo_objetivo}"

        elif tipo_accion == "FILAR":
            carta = Carta.from_dict(payload.get("carta"))
            indices = payload.get("indices_mesa")
            objetivo_fila = payload.get("objetivo_fila")
            
            for c in list(mano_oponente):
                if c.nominal == carta.nominal and c.palo == carta.palo:
                    mano_oponente.remove(c)
                    break
            
            cartas_combinadas = [carta]
            for idx in sorted(indices, reverse=True):
                elem = self.mesa.pop(idx)
                cartas_combinadas.extend(elem.cartas)

            self.mesa.append(ElementoMesa(cartas_combinadas, objetivo_fila, bloqueada=True, creador_id=jugador_id))
            self.fusionar_pilas_mesa()
            self.ultimo_anuncio_captura = f"🛡️ {self.obtener_nombre_jugador(jugador_id)} formó {objetivo_fila}"

        elif tipo_accion == "CAPTURAR":
            carta = Carta.from_dict(payload.get("carta"))
            indices = payload.get("indices_mesa")
            
            for c in list(mano_oponente):
                if c.nominal == carta.nominal and c.palo == carta.palo:
                    mano_oponente.remove(c)
                    break
            
            cartas_capturadas_total = []
            for idx in sorted(indices, reverse=True):
                elem = self.mesa.pop(idx)
                cartas_capturadas_total.extend(elem.cartas)
                pozo_oponente.extend(elem.cartas)

            pozo_oponente.append(carta)
            self.poseedor_llaves = jugador_id
            self.fusionar_pilas_mesa()
            self.ultimo_anuncio_captura = self.generar_anuncio_captura(jugador_id, carta, cartas_capturadas_total)

        # Actualizar turno al rival
        self.turno_jugador = payload.get("nuevo_turno", 1 if self.turno_jugador == 2 else 2)
        self.actualizar_vista()

    def iniciar_juego(self, modo):
        self.modo_juego = modo
        self.mi_id_jugador = 1
        self.ia_ejecutando = False
        self.limpiar_ventana()
        self.crear_interfaz_juego()

        if self.modo_juego not in ['online']:
            self.iniciar_nueva_partida()
        else:
            self.lbl_seleccion.config(text="Esperando que ambos jugadores estén en la sala...")

    def obtener_imagen_carta(self, carta, ancho=80, alto=112):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        ruta_carpeta = os.path.join(base_dir, "cartas")
        ruta_imagen = os.path.join(ruta_carpeta, carta.nombre_archivo)
        
        if not os.path.exists(ruta_imagen) and os.path.exists(ruta_carpeta):
            for f in os.listdir(ruta_carpeta):
                f_lower = f.lower()
                if carta.es_mona:
                    if "joker" in f_lower or "red_joker" in f_lower:
                        ruta_imagen = os.path.join(ruta_carpeta, f)
                        break
                else:
                    palo_code = PALOS_MAP.get(carta.palo, '').lower()
                    if palo_code in f_lower:
                        if carta.nominal == 1 and "ace" in f_lower:
                            ruta_imagen = os.path.join(ruta_carpeta, f)
                            break
                        elif carta.nominal == 11 and "jack" in f_lower:
                            ruta_imagen = os.path.join(ruta_carpeta, f)
                            break
                        elif carta.nominal == 12 and "queen" in f_lower:
                            ruta_imagen = os.path.join(ruta_carpeta, f)
                            break
                        elif carta.nominal == 13 and "king" in f_lower:
                            ruta_imagen = os.path.join(ruta_carpeta, f)
                            break
                        elif f"{carta.nominal}_of_" in f_lower:
                            ruta_imagen = os.path.join(ruta_carpeta, f)
                            break

        clave_cache = (carta.nombre_archivo, ancho, alto)
        if clave_cache in self.imagenes_cache:
            return self.imagenes_cache[clave_cache]

        if os.path.exists(ruta_imagen):
            try:
                img_pil = Image.open(ruta_imagen)
                img_pil = img_pil.resize((ancho, alto), Image.Resampling.LANCZOS)
                img_tk = ImageTk.PhotoImage(img_pil)
                self.imagenes_cache[clave_cache] = img_tk
                return img_tk
            except Exception as e:
                print(f"⚠️ Error cargando imagen {carta.nombre_archivo}: {e}")
        return None

    def crear_interfaz_juego(self):
        lbl_titulo = tk.Label(self.root, text="♠ CASINO MASTER - TRADICIÓN DIGITAL ♦", font=("Times New Roman", 18, "bold"), bg="#2d0a0a", fg="#d4af37")
        lbl_titulo.pack(pady=3)

        self.lbl_estado = tk.Label(self.root, text="", font=("Arial", 11, "bold"), bg="#2d0a0a", fg="#f39c12")
        self.lbl_estado.pack(pady=2)

        self.lbl_seleccion = tk.Label(self.root, text="Selecciona una carta de tu mano", font=("Arial", 10, "italic"), bg="#2d0a0a", fg="#ffd700")
        self.lbl_seleccion.pack(pady=2)

        frame_mesa_container = tk.LabelFrame(self.root, text=" Paño de la Mesa ", font=("Times New Roman", 12, "bold"), bg="#4a1212", fg="#d4af37", bd=2, relief="groove")
        frame_mesa_container.pack(fill="both", expand=True, padx=25, pady=4)

        self.lbl_anuncio_vivo = tk.Label(
            frame_mesa_container, 
            text=self.ultimo_anuncio_captura, 
            font=("Times New Roman", 12, "bold"), 
            bg="#1a0505", 
            fg="#ffd700", 
            bd=2, 
            relief="ridge", 
            padx=12, 
            pady=6
        )
        self.lbl_anuncio_vivo.pack(fill="x", padx=15, pady=(8, 4))

        self.frame_mesa = tk.Frame(frame_mesa_container, bg="#4a1212")
        self.frame_mesa.pack(fill="both", expand=True, padx=10, pady=6)

        frame_inferior = tk.Frame(self.root, bg="#2d0a0a")
        frame_inferior.pack(fill="x", padx=25, pady=6)

        frame_mano_container = tk.LabelFrame(frame_inferior, text=" Tu Mano ", font=("Times New Roman", 12, "bold"), bg="#4a1212", fg="#d4af37", bd=2, relief="groove")
        frame_mano_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.frame_mano = tk.Frame(frame_mano_container, bg="#4a1212")
        self.frame_mano.pack(fill="both", expand=True, padx=10, pady=8)

        self.frame_cajon = tk.LabelFrame(frame_inferior, text=" 📥 Cajón de Captura ", font=("Times New Roman", 12, "bold"), bg="#1e3d24", fg="#d4af37", bd=3, relief="ridge")
        self.frame_cajon.pack(side="right", fill="both", padx=(10, 0), ipadx=10, ipady=4)

        self.btn_cajon_captura = tk.Button(
            self.frame_cajon, 
            text="📥 CAPTURAR\nAL POZO", 
            font=("Arial", 10, "bold"), 
            bg="#234e35", 
            fg="#d4af37", 
            activebackground="#2d6a4f", 
            activeforeground="white",
            bd=2, 
            relief="raised", 
            state="disabled", 
            command=self.ejecutar_captura_multiple
        )
        self.btn_cajon_captura.pack(expand=True, fill="both", padx=8, pady=8)

        frame_acciones_pano = tk.Frame(self.root, bg="#2d0a0a")
        frame_acciones_pano.pack(fill="x", padx=25, pady=(0, 6))

        self.btn_accion_suma = tk.Button(
            frame_acciones_pano, text="➕ Sumar", 
            font=("Arial", 10, "bold"), bg="#3b1f1f", fg="#d4af37", 
            activebackground="#542b2b", activeforeground="white", bd=2, relief="raised", state="disabled", command=self.ejecutar_suma_simple
        )
        self.btn_accion_suma.pack(side="left", padx=5)

        self.btn_accion_fila = tk.Button(
            frame_acciones_pano, text="🛡️ Filar", 
            font=("Arial", 10, "bold"), bg="#3b1f1f", fg="#d4af37", 
            activebackground="#542b2b", activeforeground="white", bd=2, relief="raised", state="disabled", command=self.ejecutar_crear_fila
        )
        self.btn_accion_fila.pack(side="left", padx=5)

        self.btn_accion_lanzar = tk.Button(
            frame_acciones_pano, text="🃏 Soltar", 
            font=("Arial", 10, "bold"), bg="#3b1f1f", fg="#d4af37", 
            activebackground="#542b2b", activeforeground="white", bd=2, relief="raised", state="disabled", command=self.lanzar_carta_suelta
        )
        self.btn_accion_lanzar.pack(side="left", padx=5)

        btn_menu = tk.Button(
            frame_acciones_pano, text="🏠 Menú", 
            font=("Arial", 10, "bold"), bg="#4a1212", fg="white", 
            activebackground="#641e1e", activeforeground="white", bd=2, relief="raised", command=self.mostrar_pantalla_inicio
        )
        btn_menu.pack(side="right", padx=5)

    def fusionar_sumatorias_equivalentes(self, objetivo):
        """Une a una fila ya formada las cartas sueltas cuya suma sea el mismo objetivo.

        Ejemplos: una fila de 15 absorbe Q+3; una fila de 11 absorbe 7+4.
        Solo considera cartas sueltas (elementos de una carta), para no permitir
        que una pila existente se combine con cartas externas para crear otra fila.
        """
        # Primero fusionar pilas que ya tengan exactamente el mismo valor.
        self.fusionar_pilas_mesa()
        while True:
            indice_fila = next((i for i, e in enumerate(self.mesa)
                                if e.valor_objetivo == objetivo and len(e.cartas) > 1), None)
            if indice_fila is None:
                return

            candidatos = [i for i, e in enumerate(self.mesa)
                          if i != indice_fila and len(e.cartas) == 1
                          and 0 < e.valor_objetivo < objetivo]
            encontrado = None
            # Buscar una combinación de cartas sueltas que sume el valor de la fila.
            # Se usa búsqueda exhaustiva porque la mesa normalmente tiene pocas cartas.
            def buscar(pos, suma, indices):
                nonlocal encontrado
                if suma == objetivo and indices:
                    encontrado = list(indices)
                    return True
                if suma >= objetivo or pos >= len(candidatos):
                    return False
                for j in range(pos, len(candidatos)):
                    idx = candidatos[j]
                    if buscar(j + 1, suma + self.mesa[idx].valor_objetivo, indices + [idx]):
                        return True
                return False

            if not buscar(0, 0, []):
                return

            # Incorporar todas las cartas sueltas encontradas a la fila existente.
            fila = self.mesa[indice_fila]
            for idx in sorted(encontrado, reverse=True):
                fila.cartas.extend(self.mesa[idx].cartas)
                self.mesa.pop(idx)
                if idx < indice_fila:
                    indice_fila -= 1
            self.fusionar_pilas_mesa()

    def fusionar_pilas_mesa(self):
        dic_agrupado = {}
        for elem in self.mesa:
            obj = elem.valor_objetivo
            if obj not in dic_agrupado:
                dic_agrupado[obj] = {
                    'cartas': list(elem.cartas),
                    'bloqueada': elem.bloqueada,
                    'creador_id': elem.creador_id
                }
            else:
                dic_agrupado[obj]['cartas'].extend(elem.cartas)
                if elem.bloqueada:
                    dic_agrupado[obj]['bloqueada'] = True
                if elem.creador_id is not None:
                    dic_agrupado[obj]['creador_id'] = elem.creador_id

        nueva_mesa = []
        for obj, datos in dic_agrupado.items():
            nueva_mesa.append(ElementoMesa(datos['cartas'], obj, bloqueada=datos['bloqueada'], creador_id=datos['creador_id']))
        self.mesa = nueva_mesa

    def iniciar_nueva_partida(self):
        self.mazo.reiniciar_y_mezclar()
        self.ronda_actual = 1
        self.pozo_j1 = []
        self.pozo_j2 = []
        self.mesa = []
        
        self.turno_jugador = self.turno_inicial_partida
        self.turno_inicial_partida = 2 if self.turno_inicial_partida == 1 else 1

        self.poseedor_llaves = 1
        self.ia_ejecutando = False
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.ultimo_anuncio_captura = "♠ ¡Partida iniciada! ♦"

        carta_inicial = self.mazo.robar()
        self.mesa.append(ElementoMesa([carta_inicial], carta_inicial.nominal))
        self.repartir_ronda()

    def repartir_ronda(self):
        if self.ronda_actual > len(self.distribucion_rondas):
            self.finalizar_juego()
            return

        cant = self.distribucion_rondas[self.ronda_actual - 1]
        self.mano_j1 = [self.mazo.robar() for _ in range(cant)]
        self.mano_j2 = [self.mazo.robar() for _ in range(cant)]
        self.ia_ejecutando = False
        self.actualizar_vista()

    def mano_posee_respaldo_para_valor(self, mano, valor_objetivo):
        """Indica si al menos una carta puede respaldar el valor indicado."""
        for c in mano:
            if c.es_mona and valor_objetivo == 15:
                return True
            if c.nominal == 1 and valor_objetivo in (1, 14):
                return True
            if not c.es_mona and c.nominal == valor_objetivo:
                return True
        return False

    def mano_puede_respaldar_valores(self, mano, valores_objetivo):
        """Asigna una carta DISTINTA a cada formación que necesita respaldo.

        Una misma carta no puede respaldar dos formaciones. Se usa búsqueda
        con retroceso porque el As puede respaldar tanto 1 como 14.
        """
        valores = list(valores_objetivo)
        if not valores:
            return True
        if len(mano) < len(valores):
            return False

        # Resolver primero los valores con menos cartas compatibles.
        def compatible(carta, valor):
            return (
                (carta.es_mona and valor == 15)
                or (not carta.es_mona and carta.nominal == valor)
                or (not carta.es_mona and carta.nominal == 1 and valor in (1, 14))
            )

        valores.sort(key=lambda valor: sum(1 for carta in mano if compatible(carta, valor)))
        usadas = [False] * len(mano)

        def asignar(posicion):
            if posicion == len(valores):
                return True
            valor = valores[posicion]
            for indice, carta in enumerate(mano):
                if not usadas[indice] and compatible(carta, valor):
                    usadas[indice] = True
                    if asignar(posicion + 1):
                        return True
                    usadas[indice] = False
            return False

        return asignar(0)

    def valores_formaciones_respaldo(self, id_jugador, indices_excluidos=()):
        """Valores de las formaciones propias que seguirán sobre la mesa."""
        excluidos = set(indices_excluidos)
        return [
            elem.valor_objetivo
            for indice, elem in enumerate(self.mesa)
            if indice not in excluidos
            and elem.creador_id == id_jugador
            # Toda formación propia activa debe respetarse, no solo las filas
            # bloqueadas o las de valor 12 o superior. Esto incluye, por ejemplo,
            # una formación de 7.
        ]

    def puede_formar_con_respaldo(self, mano, carta, id_jugador, objetivo, indices_mesa_usados, nueva_fila_bloqueada=False):
        """Comprueba los respaldos contando cada valor fusionado una sola vez.

        Las formaciones propias con el mismo valor objetivo se fusionan en una
        única pila. Por eso, crear otro 14 cuando ya existe un 14 no exige un
        segundo As: basta con conservar una carta que respalde ese valor.
        """
        mano_restante = list(mano)
        if carta in mano_restante:
            mano_restante.remove(carta)

        valores_existentes = self.valores_formaciones_respaldo(
            id_jugador, indices_mesa_usados
        )
        # La mesa fusiona las formaciones del mismo valor en una sola pila;
        # la validación debe contar esa pila una sola vez también.
        valores = list(dict.fromkeys(valores_existentes))
        if objetivo not in valores:
            valores.append(objetivo)

        return self.mano_puede_respaldar_valores(mano_restante, valores)

    def existe_jugada_alternativa_valida(self, id_jugador):
        """True si el jugador puede capturar o crear una formación respaldada.

        Se usa para impedir descartes arbitrarios mientras conserva formaciones
        propias activas. Solo considera elementos sueltos al construir sumas;
        no combina una pila existente con cartas externas.
        """
        mano = self.mano_j1 if id_jugador == 1 else self.mano_j2
        if not mano:
            return False

        # Opción 1: capturar cualquier conjunto legal de elementos de la mesa.
        for carta in mano:
            val_carta = 15 if carta.es_mona else (14 if carta.nominal == 1 else carta.nominal)
            n = len(self.mesa)
            for mascara in range(1, 1 << n):
                indices = [i for i in range(n) if mascara & (1 << i)]
                elementos = [self.mesa[i] for i in indices]
                # La validación de captura ya contempla pilas y sumas permitidas.
                if self.es_particion_valida_captura(elementos, val_carta):
                    return True
                # Para As, probar también valor 1 (además de 14).
                if carta.nominal == 1 and self.es_particion_valida_captura(elementos, 1):
                    return True

        # Opción 2: formar una suma legal con elementos sueltos y conservar
        # una carta distinta que respalde el objetivo.
        for carta in mano:
            if carta.es_mona:
                continue
            for idx, elem in enumerate(self.mesa):
                if len(elem.cartas) != 1 or elem.bloqueada or elem.valor_objetivo >= 15:
                    continue
                objetivo = elem.valor_objetivo + carta.nominal
                if carta.nominal == 1:
                    objetivos = {objetivo, elem.valor_objetivo + 14}
                else:
                    objetivos = {objetivo}
                for objetivo in objetivos:
                    if objetivo > 15:
                        continue
                    if self.puede_formar_con_respaldo(
                        mano, carta, id_jugador, objetivo, [idx],
                        nueva_fila_bloqueada=(objetivo >= 12)
                    ):
                        return True
        return False

    def es_lanzamiento_permitido(self, carta_seleccionada, id_jugador):
        mano_actual = self.mano_j1 if id_jugador == 1 else self.mano_j2

        coincide_valor_existente = any(
            (carta_seleccionada.nominal == elem.valor_objetivo)
            or (carta_seleccionada.nominal == 1 and elem.valor_objetivo in (1, 14))
            or (carta_seleccionada.es_mona and elem.valor_objetivo == 15)
            for elem in self.mesa
        )
        if coincide_valor_existente:
            return False

        valores = self.valores_formaciones_respaldo(id_jugador)
        if not valores:
            return True

        # Si hay una jugada legal alternativa (otra suma respaldada o captura),
        # no se permite descartar una carta sin relación con esa jugada.
        if self.existe_jugada_alternativa_valida(id_jugador):
            return False

        mano_restante = list(mano_actual)
        if carta_seleccionada in mano_restante:
            mano_restante.remove(carta_seleccionada)

        # Si no queda respaldo para las formaciones activas, el descarte tampoco
        # es legal: el jugador debe recoger una formación.
        return self.mano_puede_respaldar_valores(mano_restante, valores)

    def obtener_nombre_jugador(self, id_j):
        if self.modo_juego == 'ia':
            return "Julian" if id_j == 1 else "La IA"
        if self.modo_juego == 'online':
            nombre = self.nombres_jugadores.get(id_j)
            if nombre:
                return nombre
            return f"Jugador {id_j}"
        return "Julian" if id_j == 1 else "Jugador 2"

    def actualizar_vista(self):
        # No fusionar/reordenar la mesa durante el redibujado. En modo online
        # las acciones remotas usan índices; mutar la mesa al dibujar puede
        # desincronizar clientes y duplicar o dejar formaciones atascadas.
        # Las fusiones deben ocurrir dentro de las acciones del juego.
        id_j_actual = self.turno_jugador
        mano_actual = self.mano_j1 if self.mi_id_jugador == 1 else self.mano_j2
        nombre_turno = self.obtener_nombre_jugador(self.turno_jugador)
        
        self.lbl_estado.config(
            text=f"Ronda: {self.ronda_actual}/6 | Turno: {nombre_turno} | Llaves: J{self.poseedor_llaves}"
        )
        
        self.lbl_anuncio_vivo.config(text=self.ultimo_anuncio_captura)
        
        mano_del_turno = self.mano_j1 if id_j_actual == 1 else self.mano_j2
        valores_formaciones = self.valores_formaciones_respaldo(id_j_actual)
        esta_acorralado = not self.mano_puede_respaldar_valores(mano_del_turno, valores_formaciones)

        if esta_acorralado:
            self.lbl_seleccion.config(text="⚠️ ESTÁS ACORRALADO: No tienes respaldo para tu fila. Debes llevarla al cajón.")
        elif self.carta_seleccionada_temporal:
            suma_sel = sum(self.mesa[i].valor_objetivo for i in self.indices_mesa_seleccionados)
            txt_sel = f"Seleccionada: {self.carta_seleccionada_temporal} | Pilas paño: {len(self.indices_mesa_seleccionados)} (Suma total: {suma_sel})"
            self.lbl_seleccion.config(text=txt_sel)
        else:
            self.lbl_seleccion.config(text=f"Turno de {nombre_turno}: Selecciona una carta")

        bloquear_por_turno = False
        if self.modo_juego == 'online' and self.turno_jugador != self.mi_id_jugador:
            bloquear_por_turno = True
        elif self.modo_juego == 'ia' and self.turno_jugador == 2:
            bloquear_por_turno = True

        es_turno_ia = (self.modo_juego == 'ia' and self.turno_jugador == 2)

        hay_seleccion = (self.carta_seleccionada_temporal is not None) and not bloquear_por_turno
        tiene_pilas = len(self.indices_mesa_seleccionados) > 0

        permite_lanzar = False
        if hay_seleccion and not bloquear_por_turno:
            permite_lanzar = self.es_lanzamiento_permitido(self.carta_seleccionada_temporal, id_j_actual)

        pila_en_techo = any(self.mesa[idx].valor_objetivo >= 15 for idx in self.indices_mesa_seleccionados)
        puede_sumar_o_fila = hay_seleccion and tiene_pilas and not pila_en_techo and not bloquear_por_turno

        self.btn_cajon_captura.config(state="normal" if (hay_seleccion and tiene_pilas and not bloquear_por_turno) else "disabled")
        self.btn_accion_suma.config(state="normal" if puede_sumar_o_fila else "disabled")
        self.btn_accion_fila.config(state="normal" if puede_sumar_o_fila else "disabled")
        self.btn_accion_lanzar.config(state="normal" if permite_lanzar else "disabled")

        for w in self.frame_mesa.winfo_children():
            if w != self.lbl_anuncio_vivo:
                w.destroy()
        for w in self.frame_mano.winfo_children():
            w.destroy()

        if not self.mesa:
            lbl_vacia = tk.Label(self.frame_mesa, text="El paño está libre.", font=("Arial", 11, "italic"), bg="#4a1212", fg="#f5b041")
            lbl_vacia.pack(pady=15)
        else:
            frame_cartas_mesa = tk.Frame(self.frame_mesa, bg="#4a1212")
            frame_cartas_mesa.pack(fill="both", expand=True, pady=5)
            
            for i, elem in enumerate(self.mesa):
                es_sel = i in self.indices_mesa_seleccionados
                bg_color = "#8b0000" if es_sel else "#3d1010"

                frame_elem = tk.Frame(frame_cartas_mesa, bg=bg_color, bd=4 if es_sel else 2, relief="solid" if es_sel else "ridge", padx=6, pady=6)
                frame_elem.pack(side="left", padx=10, pady=4)

                cant_cartas = len(elem.cartas)
                ancho_img, alto_img = 75, 105
                offset_y = 18 * min(cant_cartas - 1, 5)
                canvas_alto = alto_img + offset_y

                canvas_pila = tk.Canvas(frame_elem, width=ancho_img, height=canvas_alto, bg=bg_color, highlightthickness=0)
                canvas_pila.pack()

                canvas_pila.imagenes_referencia = []
                for idx_carta, carta in enumerate(elem.cartas):
                    img_tk = self.obtener_imagen_carta(carta, ancho=ancho_img, alto=alto_img)
                    if img_tk:
                        canvas_pila.imagenes_referencia.append(img_tk)
                        pos_y = idx_carta * 18
                        canvas_pila.create_image(0, pos_y, anchor="nw", image=img_tk)

                canvas_pila.bind("<Button-1>", lambda event, idx=i: self.alternar_seleccion_mesa(idx))

        if es_turno_ia:
            lbl_ia_turno = tk.Label(self.frame_mano, text="🤖 La IA Competitiva está pensando su jugada...", font=("Arial", 11, "bold"), bg="#4a1212", fg="#ffd700")
            lbl_ia_turno.pack(pady=15)
            if not self.ia_ejecutando:
                self.ia_ejecutando = True
                self.root.after(800, self.ejecutar_turno_ia)
        else:
            for carta in mano_actual:
                es_mano_sel = (carta == self.carta_seleccionada_temporal)
                bg_mano = "#00ffcc" if es_mano_sel else "#3d1010"
                pad_top = 0 if es_mano_sel else 10

                frame_carta_wrapper = tk.Frame(self.frame_mano, bg="#4a1212")
                frame_carta_wrapper.pack(side="left", padx=6, pady=(pad_top, 4))

                img = self.obtener_imagen_carta(carta, ancho=85, alto=120)
                if img:
                    btn_carta = tk.Button(
                        frame_carta_wrapper, 
                        image=img, 
                        bg=bg_mano, 
                        activebackground="#00ffcc", 
                        bd=6 if es_mano_sel else 1,
                        relief="solid" if es_mano_sel else "raised",
                        command=lambda c=carta: self.seleccionar_carta_mano(c)
                    )
                else:
                    btn_carta = tk.Button(
                        frame_carta_wrapper, 
                        text=str(carta), 
                        font=("Arial", 9, "bold"), 
                        bg="#00ffcc" if es_mano_sel else "#ffffff", 
                        fg="#2d0a0a", 
                        width=10, 
                        height=4,
                        bd=5 if es_mano_sel else 1,
                        command=lambda c=carta: self.seleccionar_carta_mano(c)
                    )
                btn_carta.pack()

    def seleccionar_carta_mano(self, carta):
        if self.modo_juego == 'online' and self.turno_jugador != self.mi_id_jugador:
            return
        if self.turno_jugador == 2 and self.modo_juego == 'ia':
            return
            
        if self.carta_seleccionada_temporal == carta:
            self.carta_seleccionada_temporal = None
            self.indices_mesa_seleccionados = []
        else:
            self.carta_seleccionada_temporal = carta
            self.indices_mesa_seleccionados = []
        self.actualizar_vista()

    def alternar_seleccion_mesa(self, indice_mesa):
        if self.modo_juego == 'online' and self.turno_jugador != self.mi_id_jugador:
            return
        if self.turno_jugador == 2 and self.modo_juego == 'ia':
            return
        if not self.carta_seleccionada_temporal:
            return

        if indice_mesa in self.indices_mesa_seleccionados:
            self.indices_mesa_seleccionados.remove(indice_mesa)
        else:
            self.indices_mesa_seleccionados.append(indice_mesa)
        
        self.actualizar_vista()

    def es_particion_valida_captura(self, elementos_seleccionados, objetivo):
        """
        Verifica que cada elemento seleccionado de la mesa valga 'objetivo'
        O que cartas sueltas (no formaciones acumuladas) sumen 'objetivo'.
        Prohíbe terminantemente fusionar una formación/pila ya existente con cartas sueltas externas.
        """
        if not elementos_seleccionados:
            return False

        # Si solo seleccionó una pila/elemento de la mesa
        if len(elementos_seleccionados) == 1:
            return elementos_seleccionados[0].valor_objetivo == objetivo

        # Si seleccionó múltiples elementos de la mesa:
        # Caso A: Barrida limpia -> Todos los elementos tienen el valor exacto del objetivo (ej. J de la mesa + J de la mano)
        if all(elem.valor_objetivo == objetivo for elem in elementos_seleccionados):
            return True

        # Caso B: Suma de elementos sueltos.
        # Si alguno de los elementos seleccionados es una FORMACIÓN/PILA (más de 1 carta en ese grupo)
        # y su valor es diferente del objetivo, ¡NO SE PUEDE SUMAR CON CARTAS EXTERNAS!
        for elem in elementos_seleccionados:
            if len(elem.cartas) > 1 and elem.valor_objetivo != objetivo:
                return False

        # Caso C: Son cartas sueltas (1 carta por elemento) que juntas deben sumar 'objetivo'
        # o dividirse en grupos donde cada grupo sume exactamente 'objetivo'
        valores = [elem.valor_objetivo for elem in elementos_seleccionados]
        
        def verificar_subgrupos(lista_val, obj):
            if not lista_val:
                return True
            n = len(lista_val)
            for i in range(1, 1 << n):
                subconjunto = [lista_val[j] for j in range(n) if (i & (1 << j))]
                if sum(subconjunto) == obj:
                    restantes = [lista_val[j] for j in range(n) if not (i & (1 << j))]
                    if verificar_subgrupos(restantes, obj):
                        return True
            return False

        return verificar_subgrupos(valores, objetivo)

    def generar_anuncio_captura(self, id_jugador, carta_jugada, cartas_capturadas):
        nombre_jugador = self.obtener_nombre_jugador(id_jugador)
        brillos = any(c.nominal == 10 and c.palo == 'Diamantes' for c in cartas_capturadas) or (carta_jugada.nominal == 10 and carta_jugada.palo == 'Diamantes')
        duque = any(c.nominal == 2 and c.palo == 'Picas' for c in cartas_capturadas) or (carta_jugada.nominal == 2 and carta_jugada.palo == 'Picas')
        mona = any(c.es_mona for c in cartas_capturadas) or carta_jugada.es_mona

        if mona:
            return f"🔥 ¡{nombre_jugador} se llevó la Mona! 🔥"
        elif brillos:
            return f"💎 ¡{nombre_jugador} se llevó los Brillos! 💎"
        elif duque:
            return f"🗡️ ¡{nombre_jugador} se llevó el Duque! 🗡️"
        else:
            return f"✨ ¡{nombre_jugador} capturó cartas! ✨"

    def ejecutar_captura_multiple(self):
        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
            return

        carta = self.carta_seleccionada_temporal
        elementos_sel = [self.mesa[i] for i in self.indices_mesa_seleccionados]
        suma_total = sum(elem.valor_objetivo for elem in elementos_sel)
        
        val_carta = 14 if (carta.nominal == 1 and suma_total % 14 == 0) else (15 if carta.es_mona else carta.nominal)

        # Validación estricta que impide fusionar formaciones fijas con cartas externas
        if not self.es_particion_valida_captura(elementos_sel, val_carta):
            return

        id_j = self.turno_jugador
        pozo_activo = self.pozo_j1 if id_j == 1 else self.pozo_j2
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2

        cartas_capturadas_total = []
        indices_copia = list(self.indices_mesa_seleccionados)
        for idx in sorted(indices_copia, reverse=True):
            elem = self.mesa.pop(idx)
            cartas_capturadas_total.extend(elem.cartas)
            pozo_activo.extend(elem.cartas)

        pozo_activo.append(carta)
        mano_actual.remove(carta)
        self.poseedor_llaves = id_j
        self.fusionar_pilas_mesa()

        self.ultimo_anuncio_captura = self.generar_anuncio_captura(id_j, carta, cartas_capturadas_total)

        if self.modo_juego == 'online' and self.cliente_red:
            self.cliente_red.enviar_accion("ACCION_JUEGO", {
                "tipo_accion": "CAPTURAR",
                "carta": carta.to_dict(),
                "indices_mesa": indices_copia,
                "jugador_id": self.mi_id_jugador
            })

        self.siguiente_turno()

    def seleccion_mezcla_formacion_con_carta_externa(self, indices):
        """Impide sumar una formación/pila con cartas sueltas de otro valor.

        Una pila existente (por ejemplo, 4+2 que ya vale 6) puede ampliarse
        jugando una carta directamente sobre ella, pero no puede combinarse
        además con otra carta suelta (por ejemplo, un 3) para fabricar otro
        objetivo con una carta de la mano.
        """
        elementos = [self.mesa[i] for i in indices]
        for elem in elementos:
            if len(elem.cartas) > 1:
                if any(otro is not elem and otro.valor_objetivo != elem.valor_objetivo
                       for otro in elementos):
                    return True
        return False

    def ejecutar_suma_simple(self):
        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
            return

        # No permitir, por ejemplo, usar una pila 4+2 (valor 6) junto con un
        # 3 suelto y un As para formar 10. Para subir la pila de 6 a 10 debe
        # jugarse un 4 directamente sobre esa pila.
        if self.seleccion_mezcla_formacion_con_carta_externa(self.indices_mesa_seleccionados):
            messagebox.showwarning(
                "Formación no válida",
                "No puedes combinar una formación existente con cartas sueltas externas. Juega la carta directamente sobre la formación."
            )
            return

        carta = self.carta_seleccionada_temporal
        if carta.es_mona:
            return

        for idx in self.indices_mesa_seleccionados:
            if self.mesa[idx].valor_objetivo >= 15:
                return 
            elem = self.mesa[idx]
            if not elem.bloqueada and elem.creador_id == self.turno_jugador:
                return

        suma_mesa = sum(self.mesa[i].valor_objetivo for i in self.indices_mesa_seleccionados)
        nuevo_objetivo = suma_mesa + carta.nominal

        if nuevo_objetivo > 15:
            return

        id_j = self.turno_jugador
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2
        indices_copia = list(self.indices_mesa_seleccionados)
        if not self.puede_formar_con_respaldo(
            mano_actual, carta, id_j, nuevo_objetivo, indices_copia
        ):
            messagebox.showwarning(
                "Formación sin respaldo",
                "No puedes hacer esa formación: cada formación propia debe tener una carta distinta de respaldo en tu mano."
            )
            return

        cartas_combinadas = [carta]
        for idx in sorted(indices_copia, reverse=True):
            elem = self.mesa.pop(idx)
            cartas_combinadas.extend(elem.cartas)

        self.mesa.append(ElementoMesa(cartas_combinadas, nuevo_objetivo, bloqueada=False, creador_id=id_j))
        self.fusionar_sumatorias_equivalentes(nuevo_objetivo)
        mano_actual.remove(carta)

        nombre_j = self.obtener_nombre_jugador(id_j)
        self.ultimo_anuncio_captura = f"➕ {nombre_j} formó {nuevo_objetivo}"

        if self.modo_juego == 'online' and self.cliente_red:
            self.cliente_red.enviar_accion("ACCION_JUEGO", {
                "tipo_accion": "SUMAR",
                "carta": carta.to_dict(),
                "indices_mesa": indices_copia,
                "nuevo_objetivo": nuevo_objetivo,
                "jugador_id": self.mi_id_jugador
            })

        self.siguiente_turno()

    def ejecutar_crear_fila(self):
        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
            return

        # Aplicar la misma restricción al crear una fila protegida, para que
        # la jugada ilegal no pueda hacerse usando este otro botón.
        if self.seleccion_mezcla_formacion_con_carta_externa(self.indices_mesa_seleccionados):
            messagebox.showwarning(
                "Formación no válida",
                "No puedes combinar una formación existente con cartas sueltas externas. Juega la carta directamente sobre la formación."
            )
            return

        carta = self.carta_seleccionada_temporal
        if carta.es_mona:
            return

        for idx in self.indices_mesa_seleccionados:
            if self.mesa[idx].valor_objetivo >= 15:
                return

        id_j = self.turno_jugador
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2

        valores_mesa_sel = [self.mesa[i].valor_objetivo for i in self.indices_mesa_seleccionados]
        es_agrupacion_iguales = all(v == carta.nominal or (v in [1, 14] and carta.nominal == 1) for v in valores_mesa_sel)

        if es_agrupacion_iguales:
            objetivo_fila = carta.nominal
        else:
            suma_mesa = sum(valores_mesa_sel)
            if suma_mesa == carta.nominal or (carta.nominal == 1 and suma_mesa in [1, 14]):
                objetivo_fila = carta.nominal if carta.nominal != 1 else (14 if suma_mesa == 14 else 1)
            else:
                objetivo_fila = suma_mesa + carta.nominal

        if objetivo_fila > 15:
            return

        indices_copia = list(self.indices_mesa_seleccionados)
        if not self.puede_formar_con_respaldo(
            mano_actual, carta, id_j, objetivo_fila, indices_copia,
            nueva_fila_bloqueada=True
        ):
            messagebox.showwarning(
                "Formación sin respaldo",
                "No puedes hacer esa fila: cada formación propia debe tener una carta distinta de respaldo en tu mano."
            )
            return

        cartas_combinadas = [carta]
        for idx in sorted(indices_copia, reverse=True):
            elem = self.mesa.pop(idx)
            cartas_combinadas.extend(elem.cartas)

        self.mesa.append(ElementoMesa(cartas_combinadas, objetivo_fila, bloqueada=True, creador_id=id_j))
        self.fusionar_sumatorias_equivalentes(objetivo_fila)
        mano_actual.remove(carta)

        nombre_j = self.obtener_nombre_jugador(id_j)
        self.ultimo_anuncio_captura = f"🛡️ {nombre_j} formó {objetivo_fila}"

        if self.modo_juego == 'online' and self.cliente_red:
            self.cliente_red.enviar_accion("ACCION_JUEGO", {
                "tipo_accion": "FILAR",
                "carta": carta.to_dict(),
                "indices_mesa": indices_copia,
                "objetivo_fila": objetivo_fila,
                "jugador_id": self.mi_id_jugador
            })

        self.siguiente_turno()

    def lanzar_carta_suelta(self):
        if not self.carta_seleccionada_temporal:
            return
        
        id_j = self.turno_jugador
        carta = self.carta_seleccionada_temporal
        
        if not self.es_lanzamiento_permitido(carta, id_j):
            return

        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2
        if carta in mano_actual:
            mano_actual.remove(carta)
        self.mesa.append(ElementoMesa([carta], carta.nominal))
        self.fusionar_pilas_mesa()
        
        nombre_j = self.obtener_nombre_jugador(id_j)
        self.ultimo_anuncio_captura = f"🃏 {nombre_j} soltó {carta}"

        if self.modo_juego == 'online' and self.cliente_red:
            self.cliente_red.enviar_accion("ACCION_JUEGO", {
                "tipo_accion": "LANZAR",
                "carta": carta.to_dict(),
                "jugador_id": self.mi_id_jugador
            })

        self.siguiente_turno()

    def ejecutar_turno_ia(self):
        self.ia_ejecutando = False
        if self.ronda_actual > len(self.distribucion_rondas):
            return

        ia_mano = self.mano_j2
        if not ia_mano:
            self.siguiente_turno()
            return

        pozo_ia = self.pozo_j2
        mejor_opcion = None
        max_puntos_captura = -1

        for carta in ia_mano:
            val_comparar = 14 if (carta.nominal == 1) else (15 if carta.es_mona else carta.nominal)
            indices_captura = self.encontrar_mejor_combinacion_captura(val_comparar)
            if indices_captura is not None:
                puntos_pilas = sum(c.puntos for idx in indices_captura for c in self.mesa[idx].cartas) + carta.puntos
                if puntos_pilas > max_puntos_captura:
                    max_puntos_captura = puntos_pilas
                    mejor_opcion = (carta, indices_captura)

        if mejor_opcion is not None:
            carta, indices_captura = mejor_opcion
            cartas_capturadas_total = []
            for idx in sorted(indices_captura, reverse=True):
                elem = self.mesa.pop(idx)
                cartas_capturadas_total.extend(elem.cartas)
                pozo_ia.extend(elem.cartas)
            pozo_ia.append(carta)
            ia_mano.remove(carta)
            self.poseedor_llaves = 2
            self.ultimo_anuncio_captura = self.generar_anuncio_captura(2, carta, cartas_capturadas_total)
            self.siguiente_turno()
            return

        for carta in ia_mano:
            if carta.es_mona or carta.nominal == 1:
                continue
            for idx, elem in enumerate(self.mesa):
                if not elem.bloqueada and elem.valor_objetivo < 15:
                    nuevo_objetivo = elem.valor_objetivo + carta.nominal
                    if nuevo_objetivo <= 15:
                        if self.puede_formar_con_respaldo(
                            ia_mano, carta, 2, nuevo_objetivo, [idx],
                            nueva_fila_bloqueada=(nuevo_objetivo >= 12)
                        ):
                            cartas_combinadas = [carta] + list(elem.cartas)
                            self.mesa.pop(idx)
                            bloquear_fila = (nuevo_objetivo >= 12)
                            self.mesa.append(ElementoMesa(cartas_combinadas, nuevo_objetivo, bloqueada=bloquear_fila, creador_id=2))
                            self.fusionar_pilas_mesa()
                            ia_mano.remove(carta)
                            self.ultimo_anuncio_captura = f"➕ La IA formó {nuevo_objetivo}"
                            self.siguiente_turno()
                            return

        cartas_validas = [c for c in ia_mano if self.es_lanzamiento_permitido(c, 2)]
        if cartas_validas:
            cartas_seguras = [c for c in cartas_validas if c.puntos == 0 and not c.es_mona and c.nominal not in [1, 10, 2]]
            carta_a_lanzar = cartas_seguras[0] if cartas_seguras else cartas_validas[0]
            ia_mano.remove(carta_a_lanzar)
            self.mesa.append(ElementoMesa([carta_a_lanzar], carta_a_lanzar.nominal))
            self.fusionar_pilas_mesa()
            self.ultimo_anuncio_captura = f"🃏 La IA soltó {carta_a_lanzar}"
            self.siguiente_turno()
            return

        carta_a_lanzar = ia_mano[0]
        ia_mano.remove(carta_a_lanzar)
        self.mesa.append(ElementoMesa([carta_a_lanzar], carta_a_lanzar.nominal))
        self.fusionar_pilas_mesa()
        self.ultimo_anuncio_captura = f"🃏 La IA soltó una carta"
        self.siguiente_turno()

    def encontrar_mejor_combinacion_captura(self, objetivo):
        n = len(self.mesa)
        for i in range(1, 1 << n):
            sub_indices = [j for j in range(n) if (i & (1 << j))]
            elementos_sub = [self.mesa[idx] for idx in sub_indices]
            if self.es_particion_valida_captura(elementos_sub, objetivo):
                return sub_indices
        return None

    def siguiente_turno(self):
        self.ia_ejecutando = False
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []

        # Cambiar al otro jugador antes de comprobar si terminó la ronda.
        self.turno_jugador = 2 if self.turno_jugador == 1 else 1

        # Importante: comprobar las manos después de CADA jugada. Si el primer
        # jugador de la ronda alternó por la revancha, el último movimiento puede
        # corresponder al Jugador 1; la comprobación anterior solo funcionaba
        # correctamente cuando el último movimiento era del Jugador 2.
        if not self.mano_j1 and not self.mano_j2:
            if self.ronda_actual >= len(self.distribucion_rondas):
                if self.modo_juego == 'online' and self.cliente_red:
                    self.cliente_red.enviar_accion("FINALIZAR_PARTIDA", {})
                self.finalizar_juego()
                return

            self.ronda_actual += 1
            if self.modo_juego == 'online' and self.cliente_red:
                # El servidor reparte y notifica NUEVA_RONDA a ambos clientes.
                self.cliente_red.enviar_accion("REPARTIR_RONDA", {"ronda": self.ronda_actual})
                return

            self.repartir_ronda()
            return

        self.actualizar_vista()

    def finalizar_juego_red(self):
        if isinstance(self.root.winfo_children()[-1], tk.Frame) and any(w.cget("text") == "♠ FIN DE LA PARTIDA ♦" for w in self.root.winfo_children()[-1].winfo_children() if isinstance(w, tk.Label)):
            return
        self.finalizar_juego()

    def solicitar_revancha(self):
        if self.modo_juego == 'online' and self.cliente_red:
            self.cliente_red.enviar_accion("SOLICITAR_REVANCHA", {})
            messagebox.showinfo("Revancha", "Solicitud de revancha enviada.")
        else:
            self.iniciar_nueva_partida()

    def finalizar_juego(self):
        if self.mesa:
            pozo_ganador = self.pozo_j1 if self.poseedor_llaves == 1 else self.pozo_j2
            for elem in self.mesa:
                pozo_ganador.extend(elem.cartas)
            self.mesa = []

        brillos_j1 = sum(1 for c in self.pozo_j1 if c.nominal == 10 and c.palo == 'Diamantes') * 2
        brillos_j2 = sum(1 for c in self.pozo_j2 if c.nominal == 10 and c.palo == 'Diamantes') * 2

        duque_j1 = sum(1 for c in self.pozo_j1 if c.nominal == 2 and c.palo == 'Picas') * 1
        duque_j2 = sum(1 for c in self.pozo_j2 if c.nominal == 2 and c.palo == 'Picas') * 1

        ases_j1 = sum(1 for c in self.pozo_j1 if c.nominal == 1) * 1
        ases_j2 = sum(1 for c in self.pozo_j2 if c.nominal == 1) * 1

        mona_j1 = sum(3 for c in self.pozo_j1 if c.es_mona)
        mona_j2 = sum(3 for c in self.pozo_j2 if c.es_mona)

        pts_cartas_j1 = 3 if len(self.pozo_j1) > len(self.pozo_j2) else 0
        pts_cartas_j2 = 3 if len(self.pozo_j2) > len(self.pozo_j1) else 0

        picas_j1_cnt = sum(1 for c in self.pozo_j1 if c.palo == 'Picas')
        picas_j2_cnt = sum(1 for c in self.pozo_j2 if c.palo == 'Picas')
        pts_picas_j1 = 1 if picas_j1_cnt > picas_j2_cnt else 0
        pts_picas_j2 = 1 if picas_j2_cnt > picas_j1_cnt else 0

        total_j1 = brillos_j1 + duque_j1 + ases_j1 + mona_j1 + pts_cartas_j1 + pts_picas_j1
        total_j2 = brillos_j2 + duque_j2 + ases_j2 + mona_j2 + pts_cartas_j2 + pts_picas_j2

        nombre_j2 = "Jugador 2" if self.modo_juego in ['1v1', 'online'] else "IA Competitiva"
        
        if total_j1 > total_j2:
            ganador_txt = "¡JULIAN GANA LA PARTIDA!"
            color_ganador = "#2ecc71"
        elif total_j2 > total_j1:
            ganador_txt = f"¡{nombre_j2.upper()} GANA LA PARTIDA!"
            color_ganador = "#e74c3c"
        else:
            ganador_txt = "¡EMPATE TÉCNICO!"
            color_ganador = "#f39c12"

        self.limpiar_ventana()

        frame_resultado = tk.Frame(self.root, bg="#2d0a0a")
        frame_resultado.pack(expand=True, fill="both", padx=50, pady=30)

        lbl_fin = tk.Label(frame_resultado, text="♠ FIN DE LA PARTIDA ♦", font=("Times New Roman", 30, "bold"), bg="#2d0a0a", fg="#d4af37")
        lbl_fin.pack(pady=10)

        lbl_ganador = tk.Label(frame_resultado, text=ganador_txt, font=("Arial", 18, "bold"), bg="#2d0a0a", fg=color_ganador)
        lbl_ganador.pack(pady=10)

        frame_tarjetas = tk.Frame(frame_resultado, bg="#2d0a0a")
        frame_tarjetas.pack(expand=True, fill="both", pady=10)

        frame_j1 = tk.LabelFrame(frame_tarjetas, text=" 🔵 JULIAN: Total [ " + str(total_j1) + " PTS ] ", font=("Times New Roman", 14, "bold"), bg="#4a1212", fg="#d4af37", bd=3, relief="groove")
        frame_j1.pack(side="left", expand=True, fill="both", padx=15, pady=10)

        txt_j1 = (
            f"• BRILLOS (10♦): {brillos_j1} pts\n"
            f"• DUQUE (2♠): {duque_j1} pts\n"
            f"• Ases: {ases_j1} pts\n"
            f"• Mona (15): {mona_j1} pts\n"
            f"• Mayoría de Cartas ({len(self.pozo_j1)}): {pts_cartas_j1} pts\n"
            f"• Mayoría de Picas ({picas_j1_cnt}): {pts_picas_j1} pts"
        )
        tk.Label(frame_j1, text=txt_j1, font=("Arial", 12), bg="#4a1212", fg="white", justify="left").pack(padx=20, pady=20, anchor="w")

        frame_j2 = tk.LabelFrame(frame_tarjetas, text=f" 🔴 {nombre_j2.upper()}: Total [ {total_j2} PTS ] ", font=("Times New Roman", 14, "bold"), bg="#4a1212", fg="#d4af37", bd=3, relief="groove")
        frame_j2.pack(side="right", expand=True, fill="both", padx=15, pady=10)

        txt_j2 = (
            f"• BRILLOS (10♦): {brillos_j2} pts\n"
            f"• DUQUE (2♠): {duque_j2} pts\n"
            f"• Ases: {ases_j2} pts\n"
            f"• Mona (15): {mona_j2} pts\n"
            f"• Mayoría de Cartas ({len(self.pozo_j2)}): {pts_cartas_j2} pts\n"
            f"• Mayoría de Picas ({picas_j2_cnt}): {pts_picas_j2} pts"
        )
        tk.Label(frame_j2, text=txt_j2, font=("Arial", 12), bg="#4a1212", fg="white", justify="left").pack(padx=20, pady=20, anchor="w")

        lbl_llaves = tk.Label(frame_resultado, text=f"🔑 Llaves finales ganadas por: {'Julian' if self.poseedor_llaves == 1 else nombre_j2}", font=("Arial", 12, "italic"), bg="#2d0a0a", fg="#f5b041")
        lbl_llaves.pack(pady=10)

        frame_botones_fin = tk.Frame(frame_resultado, bg="#2d0a0a")
        frame_botones_fin.pack(pady=15)

        tk.Button(frame_botones_fin, text="🔄 Revancha", font=("Arial", 14, "bold"), bg="#1e3d24", fg="#d4af37", activebackground="#2d6a4f", bd=3, relief="raised", command=self.solicitar_revancha).pack(side="left", padx=10, ipady=6, ipadx=15)
        tk.Button(frame_botones_fin, text="🏠 Menú Principal", font=("Arial", 14, "bold"), bg="#4a1212", fg="white", activebackground="#641e1e", bd=3, relief="raised", command=self.mostrar_pantalla_inicio).pack(side="right", padx=10, ipady=6, ipadx=15)

if __name__ == "__main__":
    root = tk.Tk()
    app = CasinoRoyaleApp(root)
    root.mainloop()