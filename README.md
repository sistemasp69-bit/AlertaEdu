# AlertaEdu

Aplicación web en español para gestión y seguimiento académico. Usa FastAPI en el servidor, PostgreSQL de Supabase para los datos y Supabase Auth para las cuentas del despliegue. Render publica la aplicación a partir de `render.yaml`.

> **Estado:** el código está en GitHub y las pruebas automatizadas simulan los proveedores de correo. La conexión local a Supabase PostgreSQL se verificó. El envío real de correo y el despliegue público aún no se han probado.

## Funciones

- Registro e inicio de sesión con correo y contraseña mediante Supabase Auth.
- Solicitud de restablecimiento de contraseña y página para establecer una nueva.
- Gestión académica, evaluaciones, seguimientos y alertas.
- API FastAPI con comprobación de salud en `/healthz`.

La autenticación activa en Render es **Supabase Auth**. Las cuentas nuevas tienen rol `Usuario` por defecto; un administrador debe asignar el rol institucional a la cuenta verificada siguiendo la migración de roles en `sql/20261119_supabase_auth_roles_audit.sql`. El código de recuperación antiguo de usuarios locales (`/api/auth/email/...`) no se utiliza en ese modo. No confundas esos endpoints ni la integración directa de Brevo API con el correo de recuperación de Supabase Auth.

## Recuperación de contraseña y correo

El botón **¿Olvidaste tu contraseña?** envía la solicitud a `/api/supabase/forgot`. El servidor llama a Supabase Auth, y Supabase entrega el correo de recuperación usando el SMTP configurado en el proyecto Supabase. El enlace debe volver a `/reset-password`, donde la persona establece su contraseña nueva.

Para usar **Brevo** en este flujo:

1. Verifica en Brevo el dominio o remitente autorizado para enviar correo.
2. En Supabase, abre **Authentication → SMTP Settings** y habilita SMTP personalizado.
3. Introduce las credenciales SMTP de Brevo y el remitente verificado. La API key de Brevo no reemplaza las credenciales SMTP.
4. En Supabase, configura **Authentication → URL Configuration**: el `Site URL` debe ser el dominio HTTPS de Render; incluye `https://TU-DOMINIO/reset-password` entre las URL de redirección permitidas.
5. Despliega la aplicación y prueba el recorrido con una cuenta de prueba cuyo correo puedas revisar: solicitar el enlace, abrirlo, guardar una contraseña nueva e iniciar sesión con ella.

Las variables `BREVO_API_KEY` y `BREVO_FROM_EMAIL` son para el transporte directo de la ruta heredada de cuentas locales; por sí solas **no conectan** Brevo con Supabase Auth. No guardes ninguna clave en GitHub. Las credenciales SMTP deben configurarse en el panel de Supabase, y las claves de base de datos en el panel de Render.

## Ejecutar localmente en Windows

Desde esta carpeta (`AlertaEdu`), en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Completa `.env` localmente con la conexión PostgreSQL de Supabase y la clave publicable. No compartas ni subas `.env`. Comprueba la conexión e inicia la aplicación:

```powershell
.\.venv\Scripts\python.exe VERIFICAR_CONEXION.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000`. Los accesos de Supabase Auth y el restablecimiento por correo necesitan conexión a Internet y una configuración válida en Supabase.

## Desplegar en Render

1. Conecta este repositorio de GitHub a Render y crea el servicio usando el Blueprint `render.yaml` en la raíz.
2. Configura en Render las variables privadas requeridas por el Blueprint: `DATABASE_URL` y `SUPABASE_PUBLISHABLE_KEY`. No las guardes en el repositorio.
3. Configura el SMTP de recuperación en Supabase y las URL permitidas como se explica arriba.
4. Cuando Render muestre el servicio como **Live**, verifica `https://TU-DOMINIO/healthz` y ejecuta:

   ```powershell
   python VERIFICAR_PUBLICACION.py https://TU-DOMINIO
   ```

El chequeo de salud no envía correo ni verifica la recuperación de contraseñas.

## Pruebas y estado comprobado

Ejecuta:

```powershell
python -m pytest
```

Las pruebas simulan los proveedores de correo; no mandan mensajes ni cambian contraseñas reales. `VERIFICAR_CONEXION.py` se conectó a PostgreSQL y encontró `risk_settings`. La prueba de salud local no encontró un servidor ejecutándose en `127.0.0.1:8000`; tampoco se verificó aquí una URL pública de Render ni la entrega real de un correo.

## Documentación adicional

- [Configuración local y Supabase](CONFIGURACION.md)
- [Guía de Render, correo y publicación](CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md)
- [Guía final de Render y Supabase](GUIA_FINAL_GMAIL_RENDER_SUPABASE.md)
- [Esquema de referencia de PostgreSQL](ESQUEMA_SUPABASE.sql)
