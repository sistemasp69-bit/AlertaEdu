"""RF-07: lectura no destructiva de versiones del laboratorio UCI (no producción)."""
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = ROOT / 'modelos' / 'versiones_uci'


def listar() -> dict:
    items = []
    if VERSIONS.is_dir():
        for path in sorted(VERSIONS.iterdir(), reverse=True):
            if not path.is_dir() or not path.name.startswith('uci-'):
                continue
            meta_path = path / 'version.json'
            if not meta_path.is_file():
                continue
            try:
                obj = json.loads(meta_path.read_text(encoding='utf-8'))
                m = obj['metricas']
                items.append({
                    'version': str(obj['version'])[:80],
                    'fecha_utc': str(obj['fecha_utc'])[:60],
                    'archivo_fuente': str(obj['archivo_fuente'])[:100],
                    'sha256_datos': str(obj.get('sha256_datos', ''))[:64],
                    'f1_dropout': float(m['f1_dropout']),
                    'recall_dropout': float(m['recall_dropout']),
                    'roc_auc': float(m['roc_auc']),
                    'criterios_rnf03_preliminares': bool(m['criterios_rnf03_preliminares']),
                    'estado': 'experimental; no activado en estudiantes',
                })
            except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if len(items) == 30:
                break
    return {'total_mostrado': len(items), 'items': items,
            'detalle': 'Historial local de entrenamiento UCI. Ninguna versión se despliega automáticamente como modelo institucional.'}
