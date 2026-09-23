/**
 * La Tercera Cámara — capa interactiva del hemiciclo.
 *
 * Se monta ENCIMA del SVG que ya viene servido desde el servidor, no en su
 * lugar. Quien llegue sin JavaScript, o un rastreador, sigue viendo los 350
 * escaños, la leyenda y los enlaces: esto solo añade el hover, los filtros y
 * el resaltado. Si este fichero no carga, la página no se rompe, pierde
 * adornos.
 */
import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { render } from "react-dom";

const pct = (n, t) => {
  if (!t) return null;
  const v = Math.round((100 * n) / t);
  if (v === 100 && n < t) return 99;
  if (v === 0 && n) return 1;
  return v;
};

/** Sin acentos y en minúsculas, para que «Nuñez» encuentre a «Núñez». */
const plano = (t) =>
  (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function Ficha({ d, x, y, abajo }) {
  if (!d) return null;
  const asistencia = pct(d.sa, d.st);
  const emitidos = pct(d.si + d.no + d.ab, d.vt);
  return (
    <div className={"ficha-flotante" + (abajo ? " ff-abajo" : "")}
         style={{ left: x, top: y }} role="tooltip">
      <p className="ff-grupo">{d.g}{d.c ? ` · ${d.c}` : ""}</p>
      <h3 className="ff-nombre">{d.n}</h3>
      <dl className="ff-datos">
        <div><dt>Intervenciones</dt><dd>{d.iv}</dd></div>
        {d.vt > 0 && <div><dt>Votaciones</dt><dd>{d.vt}</dd></div>}
        {asistencia !== null && <div><dt>Asistencia</dt><dd>{asistencia} %</dd></div>}
        {emitidos !== null && <div><dt>Votos emitidos</dt><dd>{emitidos} %</dd></div>}
        {d.ds > 0 && (
          <div className="ff-disidencia">
            <dt>Distintos a su grupo</dt><dd>{d.ds}</dd>
          </div>
        )}
      </dl>
      {d.ua && (
        <p className="ff-ultima">
          <span>Última intervención</span>
          {d.ua}
          {d.uf ? ` · ${d.uf}` : ""}
        </p>
      )}
      <p className="ff-pie">Pulsa para ver su ficha completa</p>
    </div>
  );
}

function Controles({ grupos, estado, set, conteos, total, fechaSesion }) {
  return (
    <div className="hemi-controles">
      <div className="hc-fila">
        <input
          className="hc-buscar"
          type="search"
          placeholder="Buscar por nombre, grupo o provincia…"
          value={estado.q}
          onChange={(e) => set({ ...estado, q: e.target.value })}
          aria-label="Buscar parlamentario"
        />
        {(estado.q || estado.grupo || estado.marca) && (
          <button className="hc-limpiar" onClick={() => set({ q: "", grupo: "", marca: "" })}>
            Limpiar
          </button>
        )}
      </div>

      <div className="hc-fila hc-chips">
        {grupos.map((g) =>
          conteos[g.s] ? (
            <button
              key={g.s}
              className={"chip" + (estado.grupo === g.s ? " on" : "")}
              style={{ "--c": g.c }}
              onClick={() =>
                set({ ...estado, grupo: estado.grupo === g.s ? "" : g.s })
              }
              aria-pressed={estado.grupo === g.s}
            >
              <i /> {g.n} <b>{conteos[g.s]}</b>
            </button>
          ) : null
        )}
      </div>

      <div className="hc-fila hc-chips">
        <button
          className={"chip marca" + (estado.marca === "ult" ? " on" : "")}
          onClick={() => set({ ...estado, marca: estado.marca === "ult" ? "" : "ult" })}
          aria-pressed={estado.marca === "ult"}
        >
          Intervinieron el {fechaSesion || "último día"}
        </button>
        <button
          className={"chip marca" + (estado.marca === "dis" ? " on" : "")}
          onClick={() => set({ ...estado, marca: estado.marca === "dis" ? "" : "dis" })}
          aria-pressed={estado.marca === "dis"}
        >
          Se apartaron de su grupo
        </button>
        <button
          className={"chip marca" + (estado.marca === "aus" ? " on" : "")}
          onClick={() => set({ ...estado, marca: estado.marca === "aus" ? "" : "aus" })}
          aria-pressed={estado.marca === "aus"}
        >
          Menos asistencia
        </button>
      </div>

      <p className="hc-resumen" aria-live="polite">
        {total === grupos.totalGlobal
          ? `${total} escaños`
          : `${total} de ${grupos.totalGlobal} escaños destacados`}
      </p>
    </div>
  );
}

function Hemiciclo({ datos }) {
  const [estado, setEstado] = useState({ q: "", grupo: "", marca: "" });
  const [activo, setActivo] = useState(null);
  const [pos, setPos] = useState({ x: 0, y: 0, abajo: false });
  const caja = useRef(null);

  const porSlug = useMemo(() => {
    const m = {};
    datos.diputados.forEach((d) => (m[d.s] = d));
    return m;
  }, [datos]);

  const conteos = useMemo(() => {
    const c = {};
    datos.diputados.forEach((d) => (c[d.gs] = (c[d.gs] || 0) + 1));
    return c;
  }, [datos]);

  /** El umbral de «poca asistencia» sale de los datos, no de un número
   *  inventado: el cuartil inferior de los que tienen sesiones registradas. */
  const umbralAusencia = useMemo(() => {
    const v = datos.diputados
      .filter((d) => d.st > 0)
      .map((d) => d.sa / d.st)
      .sort((a, b) => a - b);
    return v.length ? v[Math.floor(v.length * 0.25)] : 0;
  }, [datos]);

  const destacados = useMemo(() => {
    const q = plano(estado.q);
    const s = new Set();
    datos.diputados.forEach((d) => {
      if (estado.grupo && d.gs !== estado.grupo) return;
      if (q && !(plano(d.n).includes(q) || plano(d.g).includes(q) || plano(d.c).includes(q)))
        return;
      if (estado.marca === "ult" && !d.ult) return;
      if (estado.marca === "dis" && !d.ds) return;
      if (estado.marca === "aus" && !(d.st > 0 && d.sa / d.st <= umbralAusencia)) return;
      s.add(d.s);
    });
    return s;
  }, [datos, estado, umbralAusencia]);

  const filtrando = !!(estado.q || estado.grupo || estado.marca);

  // El SVG lo pinta el servidor; aquí solo se le añaden clases y escuchas.
  useEffect(() => {
    const svg = document.getElementById("hemiciclo");
    if (!svg) return;
    svg.classList.toggle("filtrando", filtrando);
    svg.querySelectorAll(".escano").forEach((c) => {
      const slug = c.getAttribute("data-d");
      c.classList.toggle("apagado", filtrando && !destacados.has(slug));
      c.classList.toggle("vivo", filtrando && destacados.has(slug));
    });
  }, [destacados, filtrando]);

  useEffect(() => {
    const svg = document.getElementById("hemiciclo");
    if (!svg) return;
    const rect = () => caja.current?.getBoundingClientRect();

    const entrar = (e) => {
      const c = e.target.closest(".escano");
      if (!c) return;
      const d = porSlug[c.getAttribute("data-d")];
      if (!d) return;
      const r = rect();
      const b = c.getBoundingClientRect();
      if (r) {
        // Los escaños de la fila de arriba no dejan sitio para la ficha
        // encima: ahí se dibuja debajo. Y el centro se recorta a los bordes
        // del contenedor para que no se salga por los lados en pantallas
        // estrechas.
        const abajo = b.top < 250;
        const medio = Math.min(Math.max(b.left - r.left + b.width / 2, 8),
                               r.width - 8);
        setPos({ x: medio, y: (abajo ? b.bottom : b.top) - r.top, abajo });
      }
      setActivo(d);
    };
    const salir = (e) => {
      if (e.target.closest(".escano")) setActivo(null);
    };
    const pulsar = (e) => {
      const c = e.target.closest(".escano");
      if (c) location.href = c.getAttribute("data-d") + ".html";
    };

    svg.addEventListener("mouseover", entrar);
    svg.addEventListener("mouseout", salir);
    svg.addEventListener("focusin", entrar);
    svg.addEventListener("focusout", salir);
    svg.addEventListener("click", pulsar);
    svg.querySelectorAll(".escano").forEach((c) => {
      c.setAttribute("tabindex", "0");
      c.setAttribute("role", "link");
    });
    return () => {
      svg.removeEventListener("mouseover", entrar);
      svg.removeEventListener("mouseout", salir);
      svg.removeEventListener("focusin", entrar);
      svg.removeEventListener("focusout", salir);
      svg.removeEventListener("click", pulsar);
    };
  }, [porSlug]);

  const lista = useMemo(
    () =>
      datos.diputados
        .filter((d) => destacados.has(d.s))
        .sort((a, b) => b.iv - a.iv)
        .slice(0, 24),
    [datos, destacados]
  );

  return (
    <div className="hemi-interactivo" ref={caja}>
      <Controles
        grupos={Object.assign(datos.grupos, { totalGlobal: datos.diputados.length })}
        estado={estado}
        set={setEstado}
        conteos={conteos}
        total={destacados.size}
        fechaSesion={datos.fechaUltimaSesion}
      />
      <Ficha d={activo} x={pos.x} y={pos.y} abajo={pos.abajo} />
      {filtrando && (
        <ul className="rejilla-dip hemi-resultados">
          {lista.map((d) => (
            <li className="dip" key={d.s}>
              <a href={d.s + ".html"}>
                <span className="dip-nombre">{d.n}</span>
                <span className="dip-meta">
                  {d.g}
                  {d.c ? ` · ${d.c}` : ""}
                </span>
                <span className="dip-cifras">
                  {d.iv} intervenciones
                  {d.vt ? ` · ${d.vt} votaciones` : ""}
                  {d.ds ? ` · ${d.ds} fuera de grupo` : ""}
                </span>
              </a>
            </li>
          ))}
          {!lista.length && <li className="dip vacio">Nadie encaja con ese filtro.</li>}
        </ul>
      )}
    </div>
  );
}

async function arrancar() {
  const raiz = document.getElementById("hemiciclo-app");
  if (!raiz) return;
  try {
    const r = await fetch(raiz.dataset.src || "../datos/parlamento.json");
    if (!r.ok) throw new Error(r.status);
    const datos = await r.json();
    const u = datos.ultimaSesion;
    datos.fechaUltimaSesion = u
      ? `${u.slice(6, 8)}/${u.slice(4, 6)}/${u.slice(0, 4)}`
      : "";
    render(<Hemiciclo datos={datos} />, raiz);
  } catch (e) {
    // Sin datos no se monta nada: el hemiciclo del servidor se queda como está.
    console.warn("No se pudo cargar el parlamento interactivo:", e);
  }
}

if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", arrancar);
else arrancar();
