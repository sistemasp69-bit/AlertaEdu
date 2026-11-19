"""Motor ML opcional. NUNCA entrena con riesgos generados mediante reglas.

El modelo sólo se publica tras entrenar con historiales verificados y
etiquetados como deserción (1) / continuidad (0).
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / 'modelos'
MODEL_FILE = MODEL_DIR / 'modelo_rf_calibrado.joblib'
METADATA_FILE = MODEL_DIR / 'modelo_rf_metadata.json'
FEATURES = ('promedio', 'asistencia', 'reprobadas')


def model_status():
    if not (MODEL_FILE.is_file() and METADATA_FILE.is_file()):
        return {'disponible': False, 'detalle': 'Falta entrenar y validar la IA con historiales etiquetados.'}
    try:
        meta = json.loads(METADATA_FILE.read_text(encoding='utf-8'))
        if not meta.get('aprobado') or meta.get('features') != list(FEATURES):
            return {'disponible': False, 'detalle': 'El modelo no está aprobado o usa variables incompatibles.'}
        return {'disponible': True, 'version': meta['version'],
                'metricas': meta['metricas'], 'features': list(FEATURES),
                'detalle': 'Probabilidades estimadas por modelo supervisado; no determinan por sí solas la deserción.'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'disponible': False, 'detalle': 'Archivos del modelo inválidos.'}


@lru_cache(maxsize=1)
def _load_model(path: str, modified: float):
    # Joblib usa pickle: cargar solamente el archivo creado y revisado localmente.
    import joblib
    return joblib.load(path)


def predict_probability(promedio: float, asistencia: float, reprobadas: int):
    status = model_status()
    if not status['disponible']:
        raise RuntimeError(status['detalle'])
    try:
        model = _load_model(str(MODEL_FILE), MODEL_FILE.stat().st_mtime)
        probability = float(model.predict_proba([[promedio, asistencia, reprobadas]])[0][1])
    except Exception as exc:
        raise RuntimeError('No se pudo cargar o ejecutar el modelo de IA validado.') from exc
    probability = max(0.0, min(1.0, probability))
    level = 'Alto' if probability >= 0.70 else 'Medio' if probability >= 0.40 else 'Bajo'
    return {'probabilidad_desercion': round(probability, 6),
            'nivel_ia': level, 'modelo_version': status['version'],
            'metodo': 'Random Forest calibrado',
            'nota': 'Estimación estadística: no equivale a certeza ni sustituye la revisión del tutor.'}
