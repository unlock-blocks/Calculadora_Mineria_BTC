# -*- coding: utf-8 -*-
"""
Calculadora de Minería Solar para Bitcoin
==========================================

Aplicación GUI que permite calcular la rentabilidad de la minería de Bitcoin
utilizando energía solar y/o conexión a la red eléctrica convencional.

Características principales:
- Cálculo de hashprice en tiempo real
- Soporte para múltiples modelos de ASICs
- Análisis de rentabilidad con energía solar
- Comparativa con energía de red eléctrica
- Estimación de amortización y ROI
- Conversión automática EUR/USD

Autor: @unlock_blocks
Versión: 2.0
"""
import sys
import requests
import time
import math
import matplotlib.pyplot as plt
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QFormLayout, QMessageBox,
    QComboBox, QHBoxLayout, QFrame, QCheckBox, QScrollArea, QVBoxLayout, QSlider
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# ===== CONSTANTES GLOBALES =====
CASCADA_OFFSET_X = 30          # Offset horizontal para ventanas en cascada (píxeles)
CASCADA_OFFSET_Y = 30          # Offset vertical para ventanas en cascada (píxeles)
BLOQUES_POR_DIA = 144          # Número promedio de bloques minados por día en Bitcoin
FACTOR_RENDIMIENTO_SOLAR = 0.8 # Rendimiento solar típico (80%): incluye pérdidas inversor, temperatura, suciedad, sombreado y cableado

# ===== BASE DE DATOS DE MINEROS ASIC =====
# Diccionario con especificaciones técnicas de diferentes modelos de mineros Bitcoin
# Estructura: "Modelo": {"ths": hashrate_TH/s, "consumo": potencia_watts, "precio": precio_EUR}
MINEROS = {
    # === Antminer Series (Bitmain) ===
    "S19":      {"ths": 95,  "consumo": 3250, "precio": 550},     # Modelo básico S19
    "S19K Pro": {"ths": 120, "consumo": 2760, "precio": 770},     # S19 optimizado eficiencia
    "S21":      {"ths": 200, "consumo": 3500, "precio": 2211},    # Nueva generación 2024
    "S21 XP": {"ths": 270, "consumo": 3645, "precio": 4850.62},   # Versión extendida S21
    "S23 Hyd":  {"ths": 580, "consumo": 5510, "precio": 11311},   # Refrigeración líquida
    
    # === Otras Marcas Profesionales ===
    "Fluminer T3": {"ths": 115, "consumo": 1700, "precio": 1900}, # Alternativa eficiente
    "Avalon Q": {"ths": 90, "consumo": 1674, "precio": 1500},     # CanAan Avalon
    "Avalon Nano 3S": {"ths": 6, "consumo": 140, "precio": 290},  # Minero compacto
    
    # === Mineros Educativos/Hobby ===
    "NerdMiner NerdQaxe++": {"ths": 4.8, "consumo": 72, "precio": 350},      # Proyecto educativo
    "NerdMiner NerdQaxe+ Hyd": {"ths": 2.5, "consumo": 60, "precio": 429},   # Versión líquida
    "Bitaxe Touch": {"ths": 1.6, "consumo": 22, "precio": 275},              # Ultra-eficiente
    "Bitaxe Gamma 601": {"ths": 1.2, "consumo": 17, "precio": 58},           # Básico económico
    "Bitaxe Gamma Turbo": {"ths": 2.5, "consumo": 36, "precio": 347},        # Versión acelerada
    "Bitaxe Supra Hex 701": {"ths": 4.2, "consumo": 90, "precio": 235},      # Hexacore
}

# ===== FUNCIONES DE CONEXIÓN A APIs =====

