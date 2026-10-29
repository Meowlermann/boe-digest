// /empleo/ (UX-3): filtro por tipo y «Últimos N días» en el cliente.
// Sin JS no corre y se ve el listado completo. Estado en ?tipo=&dias= o #tipo=.
(function () {
  var c = document.getElementById("filtro-tipo");
  if (!c) return;
  var bs = c.querySelectorAll(".em-fb"), out = c.querySelector(".em-fn");
  var q = new URLSearchParams(location.search), h = new URLSearchParams(location.hash.slice(1));
  var st = { tipo: q.get("tipo") || h.get("tipo") || "", dias: q.get("dias") || h.get("dias") || "" };
  var ok = { tipo: {}, dias: {} };
  bs.forEach(function (b) { ok[b.dataset.f][b.dataset.v] = 1; });
  if (!ok.tipo[st.tipo]) st.tipo = "";
  if (!ok.dias[st.dias]) st.dias = "";
  var ref = Date.parse(c.dataset.ref);

  function pinta(guarda) {
    var corte = st.dias ? ref - st.dias * 864e5 : -Infinity, total = 0;
    bs.forEach(function (b) {
      var on = b.dataset.f === "tipo" ? b.dataset.v === st.tipo : b.dataset.v === st.dias;
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("section.em-sec[data-tipo]").forEach(function (s) {
      var n = 0;
      s.querySelectorAll("li.em-card").forEach(function (li) {
        var v = (!st.tipo || s.dataset.tipo === st.tipo) && Date.parse(li.dataset.fecha) >= corte;
        li.hidden = !v;
        if (v) n++;
      });
      var e = s.firstElementChild;
      if (!e.dataset.o) e.dataset.o = e.textContent;
      e.textContent = st.tipo || st.dias ? e.dataset.o.replace(/\([^)]*\)$/, "(" + n + ")") : e.dataset.o;
      s.hidden = !n;
      total += n;
    });
    document.querySelectorAll("section.em-grupo").forEach(function (g) {
      g.hidden = !g.querySelector("section.em-sec[data-tipo]:not([hidden])");
    });
    out.textContent = st.tipo || st.dias ? total + (total === 1 ? " disposición" : " disposiciones") +
      " con este filtro." : "";
    if (guarda) {
      var p = new URLSearchParams(location.search);
      ["tipo", "dias"].forEach(function (k) { if (st[k]) p.set(k, st[k]); else p.delete(k); });
      var s = p.toString();
      history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + (h.get("tipo") ? "" : location.hash));
    }
  }

  bs.forEach(function (b) {
    b.addEventListener("click", function () {
      var f = b.dataset.f;
      st[f] = f === "dias" && st.dias ? "" : b.dataset.v;
      pinta(true);
    });
  });
  c.hidden = false;
  pinta(false);
})();
