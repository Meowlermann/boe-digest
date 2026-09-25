/* Votaciones: el hemiciclo de cada votación, pintado por el sentido del voto.
 *
 * La página ya viene servida con todo lo importante en HTML (resultado, voto
 * de cada grupo, quién se apartó, lista nominal). Esto añade encima:
 *
 *   1. Un hemiciclo por votación, con un escaño por diputado coloreado según
 *      lo que votó. Se dibuja al acercarse a la pantalla, no todos de golpe:
 *      un pleno puede traer sesenta votaciones.
 *   2. Al pasar el ratón (o tocar) un escaño: quién es y qué votó.
 *   3. «¿Qué votó tu diputado?»: se elige a alguien y cada votación dice qué
 *      votó y marca su escaño. Queda en la URL (?d=slug) para compartirlo.
 */
(function () {
  "use strict";
  var nodo = document.getElementById("vt-datos");
  if (!nodo) return;
  var datos;
  try { datos = JSON.parse(nodo.textContent); } catch (e) { return; }
  var A = datos.asientos || [], V = datos.votos || {};
  var NS = "http://www.w3.org/2000/svg";
  var TXT = { S: "Sí", N: "No", A: "Abstención", X: "No vota", "-": "No estaba en la Cámara" };
  var CL = { S: "si", N: "no", A: "abs", X: "nv", "-": "fuera" };
  var porSlug = {};
  A.forEach(function (a, i) { porSlug[a[3]] = i; });
  var elegido = null;

  /* ------------------------------------------------------------ tooltip */
  var tip = document.createElement("div");
  tip.className = "vt-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  function mostrar(ev, i, letra) {
    var a = A[i];
    tip.innerHTML = "<b></b><span></span><em></em>";
    tip.children[0].textContent = a[4];
    tip.children[1].textContent = a[5];
    tip.children[2].textContent = TXT[letra] || "";
    tip.children[2].className = "vv-" + (CL[letra] || "nv");
    tip.hidden = false;
    var r = ev.target.getBoundingClientRect();
    var x = r.left + r.width / 2 + window.scrollX, y = r.top + window.scrollY;
    tip.style.left = Math.max(8, Math.min(x - 90, window.scrollX + document.documentElement.clientWidth - 188)) + "px";
    tip.style.top = (y - tip.offsetHeight - 10) + "px";
  }

  /* ---------------------------------------------------------- hemiciclo */
  function dibujar(art) {
    var caja = art.querySelector(".vt-hemi");
    var cad = V[art.dataset.v];
    if (!caja || !cad || caja.firstChild) return;
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 720 386");
    svg.setAttribute("class", "vt-svg");
    for (var i = 0; i < A.length; i++) {
      var a = A[i], letra = cad.charAt(i) || "-";
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", a[0]); c.setAttribute("cy", a[1]); c.setAttribute("r", a[2]);
      c.setAttribute("class", "vs vs-" + CL[letra]);
      c.dataset.i = i; c.dataset.l = letra;
      svg.appendChild(c);
    }
    svg.addEventListener("mouseover", function (e) {
      var t = e.target;
      if (t.dataset && t.dataset.i) mostrar(e, +t.dataset.i, t.dataset.l);
    });
    svg.addEventListener("mouseout", function () { tip.hidden = true; });
    svg.addEventListener("click", function (e) {
      var t = e.target;
      if (!t.dataset || !t.dataset.i) return;
      // En táctil el primer toque enseña quién es; el segundo lleva a su ficha.
      if (window.matchMedia("(hover: none)").matches && tip.dataset.i !== t.dataset.i) {
        tip.dataset.i = t.dataset.i;
        mostrar(e, +t.dataset.i, t.dataset.l);
        return;
      }
      location.href = "/diputados/" + A[+t.dataset.i][3] + ".html";
    });
    caja.appendChild(svg);
    if (elegido !== null) marcar(art);
  }

  var arts = [].slice.call(document.querySelectorAll("article.votacion"));
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { dibujar(e.target); io.unobserve(e.target); }
      });
    }, { rootMargin: "400px 0px" });
    arts.forEach(function (a) { io.observe(a); });
  } else {
    arts.forEach(dibujar);
  }

  /* ------------------------------------------- quién votó qué, uno a uno */
  // La lista nominal se monta al abrirla: servida en HTML, un pleno de
  // sesenta votaciones pesaba varios megas.
  function listar(art) {
    var caja = art.querySelector(".vn");
    var cad = V[art.dataset.v] || "";
    if (!caja || caja.firstChild) return;
    ["S", "N", "A", "X"].forEach(function (l) {
      var quienes = [];
      for (var i = 0; i < A.length; i++) if (cad.charAt(i) === l) quienes.push(A[i]);
      if (!quienes.length) return;
      var b = document.createElement("div");
      b.className = "vn-bloque";
      var t = document.createElement("p");
      t.className = "vn-t vv-" + CL[l];
      t.textContent = TXT[l] + " (" + quienes.length + ")";
      var ul = document.createElement("ul");
      ul.className = "vn-l";
      quienes.forEach(function (a) {
        var li = document.createElement("li"), en = document.createElement("a"),
            g = document.createElement("span");
        en.href = "/diputados/" + a[3] + ".html"; en.textContent = a[4];
        g.className = "ref"; g.textContent = a[5];
        li.appendChild(en); li.appendChild(g); ul.appendChild(li);
      });
      b.appendChild(t); b.appendChild(ul); caja.appendChild(b);
    });
  }
  [].forEach.call(document.querySelectorAll("details.vt-nombres"), function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) listar(d.closest("article.votacion"));
    });
  });

  /* ------------------------------------------------ ¿qué votó tu diputado? */
  function marcar(art) {
    var mio = art.querySelector(".vt-mio");
    var cad = V[art.dataset.v] || "";
    var previo = art.querySelector(".vs.yo");
    if (previo) previo.classList.remove("yo");
    if (elegido === null) { if (mio) mio.hidden = true; return; }
    var letra = cad.charAt(elegido) || "-";
    if (mio) {
      mio.hidden = false;
      mio.innerHTML = "<span></span> <b></b>";
      mio.children[0].textContent = A[elegido][4] + ":";
      mio.children[1].textContent = TXT[letra];
      mio.children[1].className = "vd-voto vv-" + CL[letra];
    }
    var c = art.querySelector('.vs[data-i="' + elegido + '"]');
    if (c) { c.classList.add("yo"); c.parentNode.appendChild(c); }
  }
  function elegir(slug) {
    elegido = slug && porSlug[slug] !== undefined ? porSlug[slug] : null;
    arts.forEach(marcar);
    if (borrar) borrar.hidden = elegido === null;
    try {
      var u = new URL(location.href);
      if (elegido === null) u.searchParams.delete("d"); else u.searchParams.set("d", slug);
      history.replaceState(null, "", u);
    } catch (e) { /* sin URL API: no pasa nada */ }
  }

  var caja = document.getElementById("vt-quien");
  var borrar = document.getElementById("vt-borrar");
  if (caja) {
    var porNombre = {};
    A.forEach(function (a) { porNombre[a[4].toLowerCase()] = a[3]; });
    caja.addEventListener("input", function () {
      var s = porNombre[caja.value.trim().toLowerCase()];
      if (s) elegir(s);
      else if (!caja.value.trim()) elegir(null);
    });
    if (borrar) borrar.addEventListener("click", function () { caja.value = ""; elegir(null); caja.focus(); });
    var inicial = null;
    try { inicial = new URL(location.href).searchParams.get("d"); } catch (e) {}
    if (inicial && porSlug[inicial] !== undefined) {
      caja.value = A[porSlug[inicial]][4];
      elegir(inicial);
    }
  }
})();
