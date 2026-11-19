"""Genera probabilidad por ML para estudiantes registrados, si hay modelo validado.

No modifica el riesgo orientativo por reglas, que continúa separado.
"""
from datetime import datetime, timezone
import json
import sys
from app import main as m
from app.ia_core import model_status, predict_probability


def recalculate():
    status = model_status()
    if not status['disponible']:
        raise RuntimeError(status['detalle'])
    count = 0
    with m.conn() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute('SELECT * FROM students ORDER BY id'):
            s = m.row_student(row)
            result = predict_probability(s['promedio'], s['asistencia'], s['reprobadas'])
            db.execute('''INSERT INTO ml_predictions (student_id, probability, level, model_version, date)
                          VALUES (?, ?, ?, ?, ?)''',
                       (s['id'], result['probabilidad_desercion'], result['nivel_ia'],
                        result['modelo_version'], datetime.now(timezone.utc).isoformat()))
            count += 1
    return count

if __name__ == '__main__':
    try:
        n = recalculate()
        print('Predicciones ML guardadas:', n)
    except Exception as exc:
        print('No se pudo recalcular IA:', exc, file=sys.stderr)
        sys.exit(1)
