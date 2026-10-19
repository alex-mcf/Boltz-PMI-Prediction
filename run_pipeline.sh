#!/usr/bin/env bash

set -euo pipefail
if command -v module >/dev/null 2>&1; then
    module load python
fi

# This script produces YAML files to be run by Boltz-2
# and submits the jobs to the University of Utah HPC.

# Run the pipeline:
# bash run_pipeline.sh --ligand_csv <ligand file> (--protein_csv <protein file> | --proteome)
#                      [--job_name <name>] [--yaml_per_job <n>] [--smiles_txt <file>] [--dry-run]

# --proteome: download the human proteome instead of supplying a protein file
# --dry-run: run without submitting jobs

echo "Starting pipeline..."

# Resolve the repository root so the script can be run from any directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables - MAKE SURE YOU CHANGED THEM TO YOUR LOCAL VARIABLES in environment_variables.sh
ENV_FILE="$REPO_ROOT/environment_variables.sh"
if [ -f "$ENV_FILE" ]; then
    . "$ENV_FILE"
fi

for var in PROJECT_ROOT YAML_DIR MSA_BASE_DIR; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is not set. Edit $ENV_FILE first." >&2
        exit 1
    fi
done

# Convert a user-supplied path to an absolute path (relative to the caller's directory)
abspath() {
    case "$1" in
        /*) echo "$1" ;;
        *) echo "$PWD/$1" ;;
    esac
}

SMILES_TXT=""
PROTEIN_CSV=""
LIGAND_CSV=""
USE_PROTEOME=0
JOB_NAME=""
YAML_PER_JOB=1

DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --protein_csv)
            PROTEIN_CSV="$(abspath "$2")"
            shift 2
            ;;
        --ligand_csv)
            LIGAND_CSV="$(abspath "$2")"
            shift 2
            ;;
        --job_name)
            JOB_NAME="$2"
            shift 2
            ;;
        --yaml_per_job)
            YAML_PER_JOB="$2"
            shift 2
            ;;
        --proteome)
            USE_PROTEOME=1
            shift
            ;;
        --smiles_txt)
            SMILES_TXT="$(abspath "$2")"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Validate input arguments
if [[ -z "$LIGAND_CSV" ]]; then
    echo "ERROR: You must provide --ligand_csv"
    exit 1
fi

if [[ "$USE_PROTEOME" -eq 1 ]]; then
    echo "Running in proteome mode (auto download + convert)."
else
    if [[ -z "$PROTEIN_CSV" ]]; then
        echo "ERROR: You must provide --protein_csv OR use --proteome"
        exit 1
    fi
    echo "Running in manual CSV mode."
fi

# The job name ties the YAML folder, output folder, and logs together,
# so pick one here if none was given.
if [[ -z "$JOB_NAME" ]]; then
    JOB_NAME="run_$(date +%Y%m%d_%H%M%S)"
    echo "No --job_name given. Using $JOB_NAME"
fi

# Ensure directories exist
mkdir -p "$YAML_DIR"

# Step 0: Check ligand CSV
echo "Checking ligand CSV..."
if [[ ! -f "$LIGAND_CSV" ]]; then
    echo "ERROR: Ligand CSV not found at $LIGAND_CSV"
    exit 1
fi
echo "Using ligand CSV: $LIGAND_CSV"

# Step 1: Check/convert protein input
if [[ "$USE_PROTEOME" -eq 0 ]]; then
    echo "Checking protein input..."

    if [[ ! -f "$PROTEIN_CSV" ]]; then
        echo "ERROR: Protein input not found at $PROTEIN_CSV"
        exit 1
    fi

    # Determine whether the protein input is FASTA or CSV
    # (tr instead of ${var,,} so this also runs on macOS bash 3.2)
    case "$(echo "$PROTEIN_CSV" | tr '[:upper:]' '[:lower:]')" in
        *.fasta|*.fa|*.faa)
            echo "Protein input detected as FASTA."

            CSV_FILE="${PROTEIN_CSV%.*}.csv"

            if [[ ! -f "$CSV_FILE" ]]; then
                echo "Converting FASTA → CSV..."
                python "$REPO_ROOT/scripts/convert_fasta_to_csv.py" \
                    --input "$PROTEIN_CSV" \
                    --output "$CSV_FILE"
                echo "CSV created at $CSV_FILE"
            else
                echo "CSV already exists at $CSV_FILE. Skipping conversion."
            fi

            PROTEIN_CSV="$CSV_FILE"
            ;;

        *.csv)
            echo "Protein input detected as CSV."
            ;;

        *)
            echo "ERROR: Protein input must be a CSV or FASTA file (.csv, .fasta, .fa, or .faa)"
            exit 1
            ;;
    esac

    echo "Using protein CSV: $PROTEIN_CSV"
fi

# Step 2: Proteome mode
if [[ "$USE_PROTEOME" -eq 1 ]]; then
    echo "Checking protein files..."

    PROTEOME_ID="${PROTEOME_ID:-UP000005640}"
    FASTA_FILE="${PROTEOME_FASTA:-$PROJECT_ROOT/inputs/proteins/proteome_${PROTEOME_ID}.fasta}"
    CSV_FILE="${FASTA_FILE%.*}.csv"

    # Download proteome FASTA if needed
    if [[ ! -s "$FASTA_FILE" ]]; then
        echo "Proteome FASTA missing. Downloading..."
        python "$REPO_ROOT/scripts/download_proteome_fasta.py" \
            --proteome_id "$PROTEOME_ID" \
            --output "$FASTA_FILE"
        echo "Proteome downloaded."
    else
        echo "FASTA already exists. Skipping download."
    fi

    # Convert FASTA to CSV if needed
    if [[ ! -f "$CSV_FILE" ]]; then
        echo "Running FASTA → CSV conversion..."
        python "$REPO_ROOT/scripts/convert_fasta_to_csv.py" \
            --input "$FASTA_FILE" \
            --output "$CSV_FILE"
        echo "CSV created at $CSV_FILE"
    else
        echo "CSV already exists. Skipping conversion."
    fi

    PROTEIN_CSV="$CSV_FILE"

    echo "Using proteome CSV: $PROTEIN_CSV"
fi

# Step 3: Generate YAMLs
echo "Generating YAML files..."

GENERATE_ARGS=(
    --proteome_csv "$PROTEIN_CSV"
    --ceramide_csv "$LIGAND_CSV"
    --msa_base_dir "$MSA_BASE_DIR"
    --out_base_dir "$YAML_DIR"
    --output_dir_name "$JOB_NAME"
)

if [[ -n "$SMILES_TXT" ]]; then
    GENERATE_ARGS+=(--smiles_txt "$SMILES_TXT")
fi

python "$REPO_ROOT/scripts/generate_yaml.py" "${GENERATE_ARGS[@]}"

echo "Step 3 complete. All YAMLs generated."

# Step 4: Submit Boltz jobs
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY RUN] Skipping Boltz job submission."
    echo "[DRY RUN] Would have submitted jobs using submit_dynamic_array.sh for $JOB_NAME"
    echo "Step 4 complete. No Boltz jobs were submitted."
else
    echo "Submitting Boltz jobs..."
    bash "$PROJECT_ROOT/slurm_scripts/submit_dynamic_array.sh" "$JOB_NAME" "$YAML_PER_JOB"
    echo "Boltz jobs submitted for $JOB_NAME."
    echo "Step 4 complete."
fi
