# AlertaEdu: configuración Render + Brevo

## 1. Lo que ya existe
- Organización Supabase: sistemasp69-bit's Org.
- Proyecto Supabase: `lwjnmebmotcnkjrhhbyl`.
- Workspace Render autorizado: `AlertaEdu` (no el anterior `My Workspace`).
- Las 13 tablas en Supabase están creadas; todavía no hay estudiantes ni usuarios iniciales.

## 2. Configura Brevo
1. Verifica tu dominio o remitente en Brevo y habilita el envío de correos transaccionales.
2. Crea una API key con permisos para enviar correo transaccional.
3. En Render > Environment configura, sin compartirlos por chat:
   - `BREVO_API_KEY`: la API key privada de Brevo.
   - `BREVO_FROM_EMAIL`: el correo verificado en Brevo.
4. `render.yaml` ya selecciona `ALERTAEDU_EMAIL_PROVIDER=brevo` y define `BREVO_FROM_NAME=AlertaEdu`.

## Alternativa: Google Apps Script
1. Abre https://script.google.com y crea proyecto llamado `AlertaEdu Correo`.
2. Copia el contenido de `apps_script/Code.gs` en `Code.gs`.
3. En **Configuración del proyecto → Propiedades de secuencia de comandos** agrega
   `ALERTAEDU_SHARED_SECRET`: un secreto aleatorio de **al menos 32 caracteres**.
   En tu PC puedes generar uno con `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Pulsa **Implementar → Nueva implementación → Aplicación web**. Ejecutar como: **Yo**;
   Acceso: **Cualquier usuario**. Autoriza el permiso de enviar correos.
5. Copia la URL del Web App que termina en `/exec`. No la publiques con el secreto.
6. Si el acceso "Cualquier usuario" no está permitido por tu cuenta institucional, necesitarás
   otro método de autenticación o proveedor de correo. No lo fuerces con configuraciones inseguras.
Para usar esta alternativa, cambia `ALERTAEDU_EMAIL_PROVIDER` a `apps_script` en Render y configura `ALERTAEDU_APPS_SCRIPT_URL` y `ALERTAEDU_APPS_SCRIPT_SECRET`.

## 3. Sube AlertaEdu a GitHub (repositorio PRIVADO)
1. Crea un repositorio privado llamado `AlertaEdu` en https://github.com/new
2. Sube **el contenido de esta carpeta** (por ejemplo `app/`, `render.yaml`, `requirements.txt`),
   no el ZIP. No subas archivos `.env`, contraseñas, datos personales o tokens.
3. Copia la URL real de ese repositorio. Render requiere el repositorio para publicar.

## 4. Crea el Web Service en Render (workspace nuevo AlertaEdu)
1. En https://dashboard.render.com cambia al workspace **AlertaEdu**.
2. Selecciona New > Web Service (o New > Blueprint) y conecta el repositorio GitHub.
3. Para Blueprint, usa `render.yaml` en la raíz.
4. Añade los secretos en **Environment**, NUNCA en GitHub:
   - `DATABASE_URL`: conexión Supabase > Connect > **Session pooler** (incluye contraseña; usar URL codificada).
   - `ALERTAEDU_BOOTSTRAP_TOKEN`: secreto aleatorio de al menos 24 caracteres, exclusivo del administrador inicial.
   - `BREVO_API_KEY` y `BREVO_FROM_EMAIL`: credenciales y remitente verificado de Brevo.
   Los demás valores ya están en `render.yaml` (`ALERTAEDU_ENV=production`, `ALERTAEDU_EMAIL_PROVIDER=brevo`, `ALERTAEDU_SEED_DEMO=0`).
5. Para arrancar el servidor automáticamente, Render usa:
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
6. Comprueba que la implementación quede Live y abre la URL HTTPS real `*.onrender.com`. La URL no existe hasta que Render termine de crear el servicio.

## 5. Prueba recuperación real
1. Abre `/setup` en tu dominio HTTPS y crea el administrador con `ALERTAEDU_BOOTSTRAP_TOKEN`.
2. En el sistema inicia sesión y registra un correo Gmail, introduciendo tu contraseña actual.
3. Debes recibir un correo de verificación. Abre el enlace.
4. Cierra sesión, pulsa **Olvidé mi contraseña**, introduce el mismo Gmail verificado.
5. Abre el correo de recuperación y establece una contraseña nueva (mínimo 12 caracteres).
6. Comprueba que la contraseña anterior no funcione y que el enlace ya utilizado no funcione otra vez.
7. Revisa también Spam si el mensaje no aparece.

## Notas
- No envíes claves de Supabase, secreto de Apps Script, contraseña de Gmail o bootstrap por chat.
- Supabase y Render conectados a ChatGPT **no** significan que se hayan configurado automáticamente las claves privadas.
- Brevo exige verificar el dominio o remitente antes de permitir envíos.
- Google Apps Script, si se elige como alternativa, está sujeto a cuotas de correo de Google.
- Esta integración de correo es independiente de Supabase Auth: AlertaEdu conserva sus propias tablas `users` y tokens.
