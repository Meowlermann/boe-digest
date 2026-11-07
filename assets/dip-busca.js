/* Buscador de /diputados/ (tanda 3-A). Sin este script los formularios no
 * navegan, pero justo debajo está la lista de las 52 circunscripciones con
 * enlaces reales: solo se pierde el atajo y el autocompletado. */
(function () {
  "use strict";
  var plano = function (t) {
    return (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  };
  var fp = document.getElementById("dip-busca-prov");
  var fn = document.getElementById("dip-busca-nom");
  var msg = document.getElementById("dip-busca-msg");
  if (fp) fp.addEventListener("submit", function (e) {
    var v = document.getElementById("dip-prov").value;
    e.preventDefault();
    if (v) location.href = v;
    else if (msg) msg.textContent = "Elige una circunscripción de la lista.";
  });
  if (fn) fn.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = plano(document.getElementById("dip-nom").value);
    var ops = document.querySelectorAll("#dip-nombres option");
    var exacta = null, parciales = [];
    for (var i = 0; i < ops.length; i++) {
      var n = plano(ops[i].value);
      if (n === q) { exacta = ops[i]; break; }
      if (q && n.indexOf(q) !== -1) parciales.push(ops[i]);
    }
    var o = exacta || (parciales.length === 1 ? parciales[0] : null);
    if (o) { location.href = o.getAttribute("data-s") + ".html"; return; }
    if (msg) msg.textContent = !q ? "Escribe un nombre." : parciales.length
      ? parciales.length + " diputados coinciden: elige uno de la lista desplegable."
      : "Ningún diputado de la XV Legislatura coincide. Prueba por circunscripción.";
  });
})();
