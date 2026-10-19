# How to do Large-Scale Predictions of Protein-Metabolite Interactions Using our Boltz-2 Pipeline

This guide explains how the project is organized and the steps needed to run it.

## How the pipeline fits together

```
 inputs/                    YAML_DIR/<job>/                 OUTPUT_DIR/<job>/                     PROCESSED_DIR/
 protein CSV ─┐             {protein}__{ligand}.yaml        boltz_results_*/predictions/<stem>/   confidence_predictions_<job>.csv
 ligand CSV  ─┼─▶ generate-yamls ─────────▶ submit_dynamic_array.sh ──▶ (Boltz on CHPC) ──▶ parse ─────────▶ boxplots / top-binders
 pair CSV    ─┘                               ▲        │
                                              └─ jobs ◀┘  (lists unfinished YAMLs for each (re)submission)
```

| Stage | Code | What it does |
|---|---|---|
| 1. Prep inputs | `boltz_pmi/prep/` | Download a proteome, convert FASTA to CSV, sample a background set, build a control set |
| 2. Generate YAMLs | `boltz_pmi/yamls.py` | One Boltz YAML per protein-ligand pair |
| 3. Run on Slurm | `slurm_scripts/`, `boltz_pmi/jobs.py` | Submit array jobs; track and resubmit unfinished YAMLs |
| 4. Compile results | `boltz_pmi/outputs.py` | Find predictions in either output layout and write one CSV per job |
| 5. Analyze | `boltz_pmi/analysis/` | Plots and binder lists from the compiled CSVs |

Shared modules keep the stages consistent:

- `boltz_pmi/naming.py` defines the `{protein}__{ligand}` naming convention. Stage 2 writes it and stage 4 reads it.
- `boltz_pmi/inputs.py` defines the three input CSV formats.
- `boltz_pmi/config.py` reads paths from `environment_variables.sh` when a command runs, so any module can be imported from a notebook or app without the environment loaded.

`run_pipeline.sh` chains stages 1–3. Every stage is also a standalone command:

```bash
python -m boltz_pmi            # list commands
python -m boltz_pmi parse -h   # options for one command
```

## Input formats

| Format | Required columns | Used for |
|---|---|---|
| Protein CSV | `accession`, `sequence` | Proteins to screen (extra columns such as `protein_name` are fine) |
| Ligand CSV | `ligand_id`, `type` (`smiles` or `ccd`), `value` | Ligands to screen against every protein |
| Pair CSV | `accession`, `sequence`, `ligand_id`, `type`, `value` | Explicit pairs instead of a full cross product (e.g. control sets) |

Protein files can also be FASTA (`.fasta`, `.fa`, `.faa`); `run_pipeline.sh` converts them to CSV.

---

## Step 1: Set up the Python environment

This project was tested using a Conda environment with Python 3.11.

```bash
conda create -n boltz-pmi python=3.11
conda activate boltz-pmi
pip install -r requirements.txt
```

---

## Step 2: Set up `environment_variables.sh`

The only path you must set is `SCRATCH_ROOT`, the scratch space for large Boltz outputs. Everything else is derived from it or from the repository location. Then load the variables:

```bash
source environment_variables.sh
```

This also adds the repository to `PYTHONPATH`, so `python -m boltz_pmi ...` works from any directory.

### Important variables

- `PROJECT_ROOT` = root of the repository (detected automatically)
- `SCRATCH_ROOT` = scratch space for large Boltz outputs (**you must set this**)
- `YAML_DIR`, `OUTPUT_DIR`, `YAML_LIST_DIR` = Boltz inputs, raw outputs, and submission lists (under `SCRATCH_ROOT`)
- `MSA_BASE_DIR` = optional precomputed MSAs at `<accession>/msa.a3m`. Proteins without one use the MSA server.
- `PROCESSED_DIR` = compiled CSVs
- `PLOT_DIR` = figures
- `SOURCE_DIR` = reference CSVs for the `control-set` and `boxplots` commands

---

## Step 3: Customize Slurm submission

All Slurm and Boltz settings live in the `SLURM SETTINGS` and `BOLTZ SETTINGS` sections of `environment_variables.sh`. You don't need to edit the Slurm scripts.

- `SLURM_MAIL_USER`: your email for job notifications (leave blank for none)
- `SLURM_ACCOUNT`, `SLURM_PARTITION`, `SLURM_QOS`, `SLURM_CLUSTER`, `SLURM_GRES`: your allocation. The defaults target the RAI partition on granite.
- `SLURM_MINUTES_PER_YAML`: walltime budget per prediction. Each array task's time limit is this multiplied by the number of YAMLs in the task (minimum 1 hour).
- `BOLTZ_MAX_MSA_SEQS`: leave blank for the Boltz default, or lower it for faster runs. It applies to every task, so results stay comparable across a run.

