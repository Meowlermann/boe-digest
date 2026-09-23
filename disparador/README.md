# Disparador de la edición diaria

Cloudflare pone el cron; GitHub solo recibe la orden. Existe porque los cron de
GitHub Actions llegan con horas de retraso y los `workflow_dispatch` no.

El workflow `daily.yml` conserva sus propios cron como red de seguridad: si
este Worker deja de funcionar, la edición sale igual, solo que tarde.

## Puesta en marcha

1. **Token de GitHub.** En GitHub › Settings › Developer settings › Personal
   access tokens › **Fine-grained tokens**, crea uno con:
   - Repository access: solo `Meowlermann/boe-digest`
   - Permissions › Repository permissions › **Actions: Read and write**
   - Caducidad: la máxima que te permita, y apúntala — el día que caduque, el
     Worker empieza a fallar en silencio salvo que mires los logs.

   Nada más. Ese token solo puede lanzar workflows en ese repositorio.

2. **Desplegar el Worker** (desde esta carpeta):

   ```
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN     # pega el token cuando lo pida
   npx wrangler deploy
   ```

   El token se guarda cifrado en tu cuenta de Cloudflare. No se escribe en
   ningún fichero de este repositorio, y `wrangler` no lo vuelve a mostrar.

3. **Comprobar.** En la consola de Cloudflare, Workers › terceracamara-disparador
   › Settings › Trigger Events › *Trigger Cron*. Debería aparecer una ejecución
   nueva en la pestaña Actions del repositorio en cuestión de segundos.

## Si un día no sale la edición

Mira los logs del Worker (`npx wrangler tail`, o la pestaña Logs en la consola).
Los dos fallos probables:

- `HTTP 401` — el token caducó o se revocó. Genera otro y repite el `secret put`.
- `HTTP 403` — al token le falta el permiso *Actions: Read and write*.
