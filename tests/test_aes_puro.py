"""Pruebas de aes_puro.py con vectores oficiales, sin red ni dependencias.

`python -m unittest tests.test_aes_puro`. FIPS-197 apéndice C (AES-128 y
AES-256, un bloque) y NIST SP 800-38A F.2.2 (CBC-AES128, cuatro bloques).
"""
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import aes_puro as a  # noqa: E402

H = bytes.fromhex


class Vectores(unittest.TestCase):
    def test_fips197_aes128(self):
        self.assertEqual(a.ecb_descifrar(H("000102030405060708090a0b0c0d0e0f"),
                                         H("69c4e0d86a7b0430d8cdb78070b4c55a")),
                         H("00112233445566778899aabbccddeeff"))

    def test_fips197_aes256(self):
        clave = H("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
        self.assertEqual(a.ecb_descifrar(clave, H("8ea2b7ca516745bfeafc49904b496089")),
                         H("00112233445566778899aabbccddeeff"))

    def test_sp800_38a_cbc(self):
        clave = H("2b7e151628aed2a6abf7158809cf4f3c")
        iv = H("000102030405060708090a0b0c0d0e0f")
        cifrado = H("7649abac8119b246cee98e9b12e9197d" "5086cb9b507219ee95db113a917678b2"
                    "73bed6b8e3c1743b7116e69e22229516" "3ff1caa1681fac09120eca307586e1a7")
        claro = H("6bc1bee22e409f96e93d7e117393172a" "ae2d8a571e03ac9c9eb76fac45af8e51"
                  "30c81c46a35ce411e5fbc1191a0a52ef" "f69f2445df4f9b17ad2b417be66c3710")
        self.assertEqual(a.cbc_descifrar(clave, iv, cifrado), claro)

    def test_crypt_aes_quita_el_relleno(self):
        # Como lo usa pypdf: el IV va delante y el último byte dice cuánto
        # relleno quitar. El último bloque en claro del vector acaba en 0x10:
        # se quitan 16 bytes.
        clave = H("2b7e151628aed2a6abf7158809cf4f3c")
        iv = H("000102030405060708090a0b0c0d0e0f")
        cifrado = H("7649abac8119b246cee98e9b12e9197d" "5086cb9b507219ee95db113a917678b2"
                    "73bed6b8e3c1743b7116e69e22229516" "3ff1caa1681fac09120eca307586e1a7")
        claro = a.cbc_descifrar(clave, iv, cifrado)
        self.assertEqual(claro[-1], 0x10)
        self.assertEqual(a.CryptAES(clave).decrypt(iv + cifrado), claro[:-16])


RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Lee el PDF de prueba (AES-128, contraseña de usuario vacía, como las
# contestaciones del Congreso) en un proceso donde `cryptography` y
# `pycryptodome` no se pueden importar: así se comporta pypdf en Actions.
LEER = f"""
import io, sys
for m in ("cryptography", "Crypto", "Cryptodome"):
    sys.modules[m] = None
sys.path.insert(0, {str(RAIZ)!r})
from pypdf import PdfReader
import aes_puro, respuestas
datos = open({str(RAIZ / "tests" / "contestacion_cifrada_aes128.pdf")!r}, "rb").read()
try:
    PdfReader(io.BytesIO(datos)).pages[0].extract_text()
    print("SIN_PARCHE_LEE")
except Exception:
    print("SIN_PARCHE_FALLA")
print("ACTIVADO" if aes_puro.activar() else "NO_ACTIVADO")
texto = PdfReader(io.BytesIO(datos)).pages[0].extract_text()
print(respuestas.extraer_escrita(texto)["cita"])
"""


class PdfCifrado(unittest.TestCase):
    def test_pypdf_sin_cryptography(self):
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", LEER],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        lineas = r.stdout.splitlines()
        self.assertEqual(lineas[:2], ["SIN_PARCHE_FALLA", "ACTIVADO"])
        self.assertTrue(lineas[2].startswith("Se informa, en relación con la pregunta planteada"))


if __name__ == "__main__":
    unittest.main()
