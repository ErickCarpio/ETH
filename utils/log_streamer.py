"""
Log Streamer
Lee logs de archivos y streams en tiempo real
"""

import time
from pathlib import Path
from typing import Generator


class LogStreamer:
    """Lee logs de archivo con tail -f style"""

    def __init__(self, log_file):
        self.log_file = Path(log_file)
        self.position = 0

    def stream(self, max_lines=100) -> Generator[str, None, None]:
        """
        Stream de nuevas líneas del log

        Args:
            max_lines: Máximo de líneas a retornar por iteración

        Yields:
            str: Líneas nuevas del log
        """
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Ir a última posición conocida
                f.seek(self.position)

                # Leer nuevas líneas
                lines = []
                for _ in range(max_lines):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip())

                # Actualizar posición
                self.position = f.tell()

                # Yield líneas
                for line in lines:
                    yield line

        except Exception as e:
            yield f"Error leyendo log: {e}"

    def read_all(self, max_lines=1000):
        """
        Lee todo el log (últimas N líneas)

        Args:
            max_lines: Máximo de líneas a retornar

        Returns:
            List[str]: Líneas del log
        """
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                return [l.rstrip() for l in lines[-max_lines:]]
        except Exception:
            return []

    def reset(self):
        """Resetea posición para leer desde el inicio"""
        self.position = 0
