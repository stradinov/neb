"""Toda prueba que fija un HOME temporal importa _entorno (8.0.0).

Con NEB_DATA declarada en el entorno del dev, un HOME temporal ya no aísla la carpeta de datos: la prueba abriría
y escribiría la base real (PD-981). _entorno quita NEB_DATA al importarse; en la suite completa basta con que la
importe un módulo cualquiera, así que el hueco solo se ve al correr un archivo por su cuenta. Esta prueba lo
atrapa sin depender del orden: revisa el texto de cada `test_*.py` que nombra USERPROFILE.

Framework: unittest (stdlib). Solo lee los archivos de esta carpeta.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT_RE = re.compile(r"^import _entorno\b", re.M)


class TestAislamiento(unittest.TestCase):

    def test_critico_toda_prueba_con_home_temporal_importa_entorno(self):
        missing = []
        for name in sorted(os.listdir(HERE)):
            if not (name.startswith("test_") and name.endswith(".py")) or name == os.path.basename(__file__):
                continue
            with open(os.path.join(HERE, name), encoding="utf-8") as fh:
                text = fh.read()
            if "USERPROFILE" in text and not IMPORT_RE.search(text):
                missing.append(name)
        self.assertEqual(missing, [], "importan HOME/USERPROFILE temporales sin `import _entorno`")


if __name__ == "__main__":
    unittest.main()
