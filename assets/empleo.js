// /empleo/: pestañas y «Últimos N días»; sin JS, todo visible. ?tipo=&dias= o #tipo=
(function () {
var D = document;
var c = D.getElementById("filtro-tipo");
if (!c) return;
var tabs = [].slice.call(c.querySelectorAll("[role=tab]")), dias = c.querySelector(".em-dias");
var out = c.querySelector(".em-fn"), def = c.dataset.defecto;
var q = new URLSearchParams(location.search), h = new URLSearchParams(location.hash.slice(1));
var ok = {};
tabs.forEach(function (b) { ok[b.dataset.v] = 1; });
var st = { tipo: q.get("tipo") || h.get("tipo") || "", dias: q.get("dias") || h.get("dias") || "" };
var m = /^#t-(\w+)$/.exec(location.hash);
if (m && ok[m[1]]) st.tipo = m[1];
if (!ok[st.tipo]) st.tipo = def;
if (st.dias !== dias.dataset.v) st.dias = "";
var ref = Date.parse(c.dataset.ref);
var secs = [].slice.call(D.querySelectorAll("section.em-sec[data-tipo]"));
secs.forEach(function (s) {
s.setAttribute("role", "tabpanel");
s.setAttribute("aria-labelledby", "tab-" + s.dataset.tipo);
});
function pinta(guarda) {
var corte = st.dias ? ref - st.dias * 864e5 : -Infinity, total = 0, todas = st.tipo === "todas";
tabs.forEach(function (b) {
var on = b.dataset.v === st.tipo;
b.setAttribute("aria-selected", on ? "true" : "false");
b.tabIndex = on ? 0 : -1;
});
dias.setAttribute("aria-pressed", st.dias ? "true" : "false");
secs.forEach(function (s) {
var n = 0, vis = todas || s.dataset.tipo === st.tipo;
s.querySelectorAll("li.em-card").forEach(function (li) {
var v = vis && Date.parse(li.dataset.fecha) >= corte;
li.hidden = !v;
if (v) n++;
});
var e = s.querySelector("h2,h3");
if (!e.dataset.o) e.dataset.o = e.textContent;
e.textContent = st.dias ? e.dataset.o.replace(/\([^)]*\)$/, "(" + n + ")") : e.dataset.o;
s.hidden = !vis;
total += n;
});
D.querySelectorAll("section.em-grupo").forEach(function (g) {
g.hidden = !g.querySelector("section.em-sec[data-tipo]:not([hidden])");
});
out.textContent = total + (total === 1 ? " disposición." : " disposiciones.");
if (guarda) {
var p = new URLSearchParams(location.search);
if (st.tipo !== def) p.set("tipo", st.tipo); else p.delete("tipo");
if (st.dias) p.set("dias", st.dias); else p.delete("dias");
var s = p.toString(), hs = /^#(tipo=|t-)/.test(location.hash) ? "" : location.hash;
history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + hs);
}
}
function elige(b, foco) {
st.tipo = b.dataset.v;
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
window.addEventListener("hashchange", function () {
var m = /^#t-(\w+)$/.exec(location.hash);
if (m && ok[m[1]]) { st.tipo = m[1]; pinta(false); }
});
c.hidden = false;
pinta(false);
})();
