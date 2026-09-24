"""Redacción con Gemini: titular y entradilla de cada pieza, a partir del texto oficial.

Es una capa ENCIMA de la redacción determinista, no un sustituto. El pipeline
sigue generando sus titulares como siempre; aquí se proponen otros mejores, se
verifican contra la fuente y solo se publican si pasan. Si Gemini no responde,
se agota la cuota o devuelve algo que no se sostiene, la edición sale igual con
lo de siempre. Nunca se queda un día sin publicar por culpa del modelo.

Por qué así, y no una llamada por noticia:

  El plan gratuito de Gemini corta antes por número de peticiones al día que
  por volumen de texto. Así que se hace UNA petición por pase con todas las
  piezas pendientes juntas, y lo ya redactado se guarda en state/redaccion.json
  para que los pases siguientes del mismo día (la edición se regenera tres o
  cuatro veces) no gasten nada. El archivo histórico se va poniendo al día poco
  a poco, siempre por detrás de lo de hoy.

Y por qué tanta verificación:

  La promesa de la web es la fidelidad. Un titular que atribuye a una norma una
  cifra o una fecha que no dice es peor que un titular feo. Toda cifra, año y
  mes que aparezca en lo que devuelve el modelo tiene que estar en el texto
  oficial; si no, la pieza se descarta y se queda la versión determinista.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import time

import requests

ESTADO = pathlib.Path(__file__).parent / "state" / "redaccion.json"
ESQUEMA = 1

API = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

# El modelo ligero basta para reescribir un titular a partir de un texto que se
# le entrega: no hay que razonar, hay que entender y resumir. Si Google retira
# o renombra uno, se prueba el siguiente: los nombres cambian cada pocos meses
# y eso no puede tumbar la edición.
MODELOS = [m for m in [os.environ.get("GEMINI_MODELO", "").strip()] if m] + [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]

# Límites propios, muy por debajo de los del plan gratuito: son un cinturón de
# seguridad contra un bucle o un reintento desbocado, no el techo real.
MAX_PETICIONES_DIA = 6
MAX_PIEZAS_POR_PETICION = 40
MAX_FUENTE = 1400           # caracteres de texto oficial por pieza

INSTRUCCIONES = """Eres el redactor jefe de «La Tercera Cámara», una publicación que traduce el Boletín Oficial del Estado y la actividad de las Cortes a lenguaje llano, con rigor absoluto.

Recibirás una lista de piezas. Para cada una escribes:

TITULAR (máximo 85 caracteres; cuenta los caracteres antes de responder):
- Dice QUIÉN hace QUÉ y a QUIÉN o DÓNDE afecta. Nombra el sujeto real y el objeto concreto: el municipio, el colectivo, la institución, la cuantía.
- El BOE suele esconder lo importante al final de la frase, detrás de la maquinaria administrativa. Sácalo delante.
- Si hay un importe, un plazo o una fecha que el lector necesita, inclúyelo si cabe.
- Frase normal en mayúsculas y minúsculas, sin punto final, sin signos de exclamación ni interrogación.
- Sin adjetivos valorativos, sin ironía, sin clickbait, sin opinión.

ENTRADILLA (una o dos frases, máximo 240 caracteres):
- Qué cambia en la práctica y para quién. Sin repetir el titular.