---

## Step 4: Run the pipeline

```bash
bash run_pipeline.sh --ligand_csv <ligand file> (--protein_csv <protein file> | --proteome) [options]
bash run_pipeline.sh --pairs_csv <pair file> [options]
```

- `--proteome`: download the reviewed human proteome (UniProt UP000005640) instead of supplying a protein file
- `--pairs_csv`: run explicit protein-ligand pairs instead of a cross product
- `--job_name`: name shared by the YAML folder, output folder, and logs (defaults to `run_<timestamp>`)
- `--yaml_per_job`: predictions per array task. Values above 1 load the Boltz model once per task instead of once per prediction, which is much faster for large runs. Batching is turned on automatically when a run would need more than 1000 array tasks.
- `--smiles_txt`: a SMILES (e.g. a cofactor such as NADPH) added to every complex as an extra, unscored ligand
- `--dry-run`: generate YAMLs without submitting jobs

Paths can be relative to your current directory, and the script can be run from any directory.

### Check progress and retry failures

```bash
python -m boltz_pmi jobs --output_folder <job_name> --verbose
bash slurm_scripts/submit_dynamic_array.sh <job_name> [yaml_per_job]
```

Resubmitting a job name only submits YAMLs without a finished prediction. `jobs --remove_unfinished` deletes output folders with no successful prediction. Don't run it while that job is still queued, because in-progress predictions look the same as failed ones.

### Control sets

To check predictions against measured affinities, build a pair CSV from the PubChem/SIFTS reference files in `SOURCE_DIR`, then run it like any other job:

```bash
python -m boltz_pmi control-set --output inputs/controls.csv
bash run_pipeline.sh --pairs_csv inputs/controls.csv --job_name control_tests
```

---

## Step 5: Compile Boltz results into CSV

```bash
python -m boltz_pmi parse --output_folder <job_name>            # one job
python -m boltz_pmi parse --output_folder job_1 job_2 job_3     # several jobs
python -m boltz_pmi parse --process_all                          # every job under OUTPUT_DIR
python -m boltz_pmi parse --output_folder <job_name> --job_name my_analysis --verbose
```

Each job creates `PROCESSED_DIR/confidence_predictions_<job_name>.csv`. With a single folder, `--job_name` sets the CSV name instead. `--verbose` reports missing confidence or affinity files.

### Output
The CSV contains the original confidence and affinity fields along with:

- protein
- ligand
- micromolar_affinity_pred_value
- molar_affinity_pred_value
- neg_log_molar_affinity_pred_value

The derived affinity values are calculated from affinity_pred_value, which is log10(IC50 in micromolar):

```
micromolar_affinity = 10 ** affinity_pred_value
molar_affinity      = micromolar_affinity / 1e6
negative_log_molar  = 6 - affinity_pred_value
```

### Missing files
A prediction is included only when both `confidence_<stem>_model_0.json` and `affinity_<stem>.json` exist. If a YAML was predicted more than once (e.g. after a resubmission), only the first complete prediction is kept.

Nested fields (`chains_ptm`, `pair_chains_iptm`) are written as JSON strings; read them with `json.loads`.

---

## Step 6: Analyze

```bash
python -m boltz_pmi top-binders --csv confidence_predictions_<job>.csv --proteome_csv <protein CSV> [--ligands ID ...] [--top_x 10]
python -m boltz_pmi boxplots --target_csvs <targets.csv> --random_csvs <background.csv> --processed_csvs <predictions.csv> [--by_ligand] [--show_stats]
```

---

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover each stage, plus an end-to-end run of `run_pipeline.sh` → submission → resubmission → `parse`, using a stub `sbatch` and fake Boltz output. They don't run `dynamic_array_worker.sh`, which needs Boltz on a GPU node.

## Notes
- Full Boltz job submission requires the HPC/Slurm environment.
- Local runs are for validating inputs, generating YAMLs, compiling results, and making figures.
- Predictions are found at `boltz_results_*/predictions/{protein}__{ligand}/`. This covers both single-YAML tasks (`boltz_results_{protein}__{ligand}`) and batched tasks (`boltz_results_batch_<job>_<task>`).
- Nothing in the repo computes MSAs yet. `protein-fastas` writes the per-protein FASTAs an MSA tool would need, and `generate-yamls` uses any MSAs found under `MSA_BASE_DIR`.
