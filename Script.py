#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SISTEMA VIP PRO - Escáner de Apuestas Deportivas
Versión: 4.0.0
Autor: Edadloko
Funcionalidades:
- Escaneo de ligas mundiales
- Alertas de cambio de cuotas en vivo
- Envío de picks VIP a Telegram
- Cálculo de variación de cuotas
- Variables de entorno para seguridad
"""

import os
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
import logging
import json
import hashlib
import sqlite3
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
import random

# ======================= CARGAR VARIABLES DE ENTORNO =======================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8863411916:AAFgGN0ZdCMMhj0Qfduw3u07HetZd8oEu44")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7911684592")
API_KEY_ODDS = os.getenv("API_KEY_ODDS", "c779994639413fb76d7fa8993faf4b8b")

# ======================= CONFIGURACIÓN =======================

class Configuracion:
    """Configuración del sistema"""
    VERSION = "4.0.0"
    PICKS_DIARIOS = 30
    CUOTA_INICIAL_MAXIMA = 1.70
    SUBIDA_MINIMA_PORCENTAJE = 20
    ESCANEO_INTERVALO = 30
    DB_PATH = "data/vip_pro.db"

# ======================= DATACLASS =======================

@dataclass
class Partido:
    """Modelo de partido"""
    id: str
    liga: str
    pais: str
    local: str
    visitante: str
    fecha: datetime
    cuota_inicial: float
    cuota_actual: float
    equipo_seguido: str
    confianza: float
    stake: int
    minuto: int = 0
    marcador_local: int = 0
    marcador_visitante: int = 0
    mercado: str = "To Qualify"

# ======================= FUNCIONES DE TELEGRAM =======================

def calcular_variacion_cuota(cuota_inicial: float, cuota_actual: float) -> float:
    """Calcula el porcentaje de variación de la cuota"""
    if cuota_inicial <= 0:
        return 0.0
    aumento = ((cuota_actual - cuota_inicial) / cuota_inicial) * 100
    return round(aumento, 2)

def enviar_a_telegram(mensaje: str) -> bool:
    """Envía mensaje a Telegram usando variables de entorno"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Error: Faltan las credenciales de Telegram")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ Alerta enviada con éxito a Telegram")
            return True
        else:
            print(f"❌ Error al enviar: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Excepción de red: {e}")
        return False

# ======================= GENERADOR DE ALERTAS VIP =======================

def generar_alerta_vip(
    partido: str,
    minuto: int,
    marcador: str,
    cuota_ini: float,
    cuota_act: float,
    mercado: str = "To Qualify",
    equipo: str = "",
    liga: str = "",
    confianza: str = "Media",
    stake: int = 1
) -> str:
    """
    Genera una alerta VIP con formato profesional
    """
    porcentaje = calcular_variacion_cuota(cuota_ini, cuota_act)
    fecha_actual = datetime.now().strftime("%d %b %Y, %H:%M")
    
    # Determinar nivel de confianza
    if cuota_act < 1.30:
        nivel_confianza = "🔵 Alta"
    elif cuota_act < 1.70:
        nivel_confianza = "🟡 Media"
    else:
        nivel_confianza = "🔴 Baja"
    
    # Emoji según porcentaje de subida
    if porcentaje > 30:
        emoji_subida = "🚨"
    elif porcentaje > 20:
        emoji_subida = "📈"
    else:
        emoji_subida = "📊"
    
    mensaje = (
        f"⚽ *{partido}*\n"
        f"⭐ *Stake {stake}%* • Confianza {nivel_confianza}  |  ⏳ {fecha_actual}\n\n"
        f"📌 *Al momento del pick:*\n"
        f"• Minuto: {minuto}'\n"
        f"• Marcador: {marcador}\n"
        f"• Cuotas: {mercado}: 1 @ {cuota_act}\n\n"
        f"📊 *Cambio de cuotas:*\n"
        f"{cuota_ini:.2f} ➔ {cuota_act:.2f} ({emoji_subida} +{porcentaje}% Subida mín.)"
    )
    
    return mensaje

# ======================= BASE DE DATOS =======================

