// /empleo/: barra única (búsqueda, pestañas de tipo, proceso, provincia, organismo, «Últimos N días»),
// etiquetas de filtros activos y rejilla por grupo con «Cargar más». Sin JS, todo visible.
// Estado en ?tipo=&dias=&clase=&prov=&org=&q= (o #tipo=, #t-…), los valores de siempre.
(function () {
var D = document;
var c = D.getElementById("filtro-tipo");
if (!c) return;
function $(s) { return c.querySelector(s); }
var tabs = [].slice.call(c.querySelectorAll("[role=tab]")), dias = $(".em-dias");
var out = $(".em-fn"), def = c.dataset.defecto, qi = $("#em-q"), act = $(".em-activos");
var sel = { clase: $("#em-clase"), prov: $("#em-prov"), org: $("#em-org") };
var q = new URLSearchParams(location.search), h = new URLSearchParams(location.hash.slice(1));
var ok = {}, K = ["tipo", "dias", "clase", "prov", "org", "q"];
tabs.forEach(function (b) { ok[b.dataset.v] = 1; });
var st = {};
K.forEach(function (k) { st[k] = q.get(k) || h.get(k) || ""; });
var m = /^#t-(\w+)$/.exec(location.hash);
if (m && ok[m[1]]) st.tipo = m[1];
function nz(t) { return t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
function txt(s) { return s ? s.options[s.selectedIndex].text.replace(/\s*\(\d+\)$/, "") : ""; }
function fija() {
if (!ok[st.tipo]) st.tipo = def;
if (st.dias !== dias.dataset.v) st.dias = "";
for (var k in sel) {
var s = sel[k];
if (!s || ![].some.call(s.options, function (o) { return o.value === st[k]; })) st[k] = "";
if (s) s.value = st[k];
}
if (st.clase && st.tipo !== "convocatoria" && st.tipo !== "todas") st.tipo = "convocatoria";
}
var ref = Date.parse(c.dataset.ref);
var secs = [].slice.call(D.querySelectorAll("section.em-sec[data-tipo]"));
secs.forEach(function (s) {
s.setAttribute("role", "tabpanel");
s.setAttribute("aria-labelledby", "tab-" + s.dataset.tipo);
});
function cuenta(e, n, f) {
if (!e) return;
if (!e.dataset.o) e.dataset.o = e.textContent;
e.textContent = f ? e.dataset.o.replace(/\([^)]*\)$/, "(" + n + ")") : e.dataset.o;
}
function pinta(guarda) {
fija();
var corte = st.dias ? ref - st.dias * 864e5 : -Infinity, total = 0, todas = st.tipo === "todas";
var ws = nz(st.q).split(/\s+/).filter(Boolean), f = !!(st.dias || st.clase || st.prov || st.org || ws.length);
tabs.forEach(function (b) {
var on = b.dataset.v === st.tipo;
b.setAttribute("aria-selected", on ? "true" : "false");
b.tabIndex = on ? 0 : -1;
});
dias.setAttribute("aria-pressed", st.dias ? "true" : "false");
if (sel.clase) sel.clase.parentNode.hidden = !(todas || st.tipo === "convocatoria");
if (qi.value !== st.q) qi.value = st.q;
secs.forEach(function (s) {
var n = 0, vis = todas || s.dataset.tipo === st.tipo;
s.querySelectorAll("li.em-card").forEach(function (li) {
if (!li._t) li._t = nz(li.textContent + " " + (li.querySelector("a").getAttribute("aria-label") || ""));
var v = vis && Date.parse(li.dataset.fecha) >= corte && (!st.clase || li.classList.contains("em-c-" + st.clase)) &&
(!st.prov || (" " + li.dataset.p + " ").indexOf(" " + st.prov + " ") >= 0) && (!st.org || li.dataset.o === st.org) &&
ws.every(function (w) { return li._t.indexOf(w) >= 0; });
li.hidden = !v;
if (v) n++;
});
cuenta(s.querySelector("h2,h3"), n, f);
s.hidden = !vis || (f && !n);
s.querySelectorAll(".em-bloque").forEach(function (k) {
var nb = k.querySelectorAll("li.em-card:not([hidden])").length;
k.hidden = !nb;
cuenta(k.querySelector(".em-bloque-t"), nb, f);
if (k._u) k._u(true);
});
var at = s.querySelector(".em-atajos");
if (at) at.hidden = f;
total += n;
});
D.querySelectorAll("section.em-grupo").forEach(function (g) {
g.hidden = !g.querySelector("section.em-sec[data-tipo]:not([hidden])");
});
out.textContent = (total === 1 ? "1 disposición." : total + " disposiciones.") + (f && !total ? " Ninguna coincide: quita algún filtro." : "");
etiquetas();
if (guarda) {
var p = new URLSearchParams(location.search);
K.forEach(function (k) { if (st[k] && !(k === "tipo" && st[k] === def)) p.set(k, st[k]); else p.delete(k); });
var s = p.toString(), hs = /^#(tipo=|t-)/.test(location.hash) ? "" : location.hash;
history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + hs);
}
}
// Etiquetas de los filtros activos, cada una con «×», y «Limpiar todo».
function boton(t, l, fn) {
var b = D.createElement("button");
b.type = "button";
b.className = "em-fb em-x";
b.textContent = t;
if (l) b.setAttribute("aria-label", l);
b.onclick = function () { fn(); pinta(true); (act.querySelector("button") || qi).focus(); };
act.appendChild(b);
}
function etiquetas() {
var xs = [];
if (st.tipo !== def) xs.push(["tipo", "Tipo: " + tabs.filter(function (b) { return b.dataset.v === st.tipo; })[0].textContent]);
if (st.clase) xs.push(["clase", "Proceso: " + txt(sel.clase)]);
if (st.prov) xs.push(["prov", "Provincia: " + txt(sel.prov)]);
if (st.org) xs.push(["org", "Organismo: " + txt(sel.org)]);
if (st.dias) xs.push(["dias", dias.textContent]);
if (st.q) xs.push(["q", "Búsqueda: «" + st.q + "»"]);
act.textContent = "";
xs.forEach(function (x) {
boton(x[1] + " ×", "Quitar filtro " + x[1], function () { st[x[0]] = ""; });
});
if (xs.length > 1) boton("Limpiar todo", "", function () { K.forEach(function (k) { st[k] = ""; }); });
act.parentNode.hidden = !xs.length;
}
function elige(b, foco) {
st.tipo = b.dataset.v;
if (st.tipo !== "convocatoria" && st.tipo !== "todas") st.clase = "";
pinta(true);
if (foco) b.focus();
}
tabs.forEach(function (b, i) {
b.addEventListener("click", function () { elige(b, false); });
b.addEventListener("keydown", function (e) {
var j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
if (j === undefined) return;
e.preventDefault();
elige(tabs[(j + tabs.length) % tabs.length], true);
});
});
dias.addEventListener("click", function () {
st.dias = st.dias ? "" : dias.dataset.v;
pinta(true);
});
Object.keys(sel).forEach(function (k) {
if (sel[k]) sel[k].addEventListener("change", function () { st[k] = sel[k].value; pinta(true); });
});
var tq;
qi.addEventListener("input", function () {
clearTimeout(tq);
tq = setTimeout(function () { st.q = qi.value.trim(); pinta(true); }, 150);
});
qi.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
// Atajos «Ir a: Oposición (65)…»: con JS filtran por proceso.
D.querySelectorAll(".em-atajos a[data-clase]").forEach(function (a) {
a.addEventListener("click", function (e) {
e.preventDefault();
st.clase = a.dataset.clase;
pinta(true);
sel.clase.focus();
});
});
window.addEventListener("hashchange", function () {
var m = /^#t-(\w+)$/.exec(location.hash), t = new URLSearchParams(location.hash.slice(1)).get("tipo");
if (m && ok[m[1]]) t = m[1];
if (t && ok[t]) { st.tipo = t; pinta(false); }
});
// Rejilla por grupo: 24 tarjetas y «Cargar más <grupo>» (sin JS, todas visibles).
var LOTE = 24;
D.querySelectorAll(".em-bloque").forEach(function (k) {
var p = k.querySelector(".em-rejilla"), lim = LOTE, mas = D.createElement("button");
mas.type = "button";
mas.className = "em-fb em-mas";
k.appendChild(mas);
function vis() { return [].slice.call(p.querySelectorAll("li.em-card:not([hidden])")); }
function upd(r) {
if (r) lim = LOTE;
var xs = vis(), q = Math.max(0, xs.length - lim);
p.querySelectorAll("li.em-card").forEach(function (li) { li.classList.toggle("em-oculta", xs.indexOf(li) >= lim); });
mas.hidden = !q;
mas.textContent = "Cargar más " + k.dataset.n + " (" + Math.min(LOTE, q) + " de " + q + " restantes)";
}
mas.onclick = function () {
var s = vis()[lim];
lim += LOTE;
upd();
if (s) (s.querySelector("a,button") || s).focus();
};
k._u = upd;
upd();
});
var nf = D.getElementById("filtros");
if (nf) nf.hidden = true;
c.hidden = false;
pinta(false);
})();
