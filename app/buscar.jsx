/* Metabuscador de La Tercera Cámara.
 *
 * Todo ocurre en el navegador: se descarga el índice una vez, se cachea y se
 * resuelve en local. Ni hay servidor de búsqueda que mantener ni queda
 * registro de lo que busca nadie. El coste es el peso del índice, que por eso
 * lleva campos de una letra y textos recortados.
 */
import { render } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";

const CLASES = [
  ["", "Todo"],
  ["norma", "Normas"],
  ["cortes", "Cortes"],
  ["diputado", "Diputados"],
  ["tema", "Materias"],
  ["edicion", "Ediciones"],
];

const ETIQUETA = {
  norma: "Norma del BOE",
  cortes: "Cortes",
  diputado: "Diputado",
  tema: "Materia",
  plazo: "Plazo",
  edicion: "Edición",
};

/* Sin acentos y en minúsculas: quien escribe «gamarra» debe encontrar
 * «Gamarra» y quien escribe «ejecucion» debe encontrar «ejecución». */
function plano(s) {
  return (s || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function fechaEs(d) {
  if (!d || d.length !== 10) return "";
  const [a, m, dd] = d.split("-");
  const meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  return `${Number(dd)} de ${meses[Number(m) - 1]} de ${a}`;
}

/* Puntuación: una coincidencia al principio del titular vale más que una
 * perdida en el cuerpo, y coincidir en todos los términos vale más que en
 * uno. Sin esto, buscar «orden» devolvía trescientas normas en orden
 * cronológico y la que importaba quedaba en la página cuatro. */
function puntuar(item, terminos) {
  const t = item._t, s = item._s, x = item._x;
  let total = 0;
  for (const q of terminos) {
    let mejor = 0;
    const pt = t.indexOf(q);
    if (pt === 0) mejor = 100;
    else if (pt > 0) mejor = t[pt - 1] === " " ? 70 : 40;
    else {
      const ps = s.indexOf(q);
      if (ps >= 0) mejor = ps === 0 ? 30 : 20;
      else if (x.indexOf(q) >= 0) mejor = 12;
    }
    if (!mejor) return 0;          // todos los términos han de aparecer
    total += mejor;
  }
  if (item.k === "diputado") total += 6;   // los nombres propios son consultas exactas
  return total;
}

function Marca({ texto, terminos }) {
  if (!terminos.length) return <>{texto}</>;
  const base = plano(texto);
  const cortes = [];
  for (const q of terminos) {
    let i = base.indexOf(q);
    while (i >= 0) {
      cortes.push([i, i + q.length]);
      i = base.indexOf(q, i + q.length);
    }
  }
  if (!cortes.length) return <>{texto}</>;
  cortes.sort((a, b) => a[0] - b[0]);
  const fundidos = [cortes[0]];
  for (const c of cortes.slice(1)) {
    const u = fundidos[fundidos.length - 1];
    if (c[0] <= u[1]) u[1] = Math.max(u[1], c[1]);
    else fundidos.push(c);
  }
  const partes = [];
  let pos = 0;
  fundidos.forEach(([a, b], i) => {
    if (a > pos) partes.push(<span key={`p${i}`}>{texto.slice(pos, a)}</span>);
    partes.push(<mark key={`m${i}`}>{texto.slice(a, b)}</mark>);
    pos = b;
  });
  if (pos < texto.length) partes.push(<span key="fin">{texto.slice(pos)}</span>);
  return <>{partes}</>;
}

function Resultado({ item, terminos, activo }) {
  return (
    <li className={"res" + (activo ? " res-activo" : "")}>
      <a href={"../" + item.u}>
        <span className={"res-clase res-" + item.k}>{ETIQUETA[item.k] || item.k}</span>
        <span className="res-titulo"><Marca texto={item.t} terminos={terminos} /></span>
        {item.s ? (
          <span className="res-sub"><Marca texto={item.s} terminos={terminos} /></span>
        ) : null}
        {item.d ? <span className="res-fecha">{fechaEs(item.d)}</span> : null}
      </a>
    </li>
  );
}

function Buscador({ datos }) {
  const params = new URLSearchParams(location.search);
  const [q, setQ] = useState(params.get("q") || "");
  const [clase, setClase] = useState("");
  const [activo, setActivo] = useState(0);
  const caja = useRef(null);

  /* El índice se prepara una vez: normalizar acentos de cinco mil cadenas en
   * cada pulsación se nota en un móvil. */
  const items = useMemo(
    () => datos.items.map((e) => ({
      ...e, _t: plano(e.t), _s: plano(e.s), _x: plano(e.x),
    })),
    [datos]
  );

  const terminos = useMemo(
    () => plano(q).split(/\s+/).filter((x) => x.length > 1),
    [q]
  );

  const resultados = useMemo(() => {
    if (!terminos.length) return [];
    const salida = [];
    for (const it of items) {
      if (clase && it.k !== clase) continue;
      const p = puntuar(it, terminos);
      if (p) salida.push([p, it]);
    }
    salida.sort((a, b) => b[0] - a[0] || (b[1].d || "").localeCompare(a[1].d || ""));
    return salida.slice(0, 60).map((x) => x[1]);
  }, [items, terminos, clase]);

  const cuentas = useMemo(() => {
    const c = {};
    if (!terminos.length) return c;
    for (const it of items) if (puntuar(it, terminos)) c[it.k] = (c[it.k] || 0) + 1;
    return c;
  }, [items, terminos]);

  useEffect(() => { setActivo(0); }, [q, clase]);

  /* La barra de direcciones refleja la búsqueda: así se puede compartir un
   * resultado y así funciona el botón de atrás. */
  useEffect(() => {
    const u = new URL(location.href);
    if (q) u.searchParams.set("q", q); else u.searchParams.delete("q");
    history.replaceState(null, "", u);
  }, [q]);

  useEffect(() => {
    const onTecla = (ev) => {
      if (ev.key === "/" && document.activeElement !== caja.current) {
        ev.preventDefault();
        caja.current && caja.current.focus();
      }
    };
    addEventListener("keydown", onTecla);
    return () => removeEventListener("keydown", onTecla);
  }, []);

  const navegar = (ev) => {
    if (!resultados.length) return;
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      setActivo((i) => Math.min(i + 1, resultados.length - 1));
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      location.href = "../" + resultados[activo].u;
    }
  };

  return (
    <div className="buscador">
      <div className="buscador-caja">
        <input
          ref={caja}
          type="search"
          className="buscador-input"
          value={q}
          autoFocus
          placeholder="Orden INT/977/2026, subvenciones, Gamarra, Barcelona…"
          aria-label="Buscar en La Tercera Cámara"
          onInput={(e) => setQ(e.target.value)}
          onKeyDown={navegar}
        />
        {q ? (
          <button className="buscador-limpiar" onClick={() => { setQ(""); caja.current.focus(); }}
                  aria-label="Limpiar">×</button>
        ) : null}
      </div>

      <div className="buscador-filtros">
        {CLASES.map(([k, etiqueta]) => {
          const n = k ? cuentas[k] || 0 : Object.values(cuentas).reduce((a, b) => a + b, 0);
          if (terminos.length && k && !n) return null;
          return (
            <button key={k || "todo"}
                    className={"chip" + (clase === k ? " chip-on" : "")}
                    onClick={() => setClase(clase === k ? "" : k)}>
              {etiqueta}{terminos.length ? ` ${n}` : ""}
            </button>
          );
        })}
      </div>

      {!terminos.length ? (
        <p className="buscador-pista">
          {datos.n.toLocaleString("es-ES")} fichas indexadas. Escribe para empezar;
          pulsa <kbd>/</kbd> desde cualquier punto de la página para volver aquí.
        </p>
      ) : resultados.length ? (
        <>
          <p className="buscador-pista">
            {resultados.length === 60 ? "Más de 60" : resultados.length} resultado
            {resultados.length === 1 ? "" : "s"}. Muévete con ↑ ↓ y abre con Intro.
          </p>
          <ul className="res-lista">
            {resultados.map((it, i) => (
              <Resultado key={it.u + it.t} item={it} terminos={terminos}
                         activo={i === activo} />
            ))}
          </ul>
        </>
      ) : (
        <p className="buscador-pista">
          Nada con «{q}». Prueba con menos palabras, con la referencia de la norma
          («INT/977/2026») o con el apellido del diputado.
        </p>
      )}
    </div>
  );
}

const raiz = document.getElementById("buscador-app");
if (raiz) {
  fetch(raiz.dataset.src)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((datos) => render(<Buscador datos={datos} />, raiz))
    .catch(() => {
      /* Si el índice no carga, la página sigue teniendo el formulario de
       * respaldo y la lista de lo más reciente: no se queda en blanco. */
      raiz.innerHTML =
        '<p class="buscador-pista">No se ha podido cargar el índice. ' +
        'Puedes usar los enlaces de abajo o el buscador de tu navegador.</p>';
    });
}