REGLAS INQUEBRANTABLES:
- Solo puedes usar hechos que estén en el texto de la pieza. No añadas nada que no esté.
- No inventes cifras, fechas, nombres, lugares ni organismos.
- No escribas ninguna cifra ni ningún año que no figure en el texto.
- Si la pieza es un trámite menor (una corrección de errores, un cambio de nombre, un nombramiento rutinario), dilo con sobriedad: no lo infles.
- Devuelve exactamente una entrada por pieza, con el mismo "id" que recibiste."""

ESQUEMA_SALIDA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "titular": {"type": "STRING"},
            "entradilla": {"type": "STRING"},
        },
        "required": ["id", "titular", "entradilla"],
    },
}

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "setiembre", "octubre", "noviembre", "diciembre")


def _log(msg: str) -> None:
    print(f"[redaccion] {msg}", flush=True)


# --------------------------------------------------------------------- estado

def _cargar() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
        if e.get("esquema") == ESQUEMA:
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"esquema": ESQUEMA, "piezas": {}, "uso": {}}


def _guardar(e: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def _huella(texto: str) -> str:
    """Si la fuente cambia (una corrección, el Senado añadido a un día ya
    publicado), la redacción anterior deja de valer y hay que rehacerla."""
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------- materiales

def _fuente_boe(s: dict) -> str:
    cuerpo = " ".join(p for p in (s.get("body") or []) if isinstance(p, str))
    partes = [s.get("titulo_oficial") or "", cuerpo]
    if s.get("dept"):
        partes.insert(0, f"Organismo: {s['dept']}.")
    return " ".join(" ".join(partes).split())[:MAX_FUENTE]


def _fuente_cortes(f: dict) -> str:
    cuerpo = " ".join(p for p in (f.get("body") or []) if isinstance(p, str))
    partes = [f"Cámara: {f.get('chamber', '')}. Tipo: {f.get('type', '')}.",
              f.get("headline") or "", f.get("standfirst") or "", cuerpo]
    return " ".join(" ".join(partes).split())[:MAX_FUENTE]


def _piezas(dias: list[dict]):
    """Todas las piezas publicables, de la más reciente a la más antigua, con su
    identificador estable, su texto fuente y el objeto a modificar."""
    for day in sorted(dias, key=lambda d: d["id"], reverse=True):
        for s in (day.get("boe", {}) or {}).get("stories") or []:
            ref = s.get("ref")
            if ref and s.get("titulo_oficial"):
                yield ref, _fuente_boe(s), s
        for f in (day.get("cortes", {}) or {}).get("feed") or []:
            url = (f.get("source") or {}).get("url") or ""
            ident = "C-" + _huella(url + (f.get("headline") or ""))
            yield ident, _fuente_cortes(f), f


# --------------------------------------------------------------- verificación

def _numeros(texto: str) -> set[str]:
    """Cifras normalizadas: «60.000» y «60000» son la misma."""
    return {re.sub(r"[.,]", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", texto or "")}


def verificar(titular: str, entradilla: str, fuente: str) -> str:
    """Devuelve "" si la redacción se sostiene contra la fuente, o el motivo."""
    t = " ".join((titular or "").split()).strip(" .")
    e = " ".join((entradilla or "").split())
    if not (20 <= len(t) <= 140):
        return f"titular de {len(t)} caracteres"
    if len(e) > 320:
        return "entradilla demasiado larga"
    if re.search(r"[!?¡¿]", t):
        return "titular con exclamación o pregunta"

    fuente_nums = _numeros(fuente)
    for n in _numeros(t + " " + e):
        # Una cifra de un solo dígito puede venir de «dos» escrito en letra en
        # la fuente; no es donde se inventa. Las de dos o más sí se comprueban.
        if len(n) >= 2 and n not in fuente_nums:
            return f"cifra «{n}» que no está en el texto oficial"

    fb = fuente.lower()
    for mes in MESES:
        if re.search(rf"\b{mes}\b", (t + " " + e).lower()) and mes not in fb:
            return f"mes «{mes}» que no está en el texto oficial"
    return ""


# ---------------------------------------------------------------------- Gemini

def _pedir(clave: str, lote: list[dict]) -> tuple[list[dict] | None, str]:
    """Una sola llamada con todo el lote. Devuelve (resultados, modelo usado)."""
    cuerpo = {
        "systemInstruction": {"parts": [{"text": INSTRUCCIONES}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(
            [{"id": p["id"], "texto": p["fuente"]} for p in lote], ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": ESQUEMA_SALIDA,
        },
    }
    for modelo in MODELOS:
        try:
            r = requests.post(API.format(modelo=modelo), json=cuerpo, timeout=120,
                              headers={"x-goog-api-key": clave,
                                       "Content-Type": "application/json"})
        except Exception as exc:                              # noqa: BLE001
            _log(f"{modelo}: sin respuesta ({exc})")
            return None, modelo
        if r.status_code == 404:
            _log(f"{modelo}: no existe o no está disponible, pruebo el siguiente")
            continue
        if r.status_code == 429:
            _log(f"{modelo}: cuota agotada por hoy; se publica con la redacción de siempre")
            return None, modelo
        if r.status_code != 200:
            _log(f"{modelo}: HTTP {r.status_code} — {r.text[:300]}")
            return None, modelo
        try:
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            datos = json.loads(texto)
            return (datos if isinstance(datos, list) else None), modelo
        except Exception as exc:                              # noqa: BLE001
            _log(f"{modelo}: respuesta ilegible ({exc})")
            return None, modelo
    return None, ""


# ------------------------------------------------------------------ interfaz

def aplicar(dias: list[dict], validar_titular=None, recortar=None) -> dict:
    """Pone la mejor redacción disponible en cada pieza, en memoria.

    Los data/*.json no se tocan: siguen siendo la versión determinista y la
    fuente de verdad. Esto es una capa que se puede quitar en cualquier momento
    borrando state/redaccion.json.

    `validar_titular` es la verja de build.py (titular_valido); se pasa desde
    fuera para no crear una dependencia circular entre módulos."""
    estado = _cargar()
    piezas = estado["piezas"]
    hoy = dt.date.today().isoformat()
    uso = estado["uso"].get(hoy, 0)

    todas = list(_piezas(dias))
    def _pendiente(i, fte):
        c = piezas.get(i, {})
        if c.get("huella") != _huella(fte):
            return True
        return bool(c.get("descartado")) and c.get("intentos", 1) < 2

    pendientes = [{"id": i, "fuente": fte, "huella": _huella(fte)}
                  for i, fte, _obj in todas if _pendiente(i, fte)]

    clave = os.environ.get("GEMINI_API_KEY", "").strip()
    resumen = {"pendientes": len(pendientes), "redactadas": 0,
               "descartadas": 0, "peticiones": 0}

    if pendientes and clave and uso < MAX_PETICIONES_DIA:
        lote = pendientes[:MAX_PIEZAS_POR_PETICION]
        t0 = time.time()
        resultados, modelo = _pedir(clave, lote)
        estado["uso"] = {hoy: uso + 1}          # solo se guarda el día en curso
        resumen["peticiones"] = 1
        por_id = {p["id"]: p for p in lote}
        for r in resultados or []:
            p = por_id.get(str(r.get("id", "")))
            if not p:
                continue
            titular = " ".join((r.get("titular") or "").split()).strip(" .")
            entradilla = " ".join((r.get("entradilla") or "").split())
            # Si se pasa de largo, se recorta por sintagma (la misma verja que la
            # redacción determinista), no se tira: el modelo cuenta mal los
            # caracteres, pero lo que dice suele ser bueno.
            if recortar and len(titular) > 105:
                titular = recortar(titular, 105)
            motivo = verificar(titular, entradilla, p["fuente"])
            if not motivo and validar_titular:
                motivo = validar_titular(titular.upper())
            if motivo:
                resumen["descartadas"] += 1
                _log(f"descartado {p['id']}: {motivo} — «{titular}»")
                # Se apunta igual, sin texto: así no se vuelve a pedir la misma
                # pieza en cada pase y la cuota no se va en reintentos inútiles.
                previo = piezas.get(p["id"], {})
                intentos = previo.get("intentos", 0) + 1 if previo.get("huella") == p["huella"] else 1
                piezas[p["id"]] = {"huella": p["huella"], "descartado": motivo,
                                   "intentos": intentos}
                continue
            piezas[p["id"]] = {"huella": p["huella"], "titular": titular,
                               "entradilla": entradilla, "modelo": modelo, "fecha": hoy}
            resumen["redactadas"] += 1
        _log(f"{resumen['redactadas']} redactadas, {resumen['descartadas']} descartadas, "
             f"{len(pendientes) - len(lote)} en cola — {modelo or 'sin modelo'}, "
             f"{time.time() - t0:.1f} s")
        _guardar(estado)
    elif pendientes and not clave:
        _log("sin GEMINI_API_KEY: se publica con la redacción determinista")
    elif pendientes:
        _log(f"tope propio de {MAX_PETICIONES_DIA} peticiones diarias alcanzado; sigue mañana")

    # Aplicar lo que haya en caché, sea de hoy o de pases anteriores.
    aplicadas = 0
    for i, fte, obj in todas:
        c = piezas.get(i)
        if c and c.get("titular") and c.get("huella") == _huella(fte):
            obj.setdefault("headline_determinista", obj.get("headline", ""))
            obj["headline"] = c["titular"].upper()
            if c.get("entradilla"):
                obj["standfirst"] = c["entradilla"]
            obj["redaccion_ia"] = True
            aplicadas += 1
    resumen["aplicadas"] = aplicadas
    return resumen