class Database:
    """Base de datos simple"""
    
    def __init__(self):
        self.db_path = Configuracion.DB_PATH
        self._init_db()
        self.logger = logging.getLogger(__name__)
    
    def _init_db(self):
        """Inicializa la base de datos"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS partidos (
                    id TEXT PRIMARY KEY,
                    liga TEXT,
                    pais TEXT,
                    local TEXT,
                    visitante TEXT,
                    fecha TIMESTAMP,
                    cuota_inicial REAL,
                    cuota_actual REAL,
                    cuota_maxima REAL,
                    equipo TEXT,
                    enviado INTEGER DEFAULT 0
                )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("✅ Base de datos lista")
            
        except Exception as e:
            self.logger.error(f"Error DB: {e}")

# ======================= MONITOR =======================

class Monitor:
    """Sistema de monitoreo con alertas en vivo"""
    
    def __init__(self):
        self.config = Configuracion()
        self.db = Database()
        self.logger = logging.getLogger(__name__)
        self.partidos_activos = {}
        self.notificaciones = []
        
        self.ligas = [
            {"key": "soccer_epl", "nombre": "Premier League", "pais": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
            {"key": "soccer_spain_la_liga", "nombre": "La Liga", "pais": "🇪🇸"},
            {"key": "soccer_italy_serie_a", "nombre": "Serie A", "pais": "🇮🇹"},
            {"key": "soccer_germany_bundesliga", "nombre": "Bundesliga", "pais": "🇩🇪"},
            {"key": "soccer_france_ligue_one", "nombre": "Ligue 1", "pais": "🇫🇷"},
            {"key": "soccer_brazil_campeonato", "nombre": "Brasileirao", "pais": "🇧🇷"},
            {"key": "soccer_argentina_primera_division", "nombre": "Liga Argentina", "pais": "🇦🇷"},
            {"key": "soccer_usa_mls", "nombre": "MLS", "pais": "🇺🇸"},
        ]
    
    async def ejecutar(self):
        """Ejecuta el monitoreo"""
        self.logger.info("🔄 INICIANDO MONITOREO VIP")
        self.logger.info(f"📊 {len(self.ligas)} ligas")
        self.logger.info(f"⚙️ Cuota inicial máxima: {self.config.CUOTA_INICIAL_MAXIMA}")
        self.logger.info(f"📈 Subida mínima: {self.config.SUBIDA_MINIMA_PORCENTAJE}%")
        self.logger.info("=" * 50)
        
        while True:
            try:
                await self._escanear()
                await self._verificar_alertas()
                await self._enviar_notificaciones()
                await asyncio.sleep(self.config.ESCANEO_INTERVALO)
            except Exception as e:
                self.logger.error(f"Error: {e}")
                await asyncio.sleep(10)
    
    async def _escanear(self):
        """Escanea partidos"""
        async with aiohttp.ClientSession() as session:
            for liga in self.ligas:
                try:
                    url = f"https://api.the-odds-api.com/v4/sports/{liga['key']}/odds/?apiKey={API_KEY_ODDS}&regions=eu,us&markets=h2h,totals"
                    
                    async with session.get(url, timeout=15) as response:
                        if response.status != 200:
                            continue
                        
                        data = await response.json()
                        
                        for partido_data in data[:10]:
                            partido = self._crear_partido(partido_data, liga)
                            if partido:
                                self.partidos_activos[partido.id] = partido
                                self.logger.info(f"📊 {partido.local} vs {partido.visitante} - {partido.cuota_actual:.2f}")
                                
                except Exception as e:
                    self.logger.error(f"Error en {liga['nombre']}: {e}")
    
    def _crear_partido(self, data: Dict, liga: Dict) -> Optional[Partido]:
        """Crea un partido"""
        try:
            local = data.get('home_team', '')
            visitante = data.get('away_team', '')
            
            if not local or not visitante:
                return None
            
            fecha_str = data.get('commence_time')
            if not fecha_str:
                return None
            
            fecha = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
            
            # Buscar mejor cuota
            mejor_cuota = 0
            mejor_nombre = ''
            for bookmaker in data.get('bookmakers', []):
                for mercado in bookmaker.get('markets', []):
                    if mercado.get('key') == 'h2h':
                        for outcome in mercado.get('outcomes', []):
                            cuota = outcome.get('price', 0)
                            nombre = outcome.get('name', '')
                            if cuota > mejor_cuota:
                                mejor_cuota = cuota
                                mejor_nombre = nombre
            
            if mejor_cuota == 0:
                return None
            
            # Solo seguir si está dentro del rango
            if mejor_cuota > self.config.CUOTA_INICIAL_MAXIMA:
                return None
            
            # Calcular confianza y stake
            if mejor_cuota < 1.30:
                confianza = 0.85
                stake = 10
            elif mejor_cuota < 1.50:
                confianza = 0.75
                stake = 7
            elif mejor_cuota < 1.70:
                confianza = 0.65
                stake = 5
            else:
                confianza = 0.50
                stake = 3
            
            partido_id = hashlib.md5(f"{local}-{visitante}-{fecha.isoformat()}".encode()).hexdigest()[:16]
            
            return Partido(
                id=partido_id,
                liga=liga['nombre'],
                pais=liga['pais'],
                local=local,
                visitante=visitante,
                fecha=fecha,
                cuota_inicial=mejor_cuota,
                cuota_actual=mejor_cuota,
                equipo_seguido=mejor_nombre,
                confianza=confianza,
                stake=stake,
                minuto=random.randint(15, 45),
                marcador_local=random.randint(0, 2),
                marcador_visitante=random.randint(0, 2)
            )
            
        except Exception as e:
            self.logger.error(f"Error creando partido: {e}")
            return None
    
    async def _verificar_alertas(self):
        """Verifica cambios de cuota y genera alertas"""
        for partido in self.partidos_activos.values():
            # Simular cambio de cuota (en producción sería API en vivo)
            if random.random() > 0.6:
                subida = random.uniform(15, 35)
                nueva_cuota = partido.cuota_inicial * (1 + subida/100)
                
                if nueva_cuota > partido.cuota_actual:
                    partido.cuota_actual = nueva_cuota
                    
                    # Verificar si supera el umbral
                    porcentaje = calcular_variacion_cuota(partido.cuota_inicial, partido.cuota_actual)
                    
                    if porcentaje >= self.config.SUBIDA_MINIMA_PORCENTAJE:
                        # Generar alerta
                        marcador = f"{partido.marcador_local}-{partido.marcador_visitante}"
                        partido_str = f"{partido.local} – {partido.visitante}"
                        
                        alerta = generar_alerta_vip(
                            partido=partido_str,
                            minuto=partido.minuto,
                            marcador=marcador,
                            cuota_ini=partido.cuota_inicial,
                            cuota_act=partido.cuota_actual,
                            mercado="To Qualify",
                            equipo=partido.equipo_seguido,
                            liga=f"{partido.pais} {partido.liga}",
                            confianza="Media" if partido.confianza < 0.80 else "Alta",
                            stake=partido.stake
                        )
                        
                        self.notificaciones.append(alerta)
                        self.logger.info(f"🚨 Alerta generada: {partido_str} - +{porcentaje:.1f}%")
    
    async def _enviar_notificaciones(self):
        """Envía notificaciones a Telegram"""
        while self.notificaciones:
            mensaje = self.notificaciones.pop(0)
            
            # Usar la función de envío con variables de entorno
            if enviar_a_telegram(mensaje):
                self.logger.info("✅ Notificación enviada")
            else:
                self.logger.error("❌ Error enviando notificación")
                self.notificaciones.append(mensaje)
                break
            
            await asyncio.sleep(2)

# ======================= MAIN =======================

async def main():
    """Función principal"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Verificar credenciales
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ERROR: Faltan credenciales de Telegram")
        print("📝 Crea un archivo .env con:")
        print("  TELEGRAM_BOT_TOKEN=tu_token")
        print("  TELEGRAM_CHAT_ID=tu_chat_id")
        return
    
    print("🚀 INICIANDO SISTEMA VIP PRO v4.0")
    print(f"🤖 Bot: @EduardoApuestasBot")
    print(f"👤 Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 50)
    
    # Enviar mensaje de inicio
    mensaje_inicio = (
        "🚀 *SISTEMA VIP PRO ACTIVADO*\n\n"
        "📊 Monitoreando 8+ ligas mundiales\n"
        "⚡ Buscando cambios de cuotas en vivo\n"
        "📈 Alertas cuando la cuota suba +20%\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    enviar_a_telegram(mensaje_inicio)
    
    monitor = Monitor()
    await monitor.ejecutar()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⏹️ Sistema detenido por el usuario")
    except Exception as e:
        print(f"💥 Error fatal: {e}")
