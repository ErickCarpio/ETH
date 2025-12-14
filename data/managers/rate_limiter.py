"""
Rate Limiter Universal para APIs
Fase 1.4: Control de Rate Limits

Características:
- Sliding window rate limiting
- Múltiples límites por fuente (requests/segundo, requests/minuto, etc.)
- Backoff automático cuando se acerca al límite
- Priorización de requests
- Métricas de uso
"""

import asyncio
import time
import logging
from typing import Dict, Optional, List
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Configuración de un límite de tasa"""
    max_requests: int  # Máximo de requests
    time_window: int   # Ventana de tiempo en segundos
    name: str = ""     # Nombre descriptivo del límite


@dataclass
class RequestRecord:
    """Registro de un request"""
    timestamp: float
    endpoint: str = ""
    priority: int = 0


class RateLimiter:
    """
    Rate Limiter con sliding window algorithm

    Soporta múltiples límites simultáneos (ej: 1200/min + 100/10s)
    """

    def __init__(self, limits: List[RateLimit], safety_margin: float = 0.9):
        """
        Args:
            limits: Lista de límites a aplicar
            safety_margin: Factor de seguridad (0.9 = usar solo 90% del límite)
        """
        self.limits = limits
        self.safety_margin = safety_margin
        self.request_history: deque = deque()
        self.lock = asyncio.Lock()

        # Métricas
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        self.rejected_requests = 0

        # Backoff dinámico
        self.backoff_multiplier = 1.0
        self.last_limit_hit = 0.0

    async def acquire(self, priority: int = 0, endpoint: str = "") -> bool:
        """
        Adquiere permiso para hacer un request

        Args:
            priority: Prioridad del request (mayor = más importante)
            endpoint: Endpoint específico (para métricas)

        Returns:
            True si el request puede proceder
        """
        async with self.lock:
            current_time = time.time()

            # Limpiar requests antiguos
            self._cleanup_old_requests(current_time)

            # Verificar si podemos proceder
            wait_time = self._calculate_wait_time(current_time)

            if wait_time > 0:
                self.total_waits += 1
                self.total_wait_time += wait_time
                logger.debug(f"⏳ Rate limit: esperando {wait_time:.2f}s (endpoint: {endpoint})")

                # Si el wait es muy largo, podría ser mejor rechazar
                if wait_time > 60:  # Más de 1 minuto de espera
                    logger.warning(f"⚠️  Request rechazado - wait time muy largo: {wait_time:.1f}s")
                    self.rejected_requests += 1
                    return False

                # Esperar
                await asyncio.sleep(wait_time)
                current_time = time.time()

            # Registrar el request
            self.request_history.append(
                RequestRecord(
                    timestamp=current_time,
                    endpoint=endpoint,
                    priority=priority
                )
            )
            self.total_requests += 1

            return True

    def _cleanup_old_requests(self, current_time: float):
        """
        Elimina requests fuera de todas las ventanas de tiempo
        """
        # Encontrar la ventana más larga
        max_window = max(limit.time_window for limit in self.limits)

        # Eliminar requests más antiguos que la ventana más larga
        cutoff_time = current_time - max_window

        while self.request_history and self.request_history[0].timestamp < cutoff_time:
            self.request_history.popleft()

    def _calculate_wait_time(self, current_time: float) -> float:
        """
        Calcula el tiempo de espera necesario para no exceder límites
        """
        max_wait = 0.0

        for limit in self.limits:
            # Contar requests en esta ventana
            cutoff_time = current_time - limit.time_window
            requests_in_window = sum(
                1 for r in self.request_history
                if r.timestamp >= cutoff_time
            )

            # Aplicar safety margin
            effective_limit = int(limit.max_requests * self.safety_margin)

            # Si estamos en el límite, calcular cuánto esperar
            if requests_in_window >= effective_limit:
                # Encontrar el request más antiguo en la ventana
                oldest_in_window = next(
                    (r for r in self.request_history if r.timestamp >= cutoff_time),
                    None
                )

                if oldest_in_window:
                    # Esperar hasta que ese request salga de la ventana
                    wait_for_this_limit = (oldest_in_window.timestamp + limit.time_window) - current_time
                    max_wait = max(max_wait, wait_for_this_limit)

                    # Registrar hit al límite
                    self.last_limit_hit = current_time

        return max(0, max_wait)

    def get_usage_stats(self) -> Dict:
        """
        Retorna estadísticas de uso
        """
        current_time = time.time()
        stats = {
            "total_requests": self.total_requests,
            "total_waits": self.total_waits,
            "total_wait_time": self.total_wait_time,
            "avg_wait_time": self.total_wait_time / max(1, self.total_waits),
            "rejected_requests": self.rejected_requests,
            "buffer_size": len(self.request_history),
        }

        # Calcular uso actual por cada límite
        for limit in self.limits:
            cutoff_time = current_time - limit.time_window
            requests_in_window = sum(
                1 for r in self.request_history
                if r.timestamp >= cutoff_time
            )
            usage_pct = (requests_in_window / limit.max_requests) * 100

            limit_name = limit.name or f"{limit.max_requests}/{limit.time_window}s"
            stats[f"usage_{limit_name}"] = {
                "current": requests_in_window,
                "max": limit.max_requests,
                "percentage": usage_pct
            }

        return stats

    def reset(self):
        """
        Resetea el rate limiter (útil para testing)
        """
        self.request_history.clear()
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        self.rejected_requests = 0


class MultiSourceRateLimiter:
    """
    Gestor de rate limiters para múltiples fuentes de datos

    Cada fuente tiene sus propios límites
    """

    def __init__(self):
        self.limiters: Dict[str, RateLimiter] = {}

    def add_source(self, source_name: str, limits: List[RateLimit], safety_margin: float = 0.9):
        """
        Agrega un rate limiter para una fuente específica

        Args:
            source_name: Nombre de la fuente (binance, coinglass, etc.)
            limits: Lista de límites para esta fuente
            safety_margin: Factor de seguridad
        """
        self.limiters[source_name] = RateLimiter(limits, safety_margin)
        logger.info(f"✅ Rate limiter configurado para {source_name}")

    async def acquire(self, source_name: str, priority: int = 0, endpoint: str = "") -> bool:
        """
        Adquiere permiso para hacer request a una fuente

        Args:
            source_name: Nombre de la fuente
            priority: Prioridad del request
            endpoint: Endpoint específico

        Returns:
            True si puede proceder
        """
        limiter = self.limiters.get(source_name)
        if not limiter:
            logger.warning(f"⚠️  No hay rate limiter para {source_name}, permitiendo request")
            return True

        return await limiter.acquire(priority, endpoint)

    def get_stats(self, source_name: Optional[str] = None) -> Dict:
        """
        Obtiene estadísticas de uso

        Args:
            source_name: Fuente específica, o None para todas
        """
        if source_name:
            limiter = self.limiters.get(source_name)
            return limiter.get_usage_stats() if limiter else {}

        return {
            source: limiter.get_usage_stats()
            for source, limiter in self.limiters.items()
        }


# Configuraciones predefinidas para APIs populares
def create_binance_limiter() -> RateLimiter:
    """
    Rate limiter para Binance API

    Límites oficiales:
    - 1200 requests/minuto (weight-based, simplificado a requests)
    - 100 requests/10 segundos (burst protection)
    """
    return RateLimiter([
        RateLimit(max_requests=1200, time_window=60, name="per_minute"),
        RateLimit(max_requests=100, time_window=10, name="per_10s"),
    ])


def create_coinglass_limiter() -> RateLimiter:
    """
    Rate limiter para Coinglass API (freemium)

    Límites aproximados:
    - 100 requests/minuto
    - 10 requests/segundo
    """
    return RateLimiter([
        RateLimit(max_requests=100, time_window=60, name="per_minute"),
        RateLimit(max_requests=10, time_window=1, name="per_second"),
    ])


def create_defillama_limiter() -> RateLimiter:
    """
    Rate limiter para DefiLlama API (no oficial, conservador)

    Límites conservadores:
    - 60 requests/minuto
    - 5 requests/segundo
    """
    return RateLimiter([
        RateLimit(max_requests=60, time_window=60, name="per_minute"),
        RateLimit(max_requests=5, time_window=1, name="per_second"),
    ])


# Ejemplo de uso
if __name__ == "__main__":
    async def test_rate_limiter():
        # Crear limiter con 5 requests/segundo
        limiter = RateLimiter([
            RateLimit(max_requests=5, time_window=1, name="test")
        ])

        print("🧪 Testing Rate Limiter...")
        print("Límite: 5 requests/segundo\n")

        start_time = time.time()

        # Intentar 10 requests rápidos
        for i in range(10):
            request_start = time.time()
            can_proceed = await limiter.acquire(endpoint=f"test_{i}")
            request_time = time.time() - request_start

            if can_proceed:
                print(f"✅ Request {i+1} - Wait: {request_time:.3f}s")
            else:
                print(f"❌ Request {i+1} - RECHAZADO")

        total_time = time.time() - start_time
        print(f"\n⏱️  Tiempo total: {total_time:.2f}s")
        print(f"📊 Stats: {limiter.get_usage_stats()}")

    async def test_multi_source():
        # Crear multi-source limiter
        multi = MultiSourceRateLimiter()
        multi.add_source("binance", create_binance_limiter().limits)
        multi.add_source("coinglass", create_coinglass_limiter().limits)

        print("\n🧪 Testing Multi-Source Limiter...")

        # Hacer requests a diferentes fuentes
        for i in range(5):
            await multi.acquire("binance", endpoint=f"/api/v3/ticker/price")
            await multi.acquire("coinglass", endpoint=f"/api/fundingRate")

        print(f"\n📊 Stats:")
        for source, stats in multi.get_stats().items():
            print(f"\n{source}:")
            print(f"  Total requests: {stats['total_requests']}")
            print(f"  Total waits: {stats['total_waits']}")

    asyncio.run(test_rate_limiter())
    asyncio.run(test_multi_source())
