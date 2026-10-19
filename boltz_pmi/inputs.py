"""Readers for the pipeline's input CSV formats.

Protein CSV:  accession, sequence (extra columns such as protein_name are kept)
Ligand CSV:   ligand_id, type (smiles | ccd), value
Pair CSV:     accession, sequence, ligand_id, type, value
              One row per protein-ligand pair to predict, for runs that are
              not a full proteins x ligands cross product (e.g. control sets).
"""
import csv
from pathlib import Path

PROTEIN_COLUMNS = ["accession", "sequence"]
LIGAND_COLUMNS = ["ligand_id", "type", "value"]
PAIR_COLUMNS = PROTEIN_COLUMNS + LIGAND_COLUMNS


def _read_rows(csv_path: Path, required: list[str]) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{csv_path} is missing required columns: {missing}")

        rows = []
        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items() if k is not None}
            if all(row.get(c) for c in required):
                rows.append(row)
        return rows


def _normalize_ligand(row: dict) -> dict:
    ltype = row["type"].lower()
    if ltype not in ("smiles", "ccd"):
        raise ValueError(f"Ligand {row['ligand_id']} has type '{row['type']}'; expected 'smiles' or 'ccd'.")
    return {"ligand_id": row["ligand_id"], "type": ltype, "value": row["value"]}


def read_proteins(csv_path: Path) -> list[dict]:
    return [
        {"accession": r["accession"], "sequence": r["sequence"].replace(" ", "")}
        for r in _read_rows(csv_path, PROTEIN_COLUMNS)
    ]


def read_ligands(csv_path: Path) -> list[dict]:
    return [_normalize_ligand(r) for r in _read_rows(csv_path, LIGAND_COLUMNS)]


def read_pairs(csv_path: Path) -> list[tuple[dict, dict]]:
    return [
        (
            {"accession": r["accession"], "sequence": r["sequence"].replace(" ", "")},
            _normalize_ligand(r),
        )
        for r in _read_rows(csv_path, PAIR_COLUMNS)
    ]


def read_single_smiles(txt_path: Path) -> str:
    text = txt_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"SMILES TXT file is empty: {txt_path}")
    return text
