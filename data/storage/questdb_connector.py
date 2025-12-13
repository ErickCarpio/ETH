"""
QuestDB Connector - Ingesta de Alta Frecuencia (ILP)
Utiliza el protocolo Influx Line para enviar métricas de microestructura
sin bloquear el hilo principal del bot.
"""

import logging
import sys
import socket
from datetime import datetime
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuestDB")

class QuestDBConnector:
    def __init__(self, host='localhost', port=9009):
        self.host = host
        self.port = port
        self.sock = None
        self.is_connected = False
        
    def connect(self):
        """Abre un socket TCP persistente para máxima velocidad"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.is_connected = True
            logger.info(f"✅ Conectado a QuestDB ILP en {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ Error conectando a QuestDB: {e}")
            self.is_connected = False

    def insert_obi_metric(self, symbol: str, bid_vol: float, ask_vol: float, obi: float, mid_price: float):
        """
        Envía una métrica OBI usando ILP.
        Formato: table_name,tags fields timestamp
        """
        if not self.is_connected:
            self.connect()
            if not self.is_connected: return

        try:
            # Protocolo ILP:
            # orderbook_metrics,symbol=ETHUSDT bid_vol=12.5,ask_vol=10.2,obi=0.15,price=3000.0 timestamp_ns
            
            timestamp_ns = time.time_ns()
            
            # Construcción manual del string para máxima eficiencia (evita librerías pesadas)
            ilp_line = (
                f"orderbook_metrics,symbol={symbol} "
                f"bid_vol={bid_vol},ask_vol={ask_vol},obi={obi},mid_price={mid_price} "
                f"{timestamp_ns}\n"
            )
            
            self.sock.sendall(ilp_line.encode('utf-8'))
            
        except BrokenPipeError:
            logger.warning("⚠️ Conexión rota con QuestDB. Reintentando...")
            self.connect()
        except Exception as e:
            logger.error(f"Error enviando métrica: {e}")

    def close(self):
        if self.sock:
            self.sock.close()
            self.is_connected = False

# Prueba unitaria
if __name__ == "__main__":
    db = QuestDBConnector()
    db.connect()
    # Simular envío de datos
    for i in range(5):
        db.insert_obi_metric("ETHUSDT", 100+i, 90+i, 0.5, 3000.0+i)
        time.sleep(0.1)
    print("Datos de prueba enviados.")
    db.close()