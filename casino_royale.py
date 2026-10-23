import os
import random
import socket
import threading
import json
import tkinter as tk
from tkinter import simpledialog
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


class CasinoRoyaleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Casino Royale - Tradición Digital")
        
        self.root.attributes('-fullscreen', True)
        self.root.bind("<Escape>", lambda event: self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen')))
        
        self.root.configure(bg="#2d0a0a")

        self.modo_juego = None  
        self.socket_conexion = None
        self.mi_id_jugador = 1  
        self.ia_ejecutando = False
        self.mazo = Mazo()
        self.ronda_actual = 1
        self.distribucion_rondas = [5, 4, 4, 4, 4, 5]

        self.turno_jugador = 1
        self.turno_inicial_partida = 1
        self.poseedor_llaves = 1
        self.pantalla_resultado_activa = False

        self.mano_j1 = []
        self.mano_j2 = []
        
        self.pozo_j1 = []
        self.pozo_j2 = []

        self.mesa = []
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.imagenes_cache = {}

        self.mostrar_pantalla_inicio()

    def limpiar_ventana(self):
        for w in self.root.winfo_children():
            w.destroy()

    def mostrar_pantalla_inicio(self):
        self.cerrar_sockets()
        self.limpiar_ventana()

        frame_menu = tk.Frame(self.root, bg="#2d0a0a")
        frame_menu.pack(expand=True)

        lbl_titulo = tk.Label(frame_menu, text="♠ CASINO ROYALE ♦", font=("Times New Roman", 38, "bold"), bg="#2d0a0a", fg="#d4af37")
        lbl_titulo.pack(pady=15)

        lbl_sub = tk.Label(frame_menu, text="Selecciona el modo de juego tradicional", font=("Arial", 14, "italic"), bg="#2d0a0a", fg="#f5b041")
        lbl_sub.pack(pady=10)

        btn_1v1 = tk.Button(frame_menu, text="👥 Jugador vs Jugador (1v1 Local)", font=("Arial", 13, "bold"), bg="#1b4f72", fg="white", activebackground="#2980b9", width=32, height=2, bd=3, relief="raised", command=lambda: self.iniciar_juego('1v1'))
        btn_1v1.pack(pady=10)

        btn_ia = tk.Button(frame_menu, text="🤖 Jugador vs IA Competitiva", font=("Arial", 13, "bold"), bg="#1e5128", fg="white", activebackground="#2d6a4f", width=32, height=2, bd=3, relief="raised", command=lambda: self.iniciar_juego('ia'))
        btn_ia.pack(pady=10)

        btn_host = tk.Button(frame_menu, text="🌐 Crear Partida en Red (Host)", font=("Arial", 13, "bold"), bg="#b9770e", fg="white", activebackground="#d68910", width=32, height=2, bd=3, relief="raised", command=self.configurar_host)
        btn_host.pack(pady=10)

        btn_cliente = tk.Button(frame_menu, text="🔗 Unirse a Partida Online", font=("Arial", 13, "bold"), bg="#6c3483", fg="white", activebackground="#8e44ad", width=32, height=2, bd=3, relief="raised", command=self.configurar_cliente)
        btn_cliente.pack(pady=10)

    def cerrar_sockets(self):
        try:
            if self.socket_conexion:
                self.socket_conexion.close()
        except:
            pass
        self.socket_conexion = None

    def configurar_host(self):
        self.modo_juego = 'host'
        self.mi_id_jugador = 1
        self.limpiar_ventana()

        frame_espera = tk.Frame(self.root, bg="#2d0a0a")
        frame_espera.pack(expand=True)

        try:
            hostname = socket.gethostname()
            ip_local = socket.gethostbyname(hostname)
        except:
            ip_local = "127.0.0.1"

        tk.Label(frame_espera, text="🌐 ESPERANDO CONEXIÓN...", font=("Times New Roman", 26, "bold"), bg="#2d0a0a", fg="#d4af37").pack(pady=20)
        tk.Label(frame_espera, text=f"Tu IP de red / Tailscale: {ip_local}", font=("Arial", 14, "bold"), bg="#2d0a0a", fg="#00ffcc").pack(pady=10)
        tk.Label(frame_espera, text="Dile a tu amigo que ingrese esta IP en 'Unirse a Partida'.", font=("Arial", 11, "italic"), bg="#2d0a0a", fg="white").pack(pady=10)

        tk.Button(frame_espera, text="❌ Cancelar", font=("Arial", 12, "bold"), bg="#78281f", fg="white", command=self.mostrar_pantalla_inicio).pack(pady=20)

        threading.Thread(target=self.iniciar_servidor_hilo, daemon=True).start()

    def iniciar_servidor_hilo(self):
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            servidor.bind(('0.0.0.0', 5555))
            servidor.listen(1)
            conn, addr = servidor.accept()
            self.socket_conexion = conn
            servidor.close()
            self.root.after(0, lambda: self.iniciar_juego('host_iniciado'))
        except Exception as e:
            print(f"Error en servidor: {e}")

    def configurar_cliente(self):
        ip_servidor = simpledialog.askstring("Conectar Online", "Ingresa la IP de Tailscale del Anfitrión:", initialvalue="100.")
        if not ip_servidor:
            return

        self.modo_juego = 'cliente'
        self.mi_id_jugador = 2
        
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((ip_servidor, 5555))
            self.socket_conexion = conn
            self.iniciar_juego('cliente_conectado')
        except Exception as e:
            tk.messagebox.showerror("Error de Conexión", f"No se pudo conectar al host: {e}")
            self.mostrar_pantalla_inicio()

    def iniciar_juego(self, modo):
        if modo in ['host', 'host_iniciado']:
            self.modo_juego = 'host'
            self.mi_id_jugador = 1
        elif modo == 'cliente_conectado':
            self.modo_juego = 'cliente'
            self.mi_id_jugador = 2
        else:
            self.modo_juego = modo
            self.mi_id_jugador = 1

        self.ia_ejecutando = False
        self.limpiar_ventana()
        self.crear_interfaz_juego()

        if self.modo_juego in ['host']:
            self.iniciar_nueva_partida()
            threading.Thread(target=self.escuchar_red, daemon=True).start()
        elif self.modo_juego == 'cliente':
            threading.Thread(target=self.escuchar_red, daemon=True).start()
        else:
            self.iniciar_nueva_partida()

    def escuchar_red(self):
        while self.socket_conexion:
            try:
                data = self.socket_conexion.recv(4096)
                if not data:
                    break
                paquete = json.loads(data.decode('utf-8'))
                self.root.after(0, lambda p=paquete: self.procesar_paquete_red(p))
            except Exception as e:
                print(f"Error recibiendo red: {e}")
                break

    def enviar_paquete_red(self, tipo, datos):
        if not self.socket_conexion:
            return
        paquete = {'tipo': tipo, 'datos': datos}
        try:
            self.socket_conexion.sendall(json.dumps(paquete).encode('utf-8'))
        except Exception as e:
            print(f"Error enviando red: {e}")

    def procesar_paquete_red(self, paquete):
        tipo = paquete['tipo']
        datos = paquete.get('datos', {})

        if tipo == 'REVANCHA_REQUEST':
            if self.modo_juego == 'host':
                self.solicitar_revancha()
            return

        if tipo == 'SYNC_ESTADO':
            # El cliente puede estar en la pantalla de resultados cuando el host
            # inicia la revancha. Reconstruir la interfaz antes de pintar el estado.
            if self.pantalla_resultado_activa:
                self.pantalla_resultado_activa = False
                self.limpiar_ventana()
                self.crear_interfaz_juego()

            self.ronda_actual = datos['ronda_actual']
            self.turno_jugador = datos['turno_jugador']
            self.poseedor_llaves = datos['poseedor_llaves']
            self.mesa = [ElementoMesa.from_dict(d) for d in datos['mesa']]
            
            if self.mi_id_jugador == 1:
                self.mano_j1 = [Carta.from_dict(c) for c in datos['mano_j1']]
                self.mano_j2 = [Carta.from_dict(c) for c in datos['mano_j2']]
                self.pozo_j1 = [Carta.from_dict(c) for c in datos['pozo_j1']]
                self.pozo_j2 = [Carta.from_dict(c) for c in datos['pozo_j2']]
            else:
                self.mano_j1 = [Carta.from_dict(c) for c in datos['mano_j2']]
                self.mano_j2 = [Carta.from_dict(c) for c in datos['mano_j1']]
                self.pozo_j1 = [Carta.from_dict(c) for c in datos['pozo_j2']]
                self.pozo_j2 = [Carta.from_dict(c) for c in datos['pozo_j1']]

            if datos['fin']:
                self.finalizar_juego()
            else:
                self.actualizar_vista()

    def sincronizar_estado_red(self, fin=False):
        if self.modo_juego != 'host':
            return
        
        datos = {
            'ronda_actual': self.ronda_actual,
            'turno_jugador': self.turno_jugador,
            'poseedor_llaves': self.poseedor_llaves,
            'mesa': [e.to_dict() for e in self.mesa],
            'mano_j1': [c.to_dict() for c in self.mano_j1],
            'mano_j2': [c.to_dict() for c in self.mano_j2],
            'pozo_j1': [c.to_dict() for c in self.pozo_j1],
            'pozo_j2': [c.to_dict() for c in self.pozo_j2],
            'fin': fin
        }
        self.enviar_paquete_red('SYNC_ESTADO', datos)

    def obtener_imagen_carta(self, carta, ancho=80, alto=112):
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
        lbl_titulo = tk.Label(self.root, text="♠ CASINO ROYALE - TRADICIÓN DIGITAL ♦", font=("Times New Roman", 22, "bold"), bg="#2d0a0a", fg="#d4af37")
        lbl_titulo.pack(pady=6)

        self.lbl_estado = tk.Label(self.root, text="", font=("Arial", 12, "bold"), bg="#2d0a0a", fg="#f39c12")
        self.lbl_estado.pack(pady=2)

        self.lbl_seleccion = tk.Label(self.root, text="Selecciona una carta de tu mano", font=("Arial", 11, "italic"), bg="#2d0a0a", fg="#ffd700")
        self.lbl_seleccion.pack(pady=2)

        frame_mesa_container = tk.LabelFrame(self.root, text=" Paño de la Mesa (Juega o Suma sobre las pilas) ", font=("Times New Roman", 13, "bold"), bg="#4a1212", fg="#d4af37", bd=2, relief="groove")
        frame_mesa_container.pack(fill="both", expand=True, padx=25, pady=6)

        self.frame_mesa = tk.Frame(frame_mesa_container, bg="#4a1212")
        self.frame_mesa.pack(fill="both", expand=True, padx=10, pady=10)

        frame_inferior = tk.Frame(self.root, bg="#2d0a0a")
        frame_inferior.pack(fill="x", padx=25, pady=8)

        frame_mano_container = tk.LabelFrame(frame_inferior, text=" Tu Mano ", font=("Times New Roman", 13, "bold"), bg="#4a1212", fg="#d4af37", bd=2, relief="groove")
        frame_mano_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.frame_mano = tk.Frame(frame_mano_container, bg="#4a1212")
        self.frame_mano.pack(fill="both", expand=True, padx=10, pady=10)

        self.frame_cajon = tk.LabelFrame(frame_inferior, text=" 📥 Cajón de Captura ", font=("Times New Roman", 13, "bold"), bg="#1e5128", fg="#d4af37", bd=3, relief="ridge")
        self.frame_cajon.pack(side="right", fill="both", padx=(10, 0), ipadx=10, ipady=5)

        self.btn_cajon_captura = tk.Button(
            self.frame_cajon, 
            text="📥 LLEVAR AL CAJÓN\n(Capturar a Pozo)", 
            font=("Arial", 11, "bold"), 
            bg="#27ae60", 
            fg="white", 
            activebackground="#2ecc71", 
            bd=3, 
            relief="raised", 
            state="disabled", 
            command=self.ejecutar_captura_multiple
        )
        self.btn_cajon_captura.pack(expand=True, fill="both", padx=10, pady=10)

        frame_acciones_pano = tk.Frame(self.root, bg="#2d0a0a")
        frame_acciones_pano.pack(fill="x", padx=25, pady=(0, 8))

        self.btn_accion_suma = tk.Button(frame_acciones_pano, text="➕ Sumar a Pila", font=("Arial", 10, "bold"), bg="#1b4f72", fg="white", activebackground="#2980b9", bd=2, state="disabled", command=self.ejecutar_suma_simple)
        self.btn_accion_suma.pack(side="left", padx=5)

        self.btn_accion_fila = tk.Button(frame_acciones_pano, text="🛡️ Crear/Agrandar Fila", font=("Arial", 10, "bold"), bg="#b9770e", fg="white", activebackground="#d68910", bd=2, state="disabled", command=self.ejecutar_crear_fila)
        self.btn_accion_fila.pack(side="left", padx=5)

        self.btn_accion_lanzar = tk.Button(frame_acciones_pano, text="🃏 Soltar en Paño", font=("Arial", 10, "bold"), bg="#6c3483", fg="white", activebackground="#8e44ad", bd=2, state="disabled", command=self.lanzar_carta_suelta)
        self.btn_accion_lanzar.pack(side="left", padx=5)

        btn_menu = tk.Button(frame_acciones_pano, text="🏠 Menú Principal", font=("Arial", 10, "bold"), bg="#78281f", fg="white", activebackground="#943126", bd=2, command=self.mostrar_pantalla_inicio)
        btn_menu.pack(side="right", padx=5)

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
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []
        self.ia_ejecutando = False
        
        if self.modo_juego == 'host':
            self.sincronizar_estado_red()

        self.actualizar_vista()

    def jugador_tiene_alternativas_para_fila(self, objetivo_fila):
        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2
        valores_mesa = [elem.valor_objetivo for elem in self.mesa]
        
        for c in mano_actual:
            val_c = 14 if c.nominal == 1 else (15 if c.es_mona else c.nominal)
            coincide_ind = any((c.nominal == elem.valor_objetivo) or (c.nominal == 1 and elem.valor_objetivo in [1, 14]) for elem in self.mesa)
            coincide_sum = self.existe_subconjunto_suma(valores_mesa, val_c)
            if coincide_ind or coincide_sum:
                return True
            if objetivo_fila < 15 and (objetivo_fila + val_c) <= 15:
                return True
            if self.existe_subconjunto_suma(valores_mesa, 15 - val_c) or self.existe_subconjunto_suma(valores_mesa, objetivo_fila - val_c):
                return True
            if not c.es_mona:
                for elem in self.mesa:
                    if not elem.bloqueada and elem.valor_objetivo + c.nominal <= 15:
                        return True
        return False

    def retirar_filas_obligatorias_sin_alternativa(self):
        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        pozo_activo = self.pozo_j1 if id_j == 1 else self.pozo_j2

        filas_retiradas = False
        indices_a_retirar = []

        for idx, elem in enumerate(self.mesa):
            if (elem.bloqueada or elem.valor_objetivo >= 15) and elem.creador_id == id_j:
                if not self.jugador_tiene_alternativas_para_fila(elem.valor_objetivo):
                    indices_a_retirar.append(idx)

        if indices_a_retirar:
            for idx in sorted(indices_a_retirar, reverse=True):
                elem = self.mesa.pop(idx)
                pozo_activo.extend(elem.cartas)
            self.poseedor_llaves = id_j
            filas_retiradas = True

        return filas_retiradas

    def actualizar_vista(self):
        self.fusionar_pilas_mesa()
        
        es_mi_turno = True
        id_j_actual = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        
        if self.modo_juego in ['host', 'cliente']:
            es_mi_turno = (self.turno_jugador == self.mi_id_jugador)
            mano_actual = self.mano_j1 if self.mi_id_jugador == 1 else self.mano_j2
            pozo_actual = self.pozo_j1 if self.mi_id_jugador == 1 else self.pozo_j2
        else:
            mano_actual = self.mano_j1 if self.turno_jugador == 1 else self.mano_j2
            pozo_actual = self.pozo_j1 if self.turno_jugador == 1 else self.pozo_j2
        
        if self.modo_juego == 'ia':
            nombre_turno = "Jugador 1" if self.turno_jugador == 1 else "IA Competitiva"
        elif self.modo_juego in ['host', 'cliente']:
            nombre_turno = "Tú" if es_mi_turno else "Tu Rival"
        else:
            nombre_turno = "Jugador 1" if self.turno_jugador == 1 else "Jugador 2"
        
        self.lbl_estado.config(
            text=f"Ronda: {self.ronda_actual}/6 | Turno: {nombre_turno} | Llaves: J{self.poseedor_llaves} | Tu Pozo: {len(pozo_actual)} cartas"
        )
        
        filas_propias = [elem for elem in self.mesa if (elem.bloqueada or elem.valor_objetivo >= 15) and elem.creador_id == id_j_actual]
        debe_retirar_fila = False
        for f in filas_propias:
            if not self.jugador_tiene_alternativas_para_fila(f.valor_objetivo):
                debe_retirar_fila = True
                break

        if debe_retirar_fila and es_mi_turno:
            self.lbl_seleccion.config(text="⚠️ ¡SIN ALTERNATIVAS! Al intentar jugar, retirarás automáticamente tu fila obligatoria al cajón.")
        elif not es_mi_turno and self.modo_juego in ['host', 'cliente']:
            self.lbl_seleccion.config(text="Esperando la jugada de tu rival...")
        elif self.carta_seleccionada_temporal:
            suma_sel = sum(self.mesa[i].valor_objetivo for i in self.indices_mesa_seleccionados)
            txt_sel = f"Seleccionada: {self.carta_seleccionada_temporal} | Pilas paño: {len(self.indices_mesa_seleccionados)} (Suma total: {suma_sel})"
            self.lbl_seleccion.config(text=txt_sel)
        else:
            self.lbl_seleccion.config(text=f"Turno de {nombre_turno}: Selecciona tu carta y toca la mesa o arrástrala al cajón")

        es_turno_ia = (self.modo_juego == 'ia' and self.turno_jugador == 2)
        bloquear_todo = not es_mi_turno if self.modo_juego in ['host', 'cliente'] else es_turno_ia

        hay_seleccion = (self.carta_seleccionada_temporal is not None) and not bloquear_todo
        tiene_pilas = len(self.indices_mesa_seleccionados) > 0

        permite_lanzar = hay_seleccion
        if hay_seleccion and permite_lanzar and not debe_retirar_fila:
            carta = self.carta_seleccionada_temporal
            coincide_valor_existente = any(
                (carta.nominal == elem.valor_objetivo) or 
                (carta.nominal == 1 and elem.valor_objetivo in [1, 14]) 
                for elem in self.mesa
            )
            if coincide_valor_existente:
                permite_lanzar = False

        pila_en_techo = any(self.mesa[idx].valor_objetivo >= 15 for idx in self.indices_mesa_seleccionados)
        puede_sumar_o_fila = hay_seleccion and tiene_pilas and not pila_en_techo and not debe_retirar_fila

        self.btn_cajon_captura.config(state="normal" if (hay_seleccion and tiene_pilas) else "disabled")
        self.btn_accion_suma.config(state="normal" if puede_sumar_o_fila else "disabled")
        self.btn_accion_fila.config(state="normal" if puede_sumar_o_fila else "disabled")
        self.btn_accion_lanzar.config(state="normal" if permite_lanzar else "disabled")

        for w in self.frame_mesa.winfo_children():
            w.destroy()
        for w in self.frame_mano.winfo_children():
            w.destroy()

        if not self.mesa:
            lbl_vacia = tk.Label(self.frame_mesa, text="El paño está libre.", font=("Arial", 11, "italic"), bg="#4a1212", fg="#f5b041")
            lbl_vacia.pack(pady=25)
        else:
            for i, elem in enumerate(self.mesa):
                es_sel = i in self.indices_mesa_seleccionados
                bg_color = "#8b0000" if es_sel else "#3d1010"

                frame_elem = tk.Frame(self.frame_mesa, bg=bg_color, bd=4 if es_sel else 2, relief="solid" if es_sel else "ridge", padx=6, pady=6)
                frame_elem.pack(side="left", padx=10, pady=8)

                cant_cartas = len(elem.cartas)
                ancho_img, alto_img = 85, 120
                offset_y = 20 * min(cant_cartas - 1, 5)
                canvas_alto = alto_img + offset_y

                canvas_pila = tk.Canvas(frame_elem, width=ancho_img, height=canvas_alto, bg=bg_color, highlightthickness=0)
                canvas_pila.pack()

                canvas_pila.imagenes_referencia = []
                for idx_carta, carta in enumerate(elem.cartas):
                    img_tk = self.obtener_imagen_carta(carta, ancho=ancho_img, alto=alto_img)
                    if img_tk:
                        canvas_pila.imagenes_referencia.append(img_tk)
                        pos_y = idx_carta * 20
                        canvas_pila.create_image(0, pos_y, anchor="nw", image=img_tk)

                canvas_pila.bind("<Button-1>", lambda event, idx=i: self.alternar_seleccion_mesa(idx))

        if es_turno_ia:
            lbl_ia_turno = tk.Label(self.frame_mano, text="🤖 La IA Competitiva está pensando su jugada...", font=("Arial", 12, "bold"), bg="#4a1212", fg="#ffd700")
            lbl_ia_turno.pack(pady=20)
            if not self.ia_ejecutando:
                self.ia_ejecutando = True
                self.root.after(800, self.ejecutar_turno_ia)
        else:
            for carta in mano_actual:
                es_mano_sel = (carta == self.carta_seleccionada_temporal)
                bg_mano = "#00ffcc" if es_mano_sel else "#3d1010"
                pad_top = 0 if es_mano_sel else 12

                frame_carta_wrapper = tk.Frame(self.frame_mano, bg="#4a1212")
                frame_carta_wrapper.pack(side="left", padx=8, pady=(pad_top, 6))

                img = self.obtener_imagen_carta(carta, ancho=95, alto=135)
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
                        font=("Arial", 10, "bold"), 
                        bg="#00ffcc" if es_mano_sel else "#ffffff", 
                        fg="#2d0a0a", 
                        width=12, 
                        height=5,
                        bd=5 if es_mano_sel else 1,
                        command=lambda c=carta: self.seleccionar_carta_mano(c)
                    )
                btn_carta.pack()

    def seleccionar_carta_mano(self, carta):
        if self.modo_juego in ['host', 'cliente'] and self.turno_jugador != self.mi_id_jugador:
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
        if self.modo_juego in ['host', 'cliente'] and self.turno_jugador != self.mi_id_jugador:
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

    def es_particion_valida_captura(self, valores, objetivo):
        if not valores:
            return True
        n = len(valores)
        for i in range(1, 1 << n):
            subconjunto = [valores[j] for j in range(n) if (i & (1 << j))]
            if sum(subconjunto) == objetivo:
                restantes = [valores[j] for j in range(n) if not (i & (1 << j))]
                if self.es_particion_valida_captura(restantes, objetivo):
                    return True
        return False

    def ejecutar_captura_multiple(self):
        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
            return

        carta = self.carta_seleccionada_temporal
        valores_seleccionados = [self.mesa[i].valor_objetivo for i in self.indices_mesa_seleccionados]
        
        suma_total = sum(valores_seleccionados)
        val_carta = 14 if (carta.nominal == 1 and suma_total % 14 == 0) else (15 if carta.es_mona else carta.nominal)

        if not self.es_particion_valida_captura(valores_seleccionados, val_carta):
            return

        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        pozo_activo = self.pozo_j1 if id_j == 1 else self.pozo_j2
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2

        for idx in sorted(self.indices_mesa_seleccionados, reverse=True):
            elem = self.mesa.pop(idx)
            pozo_activo.extend(elem.cartas)

        pozo_activo.append(carta)
        mano_actual.remove(carta)
        self.poseedor_llaves = id_j

        self.siguiente_turno()

    def ejecutar_suma_simple(self):
        if self.retirar_filas_obligatorias_sin_alternativa():
            self.actualizar_vista()
            return

        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
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

        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2
        mano_restante = list(mano_actual)
        mano_restante.remove(carta)

        tiene_respaldo_suma = any(c.nominal == nuevo_objetivo or (nuevo_objetivo == 14 and c.nominal == 1) or (nuevo_objetivo == 15 and c.es_mona) for c in mano_restante)
        if not tiene_respaldo_suma:
            return

        cartas_combinadas = [carta]
        for idx in sorted(self.indices_mesa_seleccionados, reverse=True):
            elem = self.mesa.pop(idx)
            cartas_combinadas.extend(elem.cartas)

        self.mesa.append(ElementoMesa(cartas_combinadas, nuevo_objetivo, bloqueada=False, creador_id=id_j))
        self.fusionar_pilas_mesa()
        mano_actual.remove(carta)

        self.siguiente_turno()

    def ejecutar_crear_fila(self):
        if self.retirar_filas_obligatorias_sin_alternativa():
            self.actualizar_vista()
            return

        if not self.carta_seleccionada_temporal or not self.indices_mesa_seleccionados:
            return

        carta = self.carta_seleccionada_temporal
        if carta.es_mona:
            return

        for idx in self.indices_mesa_seleccionados:
            if self.mesa[idx].valor_objetivo >= 15:
                return

        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
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

        mano_restante = list(mano_actual)
        mano_restante.remove(carta)
        tiene_respaldo = any(c.nominal == objetivo_fila or (objetivo_fila == 14 and c.nominal == 1) for c in mano_restante)
        if not tiene_respaldo:
            return

        cartas_combinadas = [carta]
        for idx in sorted(self.indices_mesa_seleccionados, reverse=True):
            elem = self.mesa.pop(idx)
            cartas_combinadas.extend(elem.cartas)

        self.mesa.append(ElementoMesa(cartas_combinadas, objetivo_fila, bloqueada=True, creador_id=id_j))
        self.fusionar_pilas_mesa()
        mano_actual.remove(carta)

        self.siguiente_turno()

    def lanzar_carta_suelta(self):
        if not self.carta_seleccionada_temporal:
            return

        if self.retirar_filas_obligatorias_sin_alternativa():
            self.actualizar_vista()
            return
        
        carta = self.carta_seleccionada_temporal
        id_j = self.mi_id_jugador if self.modo_juego in ['host', 'cliente'] else self.turno_jugador
        mano_actual = self.mano_j1 if id_j == 1 else self.mano_j2

        coincide_valor_existente = any(
            (carta.nominal == elem.valor_objetivo) or 
            (carta.nominal == 1 and elem.valor_objetivo in [1, 14]) 
            for elem in self.mesa
        )
        if coincide_valor_existente:
            return

        mano_actual.remove(carta)
        self.mesa.append(ElementoMesa([carta], carta.nominal))
        self.fusionar_pilas_mesa()
        self.siguiente_turno()

    def ejecutar_turno_ia(self):
        self.ia_ejecutando = False
        if self.ronda_actual > len(self.distribucion_rondas):
            return

        ia_mano = self.mano_j2
        if not ia_mano:
            self.siguiente_turno()
            return

        # IA retira sus filas si se quedó sin alternativas
        pozo_ia = self.pozo_j2
        indices_retirar = []
        for idx, elem in enumerate(self.mesa):
            if (elem.bloqueada or elem.valor_objetivo >= 15) and elem.creador_id == 2:
                if not self.jugador_tiene_alternativas_para_fila(elem.valor_objetivo):
                    indices_retirar.append(idx)

        if indices_retirar:
            for idx in sorted(indices_retirar, reverse=True):
                e = self.mesa.pop(idx)
                pozo_ia.extend(e.cartas)
            self.poseedor_llaves = 2

        # 1. Buscar captura
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
            for idx in sorted(indices_captura, reverse=True):
                elem = self.mesa.pop(idx)
                pozo_ia.extend(elem.cartas)
            pozo_ia.append(carta)
            ia_mano.remove(carta)
            self.poseedor_llaves = 2
            self.siguiente_turno()
            return

        # 2. Buscar formar filas
        for carta in ia_mano:
            if carta.es_mona or carta.nominal == 1:
                continue
            for idx, elem in enumerate(self.mesa):
                if not elem.bloqueada and elem.valor_objetivo < 15:
                    nuevo_objetivo = elem.valor_objetivo + carta.nominal
                    if nuevo_objetivo <= 15:
                        mano_restante = [c for c in ia_mano if c != carta]
                        tiene_respaldo = any(
                            c.nominal == nuevo_objetivo or 
                            (nuevo_objetivo == 14 and c.nominal == 1) or 
                            (nuevo_objetivo == 15 and c.es_mona) 
                            for c in mano_restante
                        )
                        if tiene_respaldo:
                            cartas_combinadas = [carta] + list(elem.cartas)
                            self.mesa.pop(idx)
                            bloquear_fila = (nuevo_objetivo >= 12)
                            self.mesa.append(ElementoMesa(cartas_combinadas, nuevo_objetivo, bloqueada=bloquear_fila, creador_id=2))
                            self.fusionar_pilas_mesa()
                            ia_mano.remove(carta)
                            self.siguiente_turno()
                            return

        # 3. Lanzar carta suelta válida
        cartas_validas = []
        for c in ia_mano:
            coincide = any(c.nominal == elem.valor_objetivo or (c.nominal == 1 and elem.valor_objetivo in [1, 14]) for elem in self.mesa)
            if not coincide:
                cartas_validas.append(c)

        if cartas_validas:
            cartas_seguras = [c for c in cartas_validas if c.puntos == 0 and not c.es_mona and c.nominal not in [1, 10, 2]]
            carta_a_lanzar = cartas_seguras[0] if cartas_seguras else cartas_validas[0]
        else:
            carta_a_lanzar = ia_mano[0]

        ia_mano.remove(carta_a_lanzar)
        self.mesa.append(ElementoMesa([carta_a_lanzar], carta_a_lanzar.nominal))
        self.fusionar_pilas_mesa()
        self.siguiente_turno()

    def encontrar_mejor_combinacion_captura(self, objetivo):
        n = len(self.mesa)
        for i in range(1, 1 << n):
            sub_indices = [j for j in range(n) if (i & (1 << j))]
            valores_sub = [self.mesa[idx].valor_objetivo for idx in sub_indices]
            if self.es_particion_valida_captura(valores_sub, objetivo):
                return sub_indices
        return None

    def existe_subconjunto_suma(self, valores, objetivo):
        n = len(valores)
        for i in range(1, 1 << n):
            suma = sum(valores[j] for j in range(n) if (i & (1 << j)))
            if suma == objetivo:
                return True
        return False

    def siguiente_turno(self):
        self.ia_ejecutando = False
        self.carta_seleccionada_temporal = None
        self.indices_mesa_seleccionados = []

        # Alternar el turno normalmente.
        self.turno_jugador = 2 if self.turno_jugador == 1 else 1

        # La ronda termina cuando ambos jugadores ya usaron todas sus cartas.
        # Comprobarlo después de cada jugada evita depender de que el turno
        # termine específicamente en un jugador concreto.
        if not self.mano_j1 and not self.mano_j2:
            self.ronda_actual += 1
            if self.ronda_actual <= len(self.distribucion_rondas):
                self.repartir_ronda()
                return
            else:
                if self.modo_juego == 'host':
                    self.sincronizar_estado_red(fin=True)
                self.finalizar_juego()
                return

        if self.modo_juego == 'host':
            self.sincronizar_estado_red()

        self.actualizar_vista()

    def finalizar_juego(self):
        self.pantalla_resultado_activa = True
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

        nombre_j2 = "Jugador 2" if self.modo_juego in ['1v1', 'host', 'cliente'] else "IA Competitiva"
        
        if total_j1 > total_j2:
            ganador_txt = "¡JUGADOR 1 GANA LA PARTIDA!"
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

        frame_j1 = tk.LabelFrame(frame_tarjetas, text=" 🔵 JUGADOR 1: Total [ " + str(total_j1) + " PTS ] ", font=("Times New Roman", 14, "bold"), bg="#4a1212", fg="#d4af37", bd=3, relief="groove")
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

        lbl_llaves = tk.Label(frame_resultado, text=f"🔑 Llaves finales ganadas por: {'Jugador 1' if self.poseedor_llaves == 1 else nombre_j2}", font=("Arial", 12, "italic"), bg="#2d0a0a", fg="#f5b041")
        lbl_llaves.pack(pady=10)

        tk.Button(
            frame_resultado,
            text="🔁 Revancha",
            font=("Arial", 14, "bold"),
            bg="#1e8449",
            fg="white",
            activebackground="#27ae60",
            bd=3,
            relief="raised",
            command=self.solicitar_revancha
        ).pack(pady=8, ipady=6, ipadx=15)

        tk.Button(frame_resultado, text="🏠 Menú Principal", font=("Arial", 14, "bold"), bg="#78281f", fg="white", activebackground="#943126", bd=3, relief="raised", command=self.mostrar_pantalla_inicio).pack(pady=8, ipady=6, ipadx=15)

    def solicitar_revancha(self):
        # En partidas locales/IA, iniciar inmediatamente. En online, el host
        # controla el mazo y el estado: el cliente solicita la revancha al host.
        if self.modo_juego == 'cliente':
            self.enviar_paquete_red('REVANCHA_REQUEST', {})
            return

        self.pantalla_resultado_activa = False
        self.limpiar_ventana()
        self.crear_interfaz_juego()
        self.iniciar_nueva_partida()

if __name__ == "__main__":
    root = tk.Tk()
    app = CasinoRoyaleApp(root)
    root.mainloop()