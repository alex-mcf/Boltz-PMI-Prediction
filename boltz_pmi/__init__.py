"""Boltz-2 protein-metabolite interaction prediction pipeline.

Stages (each is a module with its own CLI, run via `python -m boltz_pmi <command>`):

    prep/       Build protein and ligand input CSVs (download, convert, sample, control set)
    yamls       Turn input CSVs into one Boltz YAML per protein-ligand pair
    jobs        Track which YAMLs have finished and build resubmission lists
    outputs     Locate Boltz predictions and compile them into a CSV
    analysis/   Plots and summaries built from the compiled CSVs

Shared building blocks:

    config      Paths from environment_variables.sh, read when a command runs
    naming      The {protein}__{ligand} naming convention shared by yamls and outputs
    inputs      Readers for the protein, ligand, and pair CSV formats
"""
