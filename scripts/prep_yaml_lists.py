import shutil
import argparse
from pathlib import Path

from boltz_outputs import (
    iter_prediction_folders,
    iter_results_folders_without_predictions,
    prediction_successful,
    require_env_path,
)

YAML_DIR = require_env_path("YAML_DIR")
OUTPUT_DIR = require_env_path("OUTPUT_DIR")
YAML_LIST_DIR = require_env_path("YAML_LIST_DIR")

def get_finished_stems(output_folder: Path) -> set[str]:
    # Look in output directory for YAML files with completed predictions.
    # Returns the set of YAML stems whose confidence and affinity files exist.
    return {
        pred_folder.name
        for pred_folder in iter_prediction_folders(output_folder)
        if prediction_successful(pred_folder)
    }


def process_output_folder(output_folder: Path, verbose: bool = False):
    folder_name = output_folder.name

    if not output_folder.exists():
        raise FileNotFoundError(f"Error: Output folder '{folder_name}' does not exist.")

    if not output_folder.is_dir():
        raise NotADirectoryError(f"Error: Output folder '{folder_name}' is not a valid directory.")

    finished_stems = get_finished_stems(output_folder)

    job_name = folder_name.split("boltz_results_")[-1]
    input_yaml_files = get_input_yaml_files(job_name)
    unfinished_yaml_files = [f for f in input_yaml_files if f.stem not in finished_stems]

    if verbose:
        n_total = len(input_yaml_files)
        n_finished = n_total - len(unfinished_yaml_files)
        percentage = n_finished / n_total * 100 if n_total else 0.0

        report = f"Prediction Status {folder_name}:"
        report += f"\n\tFinished: {n_finished}"
        report += f"\tUnfinished: {n_total - n_finished}"
        report += f"\tTotal: {n_total}"
        report += f"\tPercentage: {percentage:.2f}%"
        print(report)

    return unfinished_yaml_files, input_yaml_files


def create_yaml_list(unfinished_yaml_files: list, input_yaml_files: list, output_folder_name: str):
    # Write the list of YAML files which have not been successfully processed by Boltz.
    # The file is always (re)written, even when empty, so a stale list from a
    # previous submission is never resubmitted.
    YAML_LIST_DIR.mkdir(parents=True, exist_ok=True)
    yaml_list_location = YAML_LIST_DIR / f"yaml_list_{output_folder_name}.txt"

    if not unfinished_yaml_files:
        print(f"All YAML files in {output_folder_name} have been processed successfully.")
    elif len(unfinished_yaml_files) == len(input_yaml_files):
        print(f"No YAML files in {output_folder_name} have been processed successfully. List of all input YAML files will be used.")

    with open(yaml_list_location, "w") as f:
        for yaml_file in unfinished_yaml_files:
            f.write(f"{yaml_file}\n")


def get_input_yaml_files(input_folder: str):
    input_folder_path = YAML_DIR / input_folder

    if not input_folder_path.is_dir():
        raise FileNotFoundError(f"Error: YAML folder '{input_folder_path}' does not exist.")

    # Sorted so array task indices map to the same YAMLs on every run
    return sorted(
        file for file in input_folder_path.iterdir()
        if file.is_file() and file.suffix == ".yaml"
    )


def remove_unfinished_output_folders(output_folder: Path, dry_run: bool = False, verbose: bool = False):
    # Do not run this while jobs for this folder are still in the queue:
    # in-progress predictions look identical to failed ones.
    partially_completed = list(iter_results_folders_without_predictions(output_folder))

    if not dry_run:
        for folder in partially_completed:
            shutil.rmtree(folder)

    if verbose and partially_completed:
        num_partially_completed = len(partially_completed)
        print(f"{num_partially_completed} partially completed predictions in {output_folder.name}:")
        for folder in partially_completed:
            if not dry_run:
                print(f"\tDeleting: {folder.name}")
            else:
                print(f"\tWould delete: {folder.name}")

    if verbose and not partially_completed:
        print(f"No partially completed predictions found in {output_folder.name}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output_folder", type=str, nargs="+")
    ap.add_argument("--process_all", action="store_true")
    ap.add_argument("--create_list", action="store_true", help="Create list of unfinished YAML files for supplemental predictions")
    ap.add_argument("--remove_unfinished", action="store_true", help="Remove output folders without successful predictions")
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not args.output_folder and not args.process_all:
        print("No arguments provided. Please provide either --output_folder or --process_all.")
        return

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
                print(f"Warning: Output folder '{folder_name}' is not a valid directory and will be skipped.")

    for folder_path in folders:
        unfinished_yaml_files, input_yaml_files = process_output_folder(folder_path, verbose=args.verbose)
        if args.create_list:
            create_yaml_list(unfinished_yaml_files, input_yaml_files, folder_path.name)
        if args.remove_unfinished:
            remove_unfinished_output_folders(folder_path, dry_run=args.dry_run, verbose=args.verbose)

if __name__ == "__main__":
    main()
