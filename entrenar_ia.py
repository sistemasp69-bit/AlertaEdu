"""Entrena RF-04 usando SOLO historiales con resultado real conocido.

CSV requerido (UTF-8): promedio,asistencia,reprobadas,deserto
'\n'deserto: 1 = abandonó estudios según criterio institucional; 0 = continuó.
NO UTILIZAR el Excel ficticio de importación ni etiquetas inventadas por reglas.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse
import csv
import json
import math
import sys

from app.ia_core import MODEL_DIR, MODEL_FILE, METADATA_FILE, FEATURES


def read_labeled_csv(path):
    xs, ys = [], []
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        needed = set(FEATURES) | {'deserto'}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError('Faltan columnas: promedio, asistencia, reprobadas, deserto')
        for no, row in enumerate(reader, start=2):
            try:
                prom = float(row['promedio'])
                asist = float(row['asistencia'])
                reprb = int(row['reprobadas'])
                label = int(row['deserto'])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Datos numéricos incorrectos en fila {no}') from exc
            if not (math.isfinite(prom) and math.isfinite(asist) and 0 <= prom <= 10
                    and 0 <= asist <= 100 and 0 <= reprb <= 30 and label in (0, 1)):
                raise ValueError(f'Fuera de rango en fila {no}')
            xs.append([prom, asist, reprb])
            ys.append(label)
    counts = Counter(ys)
    if len(xs) < 100 or min(counts.get(0, 0), counts.get(1, 0)) < 30:
        raise ValueError('Necesitas por lo menos 100 casos y 30 ejemplos de cada clase (continuó / desertó).')
    return xs, ys


def train(csv_path, confirm):
    if not confirm:
        raise ValueError('Debes confirmar explícitamente que son historiales reales, autorizados y etiquetados.')
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score, brier_score_loss
    import joblib

    xs, ys = read_labeled_csv(csv_path)
    X_train, X_test, y_train, y_test = train_test_split(
        xs, ys, test_size=0.25, random_state=42, stratify=ys
    )
    model = CalibratedClassifierCV(
        estimator=RandomForestClassifier(
            n_estimators=250, min_samples_leaf=5,
            class_weight='balanced', random_state=42, n_jobs=-1
        ), cv=3, method='sigmoid'
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= .5).astype(int)
    scores = {'f1_desercion': round(float(f1_score(y_test, preds, zero_division=0)), 4),
              'recall_desercion': round(float(recall_score(y_test, preds, zero_division=0)), 4),
              'precision_desercion': round(float(precision_score(y_test, preds, zero_division=0)), 4),
              'auc_roc': round(float(roc_auc_score(y_test, proba)), 4),
              'brier': round(float(brier_score_loss(y_test, proba)), 4),
              'casos_prueba': len(y_test)}
    print('Resultados medidos en conjunto de prueba separado:\n' + json.dumps(scores, ensure_ascii=False, indent=2))
    eligible = scores['f1_desercion'] >= 0.80 and scores['recall_desercion'] >= 0.85
    if not eligible:
        print('NO ACTIVADO: no alcanza F1 >= 0.80 y Recall >= 0.85. Ajusta y valida con datos históricos.', file=sys.stderr)
        return False

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    metadata = {'aprobado': True, 'version': version, 'metricas': scores,
                'features': list(FEATURES), 'total_historial': len(xs),
                'entrenado_utc': datetime.now(timezone.utc).isoformat(),
                'origen': 'Historial etiquetado confirmado por operador',
                'advertencia': 'Valida por periodos/cohortes antes del uso institucional.'}
    # Guardar de manera que la metainformación sólo anuncie el modelo nuevo cuando ya existe.
    temp_path = MODEL_DIR / 'modelo_rf_calibrado.temporal.joblib'
    joblib.dump(model, temp_path)
    temp_path.replace(MODEL_FILE)
    METADATA_FILE.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    print('MODELO ML VALIDADO Y PUBLICADO: ' + version)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True, type=Path, help='CSV HISTÓRICO etiquetado, no el Excel ficticio')
    parser.add_argument('--confirmar-datos-verificados', action='store_true')
    args = parser.parse_args()
    try:
        ok = train(args.csv, args.confirmar_datos_verificados)
        sys.exit(0 if ok else 2)
    except (OSError, ValueError) as exc:
        print('Entrenamiento cancelado:', exc, file=sys.stderr)
        sys.exit(1)
