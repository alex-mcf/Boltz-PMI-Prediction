"""Shared helpers for locating Boltz prediction outputs.

Boltz writes one results folder per *input path*:

    <out_dir>/boltz_results_<input_stem>/predictions/<yaml_stem>/

When a single YAML is passed, <input_stem> == <yaml_stem>. When a directory of
YAMLs is passed (batched array tasks), every prediction for that batch lives
under one boltz_results_<batch_dir> folder. Walking predictions/*/ handles both.
"""
import os
from pathlib import Path

FILE_DELIM = "__"


def require_env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Environment variable {name} is not set. "
            "Run `source environment_variables.sh` first."
        )
    return Path(value)


def split_stem(stem: str) -> tuple[str, str]:
    # Protein accessions never contain the delimiter (enforced in
    # generate_yaml.py), so split on the first occurrence only.
    if FILE_DELIM in stem:
        protein, ligand = stem.split(FILE_DELIM, 1)
        return protein, ligand
    return stem, "UNKNOWN"


def prediction_files(pred_folder: Path) -> tuple[Path, Path]:
    stem = pred_folder.name
    confidence_file = pred_folder / f"confidence_{stem}_model_0.json"
    affinity_file = pred_folder / f"affinity_{stem}.json"
    return confidence_file, affinity_file


def prediction_successful(pred_folder: Path) -> bool:
    confidence_file, affinity_file = prediction_files(pred_folder)
    return confidence_file.exists() and affinity_file.exists()


def iter_prediction_folders(output_folder: Path):
    """Yield every predictions/<stem>/ folder under a job output folder."""
    for results_folder in sorted(output_folder.iterdir()):
        if not results_folder.is_dir() or not results_folder.name.startswith("boltz_results_"):
            continue
        predictions = results_folder / "predictions"
        if not predictions.is_dir():
            continue
        for pred_folder in sorted(predictions.iterdir()):
            if pred_folder.is_dir():
                yield pred_folder


def iter_results_folders_without_predictions(output_folder: Path):
    """Yield boltz_results_* folders that produced no successful prediction."""
    for results_folder in sorted(output_folder.iterdir()):
        if not results_folder.is_dir() or not results_folder.name.startswith("boltz_results_"):
            continue
        predictions = results_folder / "predictions"
        pred_folders = [p for p in predictions.iterdir() if p.is_dir()] if predictions.is_dir() else []
        if not any(prediction_successful(p) for p in pred_folders):
            yield results_folder
