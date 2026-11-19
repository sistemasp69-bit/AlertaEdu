"""RF-07: reentrenamiento supervisado, versionado, sin sustituir modelo activo.

Ejecutar en AlertaEdu:
  python REENTRENAR_RF07.py
  python REENTRENAR_RF07.py --csv "datos_historicos/data.csv" --forzar

Requiere entrenador_rf04.py o entrenar_uci_experimental.py con train(csv_path, out_dir).
No toca la base SQLite ni modelos/experimento_uci_rf04.joblib.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil

ROOT = Path(__file__).resolve().parent
VERSIONS = ROOT / 'modelos' / 'versiones_uci'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def entrenador():
    options = (ROOT / 'entrenador_rf04.py', ROOT / 'entrenar_uci_experimental.py')
    for path in options:
        if path.is_file():
            spec = importlib.util.spec_from_file_location('_entrenador_uci_rf07_local', path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not callable(getattr(module, 'train', None)):
                continue
            return module.train, path
    raise FileNotFoundError('Falta entrenador_rf04.py o entrenar_uci_experimental.py en la carpeta AlertaEdu')


def ejecutar(csv: Path, forzar=False):
    csv = csv.expanduser().resolve()
    if not csv.is_file():
        raise FileNotFoundError(f'No se encuentra el dataset histórico: {csv}')
    train, code = entrenador()
    dataset_hash = sha256(csv)
    trainer_hash = sha256(code)
    VERSIONS.mkdir(parents=True, exist_ok=True)
    if not forzar:
        for meta in VERSIONS.glob('uci-*/version.json'):
            try:
                data = json.loads(meta.read_text(encoding='utf-8'))
                if (data.get('sha256_datos') == dataset_hash and
                    data.get('sha256_entrenador') == trainer_hash):
                    print('YA EXISTE UNA VERSIÓN PARA ESTOS DATOS Y ESTE ENTRENADOR:', data['version'])
                    print('No se duplicó. Cambia los datos históricos verificados o usa --forzar para repetir el ensayo.')
                    return data
            except (OSError, ValueError, KeyError, TypeError):
                pass
    version = 'uci-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + secrets.token_hex(2)
    staging = VERSIONS / ('.temporal-' + version)
    dest = VERSIONS / version
    if staging.exists() or dest.exists():
        raise FileExistsError('Conflicto de versión; no se sobrescribirá nada')
    staging.mkdir()
    try:
        print('Entrenando modelo experimental UCI. No modifica expedientes ni modelo activo...')
        metrics = train(csv, staging)
        model_file = staging / 'experimento_uci_rf04.joblib'
        metrics_file = staging / 'experimento_uci_rf04_metricas.json'
        if not model_file.is_file() or not metrics_file.is_file():
            raise ValueError('El entrenador no creó los dos artefactos esperados')
        data = {
            'version': version,
            'fecha_utc': datetime.now(timezone.utc).isoformat(),
            'archivo_fuente': csv.name,
            'sha256_datos': dataset_hash,
            'sha256_entrenador': trainer_hash,
            'archivo_modelo': model_file.name,
            'sha256_modelo': sha256(model_file),
            'metricas': metrics,
            'activado_en_alumnos': False,
            'advertencia': 'Modelo experimental UCI; no validado para la institución. No se reemplaza el modelo original.',
        }
        (staging / 'version.json').write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(staging, dest)
        print('\nVERSIÓN GUARDADA:', version)
        print('Ruta:', dest)
        print(f"F1={metrics['f1_dropout']:.4f}  Recall={metrics['recall_dropout']:.4f}  AUC={metrics['roc_auc']:.4f}")
        print('NO se reemplazó el modelo activo ni se modificó SQLite.')
        return data
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description='RF-07: reentrenamiento experimental UCI con historial de versiones')
    parser.add_argument('--csv', type=Path, default=ROOT / 'datos_historicos' / 'data.csv')
    parser.add_argument('--forzar', action='store_true', help='Crear otra versión aun con el mismo dataset y entrenador')
    args = parser.parse_args()
    ejecutar(args.csv, args.forzar)


if __name__ == '__main__':
    main()
