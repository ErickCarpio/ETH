"""
Cache Manager - FASE 1.4
=========================

Sistema inteligente de caché para respuestas de API.

Features:
- TTL (Time To Live) configurable por tipo de dato
- Memory optimization con LRU eviction
- Estadísticas de hit/miss
- Integración con Rate Limiter

Cache Strategy:
- Order book snapshots: 1s TTL (muy volátil)
- GEX de Deribit: 5min TTL (actualiza cada 5min)
- Funding rates: 8h TTL (actualiza cada 8h)
- Liquidaciones: 1min TTL
- Metadata (symbols, instruments): 1h TTL
"""

import time
import logging
from typing import Any, Dict, Optional, Callable
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import hashlib
import json

logger = logging.getLogger(__name__)


class CacheEntry:
    """
    Entrada individual de caché con TTL.
    """

    def __init__(self, key: str, value: Any, ttl: int):
        """
        Initialize cache entry.

        Args:
            key: Cache key
            value: Cached value
            ttl: Time to live (seconds)
        """
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 0

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return time.time() - self.created_at > self.ttl

    def touch(self) -> None:
        """Update last access time and count."""
        self.last_accessed = time.time()
        self.access_count += 1

    def age(self) -> float:
        """Get age in seconds."""
        return time.time() - self.created_at


class CacheManager:
    """
    Gestor de caché inteligente con TTL y LRU eviction.

    Features:
    - TTL configurable por tipo de dato
    - LRU (Least Recently Used) eviction cuando se alcanza max_size
    - Hit/miss statistics
    - Thread-safe
    - Memory optimization
    """

    # Default TTLs por tipo de dato (segundos)
    DEFAULT_TTLS = {
        'orderbook_snapshot': 1,        # 1 segundo (muy volátil)
        'gex': 300,                      # 5 minutos
        'funding_rate': 28800,           # 8 horas
        'liquidations': 60,              # 1 minuto
        'options_chain': 300,            # 5 minutos
        'metadata': 3600,                # 1 hora
        'price': 5,                      # 5 segundos
        'default': 60                    # 1 minuto por defecto
    }

    def __init__(self, max_size: int = 1000):
        """
        Initialize Cache Manager.

        Args:
            max_size: Máximo número de entradas en caché
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()

        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

        logger.info(f"CacheManager initialized - max_size: {max_size}")

    def _make_key(self, namespace: str, *args, **kwargs) -> str:
        """
        Genera cache key único.

        Args:
            namespace: Namespace del caché (ej: 'orderbook', 'gex')
            *args: Argumentos posicionales
            **kwargs: Argumentos con nombre

        Returns:
            Cache key único
        """
        # Combinar namespace + args + kwargs
        key_parts = [namespace]

        # Add positional args
        for arg in args:
            key_parts.append(str(arg))

        # Add keyword args (sorted for consistency)
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")

        # Create hash for long keys
        key_str = ":".join(key_parts)

        if len(key_str) > 200:
            # Hash largo para evitar keys muy largos
            key_hash = hashlib.md5(key_str.encode()).hexdigest()
            return f"{namespace}:{key_hash}"

        return key_str

    def get(self,
            namespace: str,
            *args,
            **kwargs) -> Optional[Any]:
        """
        Obtiene valor del caché.

        Args:
            namespace: Namespace del caché
            *args: Argumentos para generar key
            **kwargs: Argumentos para generar key

        Returns:
            Cached value o None si miss/expired
        """
        key = self._make_key(namespace, *args, **kwargs)

        with self.lock:
            entry = self.cache.get(key)

            if entry is None:
                self.misses += 1
                return None

            # Check expiration
            if entry.is_expired():
                # Expired - remove
                del self.cache[key]
                self.expirations += 1
                self.misses += 1
                logger.debug(f"Cache expired: {key}")
                return None

            # Hit - update LRU
            entry.touch()
            self.cache.move_to_end(key)
            self.hits += 1

            logger.debug(f"Cache hit: {key} (age: {entry.age():.1f}s)")

            return entry.value

    def set(self,
            namespace: str,
            value: Any,
            *args,
            ttl: Optional[int] = None,
            **kwargs) -> None:
        """
        Guarda valor en caché.

        Args:
            namespace: Namespace del caché
            value: Valor a cachear
            *args: Argumentos para generar key
            ttl: TTL en segundos (None = usar default)
            **kwargs: Argumentos para generar key
        """
        key = self._make_key(namespace, *args, **kwargs)

        # Get TTL
        if ttl is None:
            ttl = self.DEFAULT_TTLS.get(namespace, self.DEFAULT_TTLS['default'])

        with self.lock:
            # Si ya existe, actualizar
            if key in self.cache:
                self.cache[key] = CacheEntry(key, value, ttl)
                self.cache.move_to_end(key)
                logger.debug(f"Cache updated: {key} (ttl: {ttl}s)")
                return

            # Si llegamos a max_size, evict LRU
            if len(self.cache) >= self.max_size:
                # Remove oldest (first in OrderedDict)
                evicted_key, evicted_entry = self.cache.popitem(last=False)
                self.evictions += 1
                logger.debug(f"Cache evicted (LRU): {evicted_key}")

            # Add new entry
            self.cache[key] = CacheEntry(key, value, ttl)
            self.cache.move_to_end(key)

            logger.debug(f"Cache set: {key} (ttl: {ttl}s)")

    def invalidate(self, namespace: str, *args, **kwargs) -> bool:
        """
        Invalida entrada específica del caché.

        Args:
            namespace: Namespace
            *args: Args para key
            **kwargs: Kwargs para key

        Returns:
            True si se eliminó algo
        """
        key = self._make_key(namespace, *args, **kwargs)

        with self.lock:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"Cache invalidated: {key}")
                return True

            return False

    def invalidate_namespace(self, namespace: str) -> int:
        """
        Invalida todas las entradas de un namespace.

        Args:
            namespace: Namespace a invalidar

        Returns:
            Número de entradas eliminadas
        """
        with self.lock:
            keys_to_remove = [
                k for k in self.cache.keys()
                if k.startswith(f"{namespace}:")
            ]

            for key in keys_to_remove:
                del self.cache[key]

            if keys_to_remove:
                logger.info(f"Cache namespace invalidated: {namespace} ({len(keys_to_remove)} entries)")

            return len(keys_to_remove)

    def clear(self) -> None:
        """Limpia todo el caché."""
        with self.lock:
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"Cache cleared ({count} entries)")

    def cleanup_expired(self) -> int:
        """
        Limpia entradas expiradas.

        Returns:
            Número de entradas eliminadas
        """
        with self.lock:
            keys_to_remove = [
                k for k, v in self.cache.items()
                if v.is_expired()
            ]

            for key in keys_to_remove:
                del self.cache[key]
                self.expirations += 1

            if keys_to_remove:
                logger.debug(f"Cleaned up {len(keys_to_remove)} expired entries")

            return len(keys_to_remove)

    def get_or_fetch(self,
                     namespace: str,
                     fetch_fn: Callable,
                     *args,
                     ttl: Optional[int] = None,
                     **kwargs) -> Any:
        """
        Get from cache o fetch si no existe.

        Args:
            namespace: Namespace
            fetch_fn: Función para fetch si cache miss
            *args: Args para key y fetch_fn
            ttl: TTL opcional
            **kwargs: Kwargs para key y fetch_fn

        Returns:
            Cached o fetched value
        """
        # Try cache first
        cached = self.get(namespace, *args, **kwargs)

        if cached is not None:
            return cached

        # Cache miss - fetch
        logger.debug(f"Cache miss - fetching: {namespace}")
        value = fetch_fn(*args, **kwargs)

        # Store in cache
        self.set(namespace, value, *args, ttl=ttl, **kwargs)

        return value

    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del caché.

        Returns:
            Dict con stats
        """
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': hit_rate,
                'evictions': self.evictions,
                'expirations': self.expirations,
                'total_requests': total_requests
            }

    def get_memory_usage(self) -> Dict:
        """
        Estima uso de memoria del caché.

        Returns:
            Dict con info de memoria
        """
        import sys

        with self.lock:
            total_size = 0

            for entry in self.cache.values():
                # Aproximado - size of value
                total_size += sys.getsizeof(entry.value)
                total_size += sys.getsizeof(entry.key)

            avg_entry_size = total_size / len(self.cache) if self.cache else 0

            return {
                'total_bytes': total_size,
                'total_mb': total_size / (1024 * 1024),
                'avg_entry_bytes': avg_entry_size,
                'num_entries': len(self.cache)
            }


