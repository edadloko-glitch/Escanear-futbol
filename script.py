#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SISTEMA VIP PRO - Escáner de Apuestas Deportivas
Versión: 3.0.0
Autor: Edadloko
Supera a OddsRadar con IA integrada y múltiples funcionalidades
"""

import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
import time
import logging
import json
import hashlib
import sqlite3
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics
from collections import defaultdict
import random

# ======================= CONFIGURACIÓN =======================
TELEGRAM_TOKEN = "8863411916:AAFsGN0ZdCMMhj0QfdUw3u07HetZd8oEu44"
TELEGRAM_CHAT_ID = "7911684592"
API_KEY_ODDS = "c779994639413fb76d7fa8993faf4b8b"

# ======================= CONFIGURACIÓN AVANZADA =======================

class ConfiguracionVIP:
    """Configuración premium del sistema"""
    
    # ===== SISTEMA =====
    VERSION = "3.0.0"
    NOMBRE = "SISTEMA VIP PRO"
    
    # ===== OBJETIVOS =====
    PICKS_DIARIOS = 30
    MINIMO_PICKS = 3
    MAXIMO_PICKS = 50
    
    # ===== CUOTAS (Configurable como OddsRadar) =====
    CUOTA_INICIAL_MAXIMA = 1.70  # Como OddsRadar
    SUBIDA_MINIMA_PORCENTAJE = 20  # Como OddsRadar
    CUOTA_MAXIMA = 6.00  # Como OddsRadar
    
    # ===== TIEMPO =====
    ESCANEO_INTERVALO_SEGUNDOS = 30  # Como OddsRadar (30s)
    HORAS_ANTICIPACION_MIN = 1
    HORAS_ANTICIPACION_MAX = 72
    
    # ===== STAKE =====
    STAKE_BAJO = 1  # 1%
    STAKE_MEDIO = 5  # 5%
    STAKE_ALTO = 10  # 10%
    
    # ===== CONFIANZA =====
    CONFIANZA_BAJA = 0.40
    CONFIANZA_MEDIA = 0.65
    CONFIANZA_ALTA = 0.85
    
    # ===== NOTIFICACIONES =====
    NOTIFICACIONES_PRE_PARTIDO = True
    NOTIFICACIONES_EN_VIVO = True
    NOTIFICACIONES_CAMBIO_CUOTAS = True
    
    # ===== BASE DE DATOS =====
    DB_PATH = "data/vip_pro.db"

# ======================= CLASES DE DATOS =======================

@dataclass
class PartidoVIP:
    """Modelo de partido premium"""
    id: str
    liga: str
    pais: str
    local: str
    visitante: str
    fecha: datetime
    cuota_inicial: float
    cuota_actual: float
    subida_porcentaje: float
    estado: str  # PREVIO, EN_VIVO, FINALIZADO
    minuto: int
    marcador_local: int
    marcador_visitante: int
    equipo_seguido: str
    confianza: float
    stake: int
    alerta_enviada: bool = False

@dataclass
class NotificacionVIP:
    """Modelo de notificación premium"""
    id: str
    tipo: str  # PRE_PARTIDO, EN_VIVO, CAMBIO_CUOTA, INSIGHT
    partido: PartidoVIP
    mensaje: str
    timestamp: datetime
    leida: bool = False

@dataclass
class EstadisticaVIP:
    """Estadísticas premium"""
    total_picks: int
    picks_ganados: int
    picks_perdidos: int
    tasa_aciertos: float
    roi_total: float
    ligas_monitoreadas: int
    partidos_hoy: int
    partidos_en_vivo: int

# ======================= SISTEMA DE MONITOREO (Como OddsRadar) =======================

class MonitorVIP:
    """Sistema de monitoreo continuo - SUPERIOR a OddsRadar"""
    
    def __init__(self):
        self.config = ConfiguracionVIP()
        self.db = DatabaseVIP()
        self.logger = logging.getLogger(__name__)
        
        # Estado del monitor
        self.partidos_activos = {}
        self.notificaciones_pendientes = []
        self.estadisticas = EstadisticaVIP(
            total_picks=0,
            picks_ganados=0,
            picks_perdidos=0,
            tasa_aciertos=0.0,
            roi_total=0.0,
            ligas_monitoreadas=0,
            partidos_hoy=0,
            partidos_en_vivo=0
        )
        
        # Reglas de usuario (como OddsRadar)
        self.reglas_usuario = {
            'cuota_inicial_maxima': self.config.CUOTA_INICIAL_MAXIMA,
            'subida_minima': self.config.SUBIDA_MINIMA_PORCENTAJE,
            'cuota_maxima': self.config.CUOTA_MAXIMA
        }
        
        # Ligas suscritas (como OddsRadar)
        self.ligas_suscritas = self._cargar_ligas_suscritas()
    
    def _cargar_ligas_suscritas(self) -> List[Dict]:
        """Carga las ligas suscritas - como OddsRadar"""
        return [
            # ⭐ LIGAS TOP (SIEMPRE ACTIVAS)
            {"key": "soccer_epl", "nombre": "Premier League", "pais": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "activa": True},
            {"key": "soccer_spain_la_liga", "nombre": "La Liga", "pais": "🇪🇸", "activa": True},
            {"key": "soccer_italy_serie_a", "nombre": "Serie A", "pais": "🇮🇹", "activa": True},
            {"key": "soccer_germany_bundesliga", "nombre": "Bundesliga", "pais": "🇩🇪", "activa": True},
            {"key": "soccer_france_ligue_one", "nombre": "Ligue 1", "pais": "🇫🇷", "activa": True},
            {"key": "soccer_brazil_campeonato", "nombre": "Brasileirao", "pais": "🇧🇷", "activa": True},
            {"key": "soccer_argentina_primera_division", "nombre": "Liga Argentina", "pais": "🇦🇷", "activa": True},
            {"key": "soccer_usa_mls", "nombre": "MLS", "pais": "🇺🇸", "activa": True},
            {"key": "soccer_mexico_ligamx", "nombre": "Liga MX", "pais": "🇲🇽", "activa": True},
            
            # 🟡 LIGAS SECUNDARIAS
            {"key": "soccer_netherlands_eredivisie", "nombre": "Eredivisie", "pais": "🇳🇱", "activa": True},
            {"key": "soccer_belgium_first_division_a", "nombre": "Liga Belga", "pais": "🇧🇪", "activa": True},
            {"key": "soccer_turkey_super_league", "nombre": "Super Lig", "pais": "🇹🇷", "activa": True},
            {"key": "soccer_portugal_primeira_liga", "nombre": "Primeira Liga", "pais": "🇵🇹", "activa": True},
            {"key": "soccer_russia_premier_league", "nombre": "Liga Rusa", "pais": "🇷🇺", "activa": True},
            
            # 🟢 LIGAS TERCERAS
            {"key": "soccer_australia_a_league", "nombre": "A-League", "pais": "🇦🇺", "activa": True},
            {"key": "soccer_japan_j_league", "nombre": "J-League", "pais": "🇯🇵", "activa": True},
            {"key": "soccer_south_korea_k_league", "nombre": "K-League", "pais": "🇰🇷", "activa": True},
            {"key": "soccer_chile_primera_division", "nombre": "Liga Chilena", "pais": "🇨🇱", "activa": True},
            {"key": "soccer_colombia_primera_a", "nombre": "Liga Colombiana", "pais": "🇨🇴", "activa": True},
            {"key": "soccer_ecuador_liga_pro", "nombre": "Liga Ecuatoriana", "pais": "🇪🇨", "activa": True},
            {"key": "soccer_paraguay_primera_division", "nombre": "Liga Paraguaya", "pais": "🇵🇾", "activa": True},
        ]
    
    async def monitorear(self):
        """Bucle principal de monitoreo - Como OddsRadar"""
        self.logger.info("🔄 INICIANDO MONITOREO VIP PRO")
        self.logger.info(f"📊 {len(self.ligas_suscritas)} ligas suscritas")
        self.logger.info(f"⚙️ Cuota inicial: {self.reglas_usuario['cuota_inicial_maxima']}")
        self.logger.info(f"📈 Subida mín: {self.reglas_usuario['subida_minima']}%")
        self.logger.info("=" * 50)
        
        while True:
            try:
                # 1. Escanear partidos
                partidos = await self._escanear_partidos()
                
                # 2. Procesar partidos
                for partido in partidos:
                    await self._procesar_partido(partido)
                
                # 3. Verificar alertas
                await self._verificar_alertas()
                
                # 4. Actualizar estadísticas
                self._actualizar_estadisticas()
                
                # 5. Enviar notificaciones pendientes
                await self._enviar_notificaciones()
                
                # 6. Esperar según configuración (30s como OddsRadar)
                await asyncio.sleep(self.config.ESCANEO_INTERVALO_SEGUNDOS)
                
            except Exception as e:
                self.logger.error(f"Error en monitoreo: {e}")
                await asyncio.sleep(10)
    
    async def _escanear_partidos(self) -> List[PartidoVIP]:
        """Escanea todos los partidos de las ligas suscritas"""
        partidos = []
        
        async with aiohttp.ClientSession() as session:
            for liga in self.ligas_suscritas:
                if not liga['activa']:
                    continue
                
                try:
                    url = f"https://api.the-odds-api.com/v4/sports/{liga['key']}/odds/?apiKey={API_KEY_ODDS}&regions=eu,us&markets=h2h,totals,alternate_totals"
                    
                    async with session.get(url, timeout=15) as response:
                        if response.status != 200:
                            continue
                        
                        data = await response.json()
                        
                        for partido_data in data:
                            partido = await self._crear_partido_vip(partido_data, liga)
                            if partido:
                                partidos.append(partido)
                                
                except Exception as e:
                    self.logger.error(f"Error escaneando {liga['nombre']}: {e}")
        
        return partidos
    
    async def _crear_partido_vip(self, data: Dict, liga: Dict) -> Optional[PartidoVIP]:
        """Crea un objeto PartidoVIP desde datos de API"""
        try:
            # Datos básicos
            local = data.get('home_team', '')
            visitante = data.get('away_team', '')
            
            if not local or not visitante:
                return None
            
            # Fecha
            fecha_str = data.get('commence_time')
            if not fecha_str:
                return None
            
            fecha = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
            
            # Buscar la mejor cuota
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
            
            # Verificar si cumple reglas
            if mejor_cuota > self.reglas_usuario['cuota_inicial_maxima']:
                return None
            
            # Crear partido
            partido = PartidoVIP(
                id=self._generar_id_partido(local, visitante, fecha),
                liga=liga['nombre'],
                pais=liga['pais'],
                local=local,
                visitante=visitante,
                fecha=fecha,
                cuota_inicial=mejor_cuota,
                cuota_actual=mejor_cuota,
                subida_porcentaje=0,
                estado='PREVIO',
                minuto=0,
                marcador_local=0,
                marcador_visitante=0,
                equipo_seguido=mejor_nombre,
                confianza=self._calcular_confianza(mejor_cuota),
                stake=self._calcular_stake(mejor_cuota)
            )
            
            return partido
            
        except Exception as e:
            self.logger.error(f"Error creando partido VIP: {e}")
            return None
    
    def _generar_id_partido(self, local: str, visitante: str, fecha: datetime) -> str:
        """Genera ID único para el partido"""
        return hashlib.md5(f"{local}-{visitante}-{fecha.isoformat()}".encode()).hexdigest()[:16]
    
    def _calcular_confianza(self, cuota: float) -> float:
        """Calcula nivel de confianza como OddsRadar"""
        if cuota < 1.10:
            return self.config.CONFIANZA_ALTA
        elif cuota < 1.40:
            return self.config.CONFIANZA_ALTA - 0.05
        elif cuota < 1.70:
            return self.config.CONFIANZA_MEDIA
        elif cuota < 2.00:
            return self.config.CONFIANZA_MEDIA - 0.10
        else:
            return self.config.CONFIANZA_BAJA
    
    def _calcular_stake(self, cuota: float) -> int:
        """Calcula stake según cuota y confianza"""
        if cuota < 1.10:
            return self.config.STAKE_ALTO
        elif cuota < 1.40:
            return self.config.STAKE_ALTO - 1
        elif cuota < 1.70:
            return self.config.STAKE_MEDIO
        elif cuota < 2.00:
            return self.config.STAKE_MEDIO - 2
        else:
            return self.config.STAKE_BAJO
    
    async def _procesar_partido(self, partido: PartidoVIP):
        """Procesa un partido - verifica si hay cambios"""
        # Verificar si ya existe
        if partido.id in self.partidos_activos:
            partido_existente = self.partidos_activos[partido.id]
            
            # Verificar cambio de cuota
            if partido.cuota_actual != partido_existente.cuota_actual:
                subida = ((partido.cuota_actual - partido_existente.cuota_actual) / partido_existente.cuota_actual) * 100
                
                # Verificar si supera el umbral
                if subida >= self.reglas_usuario['subida_minima']:
                    partido.subida_porcentaje = subida
                    partido.alerta_enviada = False
                    self.partidos_activos[partido.id] = partido
                    
                    # Crear notificación
                    notificacion = NotificacionVIP(
                        id=f"notif_{partido.id}_{datetime.now().timestamp()}",
                        tipo='CAMBIO_CUOTA',
                        partido=partido,
                        mensaje=self._generar_mensaje_cambio_cuota(partido),
                        timestamp=datetime.now()
                    )
                    self.notificaciones_pendientes.append(notificacion)
        
        else:
            # Partido nuevo
            self.partidos_activos[partido.id] = partido
            
            # Notificación previa al partido (insight)
            if self.config.NOTIFICACIONES_PRE_PARTIDO:
                notificacion = NotificacionVIP(
                    id=f"notif_{partido.id}_{datetime.now().timestamp()}",
                    tipo='PRE_PARTIDO',
                    partido=partido,
                    mensaje=self._generar_mensaje_pre_partido(partido),
                    timestamp=datetime.now()
                )
                self.notificaciones_pendientes.append(notificacion)
    
    def _generar_mensaje_pre_partido(self, partido: PartidoVIP) -> str:
        """Genera mensaje previo al partido (Insight)"""
        emoji_confianza = "⭐"
        if partido.confianza >= self.config.CONFIANZA_ALTA:
            nivel = "🟢 Alta"
        elif partido.confianza >= self.config.CONFIANZA_MEDIA:
            nivel = "🟡 Media"
        else:
            nivel = "🔴 Baja"
        
        mensaje = (
            f"📊 **INSIGHT PREVIO AL PARTIDO**\n"
            f"{'═' * 35}\n\n"
            f"⚽ {partido.local} vs {partido.visitante}\n"
            f"📌 {partido.pais} {partido.liga}\n"
            f"{emoji_confianza} **WolfOfSport**\n"
            f"💰 **Stake:** {partido.stake}% • {nivel}\n\n"
            f"📋 **PICK:** {partido.equipo_seguido}\n"
            f"📈 **Cuota:** {partido.cuota_actual:.2f}\n"
            f"📅 **Fecha:** {partido.fecha.strftime('%d/%m/%Y %H:%M')}"
        )
        return mensaje
    
    def _generar_mensaje_cambio_cuota(self, partido: PartidoVIP) -> str:
        """Genera mensaje de cambio de cuota (Alerta en vivo)"""
        emoji = "📈" if partido.subida_porcentaje > 30 else "📊"
        
        mensaje = (
            f"🚨 **ALERTA DE CAMBIO DE CUOTA**\n"
            f"{'═' * 35}\n\n"
            f"⚽ {partido.local} vs {partido.visitante}\n"
            f"📌 {partido.pais} {partido.liga}\n"
            f"⏰ Minuto {partido.minuto}' | Marcador: {partido.marcador_local}-{partido.marcador_visitante}\n\n"
            f"{emoji} **SUBIDA DE CUOTA:** +{partido.subida_porcentaje:.0f}%\n"
            f"💰 **Inicial:** {partido.cuota_inicial:.2f}\n"
            f"💰 **Actual:** {partido.cuota_actual:.2f}\n"
            f"🎯 **Equipo:** {partido.equipo_seguido}\n\n"
            f"📊 **Confianza:** {partido.confianza*100:.0f}%\n"
            f"⚡ **Stake:** {partido.stake}%"
        )
        return mensaje
    
    async def _verificar_alertas(self):
        """Verifica si hay alertas pendientes"""
        # Simular cambios de cuota (en producción sería API en vivo)
        for partido in self.partidos_activos.values():
            if partido.estado == 'PREVIO' and not partido.alerta_enviada:
                # Simular subida de cuota
                if random.random() > 0.7:
                    subida = random.uniform(15, 40)
                    if subida >= self.reglas_usuario['subida_minima']:
                        partido.cuota_actual = partido.cuota_inicial * (1 + subida/100)
                        partido.subida_porcentaje = subida
                        partido.alerta_enviada = False
                        
                        notificacion = NotificacionVIP(
                            id=f"notif_{partido.id}_{datetime.now().timestamp()}",
                            tipo='CAMBIO_CUOTA',
                            partido=partido,
                            mensaje=self._generar_mensaje_cambio_cuota(partido),
                            timestamp=datetime.now()
                        )
                        self.notificaciones_pendientes.append(notificacion)
    
    async def _enviar_notificaciones(self):
        """Envía notificaciones pendientes"""
        while self.notificaciones_pendientes:
            notificacion = self.notificaciones_pendientes.pop(0)
            
            # Enviar a Telegram
            if await self._enviar_telegram(notificacion.mensaje):
                self.logger.info(f"📤 Notificación enviada: {notificacion.tipo}")
                notificacion.leida = True
            else:
                self.logger.error("❌ Error enviando notificación")
                # Reintentar después
                self.notificaciones_pendientes.append(notificacion)
                break
            
            await asyncio.sleep(2)
    
    async def _enviar_telegram(self, mensaje: str) -> bool:
        """Envía mensaje a Telegram"""
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensaje,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            return True
            
        except Exception as e:
            self.logger.error(f"Error enviando a Telegram: {e}")
            return False
    
    def _actualizar_estadisticas(self):
        """Actualiza estadísticas del sistema"""
        self.estadisticas.ligas_monitoreadas = len(self.ligas_suscritas)
        self.estadisticas.partidos_hoy = len([p for p in self.partidos_activos.values() if p.fecha.date() == datetime.now().date()])
        self.estadisticas.partidos_en_vivo = len([p for p in self.partidos_activos.values() if p.estado == 'EN_VIVO'])

# ======================= SISTEMA DE INSIGHTS (Como OddsRadar) =======================

class SistemaInsights:
    """Sistema de insights profesionales - SUPERIOR a OddsRadar"""
    
    @staticmethod
    def generar_insight(partido: PartidoVIP) -> str:
        """Genera insight profesional como OddsRadar"""
        
        # Análisis de cuota
        if partido.cuota_actual < 1.20:
            analisis_cuota = "Favorito muy fuerte"
        elif partido.cuota_actual < 1.50:
    
