"""
QuestDB Connector - Universal ILP Ingester
Permite guardar diccionarios arbitrarios de features de alta frecuencia.
"""
import logging
import socket
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
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.is_connected = True
            logger.info(f"✅ Conectado a QuestDB ILP en {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ Error conectando a QuestDB: {e}")
            self.is_connected = False

    def insert(self, table_name: str, symbol: str, data: dict):
        """
        Inserta un diccionario de datos en QuestDB.
        Ej: insert('market_features', 'ETHUSDT', {'vpin': 0.5, 'obi': 0.8})
        """
        if not self.is_connected:
            self.connect()
            if not self.is_connected: return

        try:
            # Protocolo ILP: table,tags fields timestamp
            timestamp_ns = time.time_ns()
            
            # Convertir diccionario a string de campos (field1=val1,field2=val2...)
            fields_parts = []
            for key, value in data.items():
                # QuestDB necesita floats o ints, no strings en los campos numéricos
                if isinstance(value, float):
                    fields_parts.append(f"{key}={value:.6f}")
                elif isinstance(value, int):
                    fields_parts.append(f"{key}={value}i") # 'i' indica entero
                else:
                    fields_parts.append(f"{key}=\"{str(value)}\"")

            fields_str = ",".join(fields_parts)
            
            # Línea final
            ilp_line = f"{table_name},symbol={symbol} {fields_str} {timestamp_ns}\n"
            
            self.sock.sendall(ilp_line.encode('utf-8'))
            
        except BrokenPipeError:
            logger.warning("⚠️ Conexión rota. Reintentando...")
            self.connect()
        except Exception as e:
            logger.error(f"Error insertando en DB: {e}")

    def close(self):
        if self.sock:
            self.sock.close()