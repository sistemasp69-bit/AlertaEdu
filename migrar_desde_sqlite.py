"""Optional one-time migration of the user's own *old* SQLite db to Supabase.
Requires DATABASE_URL, an initialized empty Supabase DB, and local SQLite path.
Does not migrate active sessions, password reset tokens or pending verification tokens.
"""
from pathlib import Path
from dotenv import load_dotenv
import argparse
import os
import sqlite3  # used only for reading the LEGACY input file, never at runtime
import psycopg

TABLES = [
    'students', 'users', 'risk_settings', 'followups', 'evaluations',
    'ml_predictions', 'academic_alerts', 'academic_alert_events', 'gmail_verified_emails'
]

def main():
    parser=argparse.ArgumentParser(description='Migrar base antigua de AlertaEdu a Supabase')
    parser.add_argument('archivo_sqlite', type=Path)
    parser.add_argument('--confirmar',action='store_true',help='Escribe los datos en Supabase')
    args=parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent / '.env')
    if not args.archivo_sqlite.is_file(): parser.error('No se encuentra el archivo SQLite antiguo')
    with sqlite3.connect(args.archivo_sqlite.resolve().as_uri() + '?mode=ro',uri=True) as old:
        present={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in TABLES:
            if t in present:
                print(f'{t}: {old.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]} filas')
    if not args.confirmar:
        print('Simulación completada; añade --confirmar para migrar a Supabase.')
        return
    if not os.environ.get('DATABASE_URL'): parser.error('Configura DATABASE_URL en .env')
    with sqlite3.connect(args.archivo_sqlite.resolve().as_uri() + '?mode=ro',uri=True) as old:
        old.row_factory=sqlite3.Row
        with psycopg.connect(os.environ['DATABASE_URL'],sslmode='require') as pg:
            with pg.cursor() as cur:
                if (cur.execute('SELECT count(*) FROM students').fetchone()[0] or
                    cur.execute('SELECT count(*) FROM users').fetchone()[0]):
                    parser.error('Supabase ya tiene estudiantes o cuentas: la migración automática no sobrescribirá información')
                for t in TABLES:
                    if t not in present: continue
                    cols=[x[1] for x in old.execute(f'PRAGMA table_info({t})')]
                    if not cols: continue
                    rows=old.execute(f'SELECT * FROM {t}').fetchall()
                    if not rows: continue
                    columns=','.join('"'+x+'"' for x in cols)
                    marks=','.join('%s' for _ in cols)
                    query = f'INSERT INTO {t} ({columns}) VALUES ({marks})'
                    if t == 'risk_settings':
                        query += ' ON CONFLICT (id) DO UPDATE SET medium_points=excluded.medium_points, high_points=excluded.high_points, notify_points=excluded.notify_points, updated_at=excluded.updated_at'
                    cur.executemany(query,[tuple(r) for r in rows])
                    if 'id' in cols and t not in ('students','risk_settings'):
                        cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}','id'), COALESCE((SELECT max(id) FROM {t}),1), true)")
                    print(f'Migradas {len(rows)} filas de {t}')
    print('Migración completada. Las sesiones se deberán iniciar de nuevo.')

if __name__=='__main__':main()
