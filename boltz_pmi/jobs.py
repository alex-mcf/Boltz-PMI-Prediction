"""Stage 3 support: track which YAMLs have finished and build submission lists.

submit_dynamic_array.sh calls `python -m boltz_pmi jobs --output_folder <job> --create_list`
before every submission, so resubmitting a job only runs YAMLs without a
finished prediction.
"""
import argparse
import shutil
from pathlib import Path

from boltz_pmi import config
from boltz_pmi.outputs import finished_stems, iter_results_folders_without_predictions


def input_yaml_files(yaml_dir: Path, job_name: str) -> list[Path]:
    input_folder_path = yaml_dir / job_name

    if not input_folder_path.is_dir():
        raise FileNotFoundError(f"Error: YAML folder '{input_folder_path}' does not exist.")

    # Sorted so array task indices map to the same YAMLs on every run
    return sorted(
        file for file in input_folder_path.iterdir()
        if file.is_file() and file.suffix == ".yaml"
    )


def job_status(output_folder: Path, yaml_dir: Path) -> tuple[list[Path], list[Path]]:
    """Return (unfinished YAMLs, all input YAMLs) for one job."""
    if not output_folder.is_dir():
        raise NotADirectoryError(f"Error: Output folder '{output_folder}' is not a valid directory.")

    done = finished_stems(output_folder)
    all_yamls = input_yaml_files(yaml_dir, output_folder.name)
    unfinished = [f for f in all_yamls if f.stem not in done]
    return unfinished, all_yamls


def print_status(job_name: str, unfinished: list, all_yamls: list) -> None:
    n_total = len(all_yamls)
    n_finished = n_total - len(unfinished)
    percentage = n_finished / n_total * 100 if n_total else 0.0

    report = f"Prediction Status {job_name}:"
    report += f"\n\tFinished: {n_finished}"
    report += f"\tUnfinished: {len(unfinished)}"
    report += f"\tTotal: {n_total}"
    report += f"\tPercentage: {percentage:.2f}%"
    print(report)


def write_yaml_list(unfinished: list[Path], all_yamls: list[Path], list_file: Path) -> None:
    # The file is always (re)written, even when empty, so a stale list from a
    # previous submission is never resubmitted.
    list_file.parent.mkdir(parents=True, exist_ok=True)

    if not unfinished:
        print(f"All YAML files in {list_file.stem} have been processed successfully.")
    elif len(unfinished) == len(all_yamls):
        print("No YAML files have been processed successfully yet. List of all input YAML files will be used.")

    with open(list_file, "w") as f:
        for yaml_file in unfinished:
            f.write(f"{yaml_file}\n")


def remove_unfinished_output_folders(output_folder: Path, dry_run: bool = False, verbose: bool = False):
    # Do not run this while jobs for this folder are still in the queue:
    # in-progress predictions look identical to failed ones.
    partially_completed = list(iter_results_folders_without_predictions(output_folder))

    if not dry_run:
        for folder in partially_completed:
            shutil.rmtree(folder)

    if verbose and partially_completed:
        print(f"{len(partially_completed)} partially completed predictions in {output_folder.name}:")
        for folder in partially_completed:
            print(f"\t{'Would delete' if dry_run else 'Deleting'}: {folder.name}")

    if verbose and not partially_completed:
        print(f"No partially completed predictions found in {output_folder.name}.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Report job progress and build YAML lists for (re)submission.")
    ap.add_argument("--output_folder", type=str, nargs="+", help="Job name(s) under $OUTPUT_DIR")
    ap.add_argument("--process_all", action="store_true")
    ap.add_argument("--create_list", action="store_true", help="Write the list of unfinished YAMLs to $YAML_LIST_DIR")
    ap.add_argument("--remove_unfinished", action="store_true", help="Remove output folders without successful predictions")
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Print finished/unfinished counts")
    args = ap.parse_args(argv)

    if not args.output_folder and not args.process_all:
        ap.error("Provide --output_folder or --process_all.")

    output_dir = config.path("OUTPUT_DIR")
    yaml_dir = config.path("YAML_DIR")

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
                print(f"Warning: Output folder '{folder_name}' is not a valid directory and will be skipped.")

    for folder_path in folders:
        unfinished, all_yamls = job_status(folder_path, yaml_dir)
        if args.verbose:
            print_status(folder_path.name, unfinished, all_yamls)
        if args.create_list:
            list_file = config.path("YAML_LIST_DIR") / f"yaml_list_{folder_path.name}.txt"
            write_yaml_list(unfinished, all_yamls, list_file)
        if args.remove_unfinished:
            remove_unfinished_output_folders(folder_path, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
