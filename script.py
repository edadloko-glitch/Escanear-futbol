#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SISTEMA VIP PRO - Escáner de Apuestas Deportivas
Versión: 3.0.0
Autor: Edadloko
"""

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
import random

# ======================= CONFIGURACIÓN =======================
TELEGRAM_TOKEN = "8863411916:AAFsGN0ZdCMMhj0QfdUw3u07HetZd8oEu44"
TELEGRAM_CHAT_ID = "7911684592"
API_KEY_ODDS = "c779994639413fb76d7fa8993faf4b8b"

# ======================= CONFIGURACIÓN =======================

class Configuracion:
    """Configuración del sistema"""
    VERSION = "3.0.0"
    PICKS_DIARIOS = 30
    CUOTA_INICIAL_MAXIMA = 1.70
    SUBIDA_MINIMA = 20
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
            import os
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
                    cuota REAL,
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
    """Sistema de monitoreo"""
    
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
        self.logger.info("🔄 INICIANDO MONITOREO")
        self.logger.info(f"📊 {len(self.ligas)} ligas")
        self.logger.info("=" * 50)
        
        while True:
            try:
                await self._escanear()
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
                    url = f"https://api.the-odds-api.com/v4/sports/{liga['key']}/odds/?apiKey={API_KEY_ODDS}&regions=eu,us&markets=h2h"
                    
                    async with session.get(url, timeout=15) as response:
                        if response.status != 200:
                            continue
                        
                        data = await response.json()
                        
                        for partido_data in data[:5]:
                            partido = self._crear_partido(partido_data, liga)
                            if partido and partido.id not in self.partidos_activos:
                                self.partidos_activos[partido.id] = partido
                                
                                # Crear notificación
                                mensaje = self._generar_mensaje(partido)
                                self.notificaciones.append(mensaje)
                                
                                self.logger.info(f"📊 Partido: {partido.local} vs {partido.visitante}")
                                
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
            
            if mejor_cuota == 0 or mejor_cuota > self.config.CUOTA_INICIAL_MAXIMA:
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
                stake=stake
            )
            
        except Exception as e:
            self.logger.error(f"Error creando partido: {e}")
            return None
    
    def _generar_mensaje(self, partido: Partido) -> str:
        """Genera mensaje para Telegram"""
        
        # Nivel de confianza
        if partido.confianza >= 0.80:
            nivel = "🟢 Alta"
        elif partido.confianza >= 0.60:
            nivel = "🟡 Media"
        else:
            nivel = "🔴 Baja"
        
        mensaje = (
            f"⚽ {partido.local} vs {partido.visitante}\n"
            f"📌 {partido.pais} {partido.liga}\n"
            f"📊 Confianza: {nivel}\n"
            f"💰 Stake: {partido.stake}%\n"
            f"📋 PICK: {partido.equipo_seguido}\n"
            f"📈 Cuota: {partido.cuota_actual:.2f}\n"
            f"📅 {partido.fecha.strftime('%d/%m/%Y %H:%M')}"
        )
        
        return mensaje
    
    async def _enviar_notificaciones(self):
        """Envía notificaciones"""
        while self.notificaciones:
            mensaje = self.notificaciones.pop(0)
            
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": mensaje,
                    "parse_mode": "Markdown"
                }
                
                response = requests.post(url, data=payload, timeout=10)
                response.raise_for_status()
                
                self.logger.info("✅ Mensaje enviado")
                
            except Exception as e:
                self.logger.error(f"Error enviando: {e}")
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
    
    monitor = Monitor()
    await monitor.ejecutar()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⏹️ Sistema detenido")
    except Exception as e:
        logging.error(f"💥 Error: {e}")
