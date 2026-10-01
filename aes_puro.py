"""Descifrado AES en Python puro, para que pypdf lea los PDF cifrados.

Por qué existe: las contestaciones escritas del Congreso
(/l15p/e12/e_…_n_000.pdf) van cifradas con AES-128 (/V 4, /CFM /AESV2) y
contraseña de usuario vacía. Se abren sin contraseña, pero para descifrar el
contenido pypdf necesita `cryptography` o `pycryptodome`. Sin ninguna de las
dos, lanza «cryptography>=3.1 is required for AES algorithm»: comprobado el
30 de septiembre de 2026, fallaron así 40 de 40 PDF en Actions. Como la regla
del proyecto es no añadir dependencias, aquí está el descifrado: el algoritmo
estándar (FIPS-197) con tablas precalculadas y solo en el sentido de
descifrar. Una contestación de ~200 KB tarda menos de un segundo.

activar() solo sustituye el proveedor de respaldo de pypdf, el que lanza el
error. Si `cryptography` o `pycryptodome` están instalados, no toca nada.
Las pruebas (tests/test_aes_puro.py) lo comparan con los vectores de FIPS-197
y de NIST SP 800-38A, y leen un PDF cifrado igual que los del Congreso con
`cryptography` bloqueado. Probado con pypdf 3.17 y 6.19 (pypdf 6 pasa
`strict=` a decrypt: se acepta y se ignora).
"""

from __future__ import annotations

# --- tablas -----------------------------------------------------------------

def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


def _mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _sbox() -> list:
    # Inverso multiplicativo en GF(2^8) y transformación afín.
    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if _mul(a, b) == 1:
                inv[a] = b
                break
    s = []
    for a in range(256):
        x = inv[a]
        y = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            y ^= x
        s.append(y ^ 0x63)
    return s


SBOX = _sbox()
INV_SBOX = [0] * 256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i

# Td0[x] = (0e·s, 09·s, 0d·s, 0b·s) con s = INV_SBOX[x], empaquetado en 32 bits.
TD0 = [(_mul(s, 14) << 24) | (_mul(s, 9) << 16) | (_mul(s, 13) << 8) | _mul(s, 11)
       for s in INV_SBOX]
TD1 = [((t >> 8) | (t << 24)) & 0xFFFFFFFF for t in TD0]
TD2 = [((t >> 16) | (t << 16)) & 0xFFFFFFFF for t in TD0]
TD3 = [((t >> 24) | (t << 8)) & 0xFFFFFFFF for t in TD0]
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _inv_mix(w: int) -> int:
    """InvMixColumns de una palabra (para la clave de descifrado)."""
    b = [(w >> 24) & 0xFF, (w >> 16) & 0xFF, (w >> 8) & 0xFF, w & 0xFF]
    return (TD0[SBOX[b[0]]] ^ TD1[SBOX[b[1]]] ^ TD2[SBOX[b[2]]] ^ TD3[SBOX[b[3]]])


# --- clave ------------------------------------------------------------------

