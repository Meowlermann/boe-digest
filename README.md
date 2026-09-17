# BOE Digest & Cortes en Directo

Publicación diaria y automática sobre lo que publica el BOE y lo que hacen diputados y
senadores. Se actualiza sola: nadie tiene que tocar nada cada día.

**Web:** https://meowlermann.github.io/boe-digest/

## Cómo funciona

Todo ocurre dentro de GitHub, sin servidores ni servicios de pago:

1. Cada mañana, un workflow de GitHub Actions (`.github/workflows/daily.yml`) ejecuta
   `build.py`.
2. `build.py` descarga el sumario del BOE del día, las últimas publicaciones oficiales del
   Congreso (BOCG y Diarios de Sesiones) y el último boletín del Senado.
3. Redacta los artículos. Si GitHub Models está disponible en el repositorio, lo usa para
   escribir titulares y cuerpos; si no, cae automáticamente a un modo determinista que se
   limita a reproducir el material oficial. El sitio funciona en ambos casos.
4. Guarda la edición del día en `data/AAAA-MM-DD.json`, regenera `index.html` a partir de
   `template.html` y hace commit. GitHub Pages sirve el resultado.

El histórico vive en `data/`: cada fichero es una edición y la página muestra las 30 más
recientes con su selector de días.

## Reglas editoriales

Están escritas en el `SYSTEM_PROMPT` de `build.py` y son innegociables:

- No se inventa ningún dato, cifra, nombre ni cita. Solo se usa lo que aparece en la
  publicación oficial.
- No se atribuye a nadie una frase que no figure literalmente en el documento.
- La mordacidad se reparte por igual entre todos los grupos políticos. Ningún día puede
  quedar como un ataque desproporcionado a un solo partido.
- Cada pieza de la sección Cortes enlaza al PDF oficial del que sale.
- La sátira va en el titular y en el ángulo, nunca en los hechos.

## Puesta en marcha

1. En **Settings → Pages**, elegir origen `Deploy from a branch`, rama `main`, carpeta
   `/ (root)`.
2. En **Settings → Actions → General → Workflow permissions**, marcar
   `Read and write permissions`.
3. (Opcional) En **Settings → Models**, habilitar GitHub Models para que la redacción
   automática esté disponible. Sin esto el sitio sigue publicándose, en modo descriptivo.
4. Lanzar la primera ejecución a mano desde la pestaña **Actions → Edición diaria → Run
   workflow**.

## Ejecutar en local

```bash
pip install -r requirements.txt
python build.py            # recolecta el día de hoy y regenera index.html
python build.py --render   # solo regenera el HTML desde data/
python build.py --date 2026-09-17
```

## Estructura

```
build.py                    pipeline: recolección, redacción y renderizado
template.html               plantilla del sitio (marcador __DIGEST_DATA__)
data/AAAA-MM-DD.json        una edición por día
index.html                  generado por build.py — no editar a mano
.github/workflows/daily.yml automatización diaria
```
