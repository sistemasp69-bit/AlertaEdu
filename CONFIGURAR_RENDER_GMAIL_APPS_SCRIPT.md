# AlertaEdu: configuración Render + Supabase Auth + correo

## 1. Lo que ya existe
- Organización Supabase: sistemasp69-bit's Org.
- Proyecto Supabase: `lwjnmebmotcnkjrhhbyl`.
- Workspace Render autorizado: `AlertaEdu` (no el anterior `My Workspace`).
- Las 13 tablas en Supabase están creadas; todavía no hay estudiantes ni usuarios iniciales.

## 2. Configura el correo de recuperación en Supabase
1. Verifica tu dominio o remitente en Brevo y habilita el envío de correos transaccionales.
2. En Supabase > Authentication > SMTP Settings habilita el SMTP personalizado e introduce las credenciales SMTP de Brevo y el remitente verificado. La API key de Brevo no sustituye las credenciales SMTP.
3. En Supabase > Authentication > URL Configuration define el `Site URL` como el dominio HTTPS de Render y permite `https://TU-DOMINIO/reset-password` como URL de redirección.
4. La pantalla activa usa Supabase Auth: el envío del correo lo controla Supabase SMTP, no `BREVO_API_KEY` en Render. Las variables de la integración Brevo API del servidor sólo corresponden a la recuperación heredada de usuarios locales.

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
Esta alternativa corresponde a la recuperación heredada de usuarios locales; no reemplaza el SMTP de Supabase Auth usado por el despliegue actual.

## 3. Sube AlertaEdu a GitHub
1. Este proyecto usa el repositorio `https://github.com/sistemasp69-bit/AlertaEdu`.
2. Sube **el contenido de esta carpeta** (por ejemplo `app/`, `render.yaml`, `requirements.txt`),
   no el ZIP. El repositorio actual es público: no subas archivos `.env`, contraseñas, datos personales o tokens.
3. Copia la URL real de ese repositorio. Render requiere el repositorio para publicar.

## 4. Crea el Web Service en Render (workspace nuevo AlertaEdu)
1. En https://dashboard.render.com cambia al workspace **AlertaEdu**.
2. Selecciona New > Web Service (o New > Blueprint) y conecta el repositorio GitHub.
3. Para Blueprint, usa `render.yaml` en la raíz.
4. Añade los secretos en **Environment**, NUNCA en GitHub:
   - `DATABASE_URL`: conexión Supabase > Connect > **Session pooler** (incluye contraseña; usar URL codificada).
   Los demás valores ya están en `render.yaml` (`ALERTAEDU_ENV=production`, `ALERTAEDU_AUTH_PROVIDER=supabase`, `ALERTAEDU_SEED_DEMO=0`).
5. Para arrancar el servidor automáticamente, Render usa:
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
6. Comprueba que la implementación quede Live y abre la URL HTTPS real `*.onrender.com`. La URL no existe hasta que Render termine de crear el servicio.

## 5. Prueba recuperación real
1. Crea una cuenta en `/login` usando el registro de Supabase Auth y confirma el correo de registro.
2. Asigna el rol institucional apropiado a la cuenta confirmada mediante un procedimiento administrativo autorizado.
3. En `/login`, pulsa **¿Olvidaste tu contraseña?** e introduce el correo de esa cuenta.
4. Comprueba que llegue el enlace desde Supabase SMTP (revisa también Spam) y que abra `/reset-password`.
5. Cambia la contraseña y vuelve a iniciar sesión con ella.
6. Solicita un enlace nuevo y confirma que los enlaces anteriores ya no permiten restablecerla.

## Notas
- No envíes claves de Supabase, secreto de Apps Script, contraseña de Gmail o bootstrap por chat.
- Supabase y Render conectados a ChatGPT **no** significan que se hayan configurado automáticamente las claves privadas.
- Brevo exige verificar el dominio o remitente antes de permitir envíos. El SMTP de Supabase y sus URL permitidas deben configurarse por separado.
- Google Apps Script, si se elige como alternativa, está sujeto a cuotas de correo de Google.
- Esta integración de correo es independiente de Supabase Auth: AlertaEdu conserva sus propias tablas `users` y tokens.
