#!/usr/bin/env bash

set -euo pipefail
if command -v module >/dev/null 2>&1; then
    module load python
fi

# Builds Boltz-2 YAML inputs and submits them to the University of Utah HPC.
# Each stage is a `python -m boltz_pmi <command>`; this script chains them.
#
#   1. prep inputs      download-proteome / fasta-to-csv   (when needed)
#   2. generate YAMLs   generate-yamls
#   3. submit           slurm_scripts/submit_dynamic_array.sh  (uses `jobs` to skip finished YAMLs)
#
# After the jobs finish:  python -m boltz_pmi parse --output_folder <job_name>
#
# Usage:
#   bash run_pipeline.sh --ligand_csv <file> (--protein_csv <file> | --proteome) [options]
#   bash run_pipeline.sh --pairs_csv <file> [options]
#
# Options:
#   --job_name <name>       Name for the YAML folder, output folder, and logs (default: run_<timestamp>)
#   --yaml_per_job <n>      Predictions per Slurm array task (default: 1)
#   --smiles_txt <file>     SMILES added to every complex as an extra (unscored) ligand
#   --dry-run               Generate YAMLs without submitting jobs

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

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
boltz_pmi() {
    python -m boltz_pmi "$@"
}

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
PAIRS_CSV=""
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
        --pairs_csv)
            PAIRS_CSV="$(abspath "$2")"
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
if [[ -n "$PAIRS_CSV" ]]; then
    if [[ -n "$PROTEIN_CSV$LIGAND_CSV" || "$USE_PROTEOME" -eq 1 ]]; then
        echo "ERROR: --pairs_csv cannot be combined with --protein_csv, --ligand_csv, or --proteome"
        exit 1
    fi
    if [[ ! -f "$PAIRS_CSV" ]]; then
        echo "ERROR: Pair CSV not found at $PAIRS_CSV"
        exit 1
    fi
    echo "Running in pair CSV mode."
else
    if [[ -z "$LIGAND_CSV" ]]; then
        echo "ERROR: You must provide --ligand_csv (or --pairs_csv)"
        exit 1
    fi
    if [[ ! -f "$LIGAND_CSV" ]]; then
        echo "ERROR: Ligand CSV not found at $LIGAND_CSV"
        exit 1
    fi
    if [[ "$USE_PROTEOME" -eq 1 && -n "$PROTEIN_CSV" ]]; then
        echo "ERROR: Use either --protein_csv or --proteome, not both"
        exit 1
    fi
    if [[ "$USE_PROTEOME" -eq 0 && -z "$PROTEIN_CSV" ]]; then
        echo "ERROR: You must provide --protein_csv OR use --proteome"
        exit 1
    fi
    echo "Using ligand CSV: $LIGAND_CSV"
fi

# The job name ties the YAML folder, output folder, and logs together,
# so pick one here if none was given.
if [[ -z "$JOB_NAME" ]]; then
    JOB_NAME="run_$(date +%Y%m%d_%H%M%S)"
    echo "No --job_name given. Using $JOB_NAME"
fi

# ---------------------------------------------------------------------------
# Stage 1: prepare the protein CSV
# ---------------------------------------------------------------------------
fasta_to_csv() {
    local fasta="$1" csv="${1%.*}.csv"
    if [[ ! -f "$csv" ]]; then
        echo "Converting FASTA → CSV..." >&2
        boltz_pmi fasta-to-csv --input "$fasta" --output "$csv" >&2
    else
        echo "CSV already exists at $csv. Skipping conversion." >&2
    fi
    echo "$csv"
}

if [[ "$USE_PROTEOME" -eq 1 ]]; then
    PROTEOME_ID="${PROTEOME_ID:-UP000005640}"
    FASTA_FILE="${PROTEOME_FASTA:-$PROJECT_ROOT/inputs/proteins/proteome_${PROTEOME_ID}.fasta}"

    if [[ ! -s "$FASTA_FILE" ]]; then
        echo "Proteome FASTA missing. Downloading..."
        boltz_pmi download-proteome --proteome_id "$PROTEOME_ID" --output "$FASTA_FILE"
    else
        echo "FASTA already exists. Skipping download."
    fi

    PROTEIN_CSV="$(fasta_to_csv "$FASTA_FILE")"
elif [[ -n "$PROTEIN_CSV" ]]; then
    if [[ ! -f "$PROTEIN_CSV" ]]; then
        echo "ERROR: Protein input not found at $PROTEIN_CSV"
        exit 1
    fi

    # (tr instead of ${var,,} so this also runs on macOS bash 3.2)
    case "$(echo "$PROTEIN_CSV" | tr '[:upper:]' '[:lower:]')" in
        *.fasta|*.fa|*.faa) PROTEIN_CSV="$(fasta_to_csv "$PROTEIN_CSV")" ;;
        *.csv) ;;
        *)
            echo "ERROR: Protein input must be a CSV or FASTA file (.csv, .fasta, .fa, or .faa)"
            exit 1
            ;;
    esac
fi

if [[ -n "$PROTEIN_CSV" ]]; then
    echo "Using protein CSV: $PROTEIN_CSV"
fi

# ---------------------------------------------------------------------------
# Stage 2: generate YAMLs
# ---------------------------------------------------------------------------
echo "Generating YAML files..."
mkdir -p "$YAML_DIR"

GENERATE_ARGS=(
    --msa_base_dir "$MSA_BASE_DIR"
    --out_base_dir "$YAML_DIR"
    --output_dir_name "$JOB_NAME"
)

if [[ -n "$PAIRS_CSV" ]]; then
    GENERATE_ARGS+=(--pairs_csv "$PAIRS_CSV")
else
    GENERATE_ARGS+=(--protein_csv "$PROTEIN_CSV" --ligand_csv "$LIGAND_CSV")
fi

if [[ -n "$SMILES_TXT" ]]; then
    GENERATE_ARGS+=(--smiles_txt "$SMILES_TXT")
fi

boltz_pmi generate-yamls "${GENERATE_ARGS[@]}"

echo "Stage 2 complete. All YAMLs generated."

# ---------------------------------------------------------------------------
# Stage 3: submit Boltz jobs
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY RUN] Skipping Boltz job submission."
    echo "[DRY RUN] Would have submitted jobs using submit_dynamic_array.sh for $JOB_NAME"
else
    echo "Submitting Boltz jobs..."
    bash "$SLURM_SCRIPT_DIR/submit_dynamic_array.sh" "$JOB_NAME" "$YAML_PER_JOB"
    echo "Boltz jobs submitted for $JOB_NAME."
fi

echo ""
echo "Next steps:"
echo "  Check progress:   python -m boltz_pmi jobs --output_folder $JOB_NAME --verbose"
echo "  Retry failures:   bash slurm_scripts/submit_dynamic_array.sh $JOB_NAME"
echo "  Compile results:  python -m boltz_pmi parse --output_folder $JOB_NAME"
