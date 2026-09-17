# Borrador de solicitud de acceso al Senado

Para enviar por el formulario de contacto del Senado (informacion@senado.es o el
formulario del portal de transparencia / datos abiertos). Ajusta lo que quieras antes
de mandarlo; está escrito para ser breve y concreto, que es lo que hace que estas
peticiones se contesten.

---

**Asunto:** Consulta sobre acceso automatizado a los boletines oficiales publicados en la web del Senado

Buenos días,

Mantengo un proyecto personal y sin ánimo de lucro que divulga la actividad
parlamentaria y la publicada en el BOE, con enlace siempre al documento oficial de
origen. Puede consultarse en https://meowlermann.github.io/boe-digest/

Para la parte del Congreso de los Diputados descargo una vez al día las publicaciones
oficiales desde su web, sin incidencia alguna. En el caso del Senado, las peticiones
son rechazadas con un error 403 devuelto en el borde de la red (aparentemente por la
capa de protección del servicio), tanto al índice de boletines oficiales como a los
propios PDF, por ejemplo:

- https://www.senado.es/web/actividadparlamentaria/publicacionesoficiales/senado/boletinesoficiales/index.html
- https://www.senado.es/legis15/publicaciones/pdf/senado/bocg/BOCG_T_15_459.PDF

El bloqueo parece deberse al origen de la conexión (un servicio de integración
continua alojado en la nube), no al contenido de la petición: los mismos documentos se
descargan con normalidad desde una conexión doméstica.

Mi consulta es doble:

1. ¿Existe alguna vía oficial de acceso programático a los boletines y diarios de
   sesiones —una API, un repositorio de datos abiertos o un punto de descarga— que sea
   la recomendada para este uso?

2. Si no la hay, ¿sería posible permitir el acceso a una descarga diaria identificada?
   El volumen es mínimo: una o dos peticiones al día, en horario de mañana, con un
   identificador de cliente propio y respetando los tiempos de espera entre intentos.

Quedo a su disposición para facilitar cualquier dato adicional sobre el proyecto o para
ajustarme a las condiciones de uso que me indiquen.

Muchas gracias por su tiempo.

[Tu nombre]
[Tu correo de contacto]

---

## Qué hacer con la respuesta

- **Si dan una API o punto de descarga oficial:** dímelo y adapto `build.py` para usarlo.
  Sería la solución definitiva y el recolector local dejaría de hacer falta.
- **Si permiten el acceso identificado:** habrá que fijar un `User-Agent` propio y
  declarado (algo como `boe-digest/1.0 (+https://meowlermann.github.io/boe-digest/)`)
  en lugar del de navegador; se cambia en una constante de `build.py`.
- **Si no contestan o lo deniegan:** se queda el recolector local, que ya funciona.
