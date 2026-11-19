# Auditoría y cambios de AlertaEdu — 19/11/2026

## Fuente y alcance
- Reconstruido a partir de `AlertaEdu_FINAL_CODIGO_FUENTE_COMPLETO.txt` conservado en Library (18/11/2026); no se tuvo acceso al directorio Windows ni al repositorio GitHub original.
- Backend real identificado: **FastAPI + psycopg PostgreSQL**. Se conservaron las rutas y componentes existentes.
- Supabase accesible por conector: `lwjnmebmotcnkjrhhbyl`, `ACTIVE_HEALTHY`, 14 tablas públicas, RLS activo. Consulta **real** de conteos: estudiantes=0, alertas=0, usuarios Auth=0, roles=0.
- Workspace Render "AlertaEdu" accesible: 0 servicios. No existía despliegue que pudiera verificarse.

## Modificaciones del paquete
- `app/supabase_auth.py` (nuevo): registro, login, correo de recuperación, logout, verificación de tokens contra Supabase Auth, renovación de acceso y roles consultados en PostgreSQL. Sin clave service_role.
- `app/main.py`: integración de Supabase Auth como opción predeterminada, rutas privadas protegidas, exclusión de login heredado y recuperación anterior en modo Supabase, roles de usuarios no privilegiados sin acceso académico, página de restablecimiento, diagnóstico `/healthz` con consulta real a PostgreSQL y método de cambio de contraseña vía Auth.
- `app/static/supabase-login.html` (nuevo): acceso, registro y recuperación por correo.
- `app/static/supabase-reset.html` (nuevo): sesión del enlace y actualización de contraseña mediante SDK oficial, con cierre de sesión posterior.
- `.env.example`, `render.yaml`: variables mínimas de Auth; configuración preparada, despliegue no realizado.
- `requirements.txt`: se añadió `email-validator` para validación de correos de Pydantic.
- `sql/20261119_supabase_auth_roles_audit.sql`: migración de referencia no destructiva para un entorno nuevo; **no se aplicó**, porque la tabla ya existe.

## Pruebas realizadas
- `python -m compileall`: **APROBADO** (compilación de módulos Python).
- `PYTHONPATH=. pytest -q`: **APROBADO**, 16 pruebas preexistentes, centradas en correo/diagnóstico, con dobles/mocks.
- Supabase conector `list_projects`, `list_tables`, `execute_sql` (SELECT) y `get_advisors`: **APROBADO** para accesibilidad y consulta de la base administrada. **NO PROBADO** para conexión psycopg desde Render/PC.
- Envío real Gmail, registro y login real, recuperación completa, predicción sobre datos reales, exportaciones desde navegador y despliegue: **NO PROBADO**. No había cuentas Auth ni estudiantes y falta servicio Render.

## Estado solicitado RF-01 a RF-10 (conservador)
| RF | Estado de verificación | Observación |
| --- | --- | --- |
| RF-01 Carga CSV/Excel | NO PROBADO | Código previo disponible; no se importaron estudiantes al proyecto real. |
| RF-02 CRUD estudiantes | NO PROBADO | Código previo disponible, se requiere conexión backend y prueba E2E. |
| RF-03 Riesgo por reglas | NO PROBADO | Código previo disponible; sin registro real. |
| RF-04 IA y probabilidad | NO PROBADO | No hay evidencia de datos etiquetados de deserción que validen el modelo. No confundir reglas o experimentos UCI con un modelo institucional validado. |
| RF-05 Alertas y seguimiento | NO PROBADO | Las tablas están creadas, vacías. |
| RF-06 Excel/CSV/PDF | NO PROBADO | No se probó descarga en navegador. |
| RF-07 Filtros y búsqueda | NO PROBADO | Código JS previo disponible; faltan datos reales y verificación E2E. |
| RF-08 Actualización programada | NO PROBADO | Hay scripts locales; sin scheduler verificado en Render. |
| RF-09 Supabase Auth | PARCIAL / NO PROBADO E2E | Implementación nueva validada sintácticamente; faltan correo, URLs, cuenta y ejecución real. |
| RF-10 Panel | NO PROBADO | Código previo disponible; sin estudiantes para contrastar cifras. |

## Seguridad, alcance y pendientes
- El reporte de advisors de Supabase indica RLS sin políticas en 14 tablas; **no equivale a una exposición**: hay que revisar `GRANT` antes de otorgar permisos directos de Data API. La estrategia heredada usa SQL por backend. Evitar habilitar políticas permisivas para `anon` o `authenticated` por comodidad.
- El documento universitario adjunto original exige **RF-01 a RF-14**; adicionalmente incluye XAI, reentrenamiento/versiones, eficiencia de intervenciones y permisos académicos granulares. El RF-01..RF-10 reformulado por el usuario no sustituye estos criterios.
- No se alteraron registros existentes ni se ejecutaron migraciones de producción: la tabla de roles existía, sin usuarios todavía.
- No se puede asignar administrador automáticamente al primer usuario desde el cliente. Después del primer registro y verificación, un administrador autorizado debe asignar el rol contra UUID validado, mediante panel SQL de Supabase.
- En modo Supabase se deshabilita la administración heredada de usuarios `/api/users`; requiere implementar gestión de usuarios Auth mediante una ruta administrativa segura en una iteración posterior.
- El acceso detallado por asignaciones (Docente/Directivo) aún no está implementado; esos roles se bloquean conservadoramente.
- La implementación necesita revisión de seguridad, tests E2E y validación de correos antes de exposición institucional; **no se considera producción terminada**.

## Pasos mínimos
1. En Supabase Auth > URL Configuration: Site URL `http://127.0.0.1:8000` (local) y luego dominio real `https://<servicio>.onrender.com`; agregar Redirect URLs `http://127.0.0.1:8000/reset-password`, `http://localhost:8000/reset-password` y la URL de Render con `/reset-password`.
2. Activar confirmación de correo y configurar SMTP autorizado de Supabase Auth si el proveedor integrado limita los destinatarios. Este flujo no requiere contraseña normal de Gmail ni el Apps Script anterior.
3. En Render usar `render.yaml`, establecer `DATABASE_URL` PostgreSQL de Session Pooler desde Connect (contraseña URL-encoded si contiene caracteres especiales), `SUPABASE_PUBLISHABLE_KEY` y opcional `ALERTAEDU_BASE_URL`; no guardar secretos en GitHub.
4. El código mantiene `ALERTAEDU_AUTH_PROVIDER=supabase` como predeterminado. Para la migración temporal, el proveedor heredado puede habilitarse sólo en un entorno aislado, no producción.
5. Instalar `pip install -r requirements.txt`, probar `python VERIFICAR_CONEXION.py` y ejecutar `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
6. Iniciar sesión con usuario verificado; un administrador del proyecto debe asignar su UUID a `public.auth_roles` con rol `Administrador` antes de usar el módulo académico.

## Atención a los enlaces de recuperación
Supabase Auth envía el email. El frontend recibe el enlace firmado y la sesión de recuperación, actualiza contraseña mediante Supabase Auth y cierra sesión; la eficacia depende de una URL de redirección permitida y de la entrega de correo real. **No se han enviado correos en este trabajo.**
