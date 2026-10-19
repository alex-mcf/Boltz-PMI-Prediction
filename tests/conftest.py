import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def write_fake_prediction(results_folder: Path, stem: str, affinity: float | None = 0.5, confidence: float = 0.8):
    """Create the files Boltz writes for one prediction. affinity=None simulates a failed run."""
    pred = results_folder / "predictions" / stem
    pred.mkdir(parents=True, exist_ok=True)
    (pred / f"confidence_{stem}_model_0.json").write_text(json.dumps({
        "confidence_score": confidence,
        "ligand_iptm": confidence,
        "chains_ptm": {"0": 0.9, "1": 0.7},
    }))
    if affinity is not None:
        (pred / f"affinity_{stem}.json").write_text(json.dumps({
            "affinity_pred_value": affinity,
            "affinity_probability_binary": 0.4,
        }))
    return pred


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A scratch layout matching environment_variables.sh, with env vars pointing at it."""
    dirs = {
        "SCRATCH_ROOT": tmp_path,
        "OUTPUT_DIR": tmp_path / "boltz_results",
        "YAML_DIR": tmp_path / "yaml",
        "YAML_LIST_DIR": tmp_path / "yaml_lists",
        "PROCESSED_DIR": tmp_path / "processed",
        "PLOT_DIR": tmp_path / "plots",
    }
    for name, path in dirs.items():
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name, str(path))
    return dirs


@pytest.fixture
def protein_csv(tmp_path):
    path = tmp_path / "proteins.csv"
    path.write_text(
        "accession,protein_name,sequence\n"
        "P1,Protein one,MKTAYIAK\n"
        "P2,Protein two,MSEQNNTE\n"
    )
    return path


@pytest.fixture
def ligand_csv(tmp_path):
    path = tmp_path / "ligands.csv"
    path.write_text(
        "ligand_id,type,value\n"
        "CER_C2,smiles,CCCCCCCCCCCCC/C=C/[C@@H](O)[C@H](CO)NC(C)=O\n"
        "ATP,ccd,ATP\n"
    )
    return path
