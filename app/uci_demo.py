"""RF-04: laboratorio experimental sobre el conjunto de evaluación UCI.

Mantiene INTACTA la evaluación por reglas y los expedientes de AlertaEdu.
El modelo UCI NO predice para estudiantes institucionales: sus variables no coinciden.
Solo muestra predicciones para casos de TEST que no se usaron al entrenar.
Cargar únicamente modelos joblib confiables generados localmente.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "modelos" / "experimento_uci_rf04.joblib"
METRICS_PATH = ROOT / "modelos" / "experimento_uci_rf04_metricas.json"
DATA_PATH = ROOT / "datos_historicos" / "data.csv"


def status() -> dict:
    missing = [str(p.relative_to(ROOT)) for p in (MODEL_PATH, METRICS_PATH, DATA_PATH) if not p.is_file()]
    if missing:
        return {"disponible": False, "faltan": missing,
                "detalle": "Faltan archivos del experimento UCI; no afecta los estudiantes almacenados en Supabase."}
    try:
        meta = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        if meta.get("tipo") != "experimento_uci_rf04_no_integrado":
            raise ValueError("Las métricas no corresponden a este experimento")
        metrics = {k: meta.get(k) for k in ("f1_dropout", "recall_dropout", "roc_auc", "precision_dropout", "brier", "criterios_rnf03_preliminares")}
        return {"disponible": True, "metodo": "Random Forest (experimento UCI)",
                "metricas": metrics,
                "casos_evaluacion": int(meta.get("test_n", 0)),
                "detalle": "Predicciones solo para casos reservados de prueba de UCI. NO son estimaciones válidas para los estudiantes de AlertaEdu."}
    except (OSError, ValueError, TypeError) as exc:
        return {"disponible": False, "detalle": f"Métricas inválidas: {exc}"}


@lru_cache(maxsize=2)
def _load_trusted_model(path: str, modified_ns: int):
    import joblib
    bundle = joblib.load(path)  # NUNCA cargar joblib de origen desconocido.
    if not isinstance(bundle, dict) or not {'pipeline', 'features', 'class_positive'}.issubset(bundle):
        raise ValueError('El archivo no tiene la estructura esperada')
    if bundle['class_positive'] != 'Dropout':
        raise ValueError('La clase positiva no corresponde a abandono')
    return bundle


@lru_cache(maxsize=2)
def _test_subset(path: str, modified_ns: int):
    import pandas as pd
    from sklearn.model_selection import train_test_split

    # Replica el mismo filtrado y partición usados en entrenar_uci_experimental.py
    df = pd.read_csv(path, sep=None, engine='python', encoding='utf-8-sig')
    df.columns = [str(c).strip().lstrip('\ufeff') for c in df.columns]
    if 'Target' not in df.columns:
        raise ValueError('No se encontró Target en el dataset UCI')
    target = df['Target'].astype(str).str.strip().str.casefold()
    mask = target.isin(['dropout', 'graduate'])
    subset = df.loc[mask]
    y = target.loc[mask].eq('dropout').astype(int)
    if len(subset) < 100 or y.nunique() != 2:
        raise ValueError('Dataset insuficiente o sin clases finales')
    _, test_indices = train_test_split(subset.index.to_numpy(), test_size=0.20,
                                        random_state=42, stratify=y)
    return df.loc[test_indices].reset_index(drop=True)


def predict_test_case(case_number: int) -> dict:
    import pandas as pd
    state = status()
    if not state['disponible']:
        raise RuntimeError(state['detalle'])
    if not 1 <= case_number <= 100_000:
        raise ValueError('El número de caso no es válido')

    bundle = _load_trusted_model(str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns)
    tests = _test_subset(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
    if case_number > len(tests):
        raise ValueError(f'El caso debe estar entre 1 y {len(tests)}')
    fields = bundle['features']
    if not isinstance(fields, list) or not fields or any(c not in tests.columns for c in fields):
        raise ValueError('Las columnas del dataset no coinciden con el modelo')
    record = tests.iloc[case_number - 1]
    X = pd.DataFrame([{name: pd.to_numeric(record[name], errors='coerce') for name in fields}], columns=fields)
    proba = float(bundle['pipeline'].predict_proba(X)[0][1])
    if not (0 <= proba <= 1):
        raise RuntimeError('La predicción no fue una probabilidad válida')
    actual = str(record['Target']).strip()
    return {
        'caso': case_number,
        'total_casos_prueba': len(tests),
        'probabilidad_desercion': round(proba, 6),
        'prediccion': 'Dropout' if proba >= 0.50 else 'Graduate',
        'resultado_historico': actual,
        'coincide': (proba >= 0.50) == (actual.casefold() == 'dropout'),
        'umbral': 0.50,
        'metodo': 'Random Forest, evaluación UCI separada 80/20',
        'variables': {name: None if pd.isna(X.iloc[0][name]) else float(X.iloc[0][name]) for name in fields},
        'advertencia': 'Demostración experimental con población UCI; NO usar para decidir sobre estudiantes de AlertaEdu. Probabilidad no calibrada ni validada externamente.'
    }
