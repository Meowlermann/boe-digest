/* Filtro instantáneo de las páginas índice (ver indices.py).
   Sin este script la barra no aparece y la lista se ve entera. */
(function () {
  var barra = document.querySelector('.ix-filtro'); if (!barra) return;
  barra.hidden = false;
  var input = barra.querySelector('input'), chips = barra.querySelectorAll('.ix-chips button');
  var n = barra.querySelector('.ix-n');
  var filas = [].slice.call(document.querySelectorAll('.ix-fila'));
  var grupos = [].slice.call(document.querySelectorAll('.ix-grupo'));
  var tipo = '*';
  function norm(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  filas.forEach(function (f) { f._t = norm(f.getAttribute('data-t') || ''); });
  function aplicar() {
    var q = norm(input.value.trim()), palabras = q ? q.split(/\s+/) : [], vis = 0;
    filas.forEach(function (f) {
      var ok = (tipo === '*' || f.getAttribute('data-f') === tipo) &&
               palabras.every(function (w) { return f._t.indexOf(w) >= 0; });
      f.hidden = !ok; if (ok) vis++;
    });
    grupos.forEach(function (g) { g.hidden = !g.querySelector('.ix-fila:not([hidden])'); });
    n.textContent = (q || tipo !== '*') ? vis + (vis === 1 ? ' resultado' : ' resultados') : '';
  }
  input.addEventListener('input', aplicar);
  chips.forEach(function (b) {
    b.addEventListener('click', function () {
      tipo = b.getAttribute('data-f');
      chips.forEach(function (o) { o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
      aplicar();
    });
  });
  // «/» y Ctrl+K siguen siendo del buscador general (nav.js); aquí solo Escape.
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { input.value = ''; aplicar(); input.blur(); }
  });
})();
