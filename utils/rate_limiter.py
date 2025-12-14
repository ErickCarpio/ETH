"""
Rate Limiter Universal - Gestión de Cuotas de API
Evita baneos de IP controlando la frecuencia de peticiones (Token Bucket Algorithm).
"""

import asyncio
import time
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RateLimiter")

class RateLimiter:
    def __init__(self):
        # Configuración de límites: (peticiones, segundos)
        self.limits = {
            "binance_rest": (1200, 60),   # 1200 req por minuto
            "deribit": (20, 10),          # 20 req cada 10s
            "coinglass": (10, 3600),      # Aprox 10 por hora (muy estricto)
            "github": (60, 3600),         # 60 por hora
            "default": (1, 1)             # 1 por segundo por defecto
        }
        
        # Estado de los buckets: {api_name: tokens_actuales}
        self.tokens: Dict[str, float] = {}
        self.last_update: Dict[str, float] = {}
        
        # Inicializar buckets llenos
        for api, (capacity, _) in self.limits.items():
            self.tokens[api] = capacity
            self.last_update[api] = time.time()

    async def acquire(self, api_name: str, weight: int = 1):
        """
        Espera hasta tener permiso para hacer la petición.
        :param api_name: Nombre de la API ('binance_rest', 'deribit', etc.)
        :param weight: Peso de la petición (algunas valen por 5 o 10)
        """
        if api_name not in self.limits:
            api_name = "default"
            
        capacity, window = self.limits[api_name]
        fill_rate = capacity / window
        
        while True:
            now = time.time()
            
            # 1. Rellenar tokens basado en el tiempo que pasó
            elapsed = now - self.last_update.get(api_name, now)
            self.last_update[api_name] = now
            
            new_tokens = elapsed * fill_rate
            self.tokens[api_name] = min(capacity, self.tokens.get(api_name, 0) + new_tokens)
            
            # 2. Verificar si hay suficientes tokens
            if self.tokens[api_name] >= weight:
                self.tokens[api_name] -= weight
                # logger.debug(f"🟢 Token adquirido para {api_name}. Restantes: {self.tokens[api_name]:.2f}")
                return # ¡Permiso concedido!
            
            # 3. Si no hay, esperar lo necesario
            needed = weight - self.tokens[api_name]
            wait_time = needed / fill_rate
            
            if wait_time > 1:
                logger.warning(f"⏳ Rate Limit en {api_name}: Esperando {wait_time:.2f}s...")
            
            await asyncio.sleep(wait_time)

# Instancia global (Singleton) para usar en todo el proyecto
global_rate_limiter = RateLimiter()

# --- PRUEBA UNITARIA ---
if __name__ == "__main__":
    async def test():
        limiter = RateLimiter()
        
        print("⚡ Iniciando prueba de estrés para 'Deribit' (Límite: 20 req/10s)...")
        start = time.time()
        
        # Intentar hacer 25 peticiones rápidas
        for i in range(25):
            await limiter.acquire("deribit")
            print(f"✅ Req #{i+1} enviada a los {time.time() - start:.2f}s")
            
        print("🏁 Prueba finalizada.")

    asyncio.run(test())