"""RF-06: explicación SHAP de un caso histórico UCI (NO de estudiantes institucionales).

El modelo y los datos se cargan solo desde la instalación local confiable.
No almacena inferencias en SQLite y nunca reentrena.
"""
from __future__ import annotations

from functools import lru_cache
import math

from app.uci_demo import DATA_PATH, MODEL_PATH, _load_trusted_model, _test_subset, predict_test_case

SPANISH = {
    'Admission grade': 'Nota de admisión',
    'Previous qualification (grade)': 'Nota de estudios anteriores',
    'Curricular units 1st sem (credited)': 'Materias con créditos reconocidos (1.er semestre)',
    'Curricular units 1st sem (enrolled)': 'Materias matriculadas (1.er semestre)',
    'Curricular units 1st sem (evaluations)': 'Evaluaciones rendidas (1.er semestre)',
    'Curricular units 1st sem (approved)': 'Materias aprobadas (1.er semestre)',
    'Curricular units 1st sem (grade)': 'Calificación de materias (1.er semestre)',
    'Curricular units 1st sem (without evaluations)': 'Materias sin evaluación (1.er semestre)',
    'Tuition fees up to date': 'Pagos de matrícula al día',
    'Scholarship holder': 'Beca',
    'Debtor': 'Deuda registrada',
}


@lru_cache(maxsize=2)
def _explainer(model_path: str, modified_ns: int):
    import shap
    bundle = _load_trusted_model(model_path, modified_ns)
    pipeline = bundle['pipeline']
    if 'imputer' not in pipeline.named_steps or 'forest' not in pipeline.named_steps:
        raise ValueError('Este laboratorio requiere el pipeline imputer + forest del experimento UCI')
    forest = pipeline.named_steps['forest']
    classes = list(forest.classes_)
    if classes != [0, 1]:
        raise ValueError('Clases del modelo distintas de [0, 1]')
    return shap.TreeExplainer(forest, model_output='raw')


def explicar(caso: int) -> dict:
    import numpy as np
    import pandas as pd

    original = predict_test_case(caso)
    bundle = _load_trusted_model(str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns)
    tests = _test_subset(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
    features = bundle['features']
    fila = tests.iloc[caso - 1]
    inputs = pd.DataFrame([
        {f: pd.to_numeric(fila[f], errors='coerce') for f in features}
    ], columns=features)
    imputed = bundle['pipeline'].named_steps['imputer'].transform(inputs)
    forest = bundle['pipeline'].named_steps['forest']
    shap_result = _explainer(str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns)(imputed)
    shap_values = np.asarray(shap_result.values)
    base_values = np.asarray(shap_result.base_values)
    if shap_values.ndim == 3 and shap_values.shape == (1, len(features), 2):
        impacts = shap_values[0, :, 1]
        baseline = float(base_values.reshape(-1)[1])
    elif shap_values.ndim == 2 and shap_values.shape == (1, len(features)):
        impacts = shap_values[0, :]
        baseline = float(base_values.reshape(-1)[0])
    else:
        raise ValueError(f'Formato SHAP incompatible: {shap_values.shape}')
    probability = float(forest.predict_proba(imputed)[0][1])
    reconstructed = float(baseline + impacts.sum())
    if not all(map(math.isfinite, [probability, reconstructed, baseline])):
        raise ValueError('SHAP devolvió valores no finitos')
    if abs(reconstructed - probability) > 0.025:
        raise ValueError('Las contribuciones SHAP no reconstruyen la predicción del modelo')

    ordered = sorted(range(len(features)), key=lambda i: -abs(float(impacts[i])))
    factores = []
    for i in ordered[:7]:
        contribution = float(impacts[i])
        factores.append({
            'variable': features[i], 'nombre': SPANISH.get(features[i], features[i]),
            'valor': float(imputed[0, i]),
            'aporte': round(contribution, 6),
            'direccion': 'aumenta' if contribution > 1e-9 else ('reduce' if contribution < -1e-9 else 'neutral'),
        })
    return {
        'caso': caso,
        'probabilidad_desercion': original['probabilidad_desercion'],
        'resultado_historico': original['resultado_historico'],
        'valor_base': round(baseline, 6),
        'suma_aportes': round(float(impacts.sum()), 6),
        'factores': factores,
        'metodo': 'SHAP TreeExplainer para Random Forest (clase abandono)',
        'advertencia': ('Interpretación local de una predicción experimental UCI; '
                        'las contribuciones no demuestran causalidad ni validan decisiones sobre estudiantes de AlertaEdu.'),
    }
