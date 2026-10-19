import argparse
import json
import csv
import math
from pathlib import Path

from boltz_outputs import (
    iter_prediction_folders,
    prediction_files,
    require_env_path,
    split_stem,
)

OUTPUT_DIR = require_env_path("OUTPUT_DIR")
PROCESSED_DIR = require_env_path("PROCESSED_DIR")

def get_predictions_from_output(output_folder: Path, verbose: bool = False):
    confidence_list = []
    seen_stems = set()
    num_missing_confidence_files = 0
    num_missing_affinity_files = 0
    num_duplicates = 0

    # Each predictions/<stem>/ folder corresponds to a single YAML file,
    # named {protein}__{ligand}. See boltz_outputs.py for the layout.
    for pred_folder in iter_prediction_folders(output_folder):
        stem = pred_folder.name
        protein_name, ligand_name = split_stem(stem)
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

        protein_ligand_data = {'protein': protein_name, 'ligand': ligand_name}
        prediction_result = {**protein_ligand_data, **confidence, **affinity}
        confidence_list.append(prediction_result)

    if verbose:
        print(f"\tMissing confidence files: {num_missing_confidence_files}")
        print(f"\tMissing affinity files: {num_missing_affinity_files}")
        if num_duplicates:
            print(f"\tDuplicate predictions skipped: {num_duplicates}")

    add_additional_affinity_units(confidence_list)

    return confidence_list


def add_additional_affinity_units(confidence_list: list):
    # Add micromolar affinity, molar affinity, and -log10(molar affinity).
    # affinity_pred_value is log10(IC50 in uM), so -log10(M) = 6 - value.

    for item in confidence_list:
        affinity_pred_value = item.get("affinity_pred_value")

        if affinity_pred_value is None:
            micromolar = molar = neg_log_molar = math.nan
        else:
            micromolar = 10 ** affinity_pred_value
            molar = micromolar / 1e6
            neg_log_molar = 6 - affinity_pred_value

        item["micromolar_affinity_pred_value"] = micromolar
        item["molar_affinity_pred_value"] = molar
        item["neg_log_molar_affinity_pred_value"] = neg_log_molar


def to_csv_value(value):
    # Nested fields (chains_ptm, pair_chains_iptm) are written as JSON so they
    # can be parsed downstream with json.loads instead of Python repr strings.
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def save_data_as_csv(job_name: str, data: list):
    if not data:
        print(f"No data for {job_name}. Skipping CSV creation.")
        return

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = PROCESSED_DIR / f"confidence_predictions_{job_name}.csv"

    # Rows can have different keys (e.g. extra ligands add chain entries),
    # so build the header from the union of all keys, preserving order.
    fieldnames = list(dict.fromkeys(key for row in data for key in row))

    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in data:
            writer.writerow({k: to_csv_value(v) for k, v in row.items()})

    print(f"Saved {len(data)} confidence predictions to {csv_file.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output_folder", type=str, nargs="+", help="Name(s) of the output folder(s) to process. If not provided, --process_all will be used")
    ap.add_argument("--job_name", type=str, help="Name for the output CSV")
    ap.add_argument("--process_all", action="store_true", help="Process all output folders in the outputs directory")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not args.output_folder and not args.process_all:
        ap.error("Provide --output_folder or --process_all.")

    folders = []

    if args.process_all:
        print("Processing all output folders...")
        for folder_path in sorted(OUTPUT_DIR.iterdir()):
            if folder_path.is_dir():
                folders.append(folder_path)
    elif args.output_folder:
        for folder_name in args.output_folder:
            folder_path = OUTPUT_DIR / folder_name
            if folder_path.is_dir():
                folders.append(folder_path)
            else:
                print(f"Output folder not found: {folder_name}")

    for folder_path in folders:
        print(f"Processing output folder: {folder_path.name}")
        confidence_list = get_predictions_from_output(folder_path, verbose=args.verbose)

        if not confidence_list:
            print(f"No confidence data found for output folder: {folder_path.name}")
            continue

        if args.job_name and len(folders) == 1:
            job_name = args.job_name
        else:
            job_name = folder_path.name

        save_data_as_csv(job_name, confidence_list)


if __name__ == "__main__":
    main()
