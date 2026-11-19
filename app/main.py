"""AlertaEdu: gestión académica respaldada por PostgreSQL en Supabase."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from contextlib import contextmanager
import json
import os
import math
import re
from app import db as database
from app import supabase_auth
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from app.ia_core import model_status, predict_probability
from app.rf05_rf08 import init_extra_tables, configured_rule_result, maybe_create_alert, router as rf_router

ROOT = Path(__file__).resolve().parent
DB = 'Supabase PostgreSQL'
app = FastAPI(title='AlertaEdu - Gestión académica', version='0.4.0', description='Estudiantes ficticios. Evaluación orientativa, NO predicción de machine learning.')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

SEED = [
 ('EST-001','María Zambrano','Computación',2,6.5,61,'Alto','Pendiente',[{'nombre':'Matemáticas Discretas','nota':5.5},{'nombre':'Programación II','nota':5.8},{'nombre':'Bases de Datos','nota':6.2}]),
 ('EST-002','Carlos Vera','Administración',3,5.9,62,'Alto','En seguimiento',[{'nombre':'Contabilidad','nota':5.4},{'nombre':'Estadística','nota':5.8},{'nombre':'Economía','nota':6.0}]),
 ('EST-003','Andrea Torres','Computación',5,8.9,96,'Bajo','Pendiente',[]),
 ('EST-004','José Mendoza','Contabilidad',1,6.1,68,'Alto','Pendiente',[{'nombre':'Matemáticas','nota':5.2},{'nombre':'Introducción contable','nota':6.0}]),
 ('EST-005','Valentina López','Administración',4,7.8,91,'Bajo','Atendido',[]),
 ('EST-006','Pedro Castillo','Computación',6,7.0,77,'Medio','Pendiente',[{'nombre':'Redes','nota':6.4},{'nombre':'Sistemas Operativos','nota':6.1}]),
 ('EST-007','Sofía Moreno','Contabilidad',2,8.3,94,'Bajo','Atendido',[]),
 ('EST-008','Luis Ramírez','Computación',3,6.4,71,'Medio','Pendiente',[{'nombre':'Algoritmos','nota':5.9},{'nombre':'Cálculo','nota':6.0}]),
]

@contextmanager
def conn():
    c = database.connect(DB, timeout=10)
    c.row_factory = database.Row
    try:
        yield c
    except BaseException:
        # Una solicitud fallida no debe dejar escrituras a medias en PostgreSQL.
        c.rollback()
        raise
    else:
        c.commit()
    finally:
        c.close()

def init_db():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, nombre TEXT NOT NULL, carrera TEXT NOT NULL, semestre INTEGER NOT NULL, promedio REAL NOT NULL, asistencia REAL NOT NULL, riesgo TEXT NOT NULL, estado TEXT NOT NULL, materias TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS followups (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, tipo TEXT NOT NULL, responsable TEXT NOT NULL, nota TEXT NOT NULL, fecha TEXT NOT NULL, FOREIGN KEY(student_id) REFERENCES students(id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            promedio REAL NOT NULL,
            asistencia REAL NOT NULL,
            reprobadas INTEGER NOT NULL,
            puntos INTEGER NOT NULL,
            max_puntos INTEGER NOT NULL,
            nivel TEXT NOT NULL,
            metodo TEXT NOT NULL,
            fecha TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_student ON evaluations(student_id, id DESC)')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            csrf_token TEXT NOT NULL,
            expires INTEGER NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires)')
        c.execute('''CREATE TABLE IF NOT EXISTS ml_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL,
            probability REAL NOT NULL CHECK(probability >= 0 AND probability <= 1),
            level TEXT NOT NULL, model_version TEXT NOT NULL, date TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_ml_student ON ml_predictions(student_id, id DESC)')

        n = c.execute('SELECT COUNT(*) FROM students').fetchone()[0]
        if not n and os.environ.get('ALERTAEDU_SEED_DEMO','0') == '1':
            c.executemany('INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)', [(a,b,d,e,f,g,h,i,json.dumps(j,ensure_ascii=False)) for a,b,d,e,f,g,h,i,j in SEED])

init_db()
init_extra_tables(DB)
app.include_router(rf_router)
app.include_router(supabase_auth.router)

# Inicio de sesión del proyecto: usuarios y sesiones almacenados en Supabase.
# La recuperación Gmail reutiliza tokens temporales de un solo uso.
COOKIE_NAME = 'alertaedu_session'
SESSION_SECONDS = 12 * 60 * 60
ROLES = ('Administrador', 'Tutor', 'Docente', 'Directivo')


def password_hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 310000
    ).hex()


def users_exist() -> bool:
    with conn() as c:
        return c.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None


def current_session(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    token_digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with conn() as c:
        r = c.execute('''SELECT s.username, s.csrf_token, s.expires, u.role
                         FROM sessions s JOIN users u ON s.username=u.username
                         WHERE s.token_hash=? AND u.active=1''', (token_digest,)).fetchone()
    if r is None or r['expires'] < int(time.time()):
        return None
    return dict(r)


@app.middleware('http')
async def protect_routes(request: Request, call_next):
    path, method = request.url.path, request.method
    public = {'/login', '/setup', '/reset-password', '/healthz', '/api/supabase/config', '/api/supabase/register', '/api/supabase/login', '/api/supabase/forgot', '/api/auth/status', '/api/auth/login',
              '/api/auth/bootstrap', '/api/auth/email/forgot', '/api/auth/email/reset', '/api/auth/email/verify', '/favicon.ico'}
    if path in public or (path.startswith('/static/') and path != '/static/index.html'):
        return await call_next(request)

    auth, refreshed = await supabase_auth.resolve_user(request) if supabase_auth.enabled() else (current_session(request), None)
    if supabase_auth.enabled() and path.startswith(('/api/auth/email/', '/api/auth/bootstrap', '/api/auth/login', '/api/users')):
        return JSONResponse({'detail':'Usa Supabase Auth; las cuentas antiguas están deshabilitadas'},status_code=410)
    if not auth:
        if path.startswith('/api/') or path in ('/openapi.json', '/docs', '/redoc'):
            return JSONResponse({'detail':'Debes iniciar sesión'}, status_code=401)
        target = '/login' if supabase_auth.enabled() or users_exist() else '/setup'
        return RedirectResponse(target, status_code=303)
    request.state.user = auth

    if supabase_auth.enabled() and auth['role'] in ('Usuario','Docente','Directivo') and path not in ('/api/auth/me','/api/auth/logout','/api/auth/change-password','/api/health'):
        return JSONResponse({'detail':'No tienes permiso para acceder a datos académicos'},status_code=403)
    if path == '/api/users' and auth['role'] != 'Administrador':
        return JSONResponse({'detail': 'Solo el administrador puede administrar usuarios'}, status_code=403)

    if path.startswith('/api/') and method not in ('GET', 'HEAD', 'OPTIONS'):
        # La cookie de sesión no debe poder usarse para mutaciones cross-site.
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), auth['csrf_token']):
            return JSONResponse({'detail': 'Sesión desactualizada; recarga la página'}, status_code=403)
        admin_only = (
            path == '/api/users' or
            path == '/api/students' or
            (path.startswith('/api/students/') and method in ('PUT', 'DELETE')) or
            path in ('/api/import/preview', '/api/import/students')
        )
        tutor_or_admin = (
            path == '/api/evaluations/auto' or
            path.startswith('/api/ia/predecir/') or
            path == '/api/ia/uci/predecir' or
            path == '/api/scenario' or
            path == '/api/predict' or
            (path.startswith('/api/students/') and
             (path.endswith('/evaluations') or path.endswith('/followups')))
        )
        if admin_only and auth['role'] != 'Administrador':
            return JSONResponse({'detail': 'Esta operación requiere un administrador'}, status_code=403)
        if tutor_or_admin and auth['role'] not in ('Administrador', 'Tutor'):
            return JSONResponse({'detail': 'Solo administradores y tutores pueden evaluar o registrar seguimiento'}, status_code=403)
    response = await call_next(request)
    if refreshed:
        supabase_auth.set_cookies(response,refreshed)
    return response


class LoginForm(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class CreateUser(LoginForm):
    role: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


@app.get('/api/auth/status')
def auth_status():
    return {'initialized': users_exist()}


@app.post('/api/auth/bootstrap', status_code=201)
def bootstrap(data: LoginForm, request: Request):
    # On a public deployment the first administrator must be authorized with a secret
    # configured outside the code/repository. No secret appears in any response.
    if os.environ.get('ALERTAEDU_ENV', '').strip().lower() == 'production':
        expected_token = os.environ.get('ALERTAEDU_BOOTSTRAP_TOKEN', '')
        received_token = request.headers.get('X-Setup-Token', '')
        if len(expected_token) < 24:
            raise HTTPException(503, 'Configura ALERTAEDU_BOOTSTRAP_TOKEN en el servidor (mínimo 24 caracteres).')
        if not hmac.compare_digest(received_token, expected_token):
            raise HTTPException(403, 'Código privado de instalación incorrecto')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', data.username):
        raise HTTPException(422, 'El usuario debe tener de 3 a 40 caracteres: letras, números, puntos, guiones o _')
    if len(data.password) < 10:
        raise HTTPException(422, 'La contraseña inicial debe tener al menos 10 caracteres')
    with conn() as c:
        c.execute('SELECT pg_advisory_xact_lock(9283117045)')
        if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise HTTPException(409, 'Ya existe una cuenta. Inicia sesión.')
        salt = secrets.token_hex(16)
        c.execute('INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)',
                  (data.username, password_hash(data.password, salt), salt, 'Administrador'))
    return {'created': True}


@app.post('/api/auth/login')
def login(data: LoginForm):
    with conn() as c:
        r = c.execute('SELECT * FROM users WHERE username=? AND active=1',
                      (data.username,)).fetchone()
    expected = password_hash(data.password, r['salt'] if r else '00'*16)
    if not r or not hmac.compare_digest(expected, r['password_hash']):
        raise HTTPException(401, 'Usuario o contraseña incorrectos')
    token = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    with conn() as c:
        c.execute('DELETE FROM sessions WHERE expires < ?', (int(time.time()),))
        c.execute('INSERT INTO sessions (token_hash, username, csrf_token, expires) VALUES (?, ?, ?, ?)',
                  (hashlib.sha256(token.encode('utf-8')).hexdigest(), data.username,
                   csrf, int(time.time())+SESSION_SECONDS))
    response = JSONResponse({'ok': True, 'role': r['role']})
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite='strict', secure=os.environ.get('ALERTAEDU_ENV', '').strip().lower() == 'production',
                        max_age=SESSION_SECONDS, path='/')
    return response


@app.get('/api/auth/me')
def whoami(request: Request):
    u = request.state.user
    return {'username':u['username'], 'role':u['role'], 'csrf_token':u['csrf_token']}


@app.post('/api/auth/logout')
async def logout(request: Request):
    if supabase_auth.enabled():
        return await supabase_auth.logout(request)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with conn() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?',
                      (hashlib.sha256(token.encode('utf-8')).hexdigest(),))
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE_NAME, path='/')
    return response


@app.post('/api/auth/change-password')
async def change_password(request: Request, data: PasswordChange):
    if supabase_auth.enabled():
        result = await supabase_auth.change_password(request,data.current_password,data.new_password)
        return result
    username = request.state.user['username']
    with conn() as c:
        r = c.execute('SELECT * FROM users WHERE username=? AND active=1',
                      (username,)).fetchone()
        if not r or not hmac.compare_digest(
            password_hash(data.current_password, r['salt']), r['password_hash']
        ):
            raise HTTPException(401, 'La contraseña actual no es correcta')
        if hmac.compare_digest(data.current_password, data.new_password):
            raise HTTPException(422, 'La contraseña nueva debe ser diferente')
        salt = secrets.token_hex(16)
        c.execute('UPDATE users SET password_hash=?, salt=? WHERE username=?',
                  (password_hash(data.new_password, salt), salt, username))
        c.execute('DELETE FROM sessions WHERE username=?', (username,))
    response = JSONResponse({'changed': True, 'message': 'Contraseña actualizada; vuelve a iniciar sesión'})
    response.delete_cookie(COOKIE_NAME, path='/')
    return response


@app.get('/api/users')
def list_users():
    with conn() as c:
        rows = c.execute('SELECT username, role, active FROM users ORDER BY username').fetchall()
        return {'items': [dict(r) for r in rows]}


@app.post('/api/users', status_code=201)
def create_user(data: CreateUser):
    if data.role not in ROLES:
        raise HTTPException(422, 'Rol no válido')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', data.username):
        raise HTTPException(422, 'Nombre de usuario no válido')
    if len(data.password) < 10:
        raise HTTPException(422, 'La contraseña debe tener al menos 10 caracteres')
    salt = secrets.token_hex(16)
    try:
        with conn() as c:
            c.execute('INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)',
                      (data.username, password_hash(data.password, salt), salt, data.role))
    except database.IntegrityError as exc:
        raise HTTPException(409, 'Ese nombre de usuario ya existe') from exc
    return {'username': data.username, 'role': data.role}


@app.get('/login', include_in_schema=False)
def login_page():
    return FileResponse(ROOT / 'static' / ('supabase-login.html' if supabase_auth.enabled() else 'login.html'))


@app.get('/setup', include_in_schema=False)
def setup_page():
    return FileResponse(ROOT / 'static' / ('supabase-login.html' if supabase_auth.enabled() else 'login.html'))

@app.get('/reset-password', include_in_schema=False)
def reset_password_page():
    return FileResponse(ROOT / 'static' / 'supabase-reset.html')


class Materia(BaseModel):
    nombre: str = Field(min_length=1,max_length=100)
    nota: float = Field(ge=0,le=10)

class StudentIn(BaseModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{2,32}$')
    nombre: str = Field(min_length=2,max_length=100)
    carrera: str = Field(min_length=2,max_length=80)
    semestre: int = Field(ge=1,le=15)
    promedio: float = Field(ge=0,le=10)
    asistencia: float = Field(ge=0,le=100)
    materias: list[Materia] = Field(default_factory=list,max_length=30)

class Followup(BaseModel):
    estado: str
    responsable: str = Field(min_length=2,max_length=100)
    nota: str = Field(min_length=3,max_length=1000)
    tipo: str = 'Seguimiento académico'

def row_student(r):
    d=dict(r); d['materias']=json.loads(d['materias']);d['reprobadas']=len(d['materias']);return d

def get_student(c,sid):
    row=c.execute('SELECT * FROM students WHERE id=?',(sid,)).fetchone()
    if not row: raise HTTPException(status_code=404,detail='Estudiante no encontrado')
    return row_student(row)

@app.get('/')
def index():return FileResponse(ROOT/'static'/'index.html')

@app.get('/healthz', include_in_schema=False)
def readiness():
    try:
        with conn() as c: c.execute('SELECT 1').fetchone()
    except Exception:
        return JSONResponse({'status':'unavailable','database_connected':False},status_code=503)
    return {'status':'ok','database_connected':True}

@app.get('/api/health')
def health():
    with conn() as c: c.execute('SELECT 1').fetchone()
    return {'ok':True,'database_connected':True,'database':'Supabase PostgreSQL','model_trained':model_status()['disponible'],'data_type':'registros de Supabase; origen no validado', 'excel_import_enabled': True}

@app.get('/api/students')
def students():
    with conn() as c: items=[row_student(r) for r in c.execute('SELECT * FROM students ORDER BY id').fetchall()]
    return {'items':items,'count':len(items),'source':'supabase_postgresql'}

@app.get('/api/students/{sid}')
def student(sid:str):
    with conn() as c: return get_student(c,sid)

@app.post('/api/students',status_code=201)
def add_student(s:StudentIn):
    with conn() as c:
        if c.execute('SELECT id FROM students WHERE id=?',(s.id,)).fetchone():raise HTTPException(409,'El código ya existe')
        c.execute('INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)',(s.id,s.nombre,s.carrera,s.semestre,s.promedio,s.asistencia,'Sin evaluar','Pendiente',json.dumps([m.model_dump() for m in s.materias],ensure_ascii=False)))
        _auto_evaluate_student(c, s)
        return get_student(c,s.id)

@app.put('/api/students/{sid}')
def update_student(sid:str,s:StudentIn):
    if sid!=s.id:raise HTTPException(400,'No se puede modificar el código del estudiante')
    with conn() as c:
        old=get_student(c,sid)
        nuevo_json = json.dumps([m.model_dump() for m in s.materias], ensure_ascii=False)
        changed_academic = (old['promedio'] != s.promedio or old['asistencia'] != s.asistencia
                            or old['materias'] != [m.model_dump() for m in s.materias])
        c.execute('UPDATE students SET nombre=?,carrera=?,semestre=?,promedio=?,asistencia=?,materias=? WHERE id=?',
                  (s.nombre,s.carrera,s.semestre,s.promedio,s.asistencia,nuevo_json,sid))
        if changed_academic or old['riesgo'] == 'Sin evaluar':
            _auto_evaluate_student(c, s)
        return get_student(c,sid)

@app.delete('/api/students/{sid}')
def delete_student(sid:str):
    with conn() as c:
        get_student(c,sid)
        c.execute('DELETE FROM academic_alert_events WHERE alert_id IN (SELECT id FROM academic_alerts WHERE student_id=?)',(sid,))
        c.execute('DELETE FROM academic_alerts WHERE student_id=?',(sid,))
        c.execute('DELETE FROM ml_predictions WHERE student_id=?',(sid,))
        c.execute('DELETE FROM evaluations WHERE student_id=?',(sid,))
        c.execute('DELETE FROM followups WHERE student_id=?',(sid,))
        c.execute('DELETE FROM students WHERE id=?',(sid,))
    return {'deleted':sid}

@app.post('/api/students/{sid}/followups',status_code=201)
def add_followup(sid:str, f:Followup):
    if f.estado not in ('Pendiente','En seguimiento','Atendido'):raise HTTPException(422,'Estado inválido')
    with conn() as c:
        get_student(c,sid)
        c.execute('UPDATE students SET estado=? WHERE id=?',(f.estado,sid))
        cur=c.execute('INSERT INTO followups (student_id,tipo,responsable,nota,fecha) VALUES (?,?,?,?,?)',(sid,f.tipo,f.responsable,f.nota,datetime.now(timezone.utc).isoformat()))
        return {'id':cur.lastrowid,'student_id':sid,'estado':f.estado}

@app.get('/api/students/{sid}/followups')
def list_followups(sid:str):
    with conn() as c:
        get_student(c,sid)
        return {'items':[dict(r) for r in c.execute('SELECT * FROM followups WHERE student_id=? ORDER BY id DESC',(sid,))]}

@app.get('/api/summary')
def summary():
    items=students()['items'];return {'total':len(items),'high':sum(x['riesgo']=='Alto' for x in items),'medium':sum(x['riesgo']=='Medio' for x in items),'low':sum(x['riesgo']=='Bajo' for x in items),'follow_up':sum(x['estado']=='En seguimiento' for x in items),'unevaluated':sum(x['riesgo']=='Sin evaluar' for x in items)}

class Scenario(BaseModel):
    promedio:float=Field(ge=0,le=10)
    asistencia:float=Field(ge=0,le=100)
    reprobadas:int=Field(ge=0,le=30)

# [RF05-RF08-BEGIN]
def calculate_rules(s: Scenario):
    return configured_rule_result(s, DB)
# [RF05-RF08-END]


def _record_evaluation(c, sid: str, scenario: Scenario, automatic: bool = False):
    """Clasifica y persiste dentro de la transacción de la operación llamante."""
    previous = c.execute('SELECT puntos,nivel FROM evaluations WHERE student_id=? ORDER BY id DESC LIMIT 1', (sid,)).fetchone()
    result = calculate_rules(scenario)
    metodo = ('Clasificación automática al registrar/importar; ' if automatic else 'Evaluación manual; ')
    metodo += 'reglas académicas ilustrativas, NO IA ni probabilidad de deserción'
    fecha = datetime.now(timezone.utc).isoformat()
    cursor = c.execute('''INSERT INTO evaluations
        (student_id, promedio, asistencia, reprobadas, puntos, max_puntos, nivel, metodo, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (sid, scenario.promedio, scenario.asistencia, scenario.reprobadas,
         result['puntos'], result['max_puntos'], result['nivel_orientativo'], metodo, fecha))
    c.execute('UPDATE students SET riesgo=? WHERE id=?', (result['nivel_orientativo'], sid))
    maybe_create_alert(c, sid, previous, result, fecha)
    return {'id': cursor.lastrowid, 'student_id': sid, 'fecha': fecha,
            'guardado': True, 'automatico': automatic, **result}


def _auto_evaluate_student(c, s: StudentIn):
    scenario = Scenario(promedio=s.promedio, asistencia=s.asistencia, reprobadas=len(s.materias))
    return _record_evaluation(c, s.id, scenario, automatic=True)


def _risk_totals():
    return {'Alto': 0, 'Medio': 0, 'Bajo': 0}

@app.post('/api/scenario')
def scenario(s:Scenario):
    # Prueba sin guardar.
    return calculate_rules(s)

@app.post('/api/students/{sid}/evaluations',status_code=201)
def save_evaluation(sid: str, s: Scenario):
    # Evaluación manual conserva los datos de la ficha y añade una entrada al historial.
    with conn() as c:
        get_student(c, sid)
        return _record_evaluation(c, sid, s, automatic=False)


@app.post('/api/evaluations/auto')
def auto_evaluate_pending():
    """Evalúa SOLO estudiantes 'Sin evaluar' (útil tras importaciones previas)."""
    results = _risk_totals()
    processed = 0
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        rows = c.execute("SELECT * FROM students WHERE riesgo='Sin evaluar' ORDER BY id").fetchall()
        for row in rows:
            s = row_student(row)
            scenario = Scenario(promedio=s['promedio'], asistencia=s['asistencia'], reprobadas=s['reprobadas'])
            result = _record_evaluation(c, s['id'], scenario, automatic=True)
            results[result['nivel_orientativo']] += 1
            processed += 1
    return {'guardado': True, 'evaluados': processed, 'por_nivel': results,
            'metodo': 'Reglas orientativas, NO IA',
            'mensaje': 'Los resultados se guardaron en Supabase PostgreSQL y en el historial académico.'}


@app.get('/api/students/{sid}/evaluations')
def list_evaluations(sid: str):
    with conn() as c:
        get_student(c,sid)
        entries=[dict(r) for r in c.execute('SELECT * FROM evaluations WHERE student_id=? ORDER BY id DESC',(sid,))]
        return {'items':entries,'count':len(entries)}

@app.post('/api/predict')
def predict_unavailable():
    raise HTTPException(status_code=503,detail='No hay modelo entrenado integrado en este proyecto. Usa /api/scenario para una orientación no predictiva.')

@app.get('/api/ia/estado')
def ml_model_status():
    return model_status()


@app.post('/api/ia/predecir/{sid}', status_code=201)
def predict_ml_for_student(sid: str):
    try:
        with conn() as c:
            s = get_student(c, sid)
            result = predict_probability(s['promedio'], s['asistencia'], s['reprobadas'])
            fecha = datetime.now(timezone.utc).isoformat()
            cur = c.execute('''INSERT INTO ml_predictions
                (student_id, probability, level, model_version, date)
                VALUES (?, ?, ?, ?, ?)''',
                (sid, result['probabilidad_desercion'], result['nivel_ia'],
                 result['modelo_version'], fecha))
            return {'guardado': True, 'id': cur.lastrowid, 'estudiante': sid, 'fecha': fecha, **result}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get('/api/ia/historial/{sid}')
def ml_history(sid: str):
    with conn() as c:
        get_student(c, sid)
        return {'items': [dict(r) for r in c.execute(
            'SELECT * FROM ml_predictions WHERE student_id=? ORDER BY id DESC LIMIT 100', (sid,))]}



# [RF04-UCI-LAB-BEGIN]
from app.uci_demo import status as uci_demo_status, predict_test_case as uci_predict_case

class UCITestSelection(BaseModel):
    caso: int = Field(ge=1, le=100000)

@app.get('/api/ia/uci/estado')
def uci_experiment_status():
    return uci_demo_status()

@app.post('/api/ia/uci/predecir')
def uci_experiment_predict(data: UCITestSelection):
    try:
        return uci_predict_case(data.caso)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
# [RF04-UCI-LAB-END]


# [RF06-RF07-BEGIN]
# Laboratorio explicable sobre casos históricos UCI. No evalúa estudiantes Supabase PostgreSQL.
from app.uci_xai import explicar as explicar_uci
from app.uci_versions import listar as listar_versiones_uci

@app.get('/api/ia/uci/explicar')
def explicar_caso_uci(caso: int):
    if not 1 <= caso <= 100000:
        raise HTTPException(422, 'Caso fuera de rango')
    try:
        return explicar_uci(caso)
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError, ImportError) as exc:
        raise HTTPException(503, detail='Explicación SHAP no disponible: '+str(exc)) from exc

@app.get('/api/ia/uci/versiones')
def consultar_versiones_uci():
    return listar_versiones_uci()
# [RF06-RF07-END]


# [RF10-RF13-BEGIN]
# Consultas descriptivas y exportaciones: no modifican expedientes.
from app.rf10_13 import configure as configure_reporting, router as reporting_router
configure_reporting(DB)
app.include_router(reporting_router)
# [RF10-RF13-END]

@app.get('/api/project')
def project():return {'name':'AlertaEdu','stage':'Prototipo con PostgreSQL de Supabase y reglas orientativas','pending':['Modelo ML validado para variables académicas','SHAP','Seguridad para despliegue público','Conectores institucionales y auditoría']}

# Importación masiva: lectura y validación antes de guardar datos.
# La importación asigna riesgos orientativos, nunca probabilidades de IA. Conservar historiales anteriores.
from io import BytesIO, StringIO
import csv
import unicodedata
from zipfile import ZipFile, BadZipFile
from fastapi import File, UploadFile
from openpyxl import load_workbook

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 2500
IMPORT_FIELDS = ('codigo', 'nombre', 'carrera', 'semestre', 'promedio', 'asistencia', 'materias')


def _canonical_header(header):
    value = unicodedata.normalize('NFKD', str(header or '').strip().lower())
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'[^a-z0-9]+', ' ', value).strip()
    aliases = {
        'id': 'codigo', 'codigo academico': 'codigo', 'codigo de estudiante': 'codigo',
        'codigo estudiante': 'codigo', 'codigo': 'codigo',
        'nombre completo': 'nombre', 'estudiante': 'nombre', 'nombre': 'nombre',
        'carrera': 'carrera', 'semestre': 'semestre',
        'promedio 10': 'promedio', 'promedio academico': 'promedio', 'promedio': 'promedio',
        'asistencia': 'asistencia', 'asistencia porcentaje': 'asistencia',
        'materias reprobadas': 'materias', 'asignaturas reprobadas': 'materias',
        'materias': 'materias',
    }
    return aliases.get(value)


def _import_number(value, name, integer=False):
    if value is None or isinstance(value, bool):
        raise ValueError(f'{name}: valor obligatorio')
    raw = str(value).strip().replace(' ', '')
    if name == 'Asistencia' and raw.endswith('%'):
        raw = raw[:-1]
    raw = raw.replace(',', '.')
    try:
        n = float(raw)
    except (ValueError, OverflowError):
        raise ValueError(f'{name}: escribe un número válido')
    if not (math.isfinite(n) and (not integer or n.is_integer())):
        raise ValueError(f'{name}: valor inválido')
    return int(n) if integer else n


def _import_subjects(value):
    if value is None or str(value).strip() == '':
        return []
    raw = str(value).strip()
    # Acepta la plantilla: "Nombre | 5; Otra materia | 6".
    if '|' in raw:
        pieces = re.split(r'[;\n]+', raw)
        pairs = []
        for p in pieces:
            p = p.strip()
            if not p:
                continue
            a = p.rsplit('|', 1)
            if len(a) != 2 or not a[0].strip():
                raise ValueError('materias: usa Nombre | Nota; Otra | Nota')
            pairs.append((a[0].strip(), a[1].strip()))
    else:
        # También lee la exportación CSV previa: "Materia (5.5) / Otra (6)".
        pieces = re.split(r'\s+/\s+|[;\n]+', raw)
        pairs = []
        for p in pieces:
            if not p.strip():
                continue
            match = re.fullmatch(r'(.+?)\s*\(\s*([0-9]+(?:[.,][0-9]+)?)\s*\)', p.strip())
            if not match:
                raise ValueError('materias: usa Nombre | Nota; Otra | Nota')
            pairs.append((match.group(1).strip(), match.group(2)))
    if len(pairs) > 30:
        raise ValueError('materias: máximo 30 por estudiante')
    result = []
    for nombre, nota in pairs:
        if len(nombre) > 100 or nombre.startswith(('=', '+', '@')):
            raise ValueError('materias: nombre inválido')
        n = _import_number(nota, 'Nota')
        if not 0 <= n < 7:
            raise ValueError('materias: notas reprobadas deben estar entre 0 y menos de 7')
        result.append({'nombre': nombre, 'nota': n})
    return result


def _excel_rows(data, filename):
    if filename.lower().endswith('.csv'):
        try:
            decoded = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = data.decode('cp1252')
        # Delimitador mayoritario en la primera línea; compatible con CSV de AlertaEdu.
        head = decoded.splitlines()[0] if decoded.splitlines() else ''
        delimiter = ';' if head.count(';') > head.count(',') else ','
        reader = csv.reader(StringIO(decoded), delimiter=delimiter)
        rows = []
        for i, values in enumerate(reader, start=1):
            if i > MAX_IMPORT_ROWS + 1:
                raise HTTPException(422, f'Archivo demasiado grande: máximo {MAX_IMPORT_ROWS} estudiantes')
            rows.append((i, values))
        return rows
    if not filename.lower().endswith('.xlsx'):
        raise HTTPException(422, 'Formato inválido: sube un Excel .xlsx o un CSV .csv')
    try:
        with ZipFile(BytesIO(data)) as z:
            if sum(info.file_size for info in z.infolist()) > 35 * 1024 * 1024:
                raise HTTPException(413, 'El Excel tiene contenido interno demasiado grande')
        book = load_workbook(BytesIO(data), read_only=True, data_only=True)
        try:
            sheet = book['Estudiantes'] if 'Estudiantes' in book.sheetnames else book.active
            rows = []
            for i, values in enumerate(sheet.iter_rows(values_only=True), start=1):
                if i > MAX_IMPORT_ROWS + 1:
                    raise HTTPException(422, f'Máximo {MAX_IMPORT_ROWS} estudiantes por archivo')
                rows.append((i, values))
            return rows
        finally:
            book.close()
    except (BadZipFile, OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, 'No se pudo leer el Excel. Comprueba que sea un .xlsx válido.') from exc


def _parse_import(data, filename):
    raw_rows = _excel_rows(data, filename)
    if not raw_rows:
        raise HTTPException(422, 'El archivo está vacío')
    _, header = raw_rows[0]
    normalized = [_canonical_header(h) for h in header]
    missing = [key for key in IMPORT_FIELDS if key not in normalized]
    if missing:
        raise HTTPException(422, 'Faltan columnas: ' + ', '.join(missing) + '. Usa la plantilla de AlertaEdu.')
    if any(normalized.count(k) > 1 for k in IMPORT_FIELDS):
        raise HTTPException(422, 'Hay encabezados repetidos. Usa la plantilla de AlertaEdu.')
    indexes = {key: normalized.index(key) for key in IMPORT_FIELDS}
    parsed, errors, seen = [], [], set()
    for row_number, values in raw_rows[1:]:
        if not any(v is not None and str(v).strip() for v in values):
            continue
        try:
            def get(key):
                idx = indexes[key]
                return values[idx] if idx < len(values) else None
            codigo = str(get('codigo') or '').strip().upper()
            nombre = str(get('nombre') or '').strip()
            carrera = str(get('carrera') or '').strip()
            if any(t.startswith(('=', '+', '@')) for t in (nombre, carrera)):
                raise ValueError('El nombre o la carrera contienen un valor no permitido')
            obj = StudentIn.model_validate({
                'id': codigo, 'nombre': nombre, 'carrera': carrera,
                'semestre': _import_number(get('semestre'), 'Semestre', integer=True),
                'promedio': _import_number(get('promedio'), 'Promedio'),
                'asistencia': _import_number(get('asistencia'), 'Asistencia'),
                'materias': _import_subjects(get('materias')),
            })
            if codigo in seen:
                raise ValueError('Código repetido dentro del Excel')
            seen.add(codigo)
            parsed.append((row_number, obj))
        except (ValueError, ValidationError) as exc:
            errors.append({'fila': row_number, 'error': str(exc).split('\n')[0][:180]})
    if not parsed and not errors:
        raise HTTPException(422, 'No se encontraron estudiantes. Escribe tus datos desde la fila 2.')
    with conn() as c:
        existing = {r[0] for r in c.execute('SELECT id FROM students')}
    items = []
    for row, s in parsed:
        score = calculate_rules(Scenario(promedio=s.promedio, asistencia=s.asistencia, reprobadas=len(s.materias)))
        items.append({'fila': row, 'codigo': s.id, 'nombre': s.nombre, 'carrera': s.carrera,
                      'semestre': s.semestre, 'promedio': s.promedio, 'asistencia': s.asistencia,
                      'materias': len(s.materias), 'existente': s.id in existing,
                      'riesgo_orientativo': score['nivel_orientativo'], 'puntos': score['puntos']})
    return parsed, errors, items


async def _read_import_file(file: UploadFile):
    filename = (file.filename or '').strip()
    if not filename.lower().endswith(('.xlsx', '.csv')):
        raise HTTPException(422, 'Selecciona un archivo .xlsx o .csv')
    data = await file.read(MAX_IMPORT_BYTES + 1)
    await file.close()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, 'El archivo supera el límite de 5 MB')
    if not data:
        raise HTTPException(422, 'El archivo está vacío')
    return data, filename


@app.get('/api/import/template', include_in_schema=False)
def import_template():
    return FileResponse(ROOT / 'static' / 'plantilla_estudiantes.xlsx',
                        filename='plantilla_estudiantes_AlertaEdu.xlsx',
                        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.post('/api/import/preview')
async def import_preview(file: UploadFile = File(...)):
    data, filename = await _read_import_file(file)
    parsed, errors, items = _parse_import(data, filename)
    return {
        'total': len(parsed) + len(errors), 'validos': len(parsed), 'errores': errors[:50],
        'invalidos': len(errors), 'existentes': sum(x['existente'] for x in items),
        'nuevos': sum(not x['existente'] for x in items), 'vista_previa': items[:30],
        'puede_importar': len(errors) == 0 and bool(parsed),
        'evaluacion_prevista': {'Alto': sum(i['riesgo_orientativo']=='Alto' for i in items),
                                'Medio': sum(i['riesgo_orientativo']=='Medio' for i in items),
                                'Bajo': sum(i['riesgo_orientativo']=='Bajo' for i in items)},
        'mensaje': 'Vista previa de riesgo orientativo por reglas, sin IA. No se modificó la base de datos.',
    }


@app.post('/api/import/students')
async def import_students(file: UploadFile = File(...), on_duplicate: str = 'skip'):
    if on_duplicate not in ('skip', 'update'):
        raise HTTPException(422, 'on_duplicate debe ser skip o update')
    data, filename = await _read_import_file(file)
    parsed, errors, _ = _parse_import(data, filename)
    if errors:
        raise HTTPException(422, f'Importación cancelada: {len(errors)} fila(s) inválida(s). Primera: fila {errors[0]["fila"]}, {errors[0]["error"]}')
    created = skipped = updated = unchanged = auto_evaluated = 0
    risk_counts = _risk_totals()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        for _, s in parsed:
            old = c.execute('SELECT * FROM students WHERE id=?', (s.id,)).fetchone()
            materias_json = json.dumps([m.model_dump() for m in s.materias], ensure_ascii=False)
            if old is None:
                c.execute('INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)',
                          (s.id, s.nombre, s.carrera, s.semestre, s.promedio, s.asistencia,
                           'Sin evaluar', 'Pendiente', materias_json))
                created += 1
                result = _auto_evaluate_student(c, s)
                auto_evaluated += 1
                risk_counts[result['nivel_orientativo']] += 1
            elif on_duplicate == 'skip':
                skipped += 1
            else:
                changed = any((old[k] != v for k, v in (
                    ('nombre', s.nombre), ('carrera', s.carrera),
                    ('semestre', s.semestre), ('promedio', s.promedio),
                    ('asistencia', s.asistencia), ('materias', materias_json))))
                if changed:
                    # Se conservan tutorías y evaluaciones anteriores; se recalcula el riesgo.
                    c.execute('''UPDATE students SET nombre=?, carrera=?, semestre=?, promedio=?,
                                 asistencia=?, materias=? WHERE id=?''',
                              (s.nombre, s.carrera, s.semestre, s.promedio, s.asistencia,
                               materias_json, s.id))
                    result = _auto_evaluate_student(c, s)
                    auto_evaluated += 1
                    risk_counts[result['nivel_orientativo']] += 1
                    updated += 1
                else:
                    unchanged += 1
    return {'guardado': True, 'creados': created, 'actualizados': updated,
            'sin_cambios': unchanged, 'omitidos': skipped,
            'evaluados_automaticamente': auto_evaluated, 'por_nivel': risk_counts,
            'total_procesados': len(parsed), 'metodo': 'Reglas académicas ilustrativas (NO IA)',
            'mensaje': 'Estudiantes y niveles orientativos guardados en Supabase PostgreSQL; se conservan historiales anteriores.'}


@app.get('/style.css',include_in_schema=False)
def css():return FileResponse(ROOT/'static'/'style.css',media_type='text/css')
@app.get('/app.js',include_in_schema=False)
def js():return FileResponse(ROOT/'static'/'app.js',media_type='application/javascript')

# [ALERTAEDU-GMAIL-BEGIN]
from app.correo_recuperacion import configure as configure_gmail_recovery, router as gmail_recovery_router
configure_gmail_recovery(DB)
app.include_router(gmail_recovery_router)
# [ALERTAEDU-GMAIL-END]
