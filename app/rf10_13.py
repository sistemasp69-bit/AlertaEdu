"""AlertaEdu RF-10/RF-11/RF-12/RF-13: análisis RETROSPECTIVO y exportaciones.

No cambia estudiantes, evaluaciones, intervenciones, datos UCI ni modelos.
No se infiere causalidad y no se inventan tasas de retención histórica.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from io import BytesIO, StringIO
import csv
import json
from app import db as database
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

router = APIRouter(prefix='/api/seguimiento', tags=['RF10-RF13'])
DB_PATH: Path | None = None


def configure(db):
    global DB_PATH
    DB_PATH = str(db)


def _conn():
    if DB_PATH is None:
        raise HTTPException(503, 'Base de datos no disponible')
    c = database.connect()
    c.row_factory = database.Row
    return c


def _require(request: Request, detail=False):
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(401, 'Inicia sesión')
    if detail and user['role'] not in ('Administrador', 'Tutor'):
        raise HTTPException(403, 'El acceso a expedientes individuales se limita a Administrador y Tutor')
    return user


def _impact_row(c, f):
    base = c.execute('''SELECT id,fecha,nivel,puntos,max_puntos FROM evaluations
         WHERE student_id=? AND fecha<=? ORDER BY fecha DESC,id DESC LIMIT 1''',
         (f['student_id'], f['fecha'])).fetchone()
    post = c.execute('''SELECT id,fecha,nivel,puntos,max_puntos FROM evaluations
         WHERE student_id=? AND fecha>? ORDER BY fecha ASC,id ASC LIMIT 1''',
         (f['student_id'], f['fecha'])).fetchone()
    out = {'intervencion_id':f['id'],'codigo':f['student_id'], 'nombre':f['nombre'],
           'carrera':f['carrera'], 'tipo':f['tipo'], 'responsable':f['responsable'],
           'fecha_intervencion':f['fecha'],
           'antes': dict(base) if base else None, 'despues':dict(post) if post else None,
           'diferencia_puntos':None,'resultado':'Sin comparación', 'estado_medicion':'Incompleto'}
    if base is None or post is None:
        out['motivo'] = 'Falta evaluación previa' if base is None else 'Falta evaluación posterior'
        return out
    delta = post['puntos']-base['puntos']
    out['diferencia_puntos'] = delta
    out['resultado'] = 'Mejoró' if delta<0 else 'Empeoró' if delta>0 else 'Sin cambio'
    out['estado_medicion'] = 'Comparado'
    # Otra intervención intermedia impide atribuir el cambio a un único seguimiento.
    confounding = c.execute('''SELECT count(*) FROM followups
        WHERE student_id=? AND id!=? AND fecha>? AND fecha<=?''',
        (f['student_id'], f['id'], f['fecha'], post['fecha'])).fetchone()[0]
    out['otras_intervenciones_antes_de_evaluacion'] = bool(confounding)
    out['nota'] = 'Cambio observado, NO prueba de causalidad de la intervención.'
    return out


@router.get('/rf10/efectividad')
def effectiveness(request:Request, limit:int=Query(default=100,ge=1,le=500),codigo:str=''):
    _require(request, detail=True)
    if len(codigo)>60:
        raise HTTPException(422,'Código demasiado largo')
    with _conn() as c:
        where = ' WHERE f.student_id=?' if codigo else ''
        args = [codigo] if codigo else []
        total = c.execute('SELECT COUNT(*) FROM followups f'+where,args).fetchone()[0]
        rows=c.execute('''SELECT f.id,f.student_id,f.tipo,f.responsable,f.fecha,s.nombre,s.carrera
            FROM followups f JOIN students s ON s.id=f.student_id'''+where+
            ' ORDER BY f.id DESC LIMIT ?',args+[limit]).fetchall()
        items=[_impact_row(c,r) for r in rows]
    counts=Counter(x['resultado'] for x in items)
    return {'total_intervenciones':total, 'mostradas':len(items), 'items':items,
            'resumen_mostrado':{'mejoro':counts['Mejoró'],'empeoro':counts['Empeoró'],
            'sin_cambio':counts['Sin cambio'],'sin_comparacion':counts['Sin comparación']},
            'aviso':'Comparación descriptiva de evaluaciones antes y después; NO demuestra efecto causal. '
                    'Los casos sin dos mediciones quedan incompletos.'}


@router.get('/rf11/segmentos')
def segmented(request:Request):
    _require(request)
    with _conn() as c:
        rows=c.execute('''SELECT carrera,COUNT(*) total,
          SUM(CASE WHEN riesgo='Alto' THEN 1 ELSE 0 END) alto,
          SUM(CASE WHEN riesgo='Medio' THEN 1 ELSE 0 END) medio,
          SUM(CASE WHEN riesgo='Bajo' THEN 1 ELSE 0 END) bajo,
          SUM(CASE WHEN riesgo='Sin evaluar' THEN 1 ELSE 0 END) sin_evaluar,
          ROUND(AVG(promedio)::numeric,2) promedio_general
          FROM students GROUP BY carrera ORDER BY total DESC,carrera LIMIT 100''').fetchall()
        overall=c.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    return {'total_estudiantes':overall,'por_carrera':[dict(r) for r in rows],
            'retencion_historica':None,'retencion_estimada':None,
            'sin_datos':['Facultad','Período lectivo','Modalidad','Resultado de permanencia/abandono posterior'],
            'aviso':'Las categorías de riesgo son por reglas ilustrativas; no equivalen a tasas de retención.'}


def _filters(riesgo,carrera,semestre,promedio_desde,promedio_hasta,materia,estado,buscar):
    if riesgo and riesgo not in ('Bajo','Medio','Alto','Sin evaluar'):raise HTTPException(422,'Nivel inválido')
    if estado and estado not in ('Pendiente','En seguimiento','Atendido'):raise HTTPException(422,'Estado inválido')
    if promedio_desde is not None and promedio_hasta is not None and promedio_desde>promedio_hasta:
        raise HTTPException(422,'El promedio mínimo supera al máximo')
    where=[]; args=[]
    for field,value in [('riesgo',riesgo),('carrera',carrera),('semestre',semestre),('estado',estado)]:
        if value not in ('',None):
            where.append(f's.{field}=?');args.append(value)
    if promedio_desde is not None: where.append('s.promedio>=?');args.append(promedio_desde)
    if promedio_hasta is not None: where.append('s.promedio<=?');args.append(promedio_hasta)
    for field,value in [('materias',materia),('id',buscar)]:
        if value:
            value = value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            if field=='id':
                where.append("(s.id LIKE ? ESCAPE '\\' OR s.nombre LIKE ? ESCAPE '\\')")
                args.extend(['%'+value+'%']*2)
            else:
                where.append("s.materias LIKE ? ESCAPE '\\'");args.append('%'+value+'%')
    return (' WHERE '+' AND '.join(where)) if where else '',args


def _query_students(c, params, limit, offset):
    where, args=_filters(**params)
    count=c.execute('SELECT COUNT(*) FROM students s'+where,args).fetchone()[0]
    rows=c.execute('''SELECT s.id,s.nombre,s.carrera,s.semestre,s.promedio,s.asistencia,
        s.riesgo,s.estado,s.materias FROM students s'''+where+
        ' ORDER BY s.id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    items=[]
    for r in rows:
        d=dict(r)
        try:
            arr=json.loads(d.pop('materias'))
            d['materias_reprobadas']='; '.join(str(m.get('nombre','')) for m in arr)
            d['reprobadas']=len(arr)
        except (ValueError, TypeError, AttributeError):
            d['materias_reprobadas']='[Sin formato]';d['reprobadas']=0
        items.append(d)
    return count,items


@router.get('/rf12/busqueda')
def advanced(request:Request,
             riesgo:str='',carrera:str='',semestre:int|None=Query(default=None,ge=1,le=20),
             promedio_desde:float|None=Query(default=None,ge=0,le=10),
             promedio_hasta:float|None=Query(default=None,ge=0,le=10),
             materia:str=Query(default='',max_length=100),estado:str='',
             buscar:str=Query(default='',max_length=80),
             limit:int=Query(default=100,ge=1,le=500),offset:int=Query(default=0,ge=0)):
    _require(request,detail=True)
    params=locals().copy(); del params['request'];del params['limit'];del params['offset']
    with _conn() as c: total,items=_query_students(c,params,limit,offset)
    return {'total':total,'items':items,'limit':limit,'offset':offset,
            'aviso':'Lista de registros académicos ficticios; filtros aplicados en Supabase PostgreSQL.'}


@router.get('/rf13/exportar')
def export_file(request:Request, formato:Literal['csv','xlsx','pdf']='csv',
             riesgo:str='',carrera:str='',semestre:int|None=Query(default=None,ge=1,le=20),
             promedio_desde:float|None=Query(default=None,ge=0,le=10),
             promedio_hasta:float|None=Query(default=None,ge=0,le=10),
             materia:str=Query(default='',max_length=100),estado:str='',
             buscar:str=Query(default='',max_length=80)):
    _require(request,detail=True)
    params=locals().copy();del params['request'];del params['formato']
    with _conn() as c: total,items=_query_students(c,params,20001,0)
    if total>20000:raise HTTPException(422,'Demasiados resultados; aplica filtros')
    if formato=='pdf' and total>300:
        raise HTTPException(422,'PDF admite hasta 300 estudiantes; aplica filtros, o utiliza XLSX/CSV')
    headings=('Código','Nombre','Carrera','Semestre','Promedio','Asistencia (%)','Reprobadas','Riesgo','Estado','Materias reprobadas')
    keys=('id','nombre','carrera','semestre','promedio','asistencia','reprobadas','riesgo','estado','materias_reprobadas')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
    if formato=='csv':
        f=StringIO();w=csv.writer(f);w.writerow(headings)
        for d in items:
            vals=[d[k] for k in keys]
            w.writerow([(chr(39)+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for v in vals])
        return Response(content='\ufeff'+f.getvalue(),media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition':f'attachment; filename="AlertaEdu_{stamp}.csv"', 'Cache-Control':'no-store'})
    if formato=='xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill
        book=Workbook();ws=book.active;ws.title='Estudiantes';ws.append(headings)
        for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='263D73')
        for d in items:
            vals=[d[k] for k in keys]
            # Evita inyección de fórmulas en hojas exportadas desde datos no confiables.
            vals=[("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for v in vals]
            ws.append(vals)
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col,w in {'A':19,'B':32,'C':23,'D':12,'E':13,'F':18,'G':13,'H':16,'I':19,'J':52}.items():ws.column_dimensions[col].width=w
        out=BytesIO();book.save(out)
        return Response(content=out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition':f'attachment; filename="AlertaEdu_{stamp}.xlsx"','Cache-Control':'no-store'})
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer
    from xml.sax.saxutils import escape
    out=BytesIO();story=[];styles=getSampleStyleSheet()
    story.append(Paragraph('AlertaEdu - Reporte académico operativo',styles['Title']))
    story.append(Paragraph('Datos de prueba. Clasificación orientativa por reglas, no probabilidades de IA.',styles['Normal']))
    story.append(Paragraph(f'Registros filtrados: {total} | Fecha UTC: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}',styles['Normal']))
    story.append(Spacer(1,12))
    short_keys=('id','nombre','carrera','promedio','asistencia','riesgo','estado')
    table_data=[['Código','Nombre','Carrera','Prom.','Asist.','Riesgo','Estado']]
    for d in items:
        row=[]
        for key in short_keys:
            v=escape(str(d[key]));row.append(Paragraph(v[:105],styles['BodyText']))
        table_data.append(row)
    tab=Table(table_data,colWidths=[73,122,92,48,48,58,85],repeatRows=1,hAlign='LEFT')
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#263D73')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.whitesmoke,colors.white]),
        ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#D3DBE8')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('FONTSIZE',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
    story.append(tab)
    doc=SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=35,bottomMargin=35)
    doc.build(story)
    return Response(content=out.getvalue(),media_type='application/pdf',
        headers={'Content-Disposition':f'attachment; filename="AlertaEdu_{stamp}.pdf"', 'Cache-Control':'no-store'})
