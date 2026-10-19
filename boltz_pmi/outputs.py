"""Stage 4: locate Boltz predictions and compile them into a CSV.

Boltz writes one results folder per *input path*:

    OUTPUT_DIR/<job>/boltz_results_<input_stem>/predictions/<yaml_stem>/

When a single YAML is passed, <input_stem> == <yaml_stem>. When a directory of
YAMLs is passed (batched array tasks), every prediction for that batch lives
under one boltz_results_<batch_dir> folder. Walking predictions/*/ handles both.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from boltz_pmi import config
from boltz_pmi.naming import split_stem


# ---------------------------------------------------------------------------
# Locating predictions (also used by jobs.py)
# ---------------------------------------------------------------------------

def prediction_files(pred_folder: Path) -> tuple[Path, Path]:
    stem = pred_folder.name
    confidence_file = pred_folder / f"confidence_{stem}_model_0.json"
    affinity_file = pred_folder / f"affinity_{stem}.json"
    return confidence_file, affinity_file


def prediction_successful(pred_folder: Path) -> bool:
    confidence_file, affinity_file = prediction_files(pred_folder)
    return confidence_file.exists() and affinity_file.exists()


def _results_folders(output_folder: Path):
    for results_folder in sorted(output_folder.iterdir()):
        if results_folder.is_dir() and results_folder.name.startswith("boltz_results_"):
            yield results_folder


def iter_prediction_folders(output_folder: Path):
    """Yield every predictions/<stem>/ folder under a job output folder."""
    for results_folder in _results_folders(output_folder):
        predictions = results_folder / "predictions"
        if not predictions.is_dir():
            continue
        for pred_folder in sorted(predictions.iterdir()):
            if pred_folder.is_dir():
                yield pred_folder


def finished_stems(output_folder: Path) -> set[str]:
    """YAML stems with both confidence and affinity files."""
    return {p.name for p in iter_prediction_folders(output_folder) if prediction_successful(p)}


def iter_results_folders_without_predictions(output_folder: Path):
    """Yield boltz_results_* folders that produced no successful prediction."""
    for results_folder in _results_folders(output_folder):
        predictions = results_folder / "predictions"
        pred_folders = [p for p in predictions.iterdir() if p.is_dir()] if predictions.is_dir() else []
        if not any(prediction_successful(p) for p in pred_folders):
            yield results_folder


# ---------------------------------------------------------------------------
# Compiling predictions
# ---------------------------------------------------------------------------

def add_affinity_units(row: dict) -> dict:
    # affinity_pred_value is log10(IC50 in uM), so -log10(M) = 6 - value.
    value = row.get("affinity_pred_value")
    if value is None:
        micromolar = molar = neg_log_molar = math.nan
    else:
        micromolar = 10 ** value
        molar = micromolar / 1e6
        neg_log_molar = 6 - value

    row["micromolar_affinity_pred_value"] = micromolar
    row["molar_affinity_pred_value"] = molar
    row["neg_log_molar_affinity_pred_value"] = neg_log_molar
    return row


def collect_predictions(output_folder: Path, verbose: bool = False) -> list[dict]:
    """Return one dict per finished prediction: protein, ligand, confidence and affinity fields."""
    rows = []
    seen_stems = set()
    num_missing_confidence_files = 0
    num_missing_affinity_files = 0
    num_duplicates = 0

    for pred_folder in iter_prediction_folders(output_folder):
        stem = pred_folder.name
        confidence_file, affinity_file = prediction_files(pred_folder)

        if not confidence_file.exists():
            if verbose:
                print(f"\tMissing confidence: {stem}")
            num_missing_confidence_files += 1

        if not affinity_file.exists():
            if verbose:
                print(f"\tMissing affinity: {stem}")
            num_missing_affinity_files += 1

        if not confidence_file.exists() or not affinity_file.exists():
            continue

        # A YAML that was resubmitted can have results in more than one
        # batch folder; keep only the first complete prediction.
        if stem in seen_stems:
            num_duplicates += 1
            continue
        seen_stems.add(stem)

        with open(confidence_file, "r") as f:
            confidence = json.load(f)

        with open(affinity_file, "r") as f:
            affinity = json.load(f)

        protein_name, ligand_name = split_stem(stem)
        row = {"protein": protein_name, "ligand": ligand_name, **confidence, **affinity}
        rows.append(add_affinity_units(row))

    if verbose:
        print(f"\tMissing confidence files: {num_missing_confidence_files}")
        print(f"\tMissing affinity files: {num_missing_affinity_files}")
        if num_duplicates:
            print(f"\tDuplicate predictions skipped: {num_duplicates}")

    return rows


def _csv_value(value):
    # Nested fields (chains_ptm, pair_chains_iptm) are written as JSON so they
    # can be parsed downstream with json.loads instead of Python repr strings.
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def write_predictions_csv(rows: list[dict], csv_file: Path) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)

    # Rows can have different keys (e.g. extra ligands add chain entries),
    # so build the header from the union of all keys, preserving order.
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))

    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(v) for k, v in row.items()})


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compile Boltz predictions into CSVs in $PROCESSED_DIR.")
    ap.add_argument("--output_folder", type=str, nargs="+", help="Name(s) of job folder(s) under $OUTPUT_DIR")
    ap.add_argument("--job_name", type=str, help="Name for the output CSV (single folder only)")
    ap.add_argument("--process_all", action="store_true", help="Process every job folder under $OUTPUT_DIR")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    if not args.output_folder and not args.process_all:
        ap.error("Provide --output_folder or --process_all.")

    output_dir = config.path("OUTPUT_DIR")
    processed_dir = config.path("PROCESSED_DIR")

    if args.process_all:
        print("Processing all output folders...")
        folders = [p for p in sorted(output_dir.iterdir()) if p.is_dir()]
    else:
        folders = []
        for folder_name in args.output_folder:
            folder_path = output_dir / folder_name
            if folder_path.is_dir():
                folders.append(folder_path)
            else:
                print(f"Output folder not found: {folder_name}")

    for folder_path in folders:
        print(f"Processing output folder: {folder_path.name}")
        rows = collect_predictions(folder_path, verbose=args.verbose)

        if not rows:
            print(f"No confidence data found for output folder: {folder_path.name}")
            continue

        job_name = args.job_name if args.job_name and len(folders) == 1 else folder_path.name
        csv_file = processed_dir / f"confidence_predictions_{job_name}.csv"
        write_predictions_csv(rows, csv_file)
        print(f"Saved {len(rows)} confidence predictions to {csv_file.name}")


if __name__ == "__main__":
    main()
