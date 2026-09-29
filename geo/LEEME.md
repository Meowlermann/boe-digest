# Geometría de las provincias

`provincias.json` son los contornos de las 52 circunscripciones ya proyectados
a coordenadas de SVG (viewBox de 800 de ancho), con Canarias en un recuadro
abajo a la derecha. `provincias.py` lo lee para pintar el mapa de
`/provincias/`. El pipeline diario no lo regenera: es un fichero estático.

- **Fuente:** Instituto Geográfico Nacional (CNIG), a través del paquete
  `es-atlas` 0.6.0 (licencia MIT).
- **Proyección:** cónica conforme centrada en la península; Canarias con su
  propia proyección dentro del recuadro.
- **Simplificación:** `topojson-simplify`, cuantil 0,3 (unos 50 KB).

Para regenerarlo (solo hace falta si se cambia el encuadre o la simplificación),
en una carpeta aparte, fuera del repositorio:

```
npm pack es-atlas && tar xzf es-atlas-*.tgz
npm i d3-geo topojson-client topojson-simplify
Q=0.3 node generar.mjs      # escribe mapa-provincias.json
```

Ninguna de esas dependencias entra en el repositorio ni en el workflow.
