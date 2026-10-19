"""Unit tests for each pipeline stage and the contracts between them."""
import csv
import json
import math

import pytest

from boltz_pmi import inputs, jobs, naming, outputs, yamls
from conftest import write_fake_prediction


# --- naming: the contract between generate-yamls and parse -----------------

def test_stem_round_trip():
    stem = naming.make_stem("Q9H3R0", "CER_d18:1/16:0")
    assert stem == "Q9H3R0__CER_d18_1_16_0"
    assert naming.split_stem(stem) == ("Q9H3R0", "CER_d18_1_16_0")


def test_ligand_may_contain_delimiter():
    assert naming.split_stem(naming.make_stem("P1", "a__b")) == ("P1", "a__b")


def test_protein_may_not_contain_delimiter():
    with pytest.raises(ValueError):
        naming.make_stem("bad__id", "L1")


# --- inputs -----------------------------------------------------------------

def test_read_inputs(protein_csv, ligand_csv):
    assert [p["accession"] for p in inputs.read_proteins(protein_csv)] == ["P1", "P2"]
    assert [l["type"] for l in inputs.read_ligands(ligand_csv)] == ["smiles", "ccd"]


def test_missing_columns_are_reported(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,seq\nP1,MK\n")
    with pytest.raises(ValueError, match="missing required columns"):
        inputs.read_proteins(bad)


def test_unknown_ligand_type(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("ligand_id,type,value\nL1,inchi,XYZ\n")
    with pytest.raises(ValueError, match="expected 'smiles' or 'ccd'"):
        inputs.read_ligands(bad)


# --- generate-yamls ---------------------------------------------------------

def test_cross_product_yamls(scratch, protein_csv, ligand_csv):
    yamls.main(["--protein_csv", str(protein_csv), "--ligand_csv", str(ligand_csv), "--job_name", "j"])
    files = sorted(p.name for p in (scratch["YAML_DIR"] / "j").iterdir())
    assert files == ["P1__ATP.yaml", "P1__CER_C2.yaml", "P2__ATP.yaml", "P2__CER_C2.yaml"]

    text = (scratch["YAML_DIR"] / "j" / "P1__CER_C2.yaml").read_text()
    assert "smiles: 'CCCCCCCCCCCCC/C=C/[C@@H](O)[C@H](CO)NC(C)=O'" in text
    assert "binder: B" in text
    assert "ccd: ATP" in (scratch["YAML_DIR"] / "j" / "P1__ATP.yaml").read_text()


def test_pairs_yamls(scratch, tmp_path):
    pairs = tmp_path / "pairs.csv"
    pairs.write_text(
        "accession,sequence,ligand_id,type,value,experimental_ic50\n"
        "P1,MKTAYIAK,L1,smiles,CCO,12.5\n"
        "P2,MSEQNNTE,L2,smiles,CCN,3.1\n"
    )
    yamls.main(["--pairs_csv", str(pairs), "--job_name", "ctrl"])
    assert sorted(p.name for p in (scratch["YAML_DIR"] / "ctrl").iterdir()) == ["P1__L1.yaml", "P2__L2.yaml"]


def test_msa_and_extra_ligand(tmp_path):
    (tmp_path / "msa" / "P1").mkdir(parents=True)
    (tmp_path / "msa" / "P1" / "msa.a3m").write_text(">P1\nMK\n")
    n = yamls.write_yamls(
        [({"accession": "P1", "sequence": "MK"}, {"ligand_id": "L", "type": "smiles", "value": "CC"})],
        tmp_path / "out",
        msa_base_dir=tmp_path / "msa",
        extra_smiles="NADPH",
    )
    text = (tmp_path / "out" / "P1__L.yaml").read_text()
    assert n == 1
    assert "msa: '" in text and "id: C" in text


def test_filename_collision_fails(tmp_path):
    protein = {"accession": "P1", "sequence": "MK"}
    pairs = [
        (protein, {"ligand_id": "CER a", "type": "smiles", "value": "CC"}),
        (protein, {"ligand_id": "CER_a", "type": "smiles", "value": "CCC"}),
    ]
    with pytest.raises(ValueError, match="both map to"):
        yamls.write_yamls(pairs, tmp_path)


# --- outputs + jobs: single and batched Boltz layouts -----------------------

@pytest.fixture
def finished_job(scratch, protein_csv, ligand_csv):
    """Job 'j' with 4 YAMLs: 1 single-layout success, 1 failure, 1 batched success (duplicated), 1 not run."""
    yamls.main(["--protein_csv", str(protein_csv), "--ligand_csv", str(ligand_csv), "--job_name", "j"])
    out = scratch["OUTPUT_DIR"] / "j"
    write_fake_prediction(out / "boltz_results_P1__ATP", "P1__ATP", affinity=1.0)
    write_fake_prediction(out / "boltz_results_P1__CER_C2", "P1__CER_C2", affinity=None)
    write_fake_prediction(out / "boltz_results_batch_1_0", "P2__ATP", affinity=-1.0)
    write_fake_prediction(out / "boltz_results_batch_2_0", "P2__ATP", affinity=-1.0)
    (out / "lightning_logs").mkdir()
    return out


def test_collect_predictions(finished_job):
    rows = outputs.collect_predictions(finished_job)
    assert [(r["protein"], r["ligand"]) for r in rows] == [("P1", "ATP"), ("P2", "ATP")]
    assert rows[0]["neg_log_molar_affinity_pred_value"] == pytest.approx(5.0)
    assert rows[1]["micromolar_affinity_pred_value"] == pytest.approx(0.1)


def test_missing_affinity_value_is_nan():
    row = outputs.add_affinity_units({"protein": "P", "ligand": "L"})
    assert math.isnan(row["molar_affinity_pred_value"])


def test_parse_cli_writes_json_fields(scratch, finished_job):
    outputs.main(["--output_folder", "j"])
    with open(scratch["PROCESSED_DIR"] / "confidence_predictions_j.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert json.loads(rows[0]["chains_ptm"]) == {"0": 0.9, "1": 0.7}


def test_jobs_lists_only_unfinished(scratch, finished_job):
    jobs.main(["--output_folder", "j", "--create_list"])
    listed = (scratch["YAML_LIST_DIR"] / "yaml_list_j.txt").read_text().split()
    assert sorted(p.rsplit("/", 1)[1] for p in listed) == ["P1__CER_C2.yaml", "P2__CER_C2.yaml"]


def test_jobs_list_is_emptied_when_all_done(scratch, finished_job):
    list_file = scratch["YAML_LIST_DIR"] / "yaml_list_j.txt"
    list_file.write_text("stale.yaml\n")
    for stem in ["P1__CER_C2", "P2__CER_C2"]:
        write_fake_prediction(finished_job / "boltz_results_batch_3_0", stem)
    jobs.main(["--output_folder", "j", "--create_list"])
    assert list_file.read_text() == ""


def test_remove_unfinished_keeps_partial_batches(finished_job):
    jobs.remove_unfinished_output_folders(finished_job)
    remaining = sorted(p.name for p in finished_job.iterdir())
    assert "boltz_results_P1__CER_C2" not in remaining
    assert "boltz_results_batch_1_0" in remaining
