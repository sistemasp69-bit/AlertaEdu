# AlertaEdu — Render, Supabase Auth y recuperación por correo

## Arquitectura activa
- FastAPI en Render y PostgreSQL de Supabase.
- Las cuentas del despliegue usan Supabase Auth.
- El restablecimiento de contraseña se solicita a Supabase Auth; el SMTP de recuperación se configura en Supabase, no con la API key de Brevo en Render.
- Las rutas de recuperación de cuentas locales y sus tablas `gmail_*` son heredadas; no son las que usa el inicio de sesión activo.

## A. Preparar Supabase Auth y Brevo SMTP
1. Verifica en Brevo el dominio o remitente autorizado para correo transaccional.
2. En Supabase > Authentication > SMTP Settings habilita el SMTP personalizado con las credenciales SMTP de Brevo y el remitente verificado. La API key de Brevo no sustituye el usuario/clave SMTP.
3. En Supabase > Authentication > URL Configuration define el `Site URL` con el dominio HTTPS de Render y permite `https://TU-DOMINIO/reset-password` como URL de redirección.
4. No publiques credenciales ni las pegues en el chat.

## B. Desplegar en Render
1. Conecta el repositorio `https://github.com/sistemasp69-bit/AlertaEdu` y crea el servicio desde `render.yaml`.
2. En Render > Environment define los valores privados requeridos en el Blueprint, en particular `DATABASE_URL` (Supabase Session pooler) y `SUPABASE_PUBLISHABLE_KEY`.
3. Render inicia con `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` y comprueba `/healthz`.
4. Cuando el servicio esté **Live**, añade su dominio HTTPS a la configuración de URLs permitidas de Supabase. Si todavía no hay URL pública, primero debe completarse el despliegue.

## C. Probar recuperación con una cuenta de prueba
1. Registra una cuenta desde `/login` y confirma el correo de registro.
2. Solicita un restablecimiento desde **¿Olvidaste tu contraseña?**.
3. Comprueba el correo y spam, abre el enlace y verifica que vuelva a `/reset-password`.
4. Establece una contraseña nueva de al menos 12 caracteres e inicia sesión con ella.
5. Si el usuario necesita acceso académico, un administrador autorizado debe asignarle el rol apropiado en `auth_roles`; las cuentas nuevas empiezan como `Usuario`.

## Estado comprobado desde el entorno de desarrollo
- Las pruebas automatizadas simulan los proveedores: no envían correo real ni modifican contraseñas reales.
- La conexión local a Supabase PostgreSQL se comprobó correctamente y encontró `risk_settings`.
- No se encontró un servidor local en `127.0.0.1:8000`.
- No se comprobó la URL pública de Render ni la entrega real de un correo. No afirmamos que el restablecimiento en producción ya funcione hasta completar la prueba manual anterior.

Para más detalle, consulta [README.md](README.md) y [CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md](CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md).
