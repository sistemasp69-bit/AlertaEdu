IMPORTANTE (RENDER): La autenticación activa es Supabase Auth. Configura el SMTP del proveedor de correo en Supabase Authentication; `BREVO_API_KEY` en Render no configura el restablecimiento de Supabase. Lee CONFIGURAR_RENDER_GMAIL_APPS_SCRIPT.md.

# AlertaEdu — proyecto real Supabase conectado en la nube

- **Proyecto:** AlertaEdu — `lwjnmebmotcnkjrhhbyl` (región São Paulo, Brasil)
- **Dashboard:** https://supabase.com/dashboard/project/lwjnmebmotcnkjrhhbyl
- **API pública:** https://lwjnmebmotcnkjrhhbyl.supabase.co
- **Clave publicable:** incluida en `.env.example` / `.env`. No es contraseña de PostgreSQL.
- **Backend:** Python FastAPI + PostgreSQL de Supabase; no utiliza SQLite en producción.

## Estado verificado
Las 13 tablas del proyecto fueron creadas mediante Supabase, con RLS activado, claves primarias y relaciones. El usuario `anon`/`authenticated` no tiene acceso directo a las tablas académicas. No se han importado alumnos ni cuentas anteriores. La clave privada de la base **NO** se entregó todavía, por eso la conexión de FastAPI desde tu PC sigue pendiente.

## Conectar desde Windows (un solo paso)
1. Extrae el ZIP en una carpeta de Windows.
2. En Supabase, abre el proyecto → **Connect** y revisa el método **Session pooler** (para redes IPv4). Copia la cadena. Necesitarás la **contraseña de base de datos** del proyecto: en Supabase → **Project Settings → Database** puedes restablecerla si no la recuerdas. No pegues contraseñas en ChatGPT.
3. Haz doble clic en `CONFIGURAR_WINDOWS.bat`: pega el Session pooler o pulsa Enter para usar el host directo `lwjnmebmotcnkjrhhbyl`. Introduce la contraseña PostgreSQL **en tu computadora**.
4. (Opcional) Introduce el Gmail remitente y su **contraseña de aplicación** de Google. No uses tu contraseña normal. Activa 2FA y crea una contraseña en https://myaccount.google.com/apppasswords si está disponible.
5. Haz doble clic en `INICIAR_WINDOWS.bat` para instalar dependencias y ejecutar FastAPI. Abre http://127.0.0.1:8000.
6. Para verificar manualmente: `.\.venv\Scripts\python.exe VERIFICAR_CONEXION.py` en PowerShell dentro de la carpeta.

**Importante:** La URL directa que compartiste (`postgresql://postgres:[YOUR-DATABASE-PASSWORD]@db.lwjnmebmotcnkjrhhbyl.supabase.co:5432/postgres`) no contiene una contraseña auténtica. La red de tu PC puede requerir el *Session pooler* en vez del host directo. El valor `sb_publishable_...` es público y no funciona como password de PostgreSQL. Los archivos `.env` no deben subirse a GitHub ni enviarse por correo.

## Recuperación de contraseña por correo
La autenticación activa usa Supabase Auth. El formulario **Olvidé mi contraseña** solicita el enlace a Supabase, y el correo sale por el SMTP configurado en **Supabase > Authentication > SMTP Settings**. Si usas Brevo, configura ahí sus credenciales SMTP y el remitente verificado; la API key de Brevo en Render no conecta este flujo. Añade la URL HTTPS `/reset-password` a las redirecciones permitidas de Supabase. Las tablas `gmail_verified_emails`, `gmail_pending_emails`, `gmail_reset_tokens` y `gmail_request_attempts` pertenecen al flujo heredado de cuentas locales, no al reset activo de Supabase. El envío real todavía no está comprobado.

## Acerca de los comandos Supabase CLI
Los comandos que enviaste (`supabase login`, `supabase init`, `supabase link --project-ref lwjnmebmotcnkjrhhbyl`) vinculan una carpeta local con el proyecto para trabajar con migraciones de esquema, pero **no configuran `DATABASE_URL` de FastAPI**. No son necesarios para ejecutar AlertaEdu en tu PC; la base ya existe en la nube. Si usas CLI, instala una versión vigente, revisa `supabase --help` (CLI v3 tiene cambios) y ejecútalos en tu propia carpeta de trabajo. No guardes tokens de acceso en este ZIP.

## Requerimientos pendientes
La base de datos y seguridad inicial están configuradas. ETL institucional, predicción validada con datos reales, explicabilidad para estudiantes reales, controles de acceso más granulares, notificaciones externas y métricas no funcionales requieren implementación y pruebas adicionales. La aplicación usa autenticación propia en PostgreSQL, **no** Supabase Auth. No la despliegues públicamente antes de una revisión de seguridad y protección de datos.

## Migrar registros anteriores (opcional)
Conserva un respaldo local de tu antiguo archivo SQLite, fuera de este ZIP; tras crear tus tablas y antes de crear cuentas en Supabase, ejecuta `python migrar_desde_sqlite.py RUTA_AL_ARCHIVO.sqlite3` para vista previa y luego `python migrar_desde_sqlite.py RUTA_AL_ARCHIVO.sqlite3 --confirmar`. No se trasladan sesiones ni tokens de recuperación.

## Esquema y correcciones del ZIP final
El archivo `ESQUEMA_SUPABASE.sql` contiene una copia documentada de las 13 tablas para respaldo; **no necesitas ejecutarlo sobre este proyecto** porque ya está creado. Se corrigió el SQL del flujo `Olvidé mi contraseña`, la creación concurrente de la primera cuenta y la importación de `risk_settings` desde SQLite antiguo. Es necesario probar Gmail y PostgreSQL con las credenciales en tu equipo.