# Global instance
_global_cache = None


def get_cache(max_size: int = 1000) -> CacheManager:
    """
    Obtiene instancia global de CacheManager.

    Args:
        max_size: Max size (solo para primera llamada)

    Returns:
        CacheManager instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = CacheManager(max_size=max_size)

    return _global_cache


if __name__ == "__main__":
    # Ejemplo de uso
    logging.basicConfig(level=logging.INFO)

    cache = CacheManager(max_size=100)

    # Test basic set/get
    print("\n=== Test 1: Basic Set/Get ===")
    cache.set('price', 1950.25, 'ETHUSDT')
    price = cache.get('price', 'ETHUSDT')
    print(f"Price: ${price}")

    # Test TTL
    print("\n=== Test 2: TTL Expiration ===")
    cache.set('price', 1950.50, 'ETHUSDT', ttl=1)
    print(f"Immediately: ${cache.get('price', 'ETHUSDT')}")
    time.sleep(1.5)
    print(f"After 1.5s: {cache.get('price', 'ETHUSDT')}")  # Should be None

    # Test LRU eviction
    print("\n=== Test 3: LRU Eviction ===")
    small_cache = CacheManager(max_size=3)
    small_cache.set('price', 100, 'A')
    small_cache.set('price', 200, 'B')
    small_cache.set('price', 300, 'C')
    print(f"Before eviction: A={small_cache.get('price', 'A')}, B={small_cache.get('price', 'B')}, C={small_cache.get('price', 'C')}")

    small_cache.set('price', 400, 'D')  # Should evict A (oldest)
    print(f"After adding D: A={small_cache.get('price', 'A')}, D={small_cache.get('price', 'D')}")

    # Test get_or_fetch
    print("\n=== Test 4: Get or Fetch ===")

    def fetch_price(symbol):
        print(f"  -> Fetching {symbol} from API...")
        return 1950.75

    price1 = cache.get_or_fetch('price', fetch_price, 'ETHUSDT', ttl=60)
    print(f"First call (fetch): ${price1}")

    price2 = cache.get_or_fetch('price', fetch_price, 'ETHUSDT', ttl=60)
    print(f"Second call (cache): ${price2}")

    # Stats
    print("\n=== Cache Stats ===")
    stats = cache.get_stats()
    for k, v in stats.items():
        print(f"{k}: {v}")

    print("\n=== Memory Usage ===")
    mem = cache.get_memory_usage()
    for k, v in mem.items():
        print(f"{k}: {v}")