def _hacer_request_api(url, timeout=5):
    """
    Wrapper común para peticiones HTTP a APIs externas con manejo robusto de errores.
    
    Args:
        url (str): URL de la API a consultar
        timeout (int): Tiempo límite en segundos para la petición
    
    Returns:
        dict|None: Datos JSON de la respuesta o None si hay error
    
    Note:
        Centraliza el manejo de errores de red, timeout y parsing JSON
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()  # Lanza excepción si status HTTP != 200
        return resp.json()
    except (requests.RequestException, ValueError, KeyError):
        return None

def obtener_cambio_usd_eur():
    """
    Obtiene el tipo de cambio EUR/USD actual desde frankfurter.app
    
    Returns:
        float|None: Tipo de cambio EUR/USD (cuántos dólares vale 1 euro) o None si falla
    
    Example:
        >>> cambio = obtener_cambio_usd_eur()
        >>> print(f"1 EUR = {cambio} USD")
    """
    data = _hacer_request_api("https://api.frankfurter.app/latest?from=EUR&to=USD")
    return round(data["rates"]["USD"], 4) if data else None

def obtener_precio_btc(moneda="usd"):
    """
    Obtiene el precio actual de Bitcoin desde CoinGecko API
    
    Args:
        moneda (str): Moneda objetivo ("usd" o "eur")
    
    Returns:
        float|None: Precio de Bitcoin en la moneda especificada o None si falla
    
    Note:
        Utiliza CoinGecko como fuente por su fiabilidad y gratuidad
    """
    if moneda.lower() not in ["usd", "eur"]:
        moneda = "usd"  # Fallback a USD por defecto
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies={moneda.lower()}"
    data = _hacer_request_api(url)
    return float(data["bitcoin"][moneda.lower()]) if data else None

def obtener_hashrate_eh():
    """
    Obtiene el hashrate actual de la red Bitcoin desde mempool.space
    
    Returns:
        float|None: Hashrate de la red en ExaHash/s o None si falla
    
    Note:
        Usa promedio de 3 días para evitar fluctuaciones extremas
    """
    data = _hacer_request_api("https://mempool.space/api/v1/mining/hashrate/3d")
    if data:
        hs = data["currentHashrate"]  # Hashrate en H/s
        ehs = hs / 1e18              # Convertir a EH/s
        return round(ehs, 2)
    return None

def estimar_fees_mempool(block_height, subsidio_btc=3.125):
    """
    Estima las fees de un bloque específico consultando mempool.space
    
    Args:
        block_height (int): Altura del bloque a analizar
        subsidio_btc (float): Subsidio base por bloque (3.125 BTC post-halving 2024)
    
    Returns:
        float|None: Fees del bloque en BTC o None si falla
    
    Note:
        Método detallado que requiere múltiples peticiones HTTP.
        Se usa como fallback del método optimizado.
    """
    try:
        # 1. Obtener hash del bloque desde su altura
        hash_url = f"https://mempool.space/api/block-height/{block_height}"
        block_hash = requests.get(hash_url, timeout=10).text.strip()
        
        # 2. Obtener lista de transacciones del bloque
        txids_url = f"https://mempool.space/api/block/{block_hash}/txids"
        txids = requests.get(txids_url, timeout=10).json()
        
        # 3. Analizar transacción coinbase (primera del bloque)
        coinbase_txid = txids[0]  # La coinbase siempre es la primera transacción
        coinbase_url = f"https://mempool.space/api/tx/{coinbase_txid}"
        coinbase = requests.get(coinbase_url, timeout=10).json()
        
        # 4. Calcular fees = recompensa_total - subsidio_base
        recompensa_total = sum([vout["value"] for vout in coinbase["vout"]]) / 1e8  # Convertir satoshis a BTC
        fees = recompensa_total - subsidio_btc
        return fees
    except Exception:
        return None

def obtener_fees_btc_bloque_mempool(block_count=10, subsidio_btc=3.125):
    """
    Obtiene fees promedio de Bitcoin usando endpoint optimizado de mempool.space
    
    Implementación ultra-eficiente que utiliza estadísticas pre-calculadas
    de las últimas 24 horas en lugar de consultar bloques individualmente.
    
    Args:
        block_count (int): Número de bloques para análisis (usado solo en fallback)
        subsidio_btc (float): Subsidio base por bloque Bitcoin
    
    Returns:
        tuple: (fees_promedio_BTC, numero_bloques_analizados)
    
    Note:
        - Método principal: API de estadísticas (1 sola petición)
        - Fallback: Método tradicional bloque por bloque
        - Datos en satoshis se convierten automáticamente a BTC
    """
    try:
        # === MÉTODO PRINCIPAL: Endpoint de estadísticas ===
        url = "https://mempool.space/api/v1/mining/blocks/fees/24h"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code != 200:
            # Fallback inmediato si el endpoint no responde
            fees = obtener_fees_btc_bloque_tradicional(block_count, subsidio_btc)
            return (fees, BLOQUES_POR_DIA) if fees else (None, BLOQUES_POR_DIA)
            
        data = resp.json()
        
        if data and len(data) > 0:
            # Filtrar bloques con fees válidas (> 0 satoshis)
            bloques_con_fees = [block for block in data if block.get('avgFees', 0) > 0]
            
            if bloques_con_fees:
                # Calcular promedio de fees
                total_fees_sats = sum([block.get('avgFees', 0) for block in bloques_con_fees])
                numero_bloques_reales = len(bloques_con_fees)
                avg_fees_sats = total_fees_sats / numero_bloques_reales
                avg_fees_btc = avg_fees_sats / 1e8  # Convertir satoshis a BTC
                
                return (round(avg_fees_btc, 6), numero_bloques_reales)
            
        # === FALLBACK: Método tradicional ===
        fees = obtener_fees_btc_bloque_tradicional(block_count, subsidio_btc)
        return (fees, BLOQUES_POR_DIA) if fees else (None, BLOQUES_POR_DIA)
        
    except Exception:
        # Fallback final en caso de error inesperado
        fees = obtener_fees_btc_bloque_tradicional(block_count, subsidio_btc)
        return (fees, BLOQUES_POR_DIA) if fees else (None, BLOQUES_POR_DIA)

def obtener_fees_btc_bloque_tradicional(block_count=10, subsidio_btc=3.125):
    """
    Método tradicional de cálculo de fees (FALLBACK)
    
    Analiza bloques individualmente cuando el método optimizado falla.
    Más lento pero más confiable en casos de problemas con APIs.
    
    Args:
        block_count (int): Número de bloques recientes a analizar
        subsidio_btc (float): Subsidio base por bloque
    
    Returns:
        float|None: Promedio de fees en BTC o None si falla completamente
    
    Note:
        Incluye delay de 0.2s entre peticiones para evitar rate limiting
    """
    try:
        # Obtener lista de bloques recientes
        bloques = requests.get("https://mempool.space/api/blocks", timeout=10).json()
        if not bloques:
            return None
            
        total_fees = 0
        bloques_ok = 0
        
        # Analizar cada bloque individualmente
        for bloque in bloques[:block_count]:
            height = bloque["height"]
            fees = estimar_fees_mempool(height, subsidio_btc)
            if fees is not None:
                total_fees += fees
                bloques_ok += 1
            time.sleep(0.2)  # Delay para evitar sobrecargar la API
            
        if bloques_ok == 0:
            return None
            
        media_fee_btc = total_fees / bloques_ok
        return round(media_fee_btc, 6)
    except Exception:
        return None

# ===== CLASES DE INTERFAZ GRÁFICA =====

class VentanaResultados(QWidget):
    """
    Ventana secundaria para mostrar resultados detallados de cálculos
    
    Características:
    - Posicionamiento automático en cascada respecto a ventana principal
    - Contenido HTML con scroll para resultados extensos
    - Fuentes optimizadas para mostrar emojis y símbolos
    - Texto seleccionable para copiar resultados
    
    Args:
        resultado_html (str): Contenido HTML a mostrar
        nombre_minero (str): Nombre del minero para el título de ventana
        ventana_principal (QWidget): Referencia a ventana principal para posicionamiento
        offset_cascada (int): Multiplicador de offset para efecto cascada
    """
    
    def __init__(self, resultado_html, nombre_minero, ventana_principal=None, offset_cascada=0):
        super().__init__()
        self.setWindowTitle(f"📋 Análisis - {nombre_minero}")
        
        # === POSICIONAMIENTO INTELIGENTE ===
        # Calcular posición relativa a la ventana principal con efecto cascada
        if ventana_principal:
            # Obtener dimensiones y posición de la ventana principal
            geo_principal = ventana_principal.geometry()
            x_principal = geo_principal.x()
            y_principal = geo_principal.y()
            ancho_principal = geo_principal.width()
            
            # Posicionar a la derecha de la ventana principal con margen
            # El offset de cascada permite múltiples ventanas sin superposición
            x_nueva = x_principal + ancho_principal + 20 + (offset_cascada * CASCADA_OFFSET_X)
            y_nueva = y_principal + (offset_cascada * CASCADA_OFFSET_Y)
            
            self.setGeometry(x_nueva, y_nueva, 800, 600)
        else:
            # Fallback: posición por defecto con cascada
            x_nueva = 100 + (offset_cascada * CASCADA_OFFSET_X)
            y_nueva = 100 + (offset_cascada * CASCADA_OFFSET_Y)
            self.setGeometry(x_nueva, y_nueva, 800, 600)
            
        self.init_ui(resultado_html)
        
    def init_ui(self, resultado_html):
        """
        Inicializa la interfaz de usuario de la ventana de resultados
        
        Args:
            resultado_html (str): Contenido HTML formateado para mostrar
        """
        layout = QVBoxLayout()
        
        # === CONFIGURACIÓN DEL CONTENIDO ===
        self.resultado = QLabel(resultado_html)
        self.resultado.setTextInteractionFlags(Qt.TextSelectableByMouse)  # Permitir selección de texto
        self.resultado.setWordWrap(True)  # Ajuste automático de líneas
        
        # === CONFIGURACIÓN DE FUENTES ===
        # Intentar configurar fuente compatible con emojis
        try:
            emoji_font = QFont()
            emoji_font.setPointSize(13)
            emoji_font.setStyleHint(QFont.System)  # Usar fuente del sistema para mejor compatibilidad
            self.resultado.setFont(emoji_font)
            
            # CSS básico para tamaño de fuente
            self.resultado.setStyleSheet("font-size: 13px;")
        except:
            # Fallback silencioso a configuración por defecto
            pass
        
        # === ÁREA DE SCROLL PERSONALIZADA ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # Permitir redimensionamiento automático
        scroll_area.setWidget(self.resultado)
        
        # Estilos CSS personalizados para el área de scroll
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #f8f8f8;  /* Fondo gris claro */
                border: 1px solid #ccc;     /* Borde gris */
            }
            QScrollArea > QWidget > QWidget {
                background-color: #f8f8f8;  /* Fondo del contenido */
            }
            /* Estilo de la barra de scroll vertical */
            QScrollBar:vertical {
                background-color: #d0d0d0;  /* Fondo de la barra */
                width: 14px;                /* Ancho de la barra */
                border: none;
                margin: 0;
            }
            /* Manejador (thumb) de la barra de scroll */
            QScrollBar::handle:vertical {
                background-color: #909090;  /* Color del manejador */
                border-radius: 7px;         /* Bordes redondeados */
                min-height: 30px;           /* Altura mínima */
                margin: 2px;                /* Margen interno */
            }
            /* Efectos hover y pressed del manejador */
            QScrollBar::handle:vertical:hover {
                background-color: #707070;  /* Más oscuro al pasar el mouse */
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #505050;  /* Aún más oscuro al hacer clic */
            }
            /* Ocultar flechas de scroll */
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        layout.addWidget(scroll_area)
        self.setLayout(layout)

class CalculadoraMineria(QWidget):
    """
    Clase principal de la aplicación - Calculadora de Minería Solar
    
    Funcionalidades principales:
    - Gestión de datos de red Bitcoin (precio, hashrate, fees)
    - Configuración de equipos ASIC de minería  
    - Cálculo de rentabilidad con energía solar y/o red eléctrica
    - Conversión automática entre EUR y USD
    - Generación de informes detallados y gráficas de amortización
    - Gestión de múltiples ventanas de resultados
    
    Arquitectura:
    - Interfaz gráfica basada en PySide6/Qt
    - Conexión a APIs externas para datos en tiempo real
    - Cálculos financieros y de ingeniería solar
    - Sistema de ventanas en cascada para múltiples análisis
    """

    def mostrar_grafica_amortizacion(self, beneficio_anual, inversion, nombre_minero, ventana_resultados=None, offset_cascada=0):
        """
        Genera y muestra gráfica de amortización usando matplotlib
        
        Args:
            beneficio_anual (float): Beneficio neto anual esperado
            inversion (float): Inversión inicial total
            nombre_minero (str): Nombre del minero para el título
            ventana_resultados (QWidget): Ventana de referencia para posicionamiento
            offset_cascada (int): Offset para múltiples gráficas
        
        Note:
            - Gráfica interactiva con proyección de 10 años
            - Posicionamiento automático relativo a ventana de resultados
            - Marca visual del punto de amortización si es alcanzable
        """
        # === PREPARACIÓN DE DATOS ===
        anios = np.arange(0, 11)  # Proyección de 0 a 10 años
        beneficio_acumulado = beneficio_anual * anios

        # === CONFIGURACIÓN DE LA FIGURA ===
        fig = plt.figure(figsize=(8, 5))
        fig.canvas.manager.set_window_title(f"📈 Amortización - {nombre_minero}")
        
        # === PLOTEO DE DATOS ===
        plt.plot(anios, beneficio_acumulado, label="Beneficio acumulado", marker='o', linewidth=2)
        plt.axhline(inversion, color='red', linestyle='--', label="Inversión inicial", linewidth=2)
        
        # === CONFIGURACIÓN DE EJES Y ETIQUETAS ===
        plt.xlabel("Años")
        plt.ylabel("€")
        plt.title("Análisis de Punto de Amortización")
        plt.legend()
        plt.grid(True, alpha=0.3)

        # === MARCA DEL PUNTO DE AMORTIZACIÓN ===
        if beneficio_anual > 0:
            x_amort = inversion / beneficio_anual  # Tiempo de amortización en años
            if x_amort <= anios[-1]:  # Solo si es alcanzable en el período mostrado
                plt.axvline(x_amort, color='green', linestyle=':', 
                           label=f"Amortización: {x_amort:.2f} años", linewidth=2)
                plt.legend()

        plt.tight_layout()
        plt.show()
        
        # === GESTIÓN DE REFERENCIAS ===
        # Guardar referencia para poder cerrar la figura después
        self.figuras_matplotlib.append(fig)
        
        # === POSICIONAMIENTO INTELIGENTE ===
        # Posicionar la gráfica debajo de la ventana de resultados
        if ventana_resultados:
            try:
                geo_resultados = ventana_resultados.geometry()
                x_resultados = geo_resultados.x()
                y_resultados = geo_resultados.y()
                alto_resultados = geo_resultados.height()
                
                # Calcular posición: debajo con el mismo margen estándar (20px)
                x_grafica = x_resultados
                y_grafica = y_resultados + alto_resultados + 20
                
                # === MOVER VENTANA MATPLOTLIB ===
                # Intentar diferentes métodos según el backend de matplotlib
                mngr = fig.canvas.manager
                if hasattr(mngr, 'window'):
                    if hasattr(mngr.window, 'wm_geometry'):
                        # Backend TkAgg: usar comando de geometría Tk
                        mngr.window.wm_geometry(f"+{x_grafica}+{y_grafica}")
                    elif hasattr(mngr.window, 'move'):
                        # Backends Qt: mover ventana directamente
                        mngr.window.move(x_grafica, y_grafica)
                    elif hasattr(mngr.window, 'setGeometry'):
                        # Backends Qt alternativos: establecer geometría completa
                        mngr.window.setGeometry(x_grafica, y_grafica, 640, 480)
            except Exception:
                # Fallback silencioso: si falla el posicionamiento, la gráfica se muestra en posición por defecto
                pass

    def init_ui(self):
        """
        Inicializa la interfaz de usuario completa de la aplicación
        
        Organización por secciones:
        1. Datos de la red Bitcoin (precio, hashrate, fees)
        2. Configuración del minero ASIC
        3. Instalación solar (opcional)
        4. Conexión a red eléctrica (opcional)
        5. Botones de acción
        
        Características:
        - Layout responsivo con QFormLayout
        - Conversión dinámica EUR/USD
        - Validación en tiempo real
        - Tooltips informativos
        """
        layout = QFormLayout()
        layout.setSpacing(10)  # Espaciado uniforme entre elementos

        # ===== SECCIÓN 1: DATOS DE LA RED BITCOIN =====
        titulo_red = QLabel("<b>📊 Red Bitcoin</b>")
        titulo_red.setAlignment(Qt.AlignCenter)
        titulo_red.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # Botón para actualizar todos los datos desde APIs
        self.boton_actualizar_todo = QPushButton("🔄 Actualizar datos")
        self.boton_actualizar_todo.clicked.connect(lambda: self.actualizar_todos_los_campos(incluir_fees=True))
        
        # Layout horizontal para título y botón de actualización
        hbox_red_titulo = QHBoxLayout()
        hbox_red_titulo.addStretch(1)
        hbox_red_titulo.addWidget(titulo_red)
        hbox_red_titulo.addWidget(self.boton_actualizar_todo)
        hbox_red_titulo.addStretch(1)
        contenedor_red_titulo = QWidget()
        contenedor_red_titulo.setLayout(hbox_red_titulo)
        layout.addRow(contenedor_red_titulo)

        # === SELECTOR DE MONEDA (EUR/USD) ===
        # Etiquetas con estilos visuales para indicar moneda activa
        self.label_eur = QLabel("💶 EUR")
        self.label_eur.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label_eur.setStyleSheet("font-weight: bold; color: #0066cc;")  # Azul = activo
        
        self.label_usd = QLabel("💵 USD")
        self.label_usd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label_usd.setStyleSheet("font-weight: bold; color: #888888;")  # Gris = inactivo
        
        # Slider para cambiar entre EUR (0) y USD (1)
        self.slider_moneda = QSlider(Qt.Horizontal)
        self.slider_moneda.setMinimum(0)        # 0 = EUR
        self.slider_moneda.setMaximum(1)        # 1 = USD
        self.slider_moneda.setValue(0)          # Por defecto EUR
        self.slider_moneda.setFixedWidth(80)
        self.slider_moneda.valueChanged.connect(self.cambiar_moneda_display)
        
        # Layout horizontal centrado para el selector de moneda
        hbox_divisa = QHBoxLayout()
        hbox_divisa.addStretch(1)
        hbox_divisa.addSpacing(5)
        hbox_divisa.addWidget(self.label_eur)
        hbox_divisa.addWidget(self.slider_moneda)
        hbox_divisa.addWidget(self.label_usd)
        hbox_divisa.addStretch(1)
        contenedor_divisa = QWidget()
        contenedor_divisa.setLayout(hbox_divisa)
        layout.addRow(contenedor_divisa)

        # === CAMPOS DE DATOS ECONÓMICOS ===
        # Tipo de cambio EUR/USD
        self.label_cambio = QLabel("€ Cambio EUR/USD:")
        self.label_cambio.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cambio_usd_eur = QLineEdit()
        layout.addRow(self.label_cambio, self.cambio_usd_eur)

        # Precio de Bitcoin (se actualiza automáticamente según moneda seleccionada)
        self.label_btc = QLabel("₿ Precio BTC (EUR):")
        self.label_btc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.precio_btc = QLineEdit()
        layout.addRow(self.label_btc, self.precio_btc)
        # Conectar cambios para recalcular hashprice automáticamente
        self.precio_btc.textChanged.connect(self.actualizar_hashprice_spot)

        # Hashrate de la red Bitcoin (ExaHash por segundo)
        label_hashrate = QLabel("🌐 Hashrate red (EH/s):")
        label_hashrate.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hashrate_eh = QLineEdit()
        self.hashrate_eh.textChanged.connect(self.actualizar_hashprice_spot)
        layout.addRow(label_hashrate, self.hashrate_eh)

        # Fees promedio de transacciones Bitcoin
        label_fees = QLabel("🪙 Fees últimas 24h (BTC):")
        label_fees.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fees_btc_bloque = QLineEdit()
        layout.addRow(label_fees, self.fees_btc_bloque)
        self.fees_btc_bloque.textChanged.connect(self.actualizar_hashprice_spot)

        # Hashprice calculado (ganancia por TH/s por día)
        self.label_hashprice = QLabel("💹 Hashprice (spot) (EUR/PH/día):")
        self.label_hashprice.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hashprice_spot = QLineEdit()
        layout.addRow(self.label_hashprice, self.hashprice_spot)

        # Recompensa base por bloque (post-halving 2024: 3.125 BTC)
        label_recompensa = QLabel("🎁 Recompensa por bloque (BTC):")
        label_recompensa.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.recompensa_btc = QLineEdit("3.125")
        layout.addRow(label_recompensa, self.recompensa_btc)
        # Auto-recalcular hashprice cuando cambie la recompensa
        self.recompensa_btc.textChanged.connect(self.actualizar_hashprice_spot)

        # Comisión del pool de minería (típicamente 1-3%)
        label_comision = QLabel("🏦 Pool fees (2%):")
        label_comision.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.comision = QLineEdit("0.02")
        layout.addRow(label_comision, self.comision)

        # === SEPARADOR VISUAL ===
        separador1 = QFrame()
        separador1.setFrameShape(QFrame.HLine)      # Línea horizontal
        separador1.setFrameShadow(QFrame.Sunken)    # Efecto hundido
        layout.addRow(separador1)

        # ===== SECCIÓN 2: CONFIGURACIÓN DEL MINERO ASIC =====
        titulo_minero = QLabel("<b>🔨 ASIC</b>")
        titulo_minero.setAlignment(Qt.AlignCenter)
        titulo_minero.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # === SELECTOR DE MODELO DE MINERO ===
        self.combo_minero = QComboBox()
        self.combo_minero.addItem("Selecciona un modelo")  # Opción por defecto
        # Agregar todos los modelos de la base de datos
        for modelo in MINEROS:
            self.combo_minero.addItem(modelo)
        self.combo_minero.addItem("Otro")  # Opción para configuración manual
        # Conectar cambio de selección para autocompletar especificaciones
        self.combo_minero.currentIndexChanged.connect(self.autocompletar_minero)

        # Layout horizontal para título y selector
        hbox_minero_titulo = QHBoxLayout()
        hbox_minero_titulo.addStretch(1)
        hbox_minero_titulo.addWidget(titulo_minero)
        hbox_minero_titulo.addWidget(self.combo_minero)
        hbox_minero_titulo.addStretch(1)
        contenedor_minero_titulo = QWidget()
        contenedor_minero_titulo.setLayout(hbox_minero_titulo)
        layout.addRow(contenedor_minero_titulo)

        # === CANTIDAD DE EQUIPOS ===
        label_num_minero = QLabel("📟 Número de máquinas:")
        label_num_minero.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.num_minero = QComboBox()
        
        # Rangos de cantidad adaptados a diferentes escalas de operación:
        # Pequeña escala: 1-10 unidades (hobby/hogar)
        for i in range(1, 11):
            self.num_minero.addItem(str(i))
        # Mediana escala: 20-100 unidades (operación semi-profesional)
        for i in range(20, 101, 10):
            self.num_minero.addItem(str(i))
        # Gran escala: 200-1000 unidades (operación industrial)
        for i in range(200, 1001, 100):
            self.num_minero.addItem(str(i))
        
        self.num_minero.setCurrentIndex(0)  # Por defecto: 1 máquina
        layout.addRow(label_num_minero, self.num_minero)

        # === ESPECIFICACIONES TÉCNICAS ===
        # Hashrate del equipo (potencia de cálculo)
        label_ths = QLabel("🚀 Hashrate equipo (TH/s):")
        label_ths.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ths = QLineEdit("100")  # Valor por defecto
        layout.addRow(label_ths, self.ths)

        # Consumo eléctrico del equipo
        label_consumo = QLabel("🔋 Potencia eléctrica (W):")
        label_consumo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.consumo_kw = QLineEdit("3500")  # Valor típico para ASIC moderno
        layout.addRow(label_consumo, self.consumo_kw)

        # Precio del equipo (con conversión automática EUR/USD)
        self.label_precio_equipo = QLabel("💶 Precio equipo (€):")
        self.label_precio_equipo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.precio_equipo = QLineEdit("500")
        # Conectar cambios para mantener valor base en EUR
        self.precio_equipo.textChanged.connect(self._guardar_precio_equipo_base)
        layout.addRow(self.label_precio_equipo, self.precio_equipo)
        
        # Almacenar valor base en EUR para conversiones automáticas
        self._precio_equipo_base_eur = 500.0

        # === SEPARADOR VISUAL ===
        separador2 = QFrame()
        separador2.setFrameShape(QFrame.HLine)
        separador2.setFrameShadow(QFrame.Sunken)
        layout.addRow(separador2)

        # ===== SECCIÓN 3: INSTALACIÓN SOLAR (OPCIONAL) =====
        # Checkbox para habilitar/deshabilitar configuración solar
        self.chk_solar = QCheckBox()
        self.chk_solar.setChecked(True)  # Habilitado por defecto
        self.chk_solar.stateChanged.connect(self.toggle_solar_fields)
        
        titulo_solar = QLabel("<b>🌞 Instalación solar</b>")
        titulo_solar.setAlignment(Qt.AlignCenter)
        titulo_solar.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # Layout horizontal para título y checkbox
        hbox_solar = QHBoxLayout()
        hbox_solar.addStretch(1)
        hbox_solar.addWidget(titulo_solar)
        hbox_solar.addWidget(self.chk_solar)
        hbox_solar.addStretch(1)
        contenedor_solar = QWidget()
        contenedor_solar.setLayout(hbox_solar)
        layout.addRow(contenedor_solar)

        # === PARÁMETROS ECONÓMICOS SOLARES ===
        # Coste de oportunidad: precio que se perdería por no vender energía a la red
        self.label_precio_venta = QLabel("💸 Excedente no vendido (€/kWh):")
        self.label_precio_venta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.precio_venta_solar = QLineEdit("0.04")  # Precio típico de venta de excedentes en España
        self.precio_venta_solar.textChanged.connect(self._guardar_precio_venta_base)
        layout.addRow(self.label_precio_venta, self.precio_venta_solar)
        
        # Valor base en EUR para conversiones automáticas
        self._precio_venta_base_eur = 0.04

        # === PARÁMETROS TÉCNICOS SOLARES ===
        # Horas de sol equivalentes por día (PSH - Peak Sun Hours)
        label_horas_solares = QLabel("🌤️ Horas solares/día:")
        label_horas_solares.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.horas_solares_dia = QLineEdit("5.5")  # Promedio para España: 5.5 PSH
        layout.addRow(label_horas_solares, self.horas_solares_dia)

        # Días de operación solar por año
        label_dias_uso = QLabel("📅 Días de uso/año:")
        label_dias_uso.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dias_uso = QLineEdit("365")  # Por defecto: todo el año
        layout.addRow(label_dias_uso, self.dias_uso)

        # === AGRUPACIÓN DE WIDGETS PARA CONTROL DE ESTADO ===
        # Lista de widgets que se habilitan/deshabilitan con el checkbox solar
        self.solar_widgets = [self.precio_venta_solar, self.horas_solares_dia, self.dias_uso]

        # === SEPARADOR VISUAL ===
        separador_red = QFrame()
        separador_red.setFrameShape(QFrame.HLine)
        separador_red.setFrameShadow(QFrame.Sunken)
        layout.addRow(separador_red)

        # ===== SECCIÓN 4: CONEXIÓN A RED ELÉCTRICA (OPCIONAL) =====
        # Checkbox para habilitar/deshabilitar configuración de red eléctrica
        self.chk_red = QCheckBox()
        self.chk_red.setChecked(True)  # Habilitado por defecto
        self.chk_red.stateChanged.connect(self.toggle_red_fields)
        
        titulo_red_elec = QLabel("<b>🏭 Conexión a red eléctrica</b>")
        titulo_red_elec.setAlignment(Qt.AlignCenter)
        titulo_red_elec.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # Layout horizontal para título y checkbox
        hbox_red = QHBoxLayout()
        hbox_red.addStretch(1)
        hbox_red.addWidget(titulo_red_elec)
        hbox_red.addWidget(self.chk_red)
        hbox_red.addStretch(1)
        contenedor_red = QWidget()
        contenedor_red.setLayout(hbox_red)
        layout.addRow(contenedor_red)

        # === PARÁMETROS ECONÓMICOS DE RED ELÉCTRICA ===
        # Precio de la electricidad de la red (tarifa contratada)
        self.label_precio_red = QLabel("💡 Precio electricidad (€/kWh):")
        self.label_precio_red.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.precio_red = QLineEdit("0.08")  # Precio típico industrial en España
        self.precio_red.textChanged.connect(self._guardar_precio_red_base)
        layout.addRow(self.label_precio_red, self.precio_red)
        
        # Valor base en EUR para conversiones automáticas
        self._precio_red_base_eur = 0.08

        # === PARÁMETROS OPERACIONALES DE RED ===
        # Horas de uso diario con red eléctrica
        label_horas_red = QLabel("🔌 Horas de uso/día:")
        label_horas_red.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.horas_red_dia = QLineEdit("8")  # Por defecto: horario nocturno complementario
        layout.addRow(label_horas_red, self.horas_red_dia)

        # Días de uso anual con red eléctrica
        label_dias_red = QLabel("📅 Días de uso/año:")
        label_dias_red.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dias_red = QLineEdit("365")  # Por defecto: todo el año
        layout.addRow(label_dias_red, self.dias_red)


        # === AGRUPACIÓN DE WIDGETS PARA CONTROL DE ESTADO ===
        # Lista de widgets que se habilitan/deshabilitan con el checkbox de red eléctrica
        self.red_widgets = [self.precio_red, self.horas_red_dia, self.dias_red]

        # === ESPACIADO VISUAL ===
        layout.addRow(QLabel(""))  # Línea vacía para separación

        # ===== SECCIÓN 5: BOTONES DE ACCIÓN =====
        # Botón principal de cálculo
        self.boton = QPushButton("🧮 Calcular")
        self.boton.setDefault(True)  # Se activa con Enter
        self.boton.clicked.connect(self.calcular)

        # Botón de limpieza para cerrar ventanas abiertas
        self.boton_cerrar_ventanas = QPushButton("🗑️ Cerrar ventanas")
        self.boton_cerrar_ventanas.clicked.connect(self.cerrar_todas_ventanas)

        # Layout horizontal centrado para los botones
        hbox_boton = QHBoxLayout()
        hbox_boton.addStretch(1)
        hbox_boton.addWidget(self.boton)
        hbox_boton.addSpacing(10)  # Separación entre botones
        hbox_boton.addWidget(self.boton_cerrar_ventanas)
        hbox_boton.addStretch(1)
        contenedor_boton = QWidget()
        contenedor_boton.setLayout(hbox_boton)
        layout.addRow(contenedor_boton)

        # Aplicar el layout principal a la ventana
        self.setLayout(layout)

    def __init__(self):
        """
        Constructor de la aplicación principal
        
        Inicializa:
        - Configuración de ventana principal
        - Listas de gestión de ventanas secundarias
        - Interfaz de usuario completa
        
        Note:
            La ventana se posiciona en (100,100) con tamaño 400x800 píxeles,
            optimizado para mostrar todos los controles sin scroll.
        """
        super().__init__()
        
        # === CONFIGURACIÓN DE VENTANA PRINCIPAL ===
        self.setWindowTitle("☀️ Calculadora de Minería Solar")
        self.setGeometry(100, 100, 400, 800)  # Posición (x,y) y tamaño (ancho,alto)
        
        # === GESTIÓN DE VENTANAS SECUNDARIAS ===
        self.ventanas_resultados = []    # Referencias a ventanas de análisis abiertas
        self.figuras_matplotlib = []     # Referencias a gráficas de matplotlib abiertas
        
        # === INICIALIZACIÓN DE INTERFAZ ===
        self.init_ui()

    # ===== MÉTODOS DE GESTIÓN DE VENTANAS =====

    def limpiar_ventanas_y_figuras_cerradas(self):
        """
        Limpia referencias a ventanas y figuras cerradas por el usuario
        
        Elimina automáticamente de las listas de gestión aquellas ventanas
        y figuras que ya no están visibles, evitando referencias muertas.
        
        Note:
            Se ejecuta automáticamente antes de crear nuevas ventanas
            para mantener un control eficiente de memoria.
        """
        # Filtrar solo ventanas que siguen visibles
        self.ventanas_resultados = [v for v in self.ventanas_resultados if v.isVisible()]
        
        # Obtener números de figuras matplotlib activas
        figuras_abiertas = plt.get_fignums()
        self.figuras_matplotlib = [f for f in self.figuras_matplotlib if f.number in figuras_abiertas]

    def cerrar_todas_ventanas(self):
        """
        Cierra todas las ventanas secundarias y gráficas abiertas
        
        Funcionalidad del botón "🗑️ Cerrar ventanas":
        - Cierra ventanas de resultados de análisis
        - Cierra gráficas de matplotlib
        - Limpia todas las referencias almacenadas
        
        Note:
            Útil para limpiar el escritorio después de múltiples análisis
            o antes de realizar nuevos cálculos.
        """
        # === CERRAR VENTANAS DE RESULTADOS ===
        for ventana in self.ventanas_resultados:
            if ventana.isVisible():
                ventana.close()
        self.ventanas_resultados.clear()
        
        # === CERRAR FIGURAS DE MATPLOTLIB ===
        for figura in self.figuras_matplotlib:
            try:
                plt.close(figura)
            except Exception:
                # Ignorar errores si la figura ya fue cerrada
                pass
        self.figuras_matplotlib.clear()

    def closeEvent(self, event):
        """
        Manejador del evento de cierre de la aplicación principal
        
        Se ejecuta automáticamente cuando el usuario cierra la ventana principal.
        Garantiza que todas las ventanas secundarias se cierren correctamente
        y se liberen los recursos de matplotlib.
        
        Args:
            event: Evento de cierre de Qt
        """
        self.cerrar_todas_ventanas()  # Limpiar ventanas secundarias
        super().closeEvent(event)     # Ejecutar cierre estándar de Qt

    # ===== MÉTODOS DE FORMATEO Y CONVERSIÓN DE MONEDA =====

    def formatear_valor(self, valor, decimales=2, mostrar_simbolo=True):
        """
        Formatea valores numéricos con conversión automática de moneda
        
        Args:
            valor (float): Valor numérico a formatear
            decimales (int): Número de decimales a mostrar (0, 2, o 3)
            mostrar_simbolo (bool): Si incluir símbolo de moneda
        
        Returns:
            str: Valor formateado con la moneda seleccionada
        
        Example:
            >>> self.formatear_valor(1000.50, 2, True)
            "1000.50 €"  # Si EUR está seleccionado
            "1100.55 $"  # Si USD está seleccionado (con conversión)
        
        Note:
            - Maneja automáticamente conversión EUR ↔ USD
            - Protege contra valores None, NaN e infinitos
            - Formatea según el número de decimales especificado
        """
        try:
            # === VALIDACIÓN DE ENTRADA ===
            if valor is None or math.isnan(valor) or math.isinf(valor):
                valor = 0
                
            # === CONVERSIÓN DE MONEDA ===
            es_usd = self.slider_moneda.value() == 1
            
            if es_usd and mostrar_simbolo:
                cambio = self._obtener_cambio_actual()
                valor = valor * cambio  # Convertir EUR a USD
                simbolo = "$"
            else:
                simbolo = "€"
                
            # Formatear según decimales especificados
            if decimales == 0:
                formatted = f"{valor:.0f}"
            elif decimales == 3:
                formatted = f"{valor:.3f}".rstrip('0').rstrip('.')
            else:
                formatted = f"{valor:.2f}"
                
            return f"{formatted} {simbolo}".strip() if mostrar_simbolo else formatted
        except (ValueError, TypeError, AttributeError):
            return "0"

    def formatear_campo_entrada(self, valor, tipo="general"):
        """Formatea valores para campos de entrada simplificado"""
        try:
            if valor is None or math.isnan(valor) or math.isinf(valor):
                return "0"
                
            if tipo == "precio":
                return str(int(round(valor)))
            elif tipo == "kwh":
                return f"{valor:.3f}".rstrip('0').rstrip('.')
            elif tipo == "hashrate":
                return f"{valor:.1f}".rstrip('0').rstrip('.')
            else:
                return f"{valor:.3f}".rstrip('0').rstrip('.')
        except (ValueError, TypeError, OverflowError):
            return str(valor) if valor is not None else "0"

    def es_usd(self):
        """Verifica si se está mostrando USD"""
        return self.slider_moneda.value() == 1

    def convertir_eur_a_usd(self, valor_eur):
        """Convierte EUR a USD"""
        return valor_eur * self._obtener_cambio_actual()

    def obtener_simbolo_moneda(self):
        """Obtiene el símbolo de la moneda actual"""
        return "$" if self.es_usd() else "€"

    def _obtener_cambio_actual(self):
        """Obtiene el tipo de cambio EUR/USD para cálculos - SIEMPRE la tasa base"""
        try:
            # Siempre devolver el cambio base EUR/USD, independientemente de lo que se muestre
            return self._obtener_cambio_base()
        except (ValueError, TypeError, AttributeError):
            pass
        
        # Si no hay valor válido, usar 1.10 como fallback
        return 1.10

    def cambiar_moneda_display(self):
        """
        Cambia la moneda de visualización entre USD y EUR
        
        Optimización: Solo actualiza la interfaz si realmente cambió la moneda,
        evitando actualizaciones innecesarias que consumen recursos.
        """
        es_usd = self.slider_moneda.value() == 1
        estado_anterior = getattr(self, '_estado_moneda_anterior', 0)
        estado_actual = 1 if es_usd else 0
        
        # === OPTIMIZACIÓN: Solo proceder si realmente cambió la moneda ===
        if estado_anterior == estado_actual:
            return  # No hay cambio, evitar procesamiento innecesario
        
        # Detectar si los campos esenciales están vacíos para carga automática
        campos_vacios = not all([
            self.cambio_usd_eur.text().strip(),
            self.precio_btc.text().strip(),
            self.hashrate_eh.text().strip(),
            self.fees_btc_bloque.text().strip()
        ])
        
        # Solo consultar APIs si los campos están vacíos
        if campos_vacios and not getattr(self, '_cambio_leido_api', False):
            self.actualizar_todos_los_campos(incluir_fees=True)
            self._cambio_leido_api = True
            self._precio_btc_leido_api = True
        else:
            self.actualizar_valores_moneda()
        
        # === ACTUALIZAR INTERFAZ SEGÚN MONEDA SELECCIONADA ===
        # Configuración de estilos y textos por moneda
        labels_config = {
            'eur_style': f"font-weight: bold; color: {'#888888' if es_usd else '#0066cc'};",
            'usd_style': f"font-weight: bold; color: {'#00aa00' if es_usd else '#888888'};",
            'moneda': 'USD' if es_usd else 'EUR',
            'simbolo': '$' if es_usd else '€',
            'simbolo_emoji': '💵' if es_usd else '💶'
        }
        
        # Aplicar estilos visuales a las etiquetas de moneda
        self.label_eur.setStyleSheet(labels_config['eur_style'])
        self.label_usd.setStyleSheet(labels_config['usd_style'])
        
        # Actualizar textos de etiquetas con la moneda correspondiente
        self.label_btc.setText(f"₿ Precio BTC ({labels_config['moneda']}):")
        self.label_hashprice.setText(f"💹 Hashprice (spot) ({labels_config['moneda']}/PH/día):")
        self.label_precio_equipo.setText(f"{labels_config['simbolo_emoji']} Precio equipo ({labels_config['simbolo']}):")
        self.label_precio_red.setText(f"💡 Precio electricidad ({labels_config['simbolo']}/kWh):")
        self.label_precio_venta.setText(f"💸 Excedente no vendido ({labels_config['simbolo']}/kWh):")
        self.label_cambio.setText(f"{labels_config['simbolo']} Cambio {'USD/EUR' if es_usd else 'EUR/USD'}:")
        
        # Actualizar visualización del tipo de cambio según dirección
        if es_usd:
            self._mostrar_cambio_inverso()  # Mostrar USD/EUR
        else:
            self._mostrar_cambio_directo()  # Mostrar EUR/USD
            
        # === GUARDAR ESTADO ACTUAL PARA PRÓXIMA COMPARACIÓN ===
        self._estado_moneda_anterior = estado_actual

    def actualizar_valores_moneda(self):
        """Solo actualiza la visualización - los datos base siguen en EUR"""
        # Actualizar visualización de precio BTC
        self._mostrar_precio_btc()
        
        # Actualizar visualización de hashprice  
        self._mostrar_hashprice()
        
        # Actualizar visualización de precio equipo
        self._mostrar_precio_equipo()
        
        # Actualizar visualización de precio electricidad
        self._mostrar_precio_red()
        
        # Actualizar visualización de precio venta solar
        self._mostrar_precio_venta()
        
        # Actualizar visualización del cambio según moneda seleccionada
        es_usd = self.slider_moneda.value() == 1
        if es_usd:
            self._mostrar_cambio_inverso()
        else:
            self._mostrar_cambio_directo()
        
        # Los demás campos se mantienen como están porque no necesitan conversión

    def _mostrar_cambio_directo(self):
        """Muestra el cambio EUR/USD directo"""
        try:
            cambio_eur_usd = self._obtener_cambio_base()
            self.cambio_usd_eur.setText(self.formatear_campo_entrada(cambio_eur_usd, "cambio"))
        except (ValueError, TypeError):
            pass
    
    def _mostrar_cambio_inverso(self):
        """Muestra el cambio USD/EUR (inverso)"""
        try:
            cambio_eur_usd = self._obtener_cambio_base()
            if cambio_eur_usd > 0:
                cambio_usd_eur = 1.0 / cambio_eur_usd
                self.cambio_usd_eur.setText(self.formatear_campo_entrada(cambio_usd_eur, "cambio"))
        except (ValueError, ZeroDivisionError):
            pass
    
    def _obtener_cambio_base(self):
        """Obtiene el cambio base EUR/USD almacenado internamente"""
        if not hasattr(self, '_cambio_base_eur_usd'):
            # Si no existe, calcularlo desde el campo actual
            try:
                # Intentar obtener valor del campo de texto
                if hasattr(self, 'cambio_usd_eur') and self.cambio_usd_eur.text().strip():
                    cambio_actual = float(self.cambio_usd_eur.text())
                    if cambio_actual <= 0:
                        raise ValueError("Cambio debe ser positivo")
                        
                    es_usd = getattr(self, 'slider_moneda', None) and self.slider_moneda.value() == 1
                    if es_usd:
                        # Si está mostrando USD/EUR, el valor base es el inverso
                        self._cambio_base_eur_usd = 1.0 / cambio_actual
                    else:
                        # Si está mostrando EUR/USD, ese es el valor base
                        self._cambio_base_eur_usd = cambio_actual
                else:
                    # Si no hay campo o está vacío, usar fallback
                    self._cambio_base_eur_usd = 1.10
            except (ValueError, ZeroDivisionError, AttributeError):
                self._cambio_base_eur_usd = 1.10  # fallback
        
        return self._cambio_base_eur_usd

    def guardar_valor_base(self, campo_texto, atributo_base):
        """Guarda valores base en EUR"""
        if getattr(self, '_actualizando_precios', False):
            return
            
        try:
            texto = campo_texto.text().strip()
            if texto:
                valor = float(texto)
                if self.es_usd():
                    # Convertir USD a EUR para almacenar como base
                    cambio = self._obtener_cambio_actual()
                    valor = valor / cambio if cambio > 0 else valor
                setattr(self, atributo_base, valor)
        except (ValueError, AttributeError):
            pass

    def mostrar_valor_campo(self, campo_texto, atributo_base, tipo="general"):
        """Muestra valores en la moneda seleccionada"""
        if not hasattr(self, atributo_base):
            return
            
        self._actualizando_precios = True
        try:
            valor_base = getattr(self, atributo_base)
            if self.es_usd():
                valor_mostrar = self.convertir_eur_a_usd(valor_base)
            else:
                valor_mostrar = valor_base
                
            campo_texto.setText(self.formatear_campo_entrada(valor_mostrar, tipo))
        finally:
            self._actualizando_precios = False


    def toggle_solar_fields(self):
        enabled = self.chk_solar.isChecked()
        for w in self.solar_widgets:
            w.setEnabled(enabled)

    def actualizar_hashprice_spot(self):
        """Calcula hashprice - SIEMPRE en EUR internamente"""
        try:
            # Usar precio base en EUR para cálculos
            precio_btc_eur = self._obtener_precio_btc_calculo()
            
            if precio_btc_eur <= 0:
                self.hashprice_spot.setText("0.00")
                return
            
            # Obtener datos de red con validación
            try:
                recompensa_btc = float(self.recompensa_btc.text()) if hasattr(self, 'recompensa_btc') and self.recompensa_btc.text().strip() else 3.125
                fees_btc_bloque = float(self.fees_btc_bloque.text()) if hasattr(self, 'fees_btc_bloque') and self.fees_btc_bloque.text().strip() else 0
                hashrate_eh = float(self.hashrate_eh.text()) if hasattr(self, 'hashrate_eh') and self.hashrate_eh.text().strip() else 0
            except (ValueError, AttributeError):
                # Usar valores por defecto si hay error
                recompensa_btc = 3.125
                fees_btc_bloque = 0
                hashrate_eh = 600  # Valor por defecto razonable
            
            if hashrate_eh > 0:
                hashrate_ph = hashrate_eh * 1_000
                btc_por_bloque = recompensa_btc + fees_btc_bloque
                factor_hashprice = (btc_por_bloque * BLOQUES_POR_DIA) / hashrate_ph
                
                # Calcular hashprice en EUR (base)
                hashprice_eur = factor_hashprice * precio_btc_eur
                
                # Validar resultado
                if math.isnan(hashprice_eur) or math.isinf(hashprice_eur):
                    hashprice_eur = 0
                
                # Guardar base en EUR
                self._hashprice_base_eur = hashprice_eur
                
                # Mostrar según moneda seleccionada
                self._mostrar_hashprice()
            else:
                self.hashprice_spot.setText("0.00")
                    
        except Exception:
            if hasattr(self, 'hashprice_spot'):
                self.hashprice_spot.setText("0.00")
    
    def _mostrar_hashprice(self):
        """Muestra el hashprice en la moneda seleccionada"""
        if not hasattr(self, '_hashprice_base_eur'):
            return
            
        self._actualizando_precios = True
        try:
            hashprice_mostrar = self._hashprice_base_eur * self._obtener_cambio_actual() if self.es_usd() else self._hashprice_base_eur
            self.hashprice_spot.setText(self.formatear_campo_entrada(hashprice_mostrar, "general"))
        finally:
            self._actualizando_precios = False
    
    def _obtener_hashprice_calculo(self):
        """Obtiene hashprice para cálculos - SIEMPRE en EUR"""
        return getattr(self, '_hashprice_base_eur', 0)

    def actualizar_todos_los_campos(self, incluir_fees=True):
        """Actualiza todos los campos de la red Bitcoin desde las APIs
        
        Args:
            incluir_fees (bool): Si True incluye fees, si False los omite
        """
        try:
            # Resetear flags para forzar consulta API
            self._cambio_leido_api = False
            self._precio_btc_leido_api = False
            self._forzar_actualizacion_api = True
            
            # Actualizar campos secuencialmente
            self.actualizar_cambio()
            QApplication.processEvents()
            
            self.actualizar_precio_btc()
            QApplication.processEvents()
            
            self.actualizar_hashrate()
            QApplication.processEvents()
            
            if incluir_fees:
                self.actualizar_fees_btc_bloque()
                QApplication.processEvents()
            
            self.actualizar_hashprice_spot()
            QApplication.processEvents()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error durante actualización: {e}")

    def toggle_red_fields(self):
        enabled = self.chk_red.isChecked()
        for w in self.red_widgets:
            w.setEnabled(enabled)

    def autocompletar_minero(self):
        """Autocompleta datos del minero seleccionado"""
        try:
            modelo = self.combo_minero.currentText()
            if modelo in MINEROS:
                datos = MINEROS[modelo]
                self.ths.setText(str(datos["ths"]))
                self.consumo_kw.setText(str(datos["consumo"]))
                self._precio_equipo_base_eur = datos["precio"]
                self._mostrar_precio_equipo()
            elif modelo == "Otro":
                for campo in [self.ths, self.consumo_kw, self.precio_equipo]:
                    campo.setText("")
        except (KeyError, AttributeError, ValueError):
            pass

    def actualizar_cambio(self):
        """Actualiza el tipo de cambio EUR/USD"""
        try:
            cambio_eur_usd = obtener_cambio_usd_eur()
            if cambio_eur_usd and cambio_eur_usd > 0:
                self._cambio_base_eur_usd = cambio_eur_usd
                self._actualizando_desde_api = True
                
                cambio_mostrar = 1.0 / cambio_eur_usd if self.es_usd() else cambio_eur_usd
                self.cambio_usd_eur.setText(self.formatear_campo_entrada(cambio_mostrar))
                    
                self._actualizando_desde_api = False
                self._forzar_actualizacion_api = True
            else:
                QMessageBox.warning(self, "Error", "No se pudo obtener el cambio EUR/USD.")
        except Exception:
            self._actualizando_desde_api = False
            self._forzar_actualizacion_api = False
            QMessageBox.warning(self, "Error", "No se pudo obtener el cambio EUR/USD.")

    def actualizar_precio_btc(self):
        """Actualiza el precio de BTC"""
        if (not self.precio_btc.text().strip() and not getattr(self, '_precio_btc_leido_api', False)) or getattr(self, '_forzar_actualizacion_api', False):
            try:
                precio_eur = obtener_precio_btc("eur")
                if precio_eur and precio_eur > 0:
                    self._precio_btc_base_eur = precio_eur
                    self._actualizando_desde_api = True
                    self._mostrar_precio_btc()
                    self._actualizando_desde_api = False
                    self.actualizar_hashprice_spot()
                    self._precio_btc_leido_api = True
                    self._forzar_actualizacion_api = False
                else:
                    QMessageBox.warning(self, "Error", "No se pudo obtener el precio de BTC.")
            except Exception:
                self._actualizando_desde_api = False
                QMessageBox.warning(self, "Error", "No se pudo obtener el precio de BTC.")
        elif hasattr(self, '_precio_btc_base_eur'):
            self._actualizando_desde_api = True
            self._mostrar_precio_btc()
            self._actualizando_desde_api = False
            self.actualizar_hashprice_spot()

    def _mostrar_precio_btc(self):
        """Muestra el precio BTC en la moneda seleccionada"""
        if not hasattr(self, '_precio_btc_base_eur'):
            return
            
        self._actualizando_precios = True
        try:
            precio_mostrar = self.convertir_eur_a_usd(self._precio_btc_base_eur) if self.es_usd() else self._precio_btc_base_eur
            self.precio_btc.setText(self.formatear_campo_entrada(precio_mostrar, "precio"))
        finally:
            self._actualizando_precios = False

    def _obtener_precio_btc_calculo(self):
        """Obtiene el precio BTC para cálculos en EUR"""
        return getattr(self, '_precio_btc_base_eur', 0)

    def actualizar_hashrate(self):
        """Actualiza el hashrate de la red"""
        try:
            hashrate = obtener_hashrate_eh()
            if hashrate and hashrate > 0:
                self.hashrate_eh.setText(self.formatear_campo_entrada(hashrate, "hashrate"))
            else:
                QMessageBox.warning(self, "Error", "No se pudo obtener el hashrate de la red.")
        except Exception:
            QMessageBox.warning(self, "Error", "No se pudo obtener el hashrate de la red.")

    def actualizar_fees_btc_bloque(self):
        """Actualiza los fees promedio por bloque"""
        try:
            resultado = obtener_fees_btc_bloque_mempool()
            if resultado and resultado[0] is not None:
                fee, bloques_reales = resultado
                if fee >= 0:
                    self.fees_btc_bloque.setText(f"{fee:.4f}")
                    self.actualizar_hashprice_spot()
                else:
                    QMessageBox.warning(self, "Error", "No se pudo obtener la media de fees por bloque.")
            else:
                QMessageBox.warning(self, "Error", "No se pudo obtener la media de fees por bloque.")
        except Exception:
            QMessageBox.warning(self, "Error", "No se pudo obtener la media de fees por bloque.")
    
    # Funciones helper compactas para manejo de precios  
    def _guardar_precio_equipo_base(self):
        self.guardar_valor_base(self.precio_equipo, '_precio_equipo_base_eur')
    
    def _mostrar_precio_equipo(self):
        self.mostrar_valor_campo(self.precio_equipo, '_precio_equipo_base_eur', "precio")
    
    def _obtener_precio_equipo_calculo(self):
        return getattr(self, '_precio_equipo_base_eur', 500.0)
    
    def _guardar_precio_red_base(self):
        self.guardar_valor_base(self.precio_red, '_precio_red_base_eur')
    
    def _mostrar_precio_red(self):
        self.mostrar_valor_campo(self.precio_red, '_precio_red_base_eur', "kwh")
    
    def _obtener_precio_red_calculo(self):
        return getattr(self, '_precio_red_base_eur', 0.08)
    
    def _guardar_precio_venta_base(self):
        self.guardar_valor_base(self.precio_venta_solar, '_precio_venta_base_eur')
    
    def _mostrar_precio_venta(self):
        self.mostrar_valor_campo(self.precio_venta_solar, '_precio_venta_base_eur', "kwh")
    
    def _obtener_precio_venta_calculo(self):
        return getattr(self, '_precio_venta_base_eur', 0.04)

    def validar_datos_entrada(self):
        """Valida que todos los campos obligatorios tengan valores válidos"""
        try:
            # Validaciones críticas con lambdas
            validaciones = [
                (float(self.precio_btc.text()), lambda x: x > 0),
                (float(self.cambio_usd_eur.text()), lambda x: x > 0),
                (float(self.hashrate_eh.text()), lambda x: x > 0),
                (float(self.fees_btc_bloque.text()), lambda x: x >= 0),
                (float(self.recompensa_btc.text()), lambda x: x > 0),
                (float(self.comision.text()), lambda x: 0 <= x <= 1),
                (int(self.num_minero.currentText()), lambda x: x > 0),
                (float(self.ths.text()), lambda x: x > 0),
                (float(self.consumo_kw.text()), lambda x: x > 0),
                (self._obtener_precio_equipo_calculo(), lambda x: x > 0)
            ]
            
            # Validaciones condicionales
            if self.chk_solar.isChecked():
                validaciones.extend([
                    (self._obtener_precio_venta_calculo(), lambda x: x >= 0),
                    (float(self.horas_solares_dia.text()), lambda x: 0 <= x <= 24),
                    (int(self.dias_uso.text()), lambda x: 1 <= x <= 365)
                ])
            
            if self.chk_red.isChecked():
                validaciones.extend([
                    (self._obtener_precio_red_calculo(), lambda x: x >= 0),
                    (float(self.horas_red_dia.text()), lambda x: 0 <= x <= 24),
                    (int(self.dias_red.text()), lambda x: 1 <= x <= 365)
                ])
            
            # Validar todas las condiciones
            return all(validador(valor) for valor, validador in validaciones) and (self.chk_solar.isChecked() or self.chk_red.isChecked())
            
        except (ValueError, TypeError, AttributeError, OverflowError):
            return False

    def calcular_metricas_solares(self, hashprice_th_dia, ths, consumo_kw, precio_venta_solar_eur, comision):
        """
        Calcula métricas financieras para minería con energía solar
        
        Args:
            hashprice_th_dia (float): Hashprice en EUR por TH/s por día
            ths (float): Hashrate total del equipo en TH/s
            consumo_kw (float): Consumo eléctrico total en kW
            precio_venta_solar_eur (float): Precio de venta de excedentes solares
            comision (float): Comisión del pool (decimal, ej: 0.02 = 2%)
        
        Returns:
            tuple: (ingreso_bruto, fees_pool, coste_oportunidad, beneficio_neto, energia_consumida, horas_operacion)
        
        Note:
            - Coste de oportunidad: energía que se podría vender en lugar de usar para minería
            - Solo calcula si la instalación solar está habilitada
        """
        if not self.chk_solar.isChecked():
            return 0, 0, 0, 0, 0, 0
            
        # === PARÁMETROS DE OPERACIÓN SOLAR ===
        horas_solares_dia = float(self.horas_solares_dia.text())
        dias_uso = int(self.dias_uso.text())
        horas_solares_anuales = horas_solares_dia * dias_uso
        
        # === CÁLCULOS FINANCIEROS ===
        # Ingresos de minería basados en hashprice y tiempo de operación
        ingreso_bruto = hashprice_th_dia * ths * (horas_solares_anuales / 24)
        ingreso_neto = ingreso_bruto * (1 - comision)
        
        # Coste de oportunidad: energía que se deja de vender a la red
        energia_consumida = consumo_kw * horas_solares_anuales
        coste_oportunidad = energia_consumida * precio_venta_solar_eur
        
        return ingreso_bruto, ingreso_bruto * comision, -coste_oportunidad, ingreso_neto - coste_oportunidad, energia_consumida, horas_solares_anuales

    def calcular_metricas_red(self, hashprice_th_dia, ths, consumo_kw, precio_red_eur, comision):
        """
        Calcula métricas financieras para minería con red eléctrica convencional
        
        Args:
            hashprice_th_dia (float): Hashprice en EUR por TH/s por día
            ths (float): Hashrate total del equipo en TH/s
            consumo_kw (float): Consumo eléctrico total en kW
            precio_red_eur (float): Precio de la electricidad de red
            comision (float): Comisión del pool (decimal)
        
        Returns:
            tuple: (ingreso_bruto, fees_pool, coste_electricidad, beneficio_neto, consumo_anual, horas_operacion)
        
        Note:
            - Permite operación 24/7 o configuración de horarios específicos
            - Coste directo de electricidad en lugar de coste de oportunidad
        """
        if not self.chk_red.isChecked():
            return 0, 0, 0, 0, 0, 0
            
        # === PARÁMETROS DE OPERACIÓN CON RED ===
        horas_red_dia = float(self.horas_red_dia.text())
        dias_red = int(self.dias_red.text())
        horas_red_anuales = horas_red_dia * dias_red
        
        # === CÁLCULOS FINANCIEROS ===
        # Ingresos de minería
        ingreso_bruto = hashprice_th_dia * ths * (horas_red_anuales / 24)
        ingreso_neto = ingreso_bruto * (1 - comision)
        
        # Coste directo de electricidad
        consumo_anual = consumo_kw * horas_red_anuales
        coste_electricidad = consumo_anual * precio_red_eur
        
        return ingreso_bruto, ingreso_bruto * comision, -coste_electricidad, ingreso_neto - coste_electricidad, consumo_anual, horas_red_anuales

    def calcular_probabilidad_solo_mining(self, ths):
        """
        Calcula la probabilidad estadística de encontrar un bloque en solo mining
        
        Args:
            ths (float): Hashrate total del equipo en TH/s
        
        Returns:
            str: Probabilidad expresada como "1 entre X" o "N/A" si no es calculable
        
        Note:
            - Basado en distribución de Poisson para eventos raros
            - Considera el hashrate total de la red Bitcoin
            - Útil para evaluar viabilidad de solo mining vs pool mining
        """
        try:
            # === OBTENER DATOS DE RED ===
            hashrate_red_ehs = float(self.hashrate_eh.text())
            hashrate_red_ths = hashrate_red_ehs * 1_000_000  # Convertir EH/s a TH/s
            
            # === CÁLCULO PROBABILÍSTICO ===
            bloques_anio = BLOQUES_POR_DIA * 365
            # Proporción del hashrate total de la red
            bloques_esperados = bloques_anio * (ths / hashrate_red_ths) if hashrate_red_ths > 0 else 0
            # Probabilidad usando distribución de Poisson
            prob_bloque = 1 - math.exp(-bloques_esperados) if bloques_esperados > 0 else 0
            
            if prob_bloque > 0:
                return f"1 entre {int(round(1/prob_bloque)):,}"
            else:
                return "N/A"
        except:
            return "N/A"

    def calcular(self):
        """
        Función principal de cálculo y análisis de rentabilidad
        
        Flujo de trabajo:
        1. Actualizar hashprice con datos actuales
        2. Validar todos los datos de entrada
        3. Calcular métricas para energía solar y red eléctrica
        4. Generar análisis de amortización y ROI
        5. Crear y mostrar ventana de resultados con gráfica
        
        Note:
            - Maneja automáticamente conversiones de moneda
            - Genera informes HTML detallados
            - Crea gráficas de matplotlib para visualización
        """
        # === ACTUALIZACIÓN DE DATOS EN TIEMPO REAL ===
        self.actualizar_hashprice_spot()
        
        # === VALIDACIÓN DE ENTRADA ===
        if not self.validar_datos_entrada():
            QMessageBox.critical(self, "Error", "Por favor, revisa que todos los campos contengan valores numéricos válidos.")
            return
            
        try:
            # Datos básicos
            num_minero = int(self.num_minero.currentText())
            ths = float(self.ths.text()) * num_minero
            consumo_kw = (float(self.consumo_kw.text()) / 1000) * num_minero
            precio_equipo = self._obtener_precio_equipo_calculo() * num_minero
            comision = float(self.comision.text())
            hashprice_th_dia = self._obtener_hashprice_calculo() / 1000
            precio_btc_eur = self._obtener_precio_btc_calculo()
            
            # Cálculos por fuente de energía
            metricas_solar = self.calcular_metricas_solares(hashprice_th_dia, ths, consumo_kw, self._obtener_precio_venta_calculo(), comision)
            metricas_red = self.calcular_metricas_red(hashprice_th_dia, ths, consumo_kw, self._obtener_precio_red_calculo(), comision)
            
            # Unpack de métricas
            prod_solar, fees_solar, coste_solar, benef_solar, energia_solar, _ = metricas_solar
            prod_red, fees_red, coste_red, benef_red, energia_red, _ = metricas_red
            
            # Métricas derivadas
            produccion_total = benef_solar + benef_red
            eficiencia_w_th = (float(self.consumo_kw.text()) * num_minero) / ths if ths > 0 else 0
            potencia_fotovoltaica_kwp = (consumo_kw / FACTOR_RENDIMIENTO_SOLAR) if self.chk_solar.isChecked() else 0
            
            # Amortización (usando operador ternario)
            amort_solar = precio_equipo / benef_solar if benef_solar > 0 else 0
            amort_red = precio_equipo / benef_red if benef_red > 0 else 0
            amort_total = precio_equipo / produccion_total if produccion_total > 0 else 0
            
            # Métricas de BTC
            btc_anio_bruto = (prod_solar + prod_red) / precio_btc_eur if precio_btc_eur > 0 else 0
            tiempo_btc_anios = 1 / btc_anio_bruto if btc_anio_bruto > 0 else 0
            coste_btc = (abs(coste_solar) + abs(coste_red) + fees_solar + fees_red) / btc_anio_bruto if btc_anio_bruto > 0 else 0
            
            # Generar y mostrar resultados
            resultado_html = self.generar_html_resultados(
                num_minero, ths, consumo_kw, eficiencia_w_th, precio_equipo, coste_btc, tiempo_btc_anios, 
                self.calcular_probabilidad_solo_mining(ths), amort_solar, amort_red, amort_total, produccion_total,
                prod_solar, coste_solar, fees_solar, benef_solar, energia_solar, potencia_fotovoltaica_kwp,
                prod_red, coste_red, fees_red, benef_red, energia_red, comision
            )
            
            self.mostrar_ventana_resultados(resultado_html, produccion_total, precio_equipo)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error en cálculos: {e}")

    def generar_html_resultados(self, num_minero, ths, consumo_kw, eficiencia_w_th, precio_equipo, coste_btc, tiempo_btc_anios, prob_solo_mining,
                               amort_solar, amort_red, amort_total, produccion_total,
                               prod_solar, coste_solar, fees_solar, benef_solar, energia_solar, potencia_fotovoltaica_kwp,
                               prod_red, coste_red, fees_red, benef_red, energia_red, comision):
        """Genera el HTML con los resultados"""
        simbolo_moneda = self.obtener_simbolo_moneda()
        
        return (
            f"<br>"
            f"<div style='text-align:center;'><b>🔨 DATOS DEL MINERO</b></div><br>"
            f"<div style='text-align:center;'>"
            f"<table style='border: 2px solid #333; border-collapse: collapse; text-align: center; margin: 0 auto; width: 80%;'>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>💻 <b>Modelo</b></td><td style='border: 1px solid #666; padding: 8px;'><b>{self.combo_minero.currentText()}</b></td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>📟 <b>Nº máquinas</b></td><td style='border: 1px solid #666; padding: 8px;'>{num_minero}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🚀 <b>Hashrate</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(ths, 2, False)} TH/s</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🪫 <b>Potencia</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(consumo_kw * 1000, 0, False)} W</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>✨ <b>Eficiencia energética</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(eficiencia_w_th, 2, False)} W/TH</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>💎 <b>Coste por terahash</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(precio_equipo/ths)}/TH</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>{simbolo_moneda} <b>Para minar 1 BTC</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(coste_btc)}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🕰️ <b>Tiempo para minar 1 BTC</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(tiempo_btc_anios, 2, False)} años</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🛒 <b>Inversión en equipos</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(precio_equipo)}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🎲 <b>Prob. solo mining (1 año)</b></td><td style='border: 1px solid #666; padding: 8px;'>{prob_solo_mining}</td></tr>"
            f"</table></div><br><hr><br>"
            
            f"<div style='text-align:center;'><b>💰 BENEFICIOS</b></div><br>"
            f"<div style='text-align:center;'>"
            f"<table style='border: 2px solid #333; border-collapse: collapse; text-align: center; margin: 0 auto; width: 80%;'>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🌞 <b>Amortización solar</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(amort_solar, 2, False) + ' años' if amort_solar > 0 else 'No rentable'}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🏭 <b>Amortización red</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(amort_red, 2, False) + ' años' if amort_red > 0 else 'No rentable'}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🔄 <b>Amortización combinada</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(amort_total, 2, False) + ' años' if amort_total > 0 else 'No rentable'}</td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background:white;'><b>🖐 Beneficio neto en 5 años</b></td><td style='border: 1px solid #666; padding: 8px; background:{'#e8f5e8' if (produccion_total * 5 - precio_equipo) > 0 else '#ffcccc' if (produccion_total * 5 - precio_equipo) < 0 else 'white'};'><b>{self.formatear_valor(produccion_total * 5 - precio_equipo)}</b></td></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background:white;'><b>🙌 Beneficio neto en 10 años</b></td><td style='border: 1px solid #666; padding: 8px; background:{'#e8f5e8' if (produccion_total * 10 - precio_equipo) > 0 else '#ffcccc' if (produccion_total * 10 - precio_equipo) < 0 else 'white'};'><b>{self.formatear_valor(produccion_total * 10 - precio_equipo)}</b></td></tr>"
            f"</table></div><br><hr><br>"
            
            f"<div style='text-align:center;'><b>🌞 PRODUCCIÓN SOLAR</b></div><br>"
            f"{self._generar_tabla_produccion('SOLAR', prod_solar, coste_solar, fees_solar, benef_solar, energia_solar, potencia_fotovoltaica_kwp, comision, simbolo_moneda)}"
            
            f"<div style='text-align:center;'><b>🏭 PRODUCCIÓN ELÉCTRICA</b></div><br>"
            f"{self._generar_tabla_produccion('RED', prod_red, coste_red, fees_red, benef_red, energia_red, 0, comision, simbolo_moneda)}"
            
            f"<div style='text-align:center;'><b>🌞 + 🏭 PRODUCCIÓN COMBINADA</b></div><br>"
            f"{self._generar_tabla_produccion('COMBINADA', prod_solar + prod_red, coste_solar + coste_red, fees_solar + fees_red, benef_solar + benef_red, energia_solar + energia_red, 0, comision, simbolo_moneda)}"
        )

    def _generar_tabla_produccion(self, tipo, produccion, coste, fees, beneficio, energia, potencia_kwp, comision, simbolo):
        """Genera tabla HTML para cada tipo de producción"""
        color_beneficio = '#e8f5e8' if beneficio > 0 else '#ffcccc' if beneficio < 0 else 'white'
        
        # Emoji de fajo de billetes según la moneda
        emoji_fajo = "💶" if simbolo == "€" else "💵"
        
        tabla = (
            f"<div style='text-align:center;'>"
            f"<table style='border: 2px solid #333; border-collapse: collapse; text-align: center; margin: 0 auto; width: 80%;'>"
            f"<tr style='border: 1px solid #666; background:#f5f5f5;'><th style='border: 1px solid #666; padding: 8px;'></th><th style='border: 1px solid #666; padding: 8px;'>DÍA</th><th style='border: 1px solid #666; padding: 8px;'>MES</th><th style='border: 1px solid #666; padding: 8px;'>AÑO</th></tr>"
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'><b>{emoji_fajo} Producción</b></td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(produccion/365, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(produccion/12, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(produccion, 2, False)} {simbolo}</td></tr>"
        )
        
        if tipo == "SOLAR":
            tabla += f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'><b>💸 Excedente no vendido</b></td>"
        elif tipo == "RED":
            tabla += f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'><b>💡 Electricidad</b></td>"
        else:
            tabla += f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'><b>💡 + 💸 Gastos</b></td>"
            
        tabla += (
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(coste/365, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(coste/12, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(coste, 2, False)} {simbolo}</td></tr>"
            
            f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'><b>🏦 Pool fees ({comision*100:.1f}%)</b></td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>-{self.formatear_valor(fees/365, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>-{self.formatear_valor(fees/12, 2, False)} {simbolo}</td>"
            f"<td style='border: 1px solid #666; padding: 8px;'>-{self.formatear_valor(fees, 2, False)} {simbolo}</td></tr>"
            
            f"<tr><td style='border: 1px solid #666; padding: 8px; background:white;'><b>{'✅' if beneficio >= 0 else '❌'} Beneficio neto</b></td>"
            f"<td style='border: 1px solid #666; padding: 8px; background:{color_beneficio};'><b>{self.formatear_valor(beneficio/365, 2, False)} {simbolo}</b></td>"
            f"<td style='border: 1px solid #666; padding: 8px; background:{color_beneficio};'><b>{self.formatear_valor(beneficio/12, 2, False)} {simbolo}</b></td>"
            f"<td style='border: 1px solid #666; padding: 8px; background:{color_beneficio};'><b>{self.formatear_valor(beneficio, 2, False)} {simbolo}</b></td></tr>"
            f"</table></div><br>"
        )
        
        if energia > 0:
            rentabilidad_bruta = produccion / energia if energia > 0 else 0
            rentabilidad_neta = beneficio / energia if energia > 0 else 0
            color_rent = '#e8f5e8' if rentabilidad_neta > 0 else '#ffcccc' if rentabilidad_neta < 0 else 'white'
            
            tabla += (
                f"<div style='text-align:center;'>"
                f"<table style='border: 2px solid #333; border-collapse: collapse; text-align: center; margin: 0 auto; width: 80%;'>"
            )
            
            if potencia_kwp > 0:
                tabla += f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🔆 <b>Potencia fotovoltaica</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(potencia_kwp, 2, False)} kWp</td></tr>"
                
            tabla += (
                f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>🪫 <b>Consumo anual</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(energia, 0, False)} kWh</td></tr>"
                f"<tr><td style='border: 1px solid #666; padding: 8px; background-color: #f5f5f5;'>📈 <b>Rentabilidad bruta kWh</b></td><td style='border: 1px solid #666; padding: 8px;'>{self.formatear_valor(rentabilidad_bruta, 3, False)} {simbolo}/kWh</td></tr>"
                f"<tr><td style='border: 1px solid #666; padding: 8px; background:{color_rent};'>📉 <b>Rentabilidad neta kWh</b></td><td style='border: 1px solid #666; padding: 8px; background:{color_rent};'>{self.formatear_valor(rentabilidad_neta, 3, False)} {simbolo}/kWh</td></tr>"
                f"</table></div><br>"
            )
            
        return tabla + "<hr><br>"

    def mostrar_ventana_resultados(self, resultado_html, beneficio_anual, inversion):
        """Muestra ventana de resultados y gráfica"""
        nombre_minero = self.combo_minero.currentText()
        
        # === GESTIÓN DE VENTANAS EN CASCADA ===
        # Limpiar referencias a ventanas cerradas para mantener control eficiente
        self.limpiar_ventanas_y_figuras_cerradas()
        # Calcular offset de cascada basado en ventanas abiertas
        offset_cascada = len(self.ventanas_resultados)
        
        # === CREAR Y MOSTRAR VENTANA DE RESULTADOS ===
        ventana_resultados = VentanaResultados(resultado_html, nombre_minero, self, offset_cascada)
        self.ventanas_resultados.append(ventana_resultados)  # Agregar a lista de gestión
        ventana_resultados.show()
        
        # === GENERAR GRÁFICA DE AMORTIZACIÓN ===
        # Mostrar gráfica posicionada automáticamente debajo de la ventana de resultados
        self.mostrar_grafica_amortizacion(beneficio_anual, inversion, nombre_minero, ventana_resultados, offset_cascada)

# ===== PUNTO DE ENTRADA DE LA APLICACIÓN =====
if __name__ == "__main__":
    """
    Función principal para ejecutar la aplicación
    
    Flujo de ejecución:
    1. Crear instancia de QApplication
    2. Crear ventana principal de CalculadoraMineria  
    3. Mostrar la ventana
    4. Iniciar bucle de eventos de Qt
    5. Terminar aplicación al cerrar ventana
    
    Note:
        sys.exit(app.exec_()) garantiza que la aplicación termine
        correctamente y libere todos los recursos del sistema.
    """
    # Crear aplicación Qt
    app = QApplication(sys.argv)
    
    # Crear y mostrar ventana principal
    ventana = CalculadoraMineria()
    ventana.show()
    
    # Ejecutar bucle de eventos hasta que se cierre la aplicación
    sys.exit(app.exec_())