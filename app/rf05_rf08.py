"""RF-05 / RF-08: configurable rule thresholds and internal academic alerts.

No ML predictions are produced by this module. The thresholds classify a
0-9-point illustrative academic score, not the UCI dropout probability.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import os
from app import db as database

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal

router = APIRouter(prefix='/api', tags=['RF-05 / RF-08'])


def _db_path() -> Path:
    return 'Supabase PostgreSQL'


def _open():
    path = _db_path()
    c = database.connect(path, timeout=10)
    c.row_factory = database.Row
    return c


def init_extra_tables(db_path=None):
    path = _db_path()
    with database.connect(path, timeout=10) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS risk_settings (
            id INTEGER PRIMARY KEY CHECK(id=1),
            medium_points INTEGER NOT NULL,
            high_points INTEGER NOT NULL,
            notify_points INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO risk_settings
          (id, medium_points, high_points, notify_points, updated_at)
          VALUES (1,3,6,7,'inicial');
        CREATE TABLE IF NOT EXISTS academic_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            old_level TEXT NOT NULL,
            new_level TEXT NOT NULL,
            previous_points INTEGER NOT NULL,
            new_points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Nueva',
            responsable TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE INDEX IF NOT EXISTS idx_academic_alerts_student
          ON academic_alerts(student_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_academic_alerts_state
          ON academic_alerts(estado,id DESC);
        CREATE TABLE IF NOT EXISTS academic_alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(alert_id) REFERENCES academic_alerts(id)
        );
        ''')
    _settings.cache_clear()


@lru_cache(maxsize=12)
def _settings(db: str):
    with database.connect(db, timeout=10) as c:
        row = c.execute('SELECT medium_points,high_points,notify_points FROM risk_settings WHERE id=1').fetchone()
    if not row:
        raise RuntimeError('No hay configuración de riesgo. Reinicia AlertaEdu.')
    return {'medium_points':row[0], 'high_points':row[1], 'notify_points':row[2]}


def rule_points(s):
    """Identical academic score to the original AlertaEdu v0.4 formula."""
    return (3 if s.promedio<6 else 2 if s.promedio<7 else 0) + (3 if s.asistencia<70 else 2 if s.asistencia<85 else 0) + (3 if s.reprobadas>=3 else 2 if s.reprobadas>=1 else 0)


def configured_rule_result(s, db):
    settings=_settings(str(db))
    points=rule_points(s)
    level='Alto' if points>=settings['high_points'] else 'Medio' if points>=settings['medium_points'] else 'Bajo'
    return {'nivel_orientativo':level, 'puntos':points, 'max_puntos':9,
            'metodo':'Reglas académicas configurables, NO IA ni probabilidad de deserción',
            'factores':s.model_dump()}


def maybe_create_alert(c, student_id, previous, current, when):
    """Called in the same transaction as the academic evaluation.

    Only creates alerts after a previous evaluation exists. This means existing
    historical high-risk records never generate thousands of notifications on
    installation. Re-evaluating unchanged data is idempotent for alerts.
    """
    if previous is None:
        return None
    config=_settings(str(_db_path()))
    before_level, before_points=previous['nivel'],int(previous['puntos'])
    after_level, after_points=current['nivel_orientativo'],int(current['puntos'])
    promoted=(before_level!='Alto' and after_level=='Alto')
    crossed=(before_points < config['notify_points'] <= after_points)
    if not (promoted or crossed):
        return None
    reasons=[]
    if promoted: reasons.append('El riesgo académico pasó a Alto')
    if crossed: reasons.append(f'La puntuación cruzó el umbral de aviso ({config["notify_points"]}/9)')
    reason='; '.join(reasons)
    cur=c.execute('''INSERT INTO academic_alerts
      (student_id,old_level,new_level,previous_points,new_points,reason,estado,responsable,created_at,updated_at)
      VALUES (?,?,?,?,?,?,'Nueva','',?,?)''',
      (student_id,before_level,after_level,before_points,after_points,reason,when,when))
    c.execute('''INSERT INTO academic_alert_events(alert_id,actor,action,detail,created_at)
      VALUES (?, 'sistema', 'CREADA', ?, ?)''',(cur.lastrowid,reason,when))
    return cur.lastrowid


class SettingsInput(BaseModel):
    medium_points: int = Field(ge=1,le=8)
    high_points: int = Field(ge=2,le=9)
    notify_points: int = Field(ge=2,le=9)


@router.get('/risk/settings')
def get_risk_settings():
    s=_settings(str(_db_path()))
    return {**s,'escala':'Puntuación por reglas de 0 a 9; NO probabilidad de deserción',
            'aplicacion':'Los umbrales nuevos afectan evaluaciones siguientes; el historial existente no cambia automáticamente.'}


@router.put('/risk/settings')
def put_risk_settings(data: SettingsInput, request: Request):
    if request.state.user['role']!='Administrador':
        raise HTTPException(403,'Solo el administrador puede modificar los umbrales')
    if not (data.medium_points < data.high_points <= data.notify_points):
        raise HTTPException(422,'Se exige: umbral medio < alto <= umbral de aviso')
    stamp=datetime.now(timezone.utc).isoformat()
    with _open() as c:
        c.execute('''UPDATE risk_settings SET medium_points=?,high_points=?,notify_points=?,updated_at=? WHERE id=1''',
                  (data.medium_points,data.high_points,data.notify_points,stamp))
    _settings.cache_clear()
    return {**data.model_dump(),'guardado':True,'mensaje':'Se aplicarán a nuevas evaluaciones. Los estudiantes existentes no se reclasifican solos.'}


@router.get('/alerts')
def get_academic_alerts(request: Request, estado: str='Todas', limit: int=100):
    if request.state.user['role'] not in ('Administrador','Tutor'):
        raise HTTPException(403,'Solo administradores y tutores pueden consultar alertas individuales')
    if estado not in ('Todas','Nueva','En seguimiento','Cerrada'):
        raise HTTPException(422,'Estado inválido')
    if not 1 <= limit <= 200:
        raise HTTPException(422,'El límite debe estar entre 1 y 200')
    with _open() as c:
        clause=' WHERE a.estado=?' if estado!='Todas' else ''
        args=[estado] if estado!='Todas' else []
        count=c.execute('SELECT COUNT(*) FROM academic_alerts a'+clause,args).fetchone()[0]
        rows=c.execute('''SELECT a.*,s.nombre,s.carrera FROM academic_alerts a
               JOIN students s ON s.id=a.student_id'''+clause+' ORDER BY a.id DESC LIMIT ?',args+[limit]).fetchall()
        summary={row[0]:row[1] for row in c.execute('SELECT estado, COUNT(*) FROM academic_alerts GROUP BY estado')}
    return {'items':[dict(r) for r in rows],'total':count,'resumen':summary,
            'nota':'Alertas generadas por CAMBIOS en reglas; no son notificaciones externas ni predicciones IA.'}


class AlertEdit(BaseModel):
    estado: Literal['Nueva','En seguimiento','Cerrada']
    responsable: str = Field(default='',max_length=40)


@router.patch('/alerts/{alert_id}')
def update_academic_alert(alert_id: int, data: AlertEdit, request: Request):
    if request.state.user['role'] not in ('Administrador','Tutor'):
        raise HTTPException(403,'Solo administradores y tutores pueden gestionar alertas')
    responsible=data.responsable.strip()
    with _open() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM academic_alerts WHERE id=?',(alert_id,)).fetchone()
        if old is None: raise HTTPException(404,'Alerta no encontrada')
        if responsible:
            user=c.execute("SELECT role,active FROM users WHERE username=?",(responsible,)).fetchone()
            if user is None or not user['active'] or user['role'] not in ('Administrador','Tutor'):
                raise HTTPException(422,'El responsable debe ser un usuario Tutor o Administrador activo')
        now=datetime.now(timezone.utc).isoformat()
        c.execute('UPDATE academic_alerts SET estado=?,responsable=?,updated_at=? WHERE id=?',
                  (data.estado,responsible,now,alert_id))
        if old['estado']!=data.estado or old['responsable']!=responsible:
            detail=f"{old['estado']} -> {data.estado}; {old['responsable']} -> {responsible}"
            c.execute('INSERT INTO academic_alert_events(alert_id,actor,action,detail,created_at) VALUES (?,?,?,?,?)',
                      (alert_id,request.state.user['username'],'ACTUALIZADA',detail,now))
    return {'guardado':True,'id':alert_id,'estado':data.estado,'responsable':responsible}


@router.get('/alerts/{alert_id}/history')
def get_alert_history(alert_id:int,request:Request):
    if request.state.user['role'] not in ('Administrador','Tutor'):
        raise HTTPException(403,'Acceso restringido')
    with _open() as c:
        if not c.execute('SELECT 1 FROM academic_alerts WHERE id=?',(alert_id,)).fetchone():
            raise HTTPException(404,'Alerta no encontrada')
        events=c.execute('SELECT actor,action,detail,created_at FROM academic_alert_events WHERE alert_id=? ORDER BY id DESC',(alert_id,)).fetchall()
    return {'items':[dict(x) for x in events]}
