# Servicio de entrega del boletín: comparación y recomendación

Fecha: 9 de octubre de 2026. Datos tomados de la documentación y las páginas
de precios públicas de cada servicio en esa fecha (enlaces al final). Lo que la
documentación no dice se marca como **no documentado** y hay que comprobarlo en
el panel antes de dar nada por hecho.

Contexto: el boletín lo gestiona nuestro propio backend (Worker `boletin` +
D1). El servicio externo solo **entrega** cada mensaje, uno a uno, por API,
detrás de un único adaptador `enviar(mensaje) -> resultado`. Necesitamos:
plan gratuito, cabeceras propias (`List-Unsubscribe`, `List-Unsubscribe-Post`),
avisos de rebotes y quejas, y que los registros DNS no rompan el SPF de
ImprovMX (el reenvío de datos@terceracamara.es).

## Resumen

| | Cloudflare Email Sending | Resend | Brevo (API transaccional) | Amazon SES |
|---|---|---|---|---|
| **¿Gratis?** | **No.** Solo con Workers Paid (5 $/mes): 3.000 incluidos/mes y después 0,35 $ cada 1.000. En beta. | **Sí.** 3.000/mes y **100/día**. 1 webhook, 3 dominios. | **Sí.** **300/día** (sin acumular), sin límite mensual publicado. | **No** de forma permanente: 0,10 $ cada 1.000 (o planes desde 0,16 $). Solo los créditos de bienvenida de AWS (hasta 200 $, 6–12 meses). |
| **Dónde se trata** | Cloudflare (EE. UU., red global). No documentado para este producto. | Datos de la cuenta en **EE. UU.** aunque se envíe desde Irlanda (`eu-west-1`). | Empresa francesa (UE). Puede tratar fuera del EEE con subencargados. Ubicación concreta: no documentada en la página leída. | La región que se elija (p. ej. `eu-west-1` Irlanda o `eu-south-2` España). |
| **Garantías RGPD** | DPA de Cloudflare (encargado, cláusulas contractuales tipo). | DPA con **cláusulas contractuales tipo** de la UE (§6.2) y del Reino Unido. | DPA (anexo 3 de sus condiciones): **cláusulas contractuales tipo** y Marco de Privacidad UE-EE. UU. para transferencias. | DPA de AWS incluido en las condiciones del servicio, con cláusulas contractuales tipo. |
| **Cabeceras propias** | No documentado. | **Sí** (`headers`). | **Sí** (`headers`). | Sí (API v2, campo `Headers`). |
| **Rebotes y quejas** | No documentado (solo métricas). | **Webhooks firmados** (Svix: `svix-id`, `svix-timestamp`, `svix-signature`): `email.bounced` (rechazo permanente), `email.complained`. | Webhooks con `hard_bounce`, `spam`, `soft_bounce`… Sin firma HMAC documentada; se protegen con credenciales o token en la llamada. | Notificaciones vía Amazon SNS (otro servicio que configurar). |
| **DNS** | No documentado. | SPF (`TXT` + `MX`) en el **subdominio `send.`** y DKIM en `resend._domainkey`. **No toca el SPF de la raíz.** | Código de verificación y DKIM; según el asistente, puede pedir `include:spf.brevo.com` en el **SPF de la raíz** → hay que **fusionarlo** con el de ImprovMX. DMARC recomendado. | DKIM (3 CNAME) y, si se usa MAIL FROM propio, `MX` + SPF en un subdominio. |
| **Puesta en marcha** | Inmediata, pero de pago. | Inmediata tras verificar el dominio. | Inmediata tras validar la cuenta y el dominio. | Empieza en *sandbox* (200/día, solo destinatarios verificados); hay que pedir el acceso de producción (respuesta en ~24 h). |

## Lectura

- **Cloudflare Email Sending** queda fuera: exige el plan de pago de Workers
  y está en beta. Si algún día el proyecto paga Workers, sería la opción más
  integrada (mismo proveedor que el Worker y D1).
- **Amazon SES** es lo más barato a escala, pero no es gratis, pide pasar por
  el *sandbox* y montar SNS para rebotes. Demasiada infraestructura para empezar.
- **Resend** y **Brevo** cumplen. La diferencia está en cuatro cosas:
  1. **Capacidad**: Brevo envía 300 al día; Resend, 100 al día y 3.000 al mes.
     Con el envío repartido en varios días (punto 4 de la PR), Resend llega a
     unos **600–650 suscriptores** por semana contando las confirmaciones;
     Brevo, a unos **2.000**.
  2. **Seguridad del webhook**: Resend firma cada aviso (HMAC, cabeceras
     Svix), que es lo que pide la PR («con la firma verificada»). Brevo no
     documenta firma: solo un secreto compartido en la llamada.
  3. **DNS**: Resend pone su SPF en `send.terceracamara.es`, así que **el SPF
     de la raíz (ImprovMX) no se toca** y desaparece el riesgo de quedarse sin
     el correo de datos@. Con Brevo hay que fusionar dos SPF en uno.
  4. **RGPD**: los dos tienen DPA con cláusulas contractuales tipo. Brevo es
     una empresa de la UE; Resend guarda los datos de la cuenta en EE. UU.

## Recomendación

**Resend**, para empezar: gratis, webhooks firmados, cabeceras propias y sin
tocar el SPF de la raíz. Su límite (100 al día, 3.000 al mes) cubre de sobra
los primeros meses de un boletín nuevo, y el envío ya está pensado para
repartirse en varios días.

Cuándo cambiar: cuando los activos se acerquen al 80 % de lo que Resend
permite enviar en una semana (aviso automático en la salud del envío), pasar a
**Brevo** (300/día) o a un plan de pago. Gracias al adaptador único, el
cambio es un fichero nuevo en `boletin/src/envio/` y un secreto.

## Fuentes (consultadas el 9-10-2026)

- Cloudflare Email Service: https://developers.cloudflare.com/email-service/ y
  https://developers.cloudflare.com/email-service/platform/pricing/
- Resend: https://resend.com/pricing, https://resend.com/legal/dpa,
  https://resend.com/docs/api-reference/emails/send-email,
  https://resend.com/docs/webhooks/event-types,
  https://resend.com/docs/dashboard/webhooks/verify-webhooks-requests,
  https://resend.com/docs/dashboard/domains/regions,
  https://resend.com/docs/knowledge-base/what-if-my-domain-is-not-verifying
- Brevo: https://www.brevo.com/pricing/, https://help.brevo.com/hc/en-us/articles/208589409,
  https://developers.brevo.com/docs/send-a-transactional-email,
  https://developers.brevo.com/docs/transactional-webhooks,
  https://www.brevo.com/legal/termsofuse/ (anexo 3, DPA)
- Amazon SES: https://aws.amazon.com/ses/pricing/,
  https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
