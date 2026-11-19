# EMPEZAR AQUÍ — AlertaEdu en Render

**Estado real:** El workspace `AlertaEdu` está conectado a ChatGPT, pero aún no hay servicio web creado ni URL pública. El proyecto de Supabase `lwjnmebmotcnkjrhhbyl` sí existe y sus 13 tablas están creadas.

**Autenticación activa en Render:** Supabase Auth. La recuperación de contraseña envía el correo mediante el SMTP configurado en Supabase; Brevo puede usarse como ese proveedor SMTP.

Sigue el archivo **`CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md`**. Contiene los pasos para configurar el SMTP, publicar el servicio en Render y probar la recuperación.

No subas `.env`, contraseña de PostgreSQL, secreto Apps Script ni token administrador a GitHub ni al chat.


## Brevo con Supabase Auth
* Verifica el remitente en Brevo y configura sus credenciales SMTP en Supabase > Authentication > SMTP Settings.
* Añade la URL HTTPS de Render terminada en `/reset-password` a la lista de redirecciones permitidas en Supabase.
* Las variables `BREVO_API_KEY` y `BREVO_FROM_EMAIL` en Render no configuran el correo de Supabase Auth.
* Leer `CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md` para conectar Supabase, Render y probar la recuperación.
* La conexión PostgreSQL depende de `DATABASE_URL` privado (Session pooler), no de la clave `sb_publishable_...`.
