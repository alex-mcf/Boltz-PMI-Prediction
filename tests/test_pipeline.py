"""End-to-end test: run_pipeline.sh -> fake Slurm -> fake Boltz output -> resubmit -> parse.

Boltz and Slurm are not available locally, so `sbatch` is replaced with a stub
that records its arguments. This checks the stages hand off correctly; it does
not run dynamic_array_worker.sh.
"""
import csv
import os
import stat
import subprocess
import sys

from conftest import REPO_ROOT, write_fake_prediction


def run(cmd, env, cwd):
    result = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_full_pipeline(tmp_path, protein_csv, ligand_csv):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sbatch_log = tmp_path / "sbatch_args.txt"
    sbatch = bin_dir / "sbatch"
    sbatch.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > "{sbatch_log}"\necho "Submitted batch job 42"\n')
    sbatch.chmod(sbatch.stat().st_mode | stat.S_IEXEC)
    # Use the interpreter running the tests for `python`/`python3` in the shell scripts
    for name in ("python", "python3"):
        (bin_dir / name).symlink_to(sys.executable)

    scratch = tmp_path / "scratch"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "SCRATCH_ROOT": str(scratch),
        "SLURM_MAIL_USER": "",
    }

    # Stage 1-3: run from an unrelated directory with relative paths
    out = run(
        ["bash", str(REPO_ROOT / "run_pipeline.sh"),
         "--protein_csv", protein_csv.name, "--ligand_csv", ligand_csv.name,
         "--job_name", "e2e", "--yaml_per_job", "3"],
        env, cwd=tmp_path,
    )
    assert "Submission successful" in out
    args = sbatch_log.read_text().splitlines()
    assert "--array=0-1%10" in args  # 4 YAMLs / 3 per task = 2 tasks
    assert not any(a.startswith("--mail-user") for a in args)

    # Boltz finishes 3 of 4 predictions (one batched task, one single)
    results = scratch / "boltz_results" / "e2e"
    for stem in ["P1__ATP", "P1__CER_C2"]:
        write_fake_prediction(results / "boltz_results_batch_42_0", stem)
    write_fake_prediction(results / "boltz_results_P2__ATP", "P2__ATP")

    # Resubmitting only sends the unfinished YAML
    out = run(["bash", str(REPO_ROOT / "slurm_scripts" / "submit_dynamic_array.sh"), "e2e"], env, cwd=tmp_path)
    assert "Found 1 unfinished YAML files" in out
    assert "--array=0-0%10" in sbatch_log.read_text().splitlines()

    # Compile results
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["OUTPUT_DIR"] = str(results.parent)
    env["PROCESSED_DIR"] = str(tmp_path / "processed")
    run([sys.executable, "-m", "boltz_pmi", "parse", "--output_folder", "e2e"], env, cwd=tmp_path)
    with open(tmp_path / "processed" / "confidence_predictions_e2e.csv") as f:
        rows = list(csv.DictReader(f))
    assert sorted((r["protein"], r["ligand"]) for r in rows) == [("P1", "ATP"), ("P1", "CER_C2"), ("P2", "ATP")]


def test_cli_lists_commands():
    result = subprocess.run([sys.executable, "-m", "boltz_pmi"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert "generate-yamls" in result.stdout and "parse" in result.stdout
