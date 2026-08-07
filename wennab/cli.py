"""wennab — prove that a model optimisation did something, or that it did not.

    wennab corpus   <registry.toml> [--bytes=N] [--seed=N]   build a calibration corpus
    wennab guard    <corpus.txt> --against <files...>        refuse a corpus containing its exam
    wennab twin     <reference.gguf> <candidate.gguf>        what separates two builds
    wennab twin     <reference.gguf> --emit <types.txt>      replay a reference's type map
    wennab paired   <run-a> <run-b> [--metric=acc_norm]      question-by-question comparison

Every command reads and writes plain files, and none of them wraps a model
runner: quantise with llama-quantize, evaluate with lm-evaluation-harness, and
use these to keep yourself honest in between.
"""
from __future__ import annotations

import pathlib
import sys

from . import __version__
from . import corpus as m_corpus
from . import guard as m_guard
from . import paired as m_paired
from . import twin as m_twin


def _corpus(argv: list[str]) -> int:
    return m_corpus.main(argv)


def _guard(argv: list[str]) -> int:
    if "--against" not in argv:
        print("usage: wennab guard <corpus.txt> --against <files...>", file=sys.stderr)
        return 2
    coupe = argv.index("--against")
    corpus = pathlib.Path(argv[0]).read_text(encoding="utf-8")
    fichiers = [pathlib.Path(a) for a in argv[coupe + 1:] if not a.startswith("--")]
    if not fichiers:
        print("no exam files given after --against", file=sys.stderr)
        return 2
    n = int(next((a.split("=")[1] for a in argv if a.startswith("--n=")), 8))

    r = m_guard.check(corpus, m_guard.load_exams(fichiers), n=n)
    print(m_guard.report(r, verbeux="--verbose" in argv))
    return 0 if r["clean"] else 1


def _twin(argv: list[str]) -> int:
    if not argv or argv[0].startswith("--"):
        print("usage: wennab twin <reference.gguf> <candidate.gguf>\n"
              "       wennab twin <reference.gguf> --emit <types.txt> [--baseline=<b.gguf>]",
              file=sys.stderr)
        return 2
    reference = pathlib.Path(argv[0])
    if "--emit" in argv:
        cible = argv[argv.index("--emit") + 1]
        base = next((a.split("=")[1] for a in argv if a.startswith("--baseline=")), None)
        lignes = m_twin.emit(reference, pathlib.Path(base) if base else None)
        pathlib.Path(cible).write_text("\n".join(lignes) + "\n")
        print(f"{len(lignes)} tensor override(s) → {cible}")
        print("\nfeed it to llama-quantize:\n"
              f"  llama-quantize --imatrix <yours.imatrix> --tensor-type-file {cible} \\\n"
              "      <source-BF16.gguf> <candidate.gguf> <TYPE>")
        return 0

    positionnels = [a for a in argv if not a.startswith("--")]
    if len(positionnels) < 2:
        print("usage: wennab twin <reference.gguf> <candidate.gguf>", file=sys.stderr)
        return 2
    print(m_twin.report(reference, pathlib.Path(positionnels[1])))
    return 0


def _paired(argv: list[str]) -> int:
    positionnels = [a for a in argv if not a.startswith("--")]
    if len(positionnels) < 2:
        print("usage: wennab paired <run-a> <run-b>", file=sys.stderr)
        return 2
    metrique = next((a.split("=")[1] for a in argv if a.startswith("--metric=")), "acc_norm")
    a, b = pathlib.Path(positionnels[0]), pathlib.Path(positionnels[1])
    try:
        r = m_paired.mcnemar(m_paired.outcomes(a, metrique), m_paired.outcomes(b, metrique))
    except m_paired.MismatchedRuns as e:
        print(f"cannot pair these runs: {e}", file=sys.stderr)
        return 2
    print(m_paired.report(r, (a.name, b.name)))
    return 0


COMMANDES = {"corpus": _corpus, "guard": _guard, "twin": _twin, "paired": _paired}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if argv[0] in ("-V", "--version"):
        print(f"wennab {__version__}")
        return 0
    commande = COMMANDES.get(argv[0])
    if commande is None:
        print(f"unknown command {argv[0]!r}\n", file=sys.stderr)
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return commande(argv[1:])


# Without this guard, `python -m wennab.cli twin a.gguf b.gguf` — the line the
# README gave for running the tool from a clone — imports the module, prints
# nothing and **exits 0**. A success with no output: exactly the failure mode
# this repository exists to catch.
if __name__ == "__main__":
    sys.exit(main())
