# Rama `datos` de La Tercera Cámara

Esta rama guarda **solo los datos acumulados** del sitio, no código:

- `data/AAAA-MM-DD.json`: una edición por día (la fuente de verdad del render).
- `state/`: lo que se acumula entre días (Congreso, preguntas, tramitación…).
- `debug/`: diagnóstico de la última ejecución y `salud.json`.

La escribe solo el workflow `publicar.yml` de `main` (modos `diario` y
`archivo`), a través de `tools/datos.sh`. **No se fusiona nunca con `main`**
ni se edita a mano: el código vive en `main` y la web se publica como
artefacto de GitHub Pages.

Es una rama huérfana: su historia no tiene nada que ver con la de `main`. Se
creó con un único commit «Datos iniciales» con el contenido de `data/`,
`state/` y `debug/` que había en `main` en ese momento.

Más información en `ARQUITECTURA.md` (§7 y §8) de la rama `main`.
