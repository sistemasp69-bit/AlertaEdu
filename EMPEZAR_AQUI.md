# EMPEZAR AQUÍ — AlertaEdu en Render

**Estado real:** El workspace `AlertaEdu` está conectado a ChatGPT, pero aún no hay servicio web creado ni URL pública. El proyecto de Supabase `lwjnmebmotcnkjrhhbyl` sí existe y sus 13 tablas están creadas.

**Correo elegido para Render:** Brevo (`ALERTAEDU_EMAIL_PROVIDER=brevo`). Google Apps Script permanece disponible como alternativa.

Sigue el archivo **`CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md`**. Contiene los pasos para configurar Brevo, subir el código a un repositorio privado de GitHub, crear el servicio Render y probar la recuperación.

No subas `.env`, contraseña de PostgreSQL, secreto Apps Script ni token administrador a GitHub ni al chat.


## Brevo con Render + Supabase
* Para recuperación desde el dominio público, Render envía correo transaccional por Brevo.
* Verifica el remitente en Brevo y define `BREVO_API_KEY` y `BREVO_FROM_EMAIL` en Render Environment.
* Leer `CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md` para conectar GitHub, Render, Brevo y probar la recuperación.
* Para comprobar el remitente desde Windows, ejecutar `PROBAR_CORREO_WINDOWS.bat` opción 2.
* La conexión PostgreSQL depende de `DATABASE_URL` privado (Session pooler), no de la clave `sb_publishable_...`.
