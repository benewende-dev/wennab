"""Build a control file that differs from a reference by one thing only.

The problem this solves, and it cost us a day to find it.

We rebuilt a GGUF with a new importance matrix and it came out 23 MB heavier
than the reference we meant to beat. It would have been easy — and wrong — to
attribute the accuracy difference to our calibration. A tensor-by-tensor check
showed the weight came from somewhere else entirely: the reference's publisher
had used a different *type map*, dropping `attn_qkv` to IQ4_XS and lifting
`ssm_out`, `ssm_alpha` and `ssm_beta`, on every layer except those congruent to
3 modulo 4. Two causes, one number, and no measurement taken afterwards could
have separated them.

So: read the type map off any reference GGUF, and replay it. The rebuilt file
then differs from the reference by exactly the variable under test, and every
number measured between them is attributable to that variable.

    wennab twin reference.gguf candidate.gguf          # what differs, and by how much
    wennab twin reference.gguf --emit types.txt        # a --tensor-type-file for llama-quantize

Differing type maps exit **1**, like a failed `guard`. The first version printed
"these files are NOT a valid pair" and exited 0, which left the one command that
can see a comparison already spoiled unable to stop it: the sentence went into a
log nobody rereads, and the measurement went ahead.

The emitted file feeds `llama-quantize --tensor-type-file`, so the control is
produced by the standard toolchain rather than by anything of ours.
"""
from __future__ import annotations

import pathlib
import re
from collections import defaultdict


def type_map(path: pathlib.Path) -> dict[str, str]:
    """Tensor name → quantisation type, read from the file itself."""
    from gguf import GGUFReader

    return {t.name: t.tensor_type.name for t in GGUFReader(str(path)).tensors}


def sizes(path: pathlib.Path) -> dict[str, int]:
    from gguf import GGUFReader

    return {t.name: int(t.n_bytes) for t in GGUFReader(str(path)).tensors}


def differences(reference: pathlib.Path, candidate: pathlib.Path) -> list[dict]:
    """Every tensor whose type differs, grouped by the pattern it follows.

    Grouped, because a list of 72 tensor names tells you nothing while
    "attn_qkv on 18 of 24 layers" tells you what the publisher decided.
    """
    ref, cand = type_map(reference), type_map(candidate)
    ref_sizes, cand_sizes = sizes(reference), sizes(candidate)

    groupes: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    octets: dict[tuple[str, str, str], int] = defaultdict(int)
    for nom, t_ref in ref.items():
        t_cand = cand.get(nom)
        if t_cand is None or t_cand == t_ref:
            continue
        m = re.match(r"blk\.(\d+)\.(.+)", nom)
        cle = (m.group(2) if m else nom, t_cand, t_ref)
        groupes[cle].append(int(m.group(1)) if m else -1)
        octets[cle] += ref_sizes[nom] - cand_sizes.get(nom, 0)

    sortie = []
    for (suffixe, depuis, vers), couches in sorted(groupes.items()):
        c = sorted(couches)
        sortie.append({
            "tensor": suffixe,
            "from": depuis,
            "to": vers,
            "layers": c,
            "contiguous": c == list(range(c[0], c[-1] + 1)) if c and c[0] >= 0 else True,
            "bytes": octets[(suffixe, depuis, vers)],
        })
    return sortie


def emit(reference: pathlib.Path, baseline: pathlib.Path | None = None) -> list[str]:
    """Lines for `llama-quantize --tensor-type-file`.

    With a baseline, only the tensors where the two disagree are emitted — the
    minimal set of overrides needed to turn the baseline's map into the
    reference's. Without one, every quantised tensor is pinned, which is safe
    but produces a file of several hundred lines.
    """
    ref = type_map(reference)
    base = type_map(baseline) if baseline else {}
    lignes = []
    for nom, t in sorted(ref.items()):
        if t.startswith("F32") or t.startswith("F16") or t.startswith("BF16"):
            continue  # never quantised, no override to give
        if baseline and base.get(nom) == t:
            continue
        lignes.append(f"{nom}={t.lower()}")
    return lignes


def compare(reference: pathlib.Path, candidate: pathlib.Path) -> tuple[str, list[dict]]:
    """Le rapport lisible, et les écarts qui le motivent.

    Rendus ensemble parce que l'appelant a besoin des deux : `wennab twin`
    imprime le rapport *et* décide de son code de sortie, et recalculer les
    écarts pour cette seule décision rouvrirait les deux fichiers.
    """
    diffs = differences(reference, candidate)
    return _texte(reference, candidate, diffs), diffs


def report(reference: pathlib.Path, candidate: pathlib.Path) -> str:
    return compare(reference, candidate)[0]


def _texte(reference: pathlib.Path, candidate: pathlib.Path, diffs: list[dict]) -> str:
    a, b = sum(sizes(reference).values()), sum(sizes(candidate).values())

    if not diffs:
        return (f"identical type maps ({len(type_map(reference))} tensors)\n"
                f"  reference {a:,} B\n  candidate {b:,} B\n"
                f"  difference {b - a:+,} B\n\n"
                f"These two files differ only in tensor *values*. Any measured "
                f"difference between them\nis attributable to whatever produced "
                f"those values.")

    lignes = [f"{len(diffs)} type group(s) differ — these files are NOT a valid pair\n",
              f"  {'tensor':<24} {'candidate':>9} → {'reference':<9} {'layers':>7} {'bytes':>14}"]
    for d in diffs:
        couches = (f"{d['layers'][0]}..{d['layers'][-1]}" if d["contiguous"]
                   else f"{len(d['layers'])} of them")
        lignes.append(f"  {d['tensor']:<24} {d['from']:>9} → {d['to']:<9} "
                      f"{couches:>7} {d['bytes']:>+14,}")
    lignes.append(f"\n  reference {a:,} B\n  candidate {b:,} B\n  difference {b - a:+,} B")
    lignes.append(
        "\nMeasuring these two against each other mixes the type map with whatever\n"
        "else you changed. Rebuild the candidate with:\n"
        "  wennab twin reference.gguf --emit types.txt\n"
        "  llama-quantize --imatrix yours.imatrix --tensor-type-file types.txt \\\n"
        "      source-BF16.gguf candidate.gguf <TYPE>")
    return "\n".join(lignes)
