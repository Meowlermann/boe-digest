# Instrucciones para agentes (IA o personas) que trabajen en este repositorio

Lee primero [ARQUITECTURA.md](ARQUITECTURA.md): el flujo diario, qué hace
cada módulo, dónde se guarda cada dato y cómo añadir una sección.

## Reglas del mantenedor

Son decisiones tomadas y no están abiertas a discusión en cada tarea.

- **Nada de commits directos en `main`.** Cada tarea va en su rama y llega a
  `main` con una PR. `main` es solo código: el bot no escribe en ella. La web
  se publica como artefacto de Pages desde `publicar.yml` y los datos viven en
  la rama `datos` (ARQUITECTURA.md §8).
- **La rama `datos` solo la escribe `publicar.yml`** (por `tools/datos.sh`).
  No se edita a mano, no se fusiona con `main` y no se usa como base de
  ninguna PR. Las pruebas lanzadas desde otra rama escriben en
  `datos-pruebas`.
- **Nunca se fuerza un push**, con una única excepción: la compactación de la
  rama `datos` (`tools/compactar_datos.sh`, lanzado solo por
  `.github/workflows/compactar-datos.yml`), que la reescribe como un commit con
  el mismo contenido y hace `push --force-with-lease` solo a esa rama. Ninguna
  otra rama, ningún otro workflow y ningún agente a mano.
- **`main` no versiona nada generado ni datos**: `.gitignore` lo impide. Si un
  render local o del CI deja HTML o `data/` en el árbol, no se sube.
- **Las herramientas nuevas son deterministas**: nada de LLM, APIs de pago ni
  dependencias nuevas (`requirements.txt`: requests, beautifulsoup4, pypdf).
  La capa Gemini que ya existe (`redaccion.py`) se mantiene para titulares y
  entradillas, dentro de la cuota gratuita o de la suscripción, y siempre
  verificada contra la fuente.
- **No se esquivan bloqueos.** Sin proxies, sin cabeceras que aparenten otro
  navegador y sin relés. Si una fuente bloquea (hoy, el Senado), se dice en la
  nota de cobertura y se buscan vías legítimas.
- **Nada corre en el equipo del mantenedor** salvo que él lo pida. Todo pasa
  en GitHub Actions.
- **Ningún correo personal en el sitio.** El contacto público es
  datos@terceracamara.es.
- **Las credenciales son del mantenedor.** Un agente no inicia sesión por él,
  no crea tokens ni pega secretos. Los secretos viven en Settings › Secrets
  del repositorio.
- Las PR las fusiona el agente que las abre, solo cuando ci.yml está en verde
  y la validación con datos reales (si aplica) está hecha. Nunca se fusiona con
  el CI en rojo ni desactivándolo.
- Si una comprobación de verificar.py da un falso positivo, se corrige la
  comprobación en una PR, con un test que lo cubra; no se silencia.

## Reglas editoriales

- Lo que va entre comillas es literal de la fuente oficial. Se puede recortar
  (con «…» o «[…]») y quitar acotaciones, pero nunca reescribir.
- Cada pieza enlaza al documento concreto del que sale, no a una portada.
- Si un dato no se puede obtener, se dice. No se rellena ni se estima sin
  avisar.
- Los titulares son plantillas sin adjetivos sobre datos oficiales. El tono
  informal lo pone, si acaso, la capa Gemini, y queda marcado como editorial
  (`alternativeHeadline` en el JSON-LD).

## Reglas técnicas

- Cada fuente y cada sección, en su propio `try/except` con un `log()` claro.
  Un fallo nunca tumba la edición.
- Presupuesto de peticiones por pase en constantes al principio de cada
  módulo, con una pausa entre peticiones al buscador del Congreso
  (`cd.PAUSA_BUSCADOR`).
- Lo que acumula va en `state/`, con `esquema` y poda o partición por año.
  Nunca se guardan textos completos ni PDF si basta una cita y un enlace.
- Si añades una carpeta o un fichero publicado, ponlo en
  `tools/publicables.txt`: es el único sitio (ARQUITECTURA.md §8). Lo que no
  esté ahí no llega a la web.
- El acceso a los datos va siempre por `tools/datos.sh`. No leas ni escribas
  la rama `datos` desde otro sitio.
- Documenta en el docstring del módulo el formato de la fuente tal como lo
  comprobaste, con la fecha, y los casos que no se cubren.
- Añade pruebas sin red en `tests/` (`python -m unittest discover tests`).
- Antes de abrir la PR: `python build.py --render --sin-red` y
  `python tools/verificar.py --modo ci` (es lo que hace `ci.yml`).
- Si cambias la arquitectura, actualiza ARQUITECTURA.md en la misma PR.

## Idioma

Código, comentarios, commits, PR y documentación van en español.
