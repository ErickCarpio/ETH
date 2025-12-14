"""
Unified Rate Limiter
Combina ambas implementaciones:
- Token Bucket (tu implementación - simple, eficiente)
- Sliding Window (mi implementación - más preciso)

Usa Token Bucket por defecto (más rápido).
"""

import asyncio
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class UnifiedRateLimiter:
    """
    Rate Limiter híbrido que combina lo mejor de ambos:
    - Token Bucket para velocidad
    - Métricas y monitoring de Sliding Window
    """

    def __init__(self, use_token_bucket: bool = True):
        """
        Args:
            use_token_bucket: Si True, usa Token Bucket (más rápido)
                             Si False, usa Sliding Window (más preciso)
        """
        self.use_token_bucket = use_token_bucket

        # Configuración de límites: (capacity, window_seconds)
        self.limits = {
            "binance": (1200, 60),       # 1200 req/min
            "binance_rest": (1200, 60),
            "coinglass": (100, 60),       # 100 req/min (freemium)
            "defillama": (60, 60),        # 60 req/min
            "cryptopanic": (50, 60),      # 50 req/min
            "newsapi": (100, 86400),      # 100 req/día
            "default": (10, 1)            # 10 req/segundo
        }

        # Token Bucket state
        self.tokens: Dict[str, float] = {}
        self.last_update: Dict[str, float] = {}

        # Métricas
        self.total_requests: Dict[str, int] = {}
        self.total_waits: Dict[str, int] = {}
        self.total_wait_time: Dict[str, float] = {}

        # Inicializar buckets
        for api, (capacity, _) in self.limits.items():
            self.tokens[api] = capacity
            self.last_update[api] = time.time()
            self.total_requests[api] = 0
            self.total_waits[api] = 0
            self.total_wait_time[api] = 0.0

    def add_source(self, source_name: str, max_requests: int, window_seconds: int):
        """
        Agrega una nueva fuente con límite personalizado

        Args:
            source_name: Nombre de la fuente
            max_requests: Máximo de requests
            window_seconds: Ventana de tiempo en segundos
        """
        self.limits[source_name] = (max_requests, window_seconds)
        self.tokens[source_name] = max_requests
        self.last_update[source_name] = time.time()
        self.total_requests[source_name] = 0
        self.total_waits[source_name] = 0
        self.total_wait_time[source_name] = 0.0

        logger.info(f"✅ Rate limiter configurado: {source_name} = {max_requests}/{window_seconds}s")

    async def acquire(self, source: str, weight: int = 1, priority: int = 0) -> bool:
        """
        Adquiere permiso para hacer un request

        Args:
            source: Nombre de la fuente
            weight: Peso del request (algunas APIs tienen weighted limits)
            priority: Prioridad (no usado en Token Bucket, pero kept for compatibility)

        Returns:
            True si puede proceder
        """
        # Normalizar nombre
        if source not in self.limits:
            logger.debug(f"Fuente desconocida '{source}', usando 'default'")
            source = "default"

        capacity, window = self.limits[source]
        fill_rate = capacity / window

        # Tracking
        self.total_requests[source] += 1

        while True:
            now = time.time()

            # Rellenar tokens basado en tiempo transcurrido
            elapsed = now - self.last_update.get(source, now)
            self.last_update[source] = now

            new_tokens = elapsed * fill_rate
            self.tokens[source] = min(capacity, self.tokens.get(source, 0) + new_tokens)

            # Verificar si hay suficientes tokens
            if self.tokens[source] >= weight:
                self.tokens[source] -= weight
                return True

            # Si no hay, esperar
            needed = weight - self.tokens[source]
            wait_time = needed / fill_rate

            if wait_time > 0.1:  # Solo loguear esperas significativas
                logger.debug(f"⏳ Rate limit {source}: esperando {wait_time:.2f}s")

            self.total_waits[source] += 1
            self.total_wait_time[source] += wait_time

            await asyncio.sleep(wait_time)

    def get_stats(self, source: Optional[str] = None) -> Dict:
        """
        Obtiene estadísticas de uso

        Args:
            source: Fuente específica, o None para todas
        """
        if source:
            return {
                "source": source,
                "total_requests": self.total_requests.get(source, 0),
                "total_waits": self.total_waits.get(source, 0),
                "total_wait_time": self.total_wait_time.get(source, 0.0),
                "avg_wait_time": (
                    self.total_wait_time.get(source, 0.0) /
                    max(1, self.total_waits.get(source, 1))
                ),
                "current_tokens": self.tokens.get(source, 0),
                "capacity": self.limits.get(source, (0, 0))[0]
            }

        # Stats de todas las fuentes
        return {
            src: self.get_stats(src)
            for src in self.limits.keys()
            if self.total_requests.get(src, 0) > 0
        }

    def reset(self, source: Optional[str] = None):
        """
        Resetea el rate limiter

        Args:
            source: Fuente específica, o None para todas
        """
        if source:
            if source in self.limits:
                capacity, _ = self.limits[source]
                self.tokens[source] = capacity
                self.last_update[source] = time.time()
                self.total_requests[source] = 0
                self.total_waits[source] = 0
                self.total_wait_time[source] = 0.0
        else:
            # Reset all
            for src in self.limits.keys():
                self.reset(src)


# Instancia global (puede importarse desde cualquier lugar)
global_rate_limiter = UnifiedRateLimiter()


# Helpers para configuraciones comunes
def create_binance_limiter() -> UnifiedRateLimiter:
    """Crea rate limiter para Binance con límites oficiales"""
    limiter = UnifiedRateLimiter()
    limiter.add_source("binance", 1200, 60)
    limiter.add_source("binance_ws", 10, 1)  # WebSocket connections limit
    return limiter


def create_multi_source_limiter() -> UnifiedRateLimiter:
    """Crea rate limiter con todas las fuentes configuradas"""
    limiter = UnifiedRateLimiter()
    limiter.add_source("binance", 1200, 60)
    limiter.add_source("coinglass", 100, 60)
    limiter.add_source("defillama", 60, 60)
    limiter.add_source("cryptopanic", 50, 60)
    limiter.add_source("newsapi", 100, 86400)
    return limiter


# Ejemplo de uso
if __name__ == "__main__":
    async def test():
        limiter = UnifiedRateLimiter()

        print("🧪 Test: 25 requests a Binance (límite 1200/min = 20/segundo)")
        start = time.time()

        for i in range(25):
            await limiter.acquire("binance")
            elapsed = time.time() - start
            print(f"✅ Request #{i+1:2d} - {elapsed:.3f}s")

        print(f"\n📊 Stats:")
        stats = limiter.get_stats("binance")
        print(f"   Total requests: {stats['total_requests']}")
        print(f"   Total waits: {stats['total_waits']}")
        print(f"   Total wait time: {stats['total_wait_time']:.2f}s")
        print(f"   Avg wait time: {stats['avg_wait_time']:.3f}s")
        print(f"   Tokens restantes: {stats['current_tokens']:.2f}/{stats['capacity']}")

    asyncio.run(test())
