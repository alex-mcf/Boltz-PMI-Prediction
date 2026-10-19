"""Naming convention linking YAML inputs to Boltz outputs.

Each YAML is named {protein}__{ligand}.yaml. Boltz names its prediction folder
after the YAML stem, and the outputs stage splits that stem to recover the
protein and ligand. Both directions live here so they cannot drift apart.
"""
import re

DELIM = "__"


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")


def make_stem(protein_id: str, ligand_id: str) -> str:
    protein = safe_name(protein_id)
    # Stems are split on the first delimiter, so it can't appear in the protein part
    if DELIM in protein:
        raise ValueError(
            f"Protein ID '{protein_id}' contains '{DELIM}', "
            "which is reserved as the protein/ligand separator."
        )
    return f"{protein}{DELIM}{safe_name(ligand_id)}"


def split_stem(stem: str) -> tuple[str, str]:
    if DELIM in stem:
        protein, ligand = stem.split(DELIM, 1)
        return protein, ligand
    return stem, "UNKNOWN"
