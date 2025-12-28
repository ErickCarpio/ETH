"""
Subprocess Runner
Ejecuta scripts Python en background y captura output
"""

import subprocess
import threading
import queue
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SubprocessRunner:
    """Ejecuta scripts Python en subprocess con streaming de logs"""

    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.is_running = False

    def run(self, script_path, args=None, cwd=None):
        """
        Ejecuta script Python

        Args:
            script_path: Path al script .py
            args: Lista de argumentos (default: [])
            cwd: Working directory (default: directorio del script)
        """
        if self.is_running:
            raise RuntimeError("Ya hay un proceso corriendo")

        if args is None:
            args = []

        if cwd is None:
            cwd = Path(script_path).parent

        cmd = ['python', script_path] + args

        logger.info(f"Ejecutando: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(cwd)
        )

        self.is_running = True

        # Thread para leer output
        thread = threading.Thread(target=self._read_output, daemon=True)
        thread.start()

    def _read_output(self):
        """Lee output del proceso y lo pone en queue"""
        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.output_queue.put(line.rstrip())
        except Exception as e:
            logger.error(f"Error leyendo output: {e}")
        finally:
            self.process.stdout.close()
            self.process.wait()
            self.is_running = False

    def get_output(self, timeout=0.1):
        """
        Obtiene líneas de output disponibles

        Returns:
            List[str]: Líneas de output (puede estar vacía)
        """
        lines = []
        try:
            while True:
                line = self.output_queue.get(timeout=timeout)
                lines.append(line)
        except queue.Empty:
            pass
        return lines

    def is_alive(self):
        """Verifica si el proceso sigue corriendo"""
        return self.is_running

    def get_return_code(self):
        """Obtiene return code del proceso (None si aún corre)"""
        if self.process:
            return self.process.poll()
        return None

    def stop(self):
        """Detiene el proceso"""
        if self.process and self.is_running:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.is_running = False
