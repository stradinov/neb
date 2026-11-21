"""Lo carga Python al arrancar un subproceso de prueba (PYTHONPATH lo pone tests/_sin_registro.py): las
pruebas nunca leen ni escriben el registro real de Windows."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import _sin_registro  # noqa: E402,F401
