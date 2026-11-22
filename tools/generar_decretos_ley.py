"""Genera curated/decretos_ley.json, la copia fija del panel «Decretos-ley»
(decretos_ley.py).

Se ejecuta a mano y el JSON se commitea: el build no lo regenera ni usa la red.

    python tools/generar_decretos_ley.py

1. Los decretos-leyes de 2026 que publica el BOE salen de las ediciones del
   sitio (data/*.json: título oficial, identificador y número y fecha del BOE).
2. Las fichas de expediente del Congreso (serie 130, XV Legislatura) se leen
   una a una desde la del primer RDL de curated/votos_rdl.json hasta que
   FIN_HUECOS números seguidos no tienen ficha. De cada una: el número del RDL,
   el título, el BOE («BOE Núm: N de dd/mm/aaaa»), el estado tal cual (campo
   «Resultado tramitación» o, si no está, «Situación actual») y el órgano que
   lo tramita («Pleno» o «Diputación Permanente»).
3. Para cada RDL, el BOE: su identificador (de las ediciones del sitio o, si
   no está, del sumario oficial del día de su BOE) y, en las «referencias
   posteriores» de su XML, la resolución del Congreso que publica el acuerdo
   de convalidación o derogación. De esa resolución se guardan el
   identificador, el BOE (número y fecha) y la frase literal del acuerdo
   («… acordó convalidar el Real Decreto-ley N/2026»).
   Así el estado no depende de que el buscador de iniciativas del Congreso
   muestre ya la ficha: el 22-11-2026 no mostraba las de 130/000064 a 067
   (RDL 33 a 36), que sí constan en el acta de la Diputación Permanente del
   18-11-2026 y en el BOE núm. 289, de 20-11-2026.
4. Entran los RDL de 2026 desde el primero de votos_rdl. Lo que no trae
   ninguna fuente queda vacío: no se deduce.
5. Misma entrada, mismo fichero: claves ordenadas y sin fecha de generación.
"""
from __future__ import annotations

import glob
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import decretos_ley as dl  # noqa: E402
import votos_rdl as vr  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; TerceraCamara/1.0; +https://terceracamara.es)"}
FIN_HUECOS = 8


def _get(url: str, intentos: int = 3) -> str:
    req = urllib.request.Request(url, headers=UA)
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except OSError:
            if i == intentos - 1:
                raise
            time.sleep(5)
    return ""


def ficha(expte: str) -> dict | None:
    """Lo que trae la ficha oficial del expediente, o None si no hay ficha."""
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", _get(dl.EXPTE_URL.format(expte=expte)))).split())
    m = re.search(r"Real Decreto-Ley\. (Real Decreto-ley \d+/\d{4}, .+?) \(" + re.escape(expte) + r"\)", t)
    if not m:
        return None
    titulo = m.group(1).strip()
    num = dl.RE_NUM.match(titulo)
    out = {"expediente": expte, "numero": num.group(0), "titulo": titulo,
           "estado_campo": "", "estado": "", "organo": "", "boe": ""}
    r = re.search(r"Resultado tramitación (.+?) Tramitación seguida por la iniciativa", t)
    s = re.search(r"Situación actual (.+?) Tramitación seguida por la iniciativa", t)
    if r and len(r.group(1)) <= 120:
        out["estado_campo"], out["estado"] = "Resultado tramitación", r.group(1).strip()
    elif s and len(s.group(1)) <= 120:
        out["estado_campo"], out["estado"] = "Situación actual", s.group(1).strip()
    o = re.search(r"Tramitación seguida por la iniciativa (Pleno|Diputación Permanente) ", t)
    if o:
        out["organo"] = o.group(1)
    b = re.search(r"BOE Núm: (\d+) de (\d{2}/\d{2}/\d{4})", t)
    if b:
        out["boe"] = f"BOE núm. {b.group(1)}, de {b.group(2)}"
    return out


