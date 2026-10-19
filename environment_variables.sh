### INSTRUCTIONS
# This script defines the path variables to simplify
# other scripts and allow for quick changes. Run this
# as follows to make the variables available

# source /path/to/environment_variables.sh

### PATHS
# Defaults to the directory containing this file (where you cloned the github repo)
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# SCRATCH_ROOT is the location for outputs. If not
# using the University of Utah HPC, this can be set
# to the PROJECT_ROOT or another local directory
export SCRATCH_ROOT="${SCRATCH_ROOT:-/path/to/scratch/space}"

# Makes `python -m boltz_pmi <command>` work from any directory
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

export SLURM_SCRIPT_DIR="$PROJECT_ROOT/slurm_scripts"
export LOG_DIR="$PROJECT_ROOT/logs"
export INPUT_DIR="$PROJECT_ROOT/inputs"
export PROCESSED_DIR="$PROJECT_ROOT/processed_outputs"
export PLOT_DIR="$PROJECT_ROOT/plots"
export SOURCE_DIR="$PROJECT_ROOT/inputs/proteins" # Reference CSVs used by the control-set and boxplots commands


export OUTPUT_DIR="$SCRATCH_ROOT/boltz_results"
export YAML_DIR="$SCRATCH_ROOT/yaml"
export YAML_LIST_DIR="$SCRATCH_ROOT/yaml_lists" # Per-job lists of YAMLs still to run, rebuilt on every submission
export MSA_BASE_DIR="$SCRATCH_ROOT/msa_per_protein/proteome" # Use this if you have downloaded local MSA files

### SLURM SETTINGS
# Read by slurm_scripts/submit_dynamic_array.sh. The defaults target the RAI
# partition on CHPC's granite cluster; change them for your own allocation.
export SLURM_MAIL_USER=""                 # Your email for job notifications (blank = no emails)
export SLURM_CLUSTER="granite"
export SLURM_PARTITION="rai-gpu-grn"
export SLURM_QOS="rai-gpu-grn"
export SLURM_ACCOUNT="rai"
export SLURM_GRES="gpu:h200:1"
export SLURM_CPUS_PER_TASK=4
export SLURM_MEM="16G"
export SLURM_MAX_CONCURRENT=10            # Max array tasks running at once
export SLURM_MINUTES_PER_YAML=15          # Walltime budget per prediction; scaled by YAMLs per task

### BOLTZ SETTINGS
export BOLTZ_MSA_SERVER_URL="http://colabfold02.int.chpc.utah.edu:8088"
export BOLTZ_MAX_MSA_SEQS=""              # Blank = Boltz default (8192). Set e.g. 256 for faster, less accurate runs
