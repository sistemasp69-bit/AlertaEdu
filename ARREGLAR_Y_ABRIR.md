# AlertaEdu — solución para arrancar desde Visual Studio Code

Este ZIP contiene el código y la configuración **sin contraseñas**. La base real ya está en Supabase; **no crees otra**.

## 1. Abre la carpeta correcta

En VS Code abre la carpeta `AlertaEdu` (la que contiene `requirements.txt` y `app/`). Si estás en la carpeta exterior, usa:

```powershell
cd .\AlertaEdu
```

## 2. Recupera tu .env o reconfigura

El ZIP no trae `.env`: son credenciales privadas. Si ya configuraste uno en tu PC, conserva ese archivo antes de reemplazar la carpeta; si no existe o está incompleto, ejecuta:

```powershell
.\CONFIGURAR_WINDOWS.bat
```

1. En Supabase → Connect → Method: **Session pooler**, copia la URL que incluye `postgres.ID_PROYECTO` y el host `pooler.supabase.com` (puerto 5432).
2. Pega **esa URL completa** en la pregunta de Session pooler, no solo la contraseña.
3. Cuando solicite **Contraseña PostgreSQL**, introduce la contraseña real que hayas definido en Supabase (no el texto `[YOUR-DATABASE-PASSWORD]`). La contraseña no se muestra en pantalla.
4. Si no quieres configurar Gmail local todavía, presiona Enter. Si ya estaba configurado, se conserva.
5. No publiques `.env` en GitHub ni lo envíes por chat.

## 3. Diagnóstico sin mostrar secretos

```powershell
python DIAGNOSTICAR_CONFIGURACION.py
python VERIFICAR_CONEXION.py
```

`DIAGNOSTICAR_CONFIGURACION.py` confirma el formato sin conectarse; `VERIFICAR_CONEXION.py` prueba la conexión **real**.

## 4. Arranca el servidor

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abre `http://127.0.0.1:8000` solo cuando aparezca `Application startup complete`. Alternativamente, doble clic en `INICIAR_WINDOWS.bat`.

## 5. Correo Gmail

Conexión a Supabase y entrega Gmail son pruebas diferentes. Para Gmail local usa una contraseña **de aplicación** con Google 2FA; para Render está preparado Google Apps Script, que requiere una Web App `/exec` y secreto propio. Ninguno se prueba solo por iniciar el servidor.

No se ha incluido ninguna contraseña privada, correo enviado ni verificación de despliegue en Render.
