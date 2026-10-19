"""Stage 2: write one Boltz YAML per protein-ligand pair.

Input is either a protein CSV x ligand CSV cross product, or a pair CSV
(see inputs.py). Output is YAML_DIR/<job_name>/{protein}__{ligand}.yaml.
"""
import argparse
import random
from datetime import datetime
from pathlib import Path

from boltz_pmi import config
from boltz_pmi.inputs import read_ligands, read_pairs, read_proteins, read_single_smiles
from boltz_pmi.naming import make_stem, safe_name


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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
        lines.append(f"      msa: {_quote(msa_path)}")

    lines.append("  - ligand:")
    lines.append("      id: B")

    if ligand["type"] == "ccd":
        lines.append(f"      ccd: {ligand['value']}")
    else:
        lines.append(f"      smiles: {_quote(ligand['value'])}")

    # Optional cofactor (e.g. NADPH) present in every complex but not scored
    if extra_smiles:
        lines.append("  - ligand:")
        lines.append("      id: C")
        lines.append(f"      smiles: {_quote(extra_smiles)}")

    lines.append("properties:")
    lines.append("  - affinity:")
    lines.append("      binder: B")

    return "\n".join(lines) + "\n"


def cross_pairs(proteins: list[dict], ligands: list[dict]):
    for p in proteins:
        for c in ligands:
            yield p, c


def write_yamls(
    pairs,
    out_dir: Path,
    msa_base_dir: Path | None = None,
    require_msa: bool = False,
    extra_smiles: str | None = None,
) -> int:
    """Write one YAML per (protein, ligand) pair. Returns the number written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    msa_cache = {}

    for p, c in pairs:
        stem = make_stem(p["accession"], c["ligand_id"])

        # Different IDs can map to the same safe name (or appear twice in
        # the input); fail instead of silently overwriting a YAML.
        pair = (p["accession"], c["ligand_id"])
        if stem in written:
            if written[stem] == pair:
                continue
            raise ValueError(
                f"{pair} and {written[stem]} both map to {stem}.yaml. "
                "Rename one of the proteins or ligands."
            )
        written[stem] = pair

        acc = p["accession"]
        if acc not in msa_cache:
            msa_path = None
            if msa_base_dir is not None:
                msa_file = msa_base_dir / safe_name(acc) / "msa.a3m"
                if msa_file.exists():
                    msa_path = str(msa_file.resolve())
                elif require_msa:
                    raise FileNotFoundError(f"Missing MSA for {acc}: {msa_file}")
            msa_cache[acc] = msa_path

        (out_dir / f"{stem}.yaml").write_text(
            make_yaml(p["sequence"], c, msa_path=msa_cache[acc], extra_smiles=extra_smiles),
            encoding="utf-8",
        )

    return len(written)


def _limit(items: list, n: int | None, rng: random.Random | None) -> list:
    n = min(n or len(items), len(items))
    return rng.sample(items, k=n) if rng else items[:n]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate Boltz YAMLs for protein-ligand pairs.")

    inputs = ap.add_argument_group("inputs (give --protein_csv and --ligand_csv, or --pairs_csv)")
    inputs.add_argument("--protein_csv", "--proteome_csv", type=Path)
    inputs.add_argument("--ligand_csv", "--ceramide_csv", type=Path)
    inputs.add_argument("--pairs_csv", type=Path, help="CSV listing explicit protein-ligand pairs")

    ap.add_argument("--output_dir_name", "--job_name", type=str,
                    help="Folder name under --out_base_dir (default: run_<timestamp>)")
    ap.add_argument("--out_base_dir", type=Path, default=None,
                    help="Where to write <job_name>/ (default: $YAML_DIR)")
    ap.add_argument("--msa_base_dir", type=Path, default=None,
                    help="Base dir containing per-protein MSA folders (each should contain msa.a3m).")
    ap.add_argument("--require_msa", action="store_true",
                    help="Raise an error if a protein's msa.a3m file does not exist.")
    ap.add_argument("--smiles_txt", type=Path, default=None,
                    help="Optional TXT file with one SMILES added to every complex as ligand C.")
    ap.add_argument("--max_proteins", type=int, default=None,
                    help="Only use the first (or, with --random, a random) N proteins.")
    ap.add_argument("--max_ligands", type=int, default=None,
                    help="Only use the first (or, with --random, a random) N ligands.")
    ap.add_argument("--random", action="store_true",
                    help="Randomly sample instead of taking the first --max_proteins/--max_ligands.")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    use_pairs = args.pairs_csv is not None
    if use_pairs == bool(args.protein_csv or args.ligand_csv):
        ap.error("Give either --pairs_csv, or both --protein_csv and --ligand_csv.")
    if not use_pairs and not (args.protein_csv and args.ligand_csv):
        ap.error("--protein_csv and --ligand_csv must be given together.")

    out_base_dir = args.out_base_dir or config.path("YAML_DIR")
    run_name = args.output_dir_name or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    out_dir = out_base_dir / run_name

    extra_smiles = None
    if args.smiles_txt is not None:
        extra_smiles = read_single_smiles(config.resolve_input(args.smiles_txt))

    rng = random.Random(args.seed) if args.random else None

    if use_pairs:
        pairs_csv = config.resolve_input(args.pairs_csv)
        print(f"Pair CSV: {pairs_csv}")
        pairs = _limit(read_pairs(pairs_csv), args.max_proteins, rng)
        print(f"Loaded {len(pairs)} protein-ligand pairs.")
        if not pairs:
            raise ValueError("No pairs were loaded.")
    else:
        protein_csv = config.resolve_input(args.protein_csv)
        ligand_csv = config.resolve_input(args.ligand_csv)
        print(f"Protein CSV: {protein_csv}")
        print(f"Ligand CSV:  {ligand_csv}")
        proteins = _limit(read_proteins(protein_csv), args.max_proteins, rng)
        ligands = _limit(read_ligands(ligand_csv), args.max_ligands, rng)
        print(f"Loaded {len(proteins)} proteins.")
        print(f"Loaded {len(ligands)} ligands.")
        if not proteins or not ligands:
            raise ValueError("No proteins or no ligands were loaded.")
        pairs = cross_pairs(proteins, ligands)

    n = write_yamls(
        pairs,
        out_dir,
        msa_base_dir=args.msa_base_dir,
        require_msa=args.require_msa,
        extra_smiles=extra_smiles,
    )
    print(f"Created {n} YAML files in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