def _xml(ident: str) -> str:
    return _get(f"https://www.boe.es/diario_boe/xml.php?id={ident}")


def _campo(xml: str, etiqueta: str) -> str:
    m = re.search(rf"<{etiqueta}[^>]*>(.*?)</{etiqueta}>", xml, re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()) if m else ""


_SUMARIOS: dict = {}


def sumario(aaaammdd: str) -> list[tuple[str, str]]:
    """[(identificador, título)] del sumario oficial del BOE de ese día (vacío
    si no hay BOE ese día o falla la descarga). Con caché por día."""
    if aaaammdd not in _SUMARIOS:
        req = urllib.request.Request(f"https://www.boe.es/datosabiertos/api/boe/sumario/{aaaammdd}",
                                     headers={**UA, "Accept": "application/xml"})
        t = ""
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    t = r.read().decode("utf-8", "replace")
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(5)
        _SUMARIOS[aaaammdd] = [(_campo(it, "identificador"), _campo(it, "titulo"))
                               for it in re.findall(r"<item>(.*?)</item>", t, re.S)]
    return _SUMARIOS[aaaammdd]


def resolucion_en_sumarios(numero: str, boe: str, dias_max: int = 60) -> str:
    """Si el RDL no enlaza su resolución en el BOE (pasa con las derogaciones),
    se busca en los sumarios desde el día de su BOE hasta hoy (como mucho
    dias_max días) una resolución del Congreso sobre ese RDL."""
    m = re.search(r"de (\d{2})/(\d{2})/(\d{4})$", boe or "")
    if not m:
        return ""
    import datetime as dt
    d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    hoy = dt.date.today()
    for _ in range(dias_max):
        if d > hoy:
            break
        for ident, tit in sumario(d.strftime("%Y%m%d")):
            t = dl.RE_RESOLUCION.match(tit)
            if t and t.group(2) == numero:
                return ident
        d += dt.timedelta(days=1)
    return ""


def id_en_sumario(numero: str, boe: str) -> str:
    """Identificador del RDL en el sumario oficial del día de su BOE
    («BOE núm. N, de dd/mm/aaaa»)."""
    m = re.search(r"de (\d{2})/(\d{2})/(\d{4})$", boe or "")
    if not m:
        return ""
    for ident, tit in sumario(f"{m.group(3)}{m.group(2)}{m.group(1)}"):
        if tit.startswith(numero + ","):
            return ident
    return ""


def resolucion(id_rdl: str, numero: str = "", boe: str = "") -> dict:
    """La resolución del Congreso que publica el acuerdo de convalidación o
    derogación: primero en las referencias posteriores del RDL en el BOE y,
    si no está, en los sumarios desde el día de su BOE."""
    xml = _xml(id_rdl)
    post = re.search(r"<posteriores>(.*?)</posteriores>", xml, re.S)
    refs = [(ref, "BOE (referencias posteriores del real decreto-ley)")
            for ref, palabra in re.findall(r'<posterior referencia="([^"]+)"[^>]*>\s*<palabra[^>]*>([^<]*)</palabra>',
                                           post.group(1) if post else "")
            if re.search(r"Acuerdo de (convalidación|derogación)", palabra)]
    if not refs and numero:
        ref = resolucion_en_sumarios(numero, boe)
        if ref:
            refs = [(ref, "BOE (sumario del día)")]
    for ref, origen in refs:
        rx = _xml(ref)
        i = rx.rfind("<texto>")
        cuerpo = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", rx[i:rx.find("</texto>", i)])).split())
        res = dl.resolucion_de_texto(_campo(rx, "titulo"), cuerpo)
        if not res:
            print(f"AVISO: {ref} no encaja con el patrón de resolución; no se usa")
            continue
        num, fecha = _campo(rx, "diario_numero"), _campo(rx, "fecha_publicacion")
        boe = (f"BOE núm. {num}, de {fecha[6:8]}/{fecha[4:6]}/{fecha[:4]}"
               if num and re.fullmatch(r"\d{8}", fecha) else "")
        return {"id": ref, "boe": boe, "acuerdo": res["acuerdo"], "objeto": res["objeto"],
                "fuente": origen}
    return {}


