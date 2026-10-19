"""Command-line entry point: python -m boltz_pmi <command> [options]

Run `python -m boltz_pmi <command> --help` for a command's options.
"""
import importlib
import sys

# command -> (module, one-line description), in pipeline order
COMMANDS = {
    "download-proteome": ("boltz_pmi.prep.download_proteome", "Download a UniProt proteome FASTA"),
    "fasta-to-csv":      ("boltz_pmi.prep.fasta_to_csv", "Convert a FASTA file to a protein CSV"),
    "sample-proteins":   ("boltz_pmi.prep.sample_proteins", "Randomly sample rows from a protein CSV"),
    "protein-fastas":    ("boltz_pmi.prep.protein_fastas", "Write one FASTA per protein (for MSA precompute)"),
    "control-set":       ("boltz_pmi.prep.control_set", "Build a control pair CSV with measured IC50s"),
    "generate-yamls":    ("boltz_pmi.yamls", "Write one Boltz YAML per protein-ligand pair"),
    "jobs":              ("boltz_pmi.jobs", "Report job progress and build resubmission lists"),
    "parse":             ("boltz_pmi.outputs", "Compile Boltz predictions into a CSV"),
    "boxplots":          ("boltz_pmi.analysis.boxplots", "Target vs. random protein affinity boxplots"),
    "top-binders":       ("boltz_pmi.analysis.top_binders", "Per-ligand scatter and strongest/weakest binders"),
}


def usage() -> str:
    width = max(len(c) for c in COMMANDS)
    lines = ["usage: python -m boltz_pmi <command> [options]", "", "commands:"]
    lines += [f"  {cmd:<{width}}  {desc}" for cmd, (_, desc) in COMMANDS.items()]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(usage())
        return

    command, argv = sys.argv[1], sys.argv[2:]
    if command not in COMMANDS:
        print(f"Unknown command: {command}\n\n{usage()}", file=sys.stderr)
        sys.exit(2)

    # Imported lazily so one command's dependencies (e.g. requests, seaborn)
    # aren't needed to run another
    module = importlib.import_module(COMMANDS[command][0])
    sys.argv[0] = f"python -m boltz_pmi {command}"
    module.main(argv)


if __name__ == "__main__":
    main()
