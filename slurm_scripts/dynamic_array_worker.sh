#!/bin/bash
#SBATCH --job-name=boltz_worker

# Submitted by submit_dynamic_array.sh, which exports YAML_LIST, OUTPUT_DIR,
# YAML_PER_JOB, and NUM_YAML. Mail and resource settings are passed on the
# sbatch command line from environment_variables.sh.

set -euo pipefail
module load boltz2
module load mmseqs2

job_id="$SLURM_ARRAY_TASK_ID"

# Same Boltz options for single and batched tasks so results are comparable
BOLTZ_ARGS=(
    --use_msa_server
    --msa_server_url="${BOLTZ_MSA_SERVER_URL:-http://colabfold02.int.chpc.utah.edu:8088}"
    --num_workers "$(( ${SLURM_CPUS_PER_TASK:-1} > 1 ? ${SLURM_CPUS_PER_TASK:-1} - 1 : 0 ))"
    --out_dir "$OUTPUT_DIR"
)
if [ -n "${BOLTZ_MAX_MSA_SEQS:-}" ]; then
    BOLTZ_ARGS+=(--max_msa_seqs "$BOLTZ_MAX_MSA_SEQS")
fi

mapfile -t YAMLS < "$YAML_LIST"

if [ "$YAML_PER_JOB" -gt 1 ]; then
    echo "YAML_PER_JOB is set to $YAML_PER_JOB. Each job will process multiple YAML files."

    yaml_index_start=$((job_id * YAML_PER_JOB))
    yaml_index_end=$((yaml_index_start + YAML_PER_JOB - 1))

    # Don't go past the total number of YAMLs
    if [ "$yaml_index_end" -ge "$NUM_YAML" ]; then
        yaml_index_end=$((NUM_YAML - 1))
    fi

    echo "----------------------------------------"
    echo "Running task $SLURM_ARRAY_TASK_ID on $(hostname)"
    echo "Processing the following YAML files: $((yaml_index_start + 1)) through $((yaml_index_end + 1))"
    echo "Progress: $((yaml_index_start + 1))-$((yaml_index_end + 1)) / $NUM_YAML"
    echo "----------------------------------------"

    # Link this task's YAMLs into one directory and run Boltz once on it, so
    # the model is loaded once per task instead of once per YAML. Boltz skips
    # inputs that fail and keeps going with the rest of the directory.
    # Results land in $OUTPUT_DIR/boltz_results_<batch_dir>/predictions/<yaml_stem>/
    batch_dir="${TMPDIR:-/tmp}/batch_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
    mkdir -p "$batch_dir"
    trap 'rm -rf "$batch_dir"' EXIT

    for ((i = yaml_index_start; i <= yaml_index_end; i++)); do
        echo "Queued YAML: ${YAMLS[$i]}"
        ln -sf "${YAMLS[$i]}" "$batch_dir/"
    done

    boltz predict "$batch_dir" "${BOLTZ_ARGS[@]}"

    echo ""
    echo "----------------------------------------"
    echo "Task $SLURM_ARRAY_TASK_ID completed YAML indices: $yaml_index_start to $yaml_index_end"
    echo "----------------------------------------"

else
    echo "YAML_PER_JOB is set to 1. Each job will process a single YAML file."

    # Pick YAML for this task
    YAML_FILE="${YAMLS[$SLURM_ARRAY_TASK_ID]}"

    echo "----------------------------------------"
    echo "Running task $SLURM_ARRAY_TASK_ID on $(hostname)"
    echo "Processing YAML: $YAML_FILE"
    echo "Progress: $((SLURM_ARRAY_TASK_ID + 1)) / $NUM_YAML"
    echo "----------------------------------------"

    # Run Boltz
    boltz predict "$YAML_FILE" "${BOLTZ_ARGS[@]}"

    echo ""
    echo "----------------------------------------"
    echo "Task $SLURM_ARRAY_TASK_ID completed YAML: $YAML_FILE"
    echo "----------------------------------------"
fi