def del_boe() -> dict:
    """{«Real Decreto-ley N/2026»: {id_boe, titulo, boe}} de las ediciones del sitio."""
    out = {}
    for f in sorted(glob.glob(str(RAIZ / "data" / "20*.json"))):
        try:
            d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        b = d.get("boe") or {}
        for s in b.get("stories") or []:
            t = " ".join((s.get("titulo_oficial") or "").split())
            m = dl.RE_NUM.match(t)
            if m and m.group(0) not in out and b.get("fechaISO") and b.get("numero"):
                a, mm, dd = b["fechaISO"].split("-")
                out[m.group(0)] = {"id_boe": s.get("ref") or "", "titulo": t,
                                   "boe": f"BOE núm. {b['numero']}, de {dd}/{mm}/{a}"}
    return out


def main() -> int:
    votos = vr.cargar()
    if not votos:
        print("ERROR: falta curated/votos_rdl.json")
        return 1
    primero = min(votos["votaciones"], key=lambda v: dl.clave(v["texto"]))
    inicio_num = dl.clave(primero["texto"])
    expte0 = primero.get("expediente") or ""
    if not re.match(r"^130/\d{6}$", expte0):
        print("ERROR: el primer RDL de votos_rdl no tiene expediente")
        return 1
    boe = del_boe()
    fichas, n, huecos = {}, int(expte0.split("/")[1]), 0
    while huecos < FIN_HUECOS:
        expte = f"130/{n:06d}"
        f = ficha(expte)
        if f:
            huecos = 0
            fichas[f["numero"]] = f
        else:
            huecos += 1
        n += 1
    nums = sorted({k for k in list(fichas) + list(boe)
                   if dl.clave(k)[0] == inicio_num[0] and dl.clave(k) >= inicio_num}, key=dl.clave)
    decretos = []
    for k in nums:
        f, b = fichas.get(k) or {}, boe.get(k) or {}
        boe_txt = f.get("boe") or b.get("boe") or ""
        id_boe = b.get("id_boe") or id_en_sumario(k, boe_txt)
        decretos.append({
            "numero": k,
            "titulo": f.get("titulo") or b.get("titulo") or "",
            "boe": boe_txt,
            "boe_fuente": "ficha del Congreso" if f.get("boe") else ("edición del BOE" if b.get("boe") else ""),
            "id_boe": id_boe,
            "expediente": f.get("expediente") or "",
            "estado_campo": f.get("estado_campo") or "",
            "estado": f.get("estado") or "",
            "organo": f.get("organo") or "",
            # Sin ficha con estado, también se busca la resolución en los sumarios.
            "resolucion": resolucion(id_boe, "" if f.get("estado") else k, boe_txt) if id_boe else {},
        })
    datos = {"criterio": dl.ENTRADILLA, "fuente": "Fichas de expediente del Congreso (serie 130, XV Legislatura) "
             "y ediciones del BOE del sitio.", "decretos": decretos}
    dl.DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{dl.DATOS.relative_to(RAIZ)}: {len(decretos)} decretos-leyes")
    for d in decretos:
        texto, fuente = dl.etiqueta(d)
        print(f"  {d['numero']:<26} {d['boe']:<28} {d['expediente'] or '-':<11} {texto} "
              f"[{fuente or 'sin fuente'}{': ' + d['resolucion']['id'] if fuente == 'resolucion' else ''}]"
              f"{'' if d['id_boe'] else ' · sin id BOE'}")
    fuera = dl.sin_correspondencia(datos)
    if fuera:
        print("AVISO: textos oficiales sin correspondencia (se muestran literales):")
        for x in fuera:
            print("  " + x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
