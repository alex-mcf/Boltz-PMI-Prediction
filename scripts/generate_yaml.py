#!/usr/bin/env python3
import argparse
import csv
import os
import random
import re
from datetime import datetime
from pathlib import Path


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")


def read_proteins(csv_path: Path):
    proteins = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            acc = (row.get("accession") or "").strip()
            seq = (row.get("sequence") or "").strip()
            if acc and seq:
                proteins.append({"accession": acc, "sequence": seq})
    return proteins


def read_ceramides(csv_path: Path):
    ligands = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = (row.get("ligand_id") or "").strip()
            ltype = (row.get("type") or "").strip().lower()
            val = (row.get("value") or "").strip()
            if lid and ltype and val:
                ligands.append(
                    {"ligand_id": lid, "type": ltype, "value": val}
                )
    return ligands


def read_optional_smiles(smiles_txt: Path | None) -> str | None:
    if smiles_txt is None:
        return None

    text = smiles_txt.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"SMILES TXT file is empty: {smiles_txt}")
    return text


def make_yaml(
    protein_seq: str,
    ligand: dict,
    msa_path: str | None = None,
    extra_smiles: str | None = None,
) -> str:
    lines = []
    lines.append("version: 1")
    lines.append("sequences:")
    lines.append("  - protein:")
    lines.append("      id: A")
    lines.append(f"      sequence: {protein_seq}")

    if msa_path:
        msa_v = msa_path.replace("'", "''")
        lines.append(f"      msa: '{msa_v}'")

    lines.append("  - ligand:")
    lines.append("      id: B")

    if ligand["type"] == "ccd":
        lines.append(f"      ccd: {ligand['value']}")
    else:
        v = ligand["value"].replace("'", "''")
        lines.append(f"      smiles: '{v}'")

    if extra_smiles:
        extra_v = extra_smiles.replace("'", "''")
        lines.append("  - ligand:")
        lines.append("      id: C")
        lines.append(f"      smiles: '{extra_v}'")

    lines.append("properties:")
    lines.append("  - affinity:")
    lines.append("      binder: B")

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--proteome_csv",
        type=Path,
        required=True,
    )

    ap.add_argument(
        "--ceramide_csv",
        type=Path,
        required=True,
    )

    ap.add_argument(
        "--output_dir_name",
        type=str,
    )

    ap.add_argument(
        "--max_proteins",
        type=int,
        default=None,
        help="Only use the first (or, with --random, a random) N proteins.",
    )

    ap.add_argument(
        "--max_ligands",
        type=int,
        default=None,
        help="Only use the first (or, with --random, a random) N ligands.",
    )

    ap.add_argument(
        "--random",
        action="store_true",
        help="randomly sample instead of taking the first --max_proteins/--max_ligands",
    )

    ap.add_argument(
        "--seed",
        type=int,
        default=7,
    )

    ap.add_argument(
        "--msa_base_dir",
        type=Path,
        required=True,
        help="Base dir containing per-protein MSA folders (each should contain msa.a3m).",
    )

    ap.add_argument(
        "--out_base_dir",
        type=Path,
        default=os.environ.get("YAML_DIR"),
        help="Where to write /<run_name>",
    )

    ap.add_argument(
        "--require_msa",
        action="store_true",
        help="If set, raise an error if a protein's msa.a3m file does not exist.",
    )

    ap.add_argument(
        "--smiles_txt",
        type=Path,
        default=None,
        help="Optional TXT file containing one SMILES string.",
    )

    args = ap.parse_args()

    if args.out_base_dir is None:
        ap.error("--out_base_dir is required when YAML_DIR is not set.")

    # ------------------------------------------------------------
    # Resolve project paths
    # ------------------------------------------------------------

    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    # Relative input paths are resolved against the current directory
    # first, then against the project root.

    def resolve_input(path: Path) -> Path:
        if path.is_absolute() or path.exists():
            return path.resolve()
        return (PROJECT_ROOT / path).resolve()

    proteome_csv = resolve_input(args.proteome_csv)
    ceramides_csv = resolve_input(args.ceramide_csv)

    # ------------------------------------------------------------
    # Check input files
    # ------------------------------------------------------------

    if not proteome_csv.exists():
        raise FileNotFoundError(
            f"Missing protein CSV: {proteome_csv}"
        )

    if not ceramides_csv.exists():
        raise FileNotFoundError(
            f"Missing ligand CSV: {ceramides_csv}"
        )

    # ------------------------------------------------------------
    # Resolve optional SMILES file
    # ------------------------------------------------------------

    if args.smiles_txt is not None:
        smiles_txt = resolve_input(args.smiles_txt)

        if not smiles_txt.exists():
            raise FileNotFoundError(
                f"Missing SMILES TXT file: {smiles_txt}"
            )
    else:
        smiles_txt = None

    # ------------------------------------------------------------
    # Read input files
    # ------------------------------------------------------------

    print(f"Protein CSV: {proteome_csv}")
    print(f"Ligand CSV:  {ceramides_csv}")

    proteins = read_proteins(proteome_csv)
    ceramides = read_ceramides(ceramides_csv)
    extra_smiles = read_optional_smiles(smiles_txt)

    print(f"Loaded {len(proteins)} proteins.")
    print(f"Loaded {len(ceramides)} ligands.")

    # ------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------

    x_proteins = min(args.max_proteins or len(proteins), len(proteins))
    y_ceramides = min(args.max_ligands or len(ceramides), len(ceramides))

    if args.random:
        rng = random.Random(args.seed)
        proteins = rng.sample(proteins, k=x_proteins)
        ceramides = rng.sample(ceramides, k=y_ceramides)
    else:
        proteins = proteins[:x_proteins]
        ceramides = ceramides[:y_ceramides]

    if not proteins or not ceramides:
        raise ValueError(
            "No proteins or no ligands were loaded. Protein CSVs need "
            "'accession' and 'sequence' columns; ligand CSVs need "
            "'ligand_id', 'type' and 'value' columns."
        )

    # ------------------------------------------------------------
    # Output directory
    # ------------------------------------------------------------

    if args.output_dir_name:
        run_name = args.output_dir_name
    else:
        run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")

    out_dir = Path(args.out_base_dir) / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    msa_base = args.msa_base_dir

    # ------------------------------------------------------------
    # Generate YAML files
    # ------------------------------------------------------------

    n = 0
    file_delim = "__"
    written = {}

    for p in proteins:
        acc_safe = safe_name(p["accession"])

        # The parser splits {protein}__{ligand} on the first delimiter
        if file_delim in acc_safe:
            raise ValueError(
                f"Protein accession '{p['accession']}' contains '{file_delim}', "
                "which is reserved as the protein/ligand separator."
            )

        msa_file = msa_base / acc_safe / "msa.a3m"
        msa_exists = msa_file.exists()

        if args.require_msa and not msa_exists:
            raise FileNotFoundError(
                f"Missing MSA for {p['accession']}: {msa_file}"
            )

        msa_path = str(msa_file.resolve()) if msa_exists else None

        for c in ceramides:
            fname = (
                f"{acc_safe}"
                f"{file_delim}"
                f"{safe_name(c['ligand_id'])}.yaml"
            )

            # Different IDs can map to the same safe name (or appear twice in
            # the input); fail instead of silently overwriting a YAML.
            pair = (p["accession"], c["ligand_id"])
            if fname in written:
                if written[fname] == pair:
                    continue
                raise ValueError(
                    f"{pair} and {written[fname]} both map to {fname}. "
                    "Rename one of the proteins or ligands."
                )
            written[fname] = pair

            (out_dir / fname).write_text(
                make_yaml(
                    p["sequence"],
                    c,
                    msa_path=msa_path,
                    extra_smiles=extra_smiles,
                ),
                encoding="utf-8",
            )

            n += 1

    print(f"Created {n} YAML files in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
