# AlertaEdu — configuración final Brevo + Render + Supabase

## Estado
- Supabase ya está creado y su esquema remoto tiene 13 tablas protegidas. Proyecto `lwjnmebmotcnkjrhhbyl`.
- `render.yaml` prepara el servicio Python en Render, pero **aún no hay un servicio publicado** en el workspace `AlertaEdu`.
- El despliegue usa **Brevo** para los correos transaccionales.
- Las pruebas automáticas no envían correos reales; verifica el envío con una dirección a la que puedas acceder.

## A. Arrancar desde Visual Studio Code en Windows
1. Descomprime el ZIP y abre la carpeta `AlertaEdu` en Visual Studio Code.
2. Ejecuta `CONFIGURAR_WINDOWS.bat` si no tienes un `.env` correcto. Introduce localmente tu Session pooler y la contraseña PostgreSQL real (no la escribas en el chat).
3. Ejecuta `DIAGNOSTICAR_WINDOWS.bat` para comprobar formato, y luego `VERIFICAR_CONEXION.py` para probar una conexión real.
4. Ejecuta `INICIAR_WINDOWS.bat`; si muestra `Application startup complete`, abre http://127.0.0.1:8000.

## B. Configurar Brevo
1. Verifica tu dominio o remitente en Brevo y habilita el envío de correos transaccionales.
2. Crea una API key privada para enviar correos transaccionales.
3. En Render > Environment añade `BREVO_API_KEY` y `BREVO_FROM_EMAIL` (el remitente verificado). No las guardes en GitHub ni las compartas por chat.
4. Envía una prueba de verificación/recuperación y confirma su recepción, incluyendo la carpeta de spam.

## C. Publicar AlertaEdu en Render
1. Crea un repositorio Git **privado** con el contenido de la carpeta `AlertaEdu` (NO subas `.env`, `.venv`, claves, datos privados o credenciales).
2. En Render selecciona el nuevo workspace **AlertaEdu** y crea **New → Blueprint** desde el repositorio con `render.yaml` en la raíz.
3. Configura estas variables privadas en Environment, sin mostrarlas en el chat:
   - `DATABASE_URL`: cadena PostgreSQL Session pooler de Supabase, con contraseña real codificada para URL.
   - `ALERTAEDU_BOOTSTRAP_TOKEN`: cadena aleatoria de 24+ caracteres para el primer administrador.
   - `BREVO_API_KEY`: la API key privada de Brevo.
   - `BREVO_FROM_EMAIL`: remitente verificado en Brevo.
4. El Blueprint fija `ALERTAEDU_ENV=production`, `ALERTAEDU_EMAIL_PROVIDER=brevo`, `ALERTAEDU_SEED_DEMO=0`. No añadas `.env` al repositorio.
5. Render debe iniciar con `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` y responder a `/healthz`.
6. Cuando Render marque el despliegue como **Live**, utiliza la URL HTTPS **real** proporcionada. Para un dominio personalizado, añade `ALERTAEDU_BASE_URL=https://tudominio.com` en Render; para un subdominio `onrender.com` puede utilizarse `RENDER_EXTERNAL_URL`.

## D. Comprobar recuperación de contraseña
1. Abre la URL pública `/setup` y crea la primera cuenta con el `ALERTAEDU_BOOTSTRAP_TOKEN` privado.
2. Inicia sesión y vincula tu Gmail como correo de recuperación (requiere tu contraseña actual). Verifica el enlace que llega a Gmail.
3. Cierra sesión, pulsa **¿Olvidaste tu contraseña?**, escribe ese Gmail verificado y recibe el enlace de 15 minutos.
4. Cambia la contraseña (mínimo 12 caracteres). Comprueba que la anterior ya no funcione y que el token no pueda reutilizarse.

## E. Importante
- No confundir contraseña PostgreSQL con contraseña de inicio de sesión AlertaEdu ni con cuenta Gmail.
- La clave Supabase `sb_publishable_...` no es una contraseña PostgreSQL.
- La integración actual usa **usuarios de AlertaEdu en PostgreSQL**, no Supabase Auth.
- No está publicada todavía ni se ha comprobado la entrega real de correo desde este entorno.
- Para manejar datos personales reales, completa la revisión de controles de acceso, seguridad y privacidad antes de abrir el servicio al público.
