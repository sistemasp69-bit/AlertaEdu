# Prueba de recuperación de contraseña

La autenticación activa en Render usa Supabase Auth. Para usar Gmail como destino y Brevo como remitente:

1. Configura las credenciales SMTP de Brevo en Supabase > Authentication > SMTP Settings; no basta con `BREVO_API_KEY` en Render.
2. En Supabase > Authentication > URL Configuration permite la URL HTTPS de la aplicación terminada en `/reset-password`.
3. Registra y confirma una cuenta de prueba que controle el equipo.
4. En `/login`, selecciona **¿Olvidaste tu contraseña?** y envía la solicitud a esa cuenta.
5. Revisa Recibidos y Spam. Abre el enlace y confirma que cargue `/reset-password`.
6. Cambia la contraseña y comprueba que puedes iniciar sesión con la nueva.

Las pruebas automatizadas sólo simulan proveedores y no verifican entrega real de correo. La aplicación no debe anunciarse como verificada hasta completar esta prueba con el servicio de Render desplegado.

Consulta [README.md](README.md) para el estado conocido y la configuración completa.
