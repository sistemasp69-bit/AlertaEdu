"""RF-03: actualización periódica desde un Excel/CSV actualizado autorizado.

No descarga datos de la universidad: la fuente debe actualizarse previamente
mediante una exportación o integración institucional autorizada.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys

from app import main as m

SOURCE = Path(__file__).resolve().parent / 'fuente_actualizaciones' / 'estudiantes_actualizados.xlsx'
LOG = Path(__file__).resolve().parent / 'actualizaciones.log'


def run(source: Path):
    if not source.is_file():
        raise FileNotFoundError(f'No existe {source}. Coloca ahí el Excel más reciente autorizado.')
    data = source.read_bytes()
    if len(data) > m.MAX_IMPORT_BYTES:
        raise ValueError('El archivo supera 5 MB. Divide la fuente en archivos menores.')
    parsed, errors, _ = m._parse_import(data, source.name)
    if errors:
        raise ValueError(f'No se actualizaron datos: {len(errors)} filas inválidas. Primera: {errors[0]}')
    created = updated = unchanged = 0
    with m.conn() as con:
        con.execute('BEGIN IMMEDIATE')
        for _, student in parsed:
            previous = con.execute('SELECT * FROM students WHERE id=?', (student.id,)).fetchone()
            data_materias = json.dumps([v.model_dump() for v in student.materias], ensure_ascii=False)
            if previous is None:
                con.execute('''INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)''',
                            (student.id,student.nombre,student.carrera,student.semestre,
                             student.promedio,student.asistencia,'Sin evaluar','Pendiente',data_materias))
                m._auto_evaluate_student(con, student)
                created += 1
            elif any(previous[k] != v for k,v in (
                ('nombre',student.nombre),('carrera',student.carrera),('semestre',student.semestre),
                ('promedio',student.promedio),('asistencia',student.asistencia),('materias',data_materias))):
                con.execute('''UPDATE students SET nombre=?,carrera=?,semestre=?,promedio=?,asistencia=?,materias=? WHERE id=?''',
                            (student.nombre,student.carrera,student.semestre,student.promedio,
                             student.asistencia,data_materias,student.id))
                m._auto_evaluate_student(con, student)
                updated += 1
            else:
                unchanged += 1
    return {'fuente': str(source), 'creados': created, 'actualizados': updated,
            'sin_cambios': unchanged, 'total': len(parsed), 'fecha_utc': datetime.now(timezone.utc).isoformat(),
            'metodo': 'Importación programada de Excel; riesgos calculados por reglas, NO IA'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--excel', type=Path, default=SOURCE)
    args = parser.parse_args()
    try:
        report = run(args.excel)
        line = json.dumps(report, ensure_ascii=False)
        print(line)
    except Exception as exc:
        line = datetime.now(timezone.utc).isoformat() + ' ERROR ' + str(exc)
        print(line, file=sys.stderr)
        code = 1
    else:
        code = 0
    with LOG.open('a', encoding='utf-8') as log:
        log.write(line + '\n')
    sys.exit(code)
