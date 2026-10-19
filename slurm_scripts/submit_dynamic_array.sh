#!/bin/bash

# Usage: bash submit_dynamic_array.sh <job_name> [yaml_per_job]
# Resubmitting the same job name only submits YAMLs without a finished prediction.

JOB_NAME="${1:?Usage: submit_dynamic_array.sh <job_name> [yaml_per_job]}"
YAML_PER_JOB="${2:-1}"
MAX_ARRAY_SIZE=1000

# Ensure environment variables are loaded from the repository's
# environment_variables.sh (one directory above this script)
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/environment_variables.sh"
if [ -f "$ENV_FILE" ]; then
    . "$ENV_FILE"
fi

# Check for environment variables
for var in PROJECT_ROOT OUTPUT_DIR YAML_DIR LOG_DIR YAML_LIST_DIR SCRIPT_DIR SLURM_SCRIPT_DIR; do
    if [ -z "${!var:-}" ]; then
        echo "Error: $var is not set. Environment variables are not loaded." >&2
        exit 1
    fi
done

# Slurm settings (defaults match environment_variables.sh)
SLURM_CLUSTER="${SLURM_CLUSTER:-granite}"
SLURM_PARTITION="${SLURM_PARTITION:-rai-gpu-grn}"
SLURM_QOS="${SLURM_QOS:-rai-gpu-grn}"
SLURM_ACCOUNT="${SLURM_ACCOUNT:-rai}"
SLURM_GRES="${SLURM_GRES:-gpu:h200:1}"
SLURM_CPUS_PER_TASK="${SLURM_CPUS_PER_TASK:-4}"
SLURM_MEM="${SLURM_MEM:-16G}"
SLURM_MAX_CONCURRENT="${SLURM_MAX_CONCURRENT:-10}"
SLURM_MINUTES_PER_YAML="${SLURM_MINUTES_PER_YAML:-15}"

# Paths
OUTPUT_LOC="$OUTPUT_DIR/$JOB_NAME"
YAML_LOC="$YAML_DIR/$JOB_NAME"
LOG_LOC="$LOG_DIR/boltz_array_$JOB_NAME"

# Make directories
mkdir -p "$OUTPUT_LOC" "$LOG_LOC" "$YAML_LIST_DIR"

# Produce YAML list file (only YAMLs without a finished prediction)
YAML_LIST="$YAML_LIST_DIR/yaml_list_$JOB_NAME.txt"
if ! python3 "$SCRIPT_DIR/prep_yaml_lists.py" --output_folder "$JOB_NAME" --create_list; then
    echo "Error: Could not build the YAML list for $JOB_NAME" >&2
    exit 1
fi
NUM_YAML=$(wc -l < "$YAML_LIST" | tr -d ' ')

# Ensure there are .YAML files left to run
if [ "$NUM_YAML" -eq 0 ]; then
    echo "No unfinished YAML files for $JOB_NAME in $YAML_LOC. Nothing to submit."
    exit 0
fi

# Use batching if the array would exceed the cluster limit
TASKS_NEEDED=$(( (NUM_YAML + YAML_PER_JOB - 1) / YAML_PER_JOB ))

if [ "$TASKS_NEEDED" -gt "$MAX_ARRAY_SIZE" ]; then
    echo "Warning: Requested configuration would create $TASKS_NEEDED array tasks."
    echo "Cluster limit is $MAX_ARRAY_SIZE."

    OLD_YAML_PER_JOB=$YAML_PER_JOB
    YAML_PER_JOB=$(( (NUM_YAML + MAX_ARRAY_SIZE - 1) / MAX_ARRAY_SIZE ))
    TASKS_NEEDED=$(( (NUM_YAML + YAML_PER_JOB - 1) / YAML_PER_JOB ))

    echo "Increasing YAML_PER_JOB from $OLD_YAML_PER_JOB to $YAML_PER_JOB."
fi

MAX_INDEX=$((TASKS_NEEDED - 1))

# Walltime scales with the number of predictions per task (minimum 1 hour)
TIME_MINUTES=$(( YAML_PER_JOB * SLURM_MINUTES_PER_YAML ))
if [ "$TIME_MINUTES" -lt 60 ]; then
    TIME_MINUTES=60
fi
SLURM_TIME=$(printf "%02d:%02d:00" $((TIME_MINUTES / 60)) $((TIME_MINUTES % 60)))

echo "Found $NUM_YAML unfinished YAML files in $YAML_LOC"
echo "YAML list saved to $YAML_LIST"

SBATCH_ARGS=(
    --job-name="$JOB_NAME"
    --time="$SLURM_TIME"
    --cpus-per-task="$SLURM_CPUS_PER_TASK"
    --gres="$SLURM_GRES"
    --mem="$SLURM_MEM"
    --cluster="$SLURM_CLUSTER"
    --partition="$SLURM_PARTITION"
    --qos="$SLURM_QOS"
    --account="$SLURM_ACCOUNT"
    --array=0-"$MAX_INDEX"%"$SLURM_MAX_CONCURRENT"
    --export=ALL,YAML_LIST="$YAML_LIST",OUTPUT_DIR="$OUTPUT_LOC",YAML_PER_JOB="$YAML_PER_JOB",NUM_YAML="$NUM_YAML"
    --output="$LOG_LOC/task_%A_%a.log"
    --error="$LOG_LOC/task_%A_%a.log"
)

if [ -n "${SLURM_MAIL_USER:-}" ]; then
    SBATCH_ARGS+=(--mail-user="$SLURM_MAIL_USER" --mail-type=BEGIN,END,FAIL)
fi

# Submit job array and capture output
SBATCH_OUTPUT=$(sbatch "${SBATCH_ARGS[@]}" "$SLURM_SCRIPT_DIR/dynamic_array_worker.sh" 2>&1)
SBATCH_EXIT_CODE=$?

if [ $SBATCH_EXIT_CODE -eq 0 ]; then
    JOB_ID=$(echo "$SBATCH_OUTPUT" | awk '{print $NF}')

    echo ""
    echo "========================================"
    echo "Submission successful"
    echo "Job ID: $JOB_ID"
    echo "Job Name: $JOB_NAME"
    echo "Total YAML files: $NUM_YAML"
    echo "YAMLs per task: $YAML_PER_JOB"
    echo "Array tasks: $TASKS_NEEDED"
    echo "Walltime per task: $SLURM_TIME"
    echo "Max concurrent tasks: $SLURM_MAX_CONCURRENT"
    echo "Logs: $LOG_LOC"
    echo "========================================"
else
    echo ""
    echo "========================================"
    echo "ERROR: Job submission failed"
    echo "$SBATCH_OUTPUT"
    echo "========================================"
    exit 1
fi