def _expandir(key: bytes) -> tuple[list, int]:
    nk = len(key) // 4
    if len(key) not in (16, 24, 32):
        raise ValueError("clave AES de 16, 24 o 32 bytes")
    nr = nk + 6
    w = [int.from_bytes(key[4 * i:4 * i + 4], "big") for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1]
        if i % nk == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = ((SBOX[t >> 24] << 24) | (SBOX[(t >> 16) & 0xFF] << 16) |
                 (SBOX[(t >> 8) & 0xFF] << 8) | SBOX[t & 0xFF])
            t ^= RCON[i // nk - 1] << 24
        elif nk > 6 and i % nk == 4:
            t = ((SBOX[t >> 24] << 24) | (SBOX[(t >> 16) & 0xFF] << 16) |
                 (SBOX[(t >> 8) & 0xFF] << 8) | SBOX[t & 0xFF])
        w.append(w[i - nk] ^ t)
    # Clave de descifrado equivalente (FIPS-197 §5.3.5): rondas al revés y
    # InvMixColumns en las intermedias.
    dk = []
    for r in range(nr, -1, -1):
        ronda = w[4 * r:4 * r + 4]
        dk.extend(ronda if r in (0, nr) else [_inv_mix(x) for x in ronda])
    return dk, nr


# --- bloque ------------------------------------------------------------------

def _descifrar_bloque(dk: list, nr: int, bloque: bytes) -> bytes:
    s0 = int.from_bytes(bloque[0:4], "big") ^ dk[0]
    s1 = int.from_bytes(bloque[4:8], "big") ^ dk[1]
    s2 = int.from_bytes(bloque[8:12], "big") ^ dk[2]
    s3 = int.from_bytes(bloque[12:16], "big") ^ dk[3]
    k = 4
    for _ in range(nr - 1):
        t0 = TD0[s0 >> 24] ^ TD1[(s3 >> 16) & 0xFF] ^ TD2[(s2 >> 8) & 0xFF] ^ TD3[s1 & 0xFF] ^ dk[k]
        t1 = TD0[s1 >> 24] ^ TD1[(s0 >> 16) & 0xFF] ^ TD2[(s3 >> 8) & 0xFF] ^ TD3[s2 & 0xFF] ^ dk[k + 1]
        t2 = TD0[s2 >> 24] ^ TD1[(s1 >> 16) & 0xFF] ^ TD2[(s0 >> 8) & 0xFF] ^ TD3[s3 & 0xFF] ^ dk[k + 2]
        t3 = TD0[s3 >> 24] ^ TD1[(s2 >> 16) & 0xFF] ^ TD2[(s1 >> 8) & 0xFF] ^ TD3[s0 & 0xFF] ^ dk[k + 3]
        s0, s1, s2, s3 = t0, t1, t2, t3
        k += 4
    ib = INV_SBOX
    out = bytearray(16)
    for j, (a, b, c, d) in enumerate(((s0, s3, s2, s1), (s1, s0, s3, s2),
                                      (s2, s1, s0, s3), (s3, s2, s1, s0))):
        v = ((ib[a >> 24] << 24) | (ib[(b >> 16) & 0xFF] << 16) |
             (ib[(c >> 8) & 0xFF] << 8) | ib[d & 0xFF]) ^ dk[k + j]
        out[4 * j:4 * j + 4] = v.to_bytes(4, "big")
    return bytes(out)


def ecb_descifrar(key: bytes, data: bytes, *args, **kwargs) -> bytes:
    dk, nr = _expandir(key)
    return b"".join(_descifrar_bloque(dk, nr, data[i:i + 16]) for i in range(0, len(data), 16))


def cbc_descifrar(key: bytes, iv: bytes, data: bytes, *args, **kwargs) -> bytes:
    """Sin quitar el relleno: eso lo hace quien llama, como en pypdf."""
    dk, nr = _expandir(key)
    salida = bytearray()
    previo = iv
    for i in range(0, len(data) - len(data) % 16, 16):
        bloque = data[i:i + 16]
        claro = _descifrar_bloque(dk, nr, bloque)
        salida += bytes(x ^ y for x, y in zip(claro, previo))
        previo = bloque
    return bytes(salida)


class CryptAES:
    """Misma interfaz que pypdf._crypt_providers.CryptAES, solo descifrado."""

    def __init__(self, key: bytes) -> None:
        self.key = key

    def encrypt(self, data: bytes, *args, **kwargs) -> bytes:  # pragma: no cover
        raise NotImplementedError("aes_puro solo descifra")

    def decrypt(self, data: bytes, *args, **kwargs) -> bytes:
        # pypdf 6 pasa además strict=…; se acepta y se ignora.
        iv, data = data[:16], data[16:]
        if not data:
            return data
        if len(data) % 16:
            n = 16 - len(data) % 16
            data += bytes([n]) * n
        d = cbc_descifrar(self.key, iv, data)
        n = d[-1] if d else 0
        return d[:-n] if 0 < n <= 16 else d


def activar() -> bool:
    """Sustituye el AES de respaldo de pypdf, que solo lanza un error, por el
    de este módulo. Devuelve True si lo ha sustituido."""
    try:
        import pypdf._crypt_providers as cp
        import pypdf._encryption as enc
    except Exception:                                          # noqa: BLE001
        return False
    if cp.crypt_provider[0] != "local_crypt_fallback":
        return False
    enc.CryptAES = CryptAES
    enc.aes_cbc_decrypt = cbc_descifrar
    enc.aes_ecb_decrypt = ecb_descifrar
    return True
