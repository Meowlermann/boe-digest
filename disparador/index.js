/**
 * Disparador puntual de la edición diaria.
 *
 * Por qué existe: los cron de GitHub Actions no son puntuales. GitHub los
 * encola y bajo carga los retrasa horas — medido en este repositorio: el cron
 * de las 07:37 se ejecutó a las 12:14, y el de respaldo de las 10:23 a las
 * 15:41. Para una publicación que va del BOE del día, eso es la diferencia
 * entre desayunar con ella y leerla a media tarde.
 *
 * Los `workflow_dispatch`, en cambio, arrancan en segundos: no pasan por esa
 * cola. Así que el cron lo pone Cloudflare, que sí es puntual, y GitHub solo
 * recibe la orden de ejecutar.
 *
 * El token vive como secreto en tu propia cuenta de Cloudflare y nunca sale
 * de aquí: este Worker no expone ninguna ruta que dispare nada, precisamente
 * para que una URL filtrada no se convierta en un botón de lanzar builds.
 */

const REPO = "Meowlermann/boe-digest";
const WORKFLOW = "daily.yml";
const RAMA = "main";

async function lanzar(env) {
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      // La API de GitHub rechaza las peticiones sin User-Agent.
      "User-Agent": "terceracamara-disparador",
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: RAMA }),
  });

  // 204 es el éxito de este endpoint: acepta la orden y no devuelve cuerpo.
  if (r.status === 204) {
    console.log("edición lanzada");
    return;
  }

  // Un fallo silencioso aquí significa un día sin edición y sin que nadie se
  // entere, así que se deja constancia con el cuerpo de la respuesta: es
  // donde GitHub explica si el token caducó o si le faltan permisos.
  const cuerpo = await r.text();
  console.error(`fallo al lanzar (HTTP ${r.status}): ${cuerpo.slice(0, 500)}`);
  throw new Error(`GitHub respondió ${r.status}`);
}

export default {
  async scheduled(evento, env, ctx) {
    ctx.waitUntil(lanzar(env));
  },

  // Sin ruta pública que dispare nada. Para probar sin esperar al cron, usa
  // el botón de la consola de Cloudflare (Settings › Trigger Events) o
  // `npx wrangler dev --test-scheduled`.
  async fetch() {
    return new Response(
      "Disparador de la edición diaria de La Tercera Cámara. " +
      "No hace nada por HTTP: solo responde a su propio cron.",
      { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } }
    );
  },
};
