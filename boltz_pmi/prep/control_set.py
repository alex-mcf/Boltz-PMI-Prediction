"""Stage 1: build a control set of protein-ligand pairs with measured affinities.

Joins a PubChem bioassay table (PDB, SMILES, IC50) to UniProt accessions via
SIFTS pdb_chain_uniprot.csv, keeps single-chain structures, and writes a pair
CSV (see inputs.py) that runs through the normal pipeline:

    python -m boltz_pmi control-set --output inputs/controls.csv
    bash run_pipeline.sh --pairs_csv inputs/controls.csv --job_name control_tests

The measured IC50 is kept in the CSV for comparing against predictions.
"""
import argparse
import hashlib
from pathlib import Path

import pandas as pd

from boltz_pmi import config
from boltz_pmi.inputs import PAIR_COLUMNS


def make_ligand_id(smiles):
    if not isinstance(smiles, str) or not smiles:
        return None
    return hashlib.sha256(smiles.encode("utf-8")).hexdigest()[:16]


def build_control_pairs(assay_csv: Path, pdb_chain_csv: Path, proteome_csv: Path) -> pd.DataFrame:
    data = pd.read_csv(assay_csv)
    reference = pd.read_csv(pdb_chain_csv, comment="#", low_memory=False)
    proteome = pd.read_csv(proteome_csv)

    data["PDB"] = data["PDB"].str.lower()
    reference["PDB"] = reference["PDB"].str.lower()

    data = data[["PDB", "PUBCHEM_EXT_DATASOURCE_SMILES", "IC50", "Protein Name"]]
    reference = reference[["PDB", "CHAIN", "SP_PRIMARY"]]
    proteome = proteome[["accession", "sequence"]]

    data = data.rename(columns={"PUBCHEM_EXT_DATASOURCE_SMILES": "value", "IC50": "experimental_ic50"})
    reference = reference.rename(columns={"SP_PRIMARY": "accession"})

    # Keep single-chain structures so the complex matches what Boltz is given
    chain_counts = reference.groupby("PDB")["CHAIN"].nunique()
    monomer_pdbs = chain_counts[chain_counts == 1].index
    data = data[data["PDB"].isin(monomer_pdbs)]
    reference = reference.drop(columns=["CHAIN"]).drop_duplicates()

    output = (
        data
        .merge(reference, on="PDB", how="left")
        .merge(proteome, on="accession", how="left")
    )

    output["ligand_id"] = output["value"].apply(make_ligand_id)
    output["type"] = "smiles"
    output = output.dropna(subset=["sequence", "ligand_id"])

    columns = PAIR_COLUMNS + ["PDB", "Protein Name", "experimental_ic50"]
    output = output[columns].sort_values(by=columns).drop_duplicates()

    # One pair per accession and ligand; several PDB entries can describe the same pair
    output = output.drop_duplicates(subset=["accession", "ligand_id"])
    return output


def main(argv=None):
    source_dir = config.path("SOURCE_DIR")
    ap = argparse.ArgumentParser(description="Build a control pair CSV with measured affinities.")
    ap.add_argument("--assay_csv", type=Path, default=source_dir / "AID_977608_datatable_all.csv")
    ap.add_argument("--pdb_chain_csv", type=Path, default=source_dir / "pdb_chain_uniprot.csv")
    ap.add_argument("--proteome_csv", type=Path, default=source_dir / "proteome.csv")
    ap.add_argument("--output", type=Path, default=config.path("INPUT_DIR") / "controls.csv")
    ap.add_argument("--n_pairs", type=int, default=None, help="Randomly keep N pairs (seeded)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    output = build_control_pairs(args.assay_csv, args.pdb_chain_csv, args.proteome_csv)

    if args.n_pairs is not None and args.n_pairs < len(output):
        output = output.sample(n=args.n_pairs, random_state=args.seed).sort_index()

    print(f"Number of unique accessions in output: {output['accession'].nunique()}")
    print(f"Number of unique ligands in output: {output['ligand_id'].nunique()}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"Wrote {len(output)} control pairs to {args.output}")


if __name__ == "__main__":
    main()
