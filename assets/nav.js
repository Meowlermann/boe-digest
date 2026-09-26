/* Navegación de La Tercera Cámara.
 *
 * El HTML de la barra ya viene servido con enlaces reales: sin este script se
 * navega igual, solo que sin paneles desplegables ni búsqueda instantánea.
 * Esto añade tres cosas:
 *
 *   1. Paneles: en escritorio se abren al pasar el ratón (eso lo hace el CSS);
 *      aquí se añade el clic en pantallas táctiles, el teclado y Escape.
 *   2. Búsqueda en cualquier página: se escribe en la barra y aparecen las
 *      fichas al momento. «/» o Ctrl+K llevan a la caja desde donde sea.
 *   3. En móvil, la barra inferior abre los mismos paneles como hojas.
 *
 * Sin dependencias: pesa unos pocos KB y no bloquea nada.
 */
(function () {
  "use strict";
  var nav = document.querySelector(".nav");
  if (!nav) return;
  var tabbar = document.querySelector(".tabbar");
  var pilares = [].slice.call(nav.querySelectorAll(".pilar"));
  var tactil = window.matchMedia("(hover: none)").matches;
  var velo = document.createElement("div");
  velo.className = "nav-velo";
  document.body.appendChild(velo);

  /* ------------------------------------------------- barra pegada arriba */
  // Cuando la cabecera sale de pantalla, la barra muestra una marca pequeña:
  // así nunca se pierde el camino a la portada, se esté donde se esté.
  var cabecera = document.querySelector(".masthead");
  if (cabecera && "IntersectionObserver" in window) {
    new IntersectionObserver(function (e) {
      nav.classList.toggle("pegada", !e[0].isIntersecting);
    }).observe(cabecera);
  }

  /* ---------------------------------------------------------- estás aquí */
  var ruta = location.pathname;
  var seccion =
    /^\/votaciones\//.test(ruta) ? "votaciones" :
    /^\/(diputados)\//.test(ruta) ? "parlamento" :
    /^\/(buscar|normas|temas|plazos|mapa)\//.test(ruta) ? "consultar" :
    "hoy";
  pilares.forEach(function (p) {
    if (p.dataset.pilar === seccion) p.classList.add("actual");
  });
  if (tabbar) {
    [].forEach.call(tabbar.querySelectorAll("[data-pilar]"), function (a) {
      if (a.dataset.pilar === seccion) a.classList.add("actual");
    });
  }
  [].forEach.call(nav.querySelectorAll(".panel a"), function (a) {
    if (a.getAttribute("href") === ruta) a.setAttribute("aria-current", "page");
  });

  /* ------------------------------------------------------------- paneles */
  function cerrarTodo() {
    pilares.forEach(function (p) {
      p.classList.remove("abierto");
      p.querySelector(".pilar-b").setAttribute("aria-expanded", "false");
    });
    buscador.classList.remove("abierto");
    document.body.classList.remove("hoja-abierta");
  }
  function abrir(p) {
    cerrarTodo();
    p.classList.add("abierto");
    p.querySelector(".pilar-b").setAttribute("aria-expanded", "true");
    document.body.classList.add("hoja-abierta");
  }

  pilares.forEach(function (p) {
    var b = p.querySelector(".pilar-b");
    if (!p.querySelector(".panel")) return;       // enlace directo, sin panel
    b.addEventListener("click", function (e) {
      // En táctil no hay «pasar el ratón»: el primer toque abre el panel y el
      // segundo, ya abierto, sigue el enlace a la portada de la sección.
      if (tactil && !p.classList.contains("abierto")) {
        e.preventDefault();
        abrir(p);
      }
    });
    b.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === " ") {
        e.preventDefault();
        abrir(p);
        var primero = p.querySelector(".panel a");
        if (primero) primero.focus();
      }
    });
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".nav") && !e.target.closest(".tabbar")) cerrarTodo();
  });
  velo.addEventListener("click", cerrarTodo);

  if (tabbar) {
    [].forEach.call(tabbar.querySelectorAll("[data-abre]"), function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        var que = a.dataset.abre;
        if (que === "buscar") {
          cerrarTodo();
          buscador.classList.add("abierto");
          document.body.classList.add("hoja-abierta");
          caja.focus();
          return;
        }
        var p = nav.querySelector('.pilar[data-pilar="' + que + '"]');
        if (p.classList.contains("abierto")) cerrarTodo();
        else abrir(p);
      });
    });
  }

  /* ------------------------------------------------------------ búsqueda */
  var buscador = nav.querySelector(".nav-buscar");
  var caja = buscador.querySelector("input");
  var res = buscador.querySelector(".nav-res");
  var indice = null, cargando = null, activo = -1, visibles = [];

  var ETIQ = { norma: "Norma", cortes: "Cortes", diputado: "Diputado",
               tema: "Materia", edicion: "Edición", plazo: "Plazo" };

  function plano(t) {
    return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function cargar() {
    if (indice || cargando) return cargando;
    cargando = fetch("/datos/indice.json")
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (d) {
        indice = (d.items || []).map(function (e) {
          e._t = plano(e.t); e._s = plano(e.s); e._x = plano(e.x);
          return e;
        });
        pintar();
      })
      .catch(function () { indice = []; });
    return cargando;
  }
  function puntuar(it, ts) {
    var total = 0;
    for (var i = 0; i < ts.length; i++) {
      var q = ts[i], p = it._t.indexOf(q), m = 0;
      if (p === 0) m = 100;
      else if (p > 0) m = it._t[p - 1] === " " ? 70 : 40;
      else if (it._s.indexOf(q) >= 0) m = 20;
      else if (it._x.indexOf(q) >= 0) m = 12;
      if (!m) return 0;
      total += m;
    }
    return total + (it.k === "diputado" ? 6 : 0);
  }
  function esc(t) {
    return (t || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function pintar() {
    var ts = plano(caja.value).split(/\s+/).filter(function (x) { return x.length > 1; });
    activo = -1;
    if (!ts.length) { res.hidden = true; res.innerHTML = ""; return; }
    if (!indice) { res.hidden = false; res.innerHTML = '<p class="nav-res-n">Cargando el índice…</p>'; return; }
    var r = [];
    for (var i = 0; i < indice.length; i++) {
      var p = puntuar(indice[i], ts);
      if (p) r.push([p, indice[i]]);
    }
    r.sort(function (a, b) { return b[0] - a[0] || (b[1].d || "").localeCompare(a[1].d || ""); });
    visibles = r.slice(0, 8).map(function (x) { return x[1]; });
    var q = encodeURIComponent(caja.value.trim());
    res.innerHTML = (visibles.length ? visibles.map(function (it, n) {
      return '<a class="nav-res-i" role="option" id="nr' + n + '" href="/' + esc(it.u) + '">' +
        '<em>' + (ETIQ[it.k] || it.k) + '</em><b>' + esc(it.t) + '</b>' +
        (it.s ? '<span>' + esc(it.s) + '</span>' : '') + '</a>';
    }).join("") : '<p class="nav-res-n">Nada con esas palabras.</p>') +
      '<a class="nav-res-todo" href="/buscar/?q=' + q + '">' +
      (r.length > visibles.length ? "Ver los " + r.length + " resultados" : "Abrir el buscador") + ' →</a>';
    res.hidden = false;
  }
  function marcar(n) {
    var items = res.querySelectorAll(".nav-res-i");
    if (!items.length) return;
    activo = (n + items.length) % items.length;
    [].forEach.call(items, function (el, i) { el.classList.toggle("activo", i === activo); });
    caja.setAttribute("aria-activedescendant", "nr" + activo);
  }

  caja.addEventListener("focus", cargar);
  caja.addEventListener("input", function () { cargar(); pintar(); });
  caja.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); marcar(activo + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); marcar(activo - 1); }
    else if (e.key === "Enter" && activo >= 0 && visibles[activo]) {
      e.preventDefault();
      location.href = "/" + visibles[activo].u;
    } else if (e.key === "Escape") {
      caja.value = ""; pintar(); caja.blur(); cerrarTodo();
    }
  });

  /* ------------------------------------- portada: ¿qué votó tu diputado? */
  // Sin script el formulario lleva al buscador con el nombre; con script, si
  // el nombre es de un diputado, directamente a sus votos.
  var fvt = document.querySelector(".vtb-f");
  if (fvt) {
    fvt.addEventListener("submit", function (e) {
      var q = (fvt.querySelector("input").value || "").trim().toLowerCase();
      var op = [].find.call(fvt.querySelectorAll("option"), function (o) {
        return o.value.toLowerCase() === q;
      });
      if (op) { e.preventDefault(); location.href = "/diputados/" + op.dataset.s + ".html#votos"; }
    });
  }

  /* ---------------------------------------------------------- atajos */
  document.addEventListener("keydown", function (e) {
    var escribiendo = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || "") ||
                      (e.target && e.target.isContentEditable);
    if (e.key === "Escape") { cerrarTodo(); return; }
    // La página del buscador tiene su propia caja grande y su propio «/».
    if (document.getElementById("buscador-app")) return;
    if ((e.key === "/" && !escribiendo) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
      e.preventDefault();
      if (window.matchMedia("(max-width: 720px)").matches) {
        buscador.classList.add("abierto");
        document.body.classList.add("hoja-abierta");
      }
      caja.focus();
    }
  });
})();
