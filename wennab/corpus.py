"""Generate a calibration corpus for a register, reproducibly.

What a calibration corpus is for. An importance-matrix quantisation does not
change a model's weights; it decides where to spend precision when rounding
them. That decision is made by watching which weights activate while the model
reads a reference text. Change the text, change the rounding. Most published
GGUFs inherit a calibration computed by someone else on generic English, for a
workload that is not yours.

Why generated rather than collected. Real documents in a professional register
are usually the ones you cannot publish, and public legal corpora arrive with
unclear licensing. A registry file holds entities and hand-written sentence
templates; the generator draws from them under a fixed seed. The corpus is then
reproducible from the registry alone, contains no real data, and can be read.

What this is not: authentic text. Its syntax is its templates' syntax, and a
matrix calibrated on it protects the weights those templates activate. That is
the method's ceiling, and `--report` measures it rather than assuming it —
4-gram diversity is printed with every run.

    wennab corpus registries/enterprise-fr.toml --bytes 180000 > corpus.txt

On size: hand-written text is a fixed quantity, so lengthening the corpus only
repeats it, and a matrix estimated on repetition over-weights whatever repeats.
Measure diversity at two or three sizes and keep the shortest that still gives
you enough chunks. Ours: 330 kB → 0.380, 240 kB → 0.432, 180 kB → 0.489.
"""
from __future__ import annotations

import collections
import pathlib
import random
import sys

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


class RegistryError(ValueError):
    """The registry file is missing something the generator needs."""


def load(chemin: pathlib.Path) -> dict:
    registre = tomllib.loads(chemin.read_text(encoding="utf-8"))
    for cle in ("entities", "genres"):
        if cle not in registre:
            raise RegistryError(f"{chemin}: missing [{cle}]")
    for g in registre["genres"]:
        if "id" not in g or "blocks" not in g:
            raise RegistryError(f"{chemin}: every genre needs an id and blocks")
    return registre


def _decor(alea: random.Random, entites: dict, nombres: dict) -> dict:
    """One document's cast, drawn once and reused across all its blocks.

    Drawn per document rather than per sentence: a memo whose city changes
    between its header and its signature is not a memo, and the model would be
    calibrated on text no human would write.
    """
    decor = {cle: alea.choice(valeurs) for cle, valeurs in entites.items()}
    for cle, spec in nombres.items():
        bas, haut = int(spec["min"]), int(spec["max"])
        pas = int(spec.get("step", 1))
        valeur = alea.randrange(bas, haut) * pas
        fmt = spec.get("format", "plain")
        if fmt == "spaced":
            decor[cle] = f"{valeur:,}".replace(",", " ")
        elif fmt == "grouped":
            decor[cle] = f"{valeur:,}"
        else:
            decor[cle] = str(valeur)
    return decor


def diversity(texte: str, n: int = 4) -> float:
    """Share of distinct n-grams. The ceiling on what this method can do."""
    mots = texte.split()
    if len(mots) <= n:
        return 1.0
    grammes = [" ".join(mots[i:i + n]) for i in range(len(mots) - n + 1)]
    return len(set(grammes)) / len(grammes)


def generate(registre: dict, octets_cible: int, graine: int) -> tuple[str, dict]:
    alea = random.Random(graine)
    genres = registre["genres"]
    entites = {k: v for k, v in registre["entities"].items() if isinstance(v, list)}
    nombres = registre.get("numbers", {})

    morceaux: list[str] = []
    compte: collections.Counter = collections.Counter()
    octets = 0

    # Drawn without replacement over a full cycle of genres. A free draw over
    # 180 documents leaves one genre at 6 copies and another at 22, and the
    # matrix inherits that imbalance.
    while octets < octets_cible:
        tour = genres[:]
        alea.shuffle(tour)
        for genre in tour:
            decor = _decor(alea, entites, nombres)
            texte = "\n".join(alea.choice(bloc).format(**decor) for bloc in genre["blocks"])
            morceaux.append(texte)
            compte[genre["id"]] += 1
            octets += len(texte.encode("utf-8")) + 2
            if octets >= octets_cible:
                break

    corpus = "\n\n".join(morceaux) + "\n"
    langues = collections.Counter(
        g.get("language", "?") for g in genres for _ in range(compte[g["id"]]))
    stats = {
        "documents": len(morceaux),
        "bytes": len(corpus.encode("utf-8")),
        "words": len(corpus.split()),
        "diversity_4gram": round(diversity(corpus), 3),
        "per_genre": dict(sorted(compte.items())),
        "per_language": dict(sorted(langues.items())),
    }
    return corpus, stats


def report(stats: dict) -> str:
    lignes = [
        f"  {stats['documents']} documents, {stats['bytes']:,} bytes, "
        f"{stats['words']:,} words",
        f"  4-gram diversity : {stats['diversity_4gram']:.3f}",
    ]
    total = stats["documents"]
    for langue, n in stats["per_language"].items():
        lignes.append(f"  {langue} : {n}/{total} documents ({100 * n / total:.0f} %)")
    if stats["diversity_4gram"] < 0.35:
        lignes.append(
            "\n  Diversity is low: the corpus repeats its own templates. Either\n"
            "  write more templates or ask for fewer bytes — the second is free.")
    return "\n".join(lignes)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 1
    chemin = pathlib.Path(argv[0])
    octets = int(next((a.split("=")[1] for a in argv if a.startswith("--bytes=")), 180_000))
    graine = int(next((a.split("=")[1] for a in argv if a.startswith("--seed=")), 20260803))

    corpus, stats = generate(load(chemin), octets, graine)
    sys.stdout.write(corpus)
    print(report(stats), file=sys.stderr)
    return 0
