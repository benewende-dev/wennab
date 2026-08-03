"""Refuse a calibration corpus that contains the exam it will be graded on.

The failure this prevents is silent and it flatters you. A matrix calibrated on
a text protects the weights that text activates. If the corpus contains the
prompts you will evaluate against, the rebuild improves its own marks without
improving the model, every number afterwards is inflated, and nothing in the
pipeline complains.

Generating the corpus yourself does not help — it makes it worse. The templates
and the evaluation prompts come from the same hand, the same register, the same
example cities. Ours collided on eight consecutive words between a "note de
service" template and a leave-policy test task. We only knew because we looked.

Method: n-grams of normalised words. Eight consecutive words do not coincide
between independent texts, even in the same register. The longest shared run is
printed too, because a count of zero collisions at n=8 does not tell you whether
you cleared it by a mile or by one word.

    wennab guard corpus.txt --against prompts.json tasks/*.txt

Any file works: .json (every string value is scanned, at any depth), .jsonl,
or plain text.
"""
from __future__ import annotations

import json
import pathlib
import re

_NOT_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def words(texte: str) -> list[str]:
    return _SPACES.sub(" ", _NOT_WORD.sub(" ", texte.lower())).split()


def ngrams(suite: list[str], n: int) -> set[str]:
    if len(suite) < n:
        return set()
    return {" ".join(suite[i:i + n]) for i in range(len(suite) - n + 1)}


def _strings(objet) -> list[str]:
    """Every string in a JSON structure, at any depth."""
    if isinstance(objet, str):
        return [objet]
    if isinstance(objet, dict):
        return [s for v in objet.values() for s in _strings(v)]
    if isinstance(objet, list):
        return [s for v in objet for s in _strings(v)]
    return []


def load_exams(chemins: list[pathlib.Path] | list[str]) -> list[tuple[str, str]]:
    """(label, text) for everything the corpus must stay clear of."""
    epreuves: list[tuple[str, str]] = []
    for chemin in chemins:
        chemin = pathlib.Path(chemin)
        brut = chemin.read_text(encoding="utf-8")
        if chemin.suffix == ".json":
            for i, s in enumerate(_strings(json.loads(brut))):
                if len(s.split()) >= 8:  # short strings cannot collide at n=8
                    epreuves.append((f"{chemin.name}[{i}]", s))
        elif chemin.suffix == ".jsonl":
            for i, ligne in enumerate(brut.splitlines()):
                if ligne.strip():
                    for s in _strings(json.loads(ligne)):
                        if len(s.split()) >= 8:
                            epreuves.append((f"{chemin.name}:{i}", s))
        else:
            epreuves.append((chemin.name, brut))
    return epreuves


def longest_shared(a: list[str], b: list[str], plafond: int = 40) -> tuple[int, str]:
    """Longest run of words present in both, and that run.

    Searched by increasing n and stopped at the first miss, which avoids the
    quadratic table over a thirty-thousand-word corpus.
    """
    meilleure = (0, "")
    for n in range(1, plafond + 1):
        commun = ngrams(a, n) & ngrams(b, n)
        if not commun:
            break
        meilleure = (n, sorted(commun)[0])
    return meilleure


def check(corpus: str, epreuves: list[tuple[str, str]], n: int = 8) -> dict:
    """Zero exams is not a pass.

    A file with no readable text — the wrong key, a results dump instead of the
    prompts, a path that expanded to nothing — produces zero collisions, and a
    tool that answered "clean" there would be lying in exactly the way this one
    exists to prevent. It is reported as a failure.
    """
    mots_corpus = words(corpus)
    grammes_corpus = ngrams(mots_corpus, n)

    lignes, collisions, record = [], 0, (0, "", "")
    for nom, texte in epreuves:
        suite = words(texte)
        communs = ngrams(suite, n) & grammes_corpus
        longueur, sequence = longest_shared(suite, mots_corpus)
        if longueur > record[0]:
            record = (longueur, sequence, nom)
        if communs:
            collisions += len(communs)
        lignes.append({
            "exam": nom, "collisions": len(communs), "longest": longueur,
            "sequence": sequence, "example": sorted(communs)[0] if communs else None,
        })
    return {
        "n": n,
        "corpus_words": len(mots_corpus),
        "corpus_ngrams": len(grammes_corpus),
        "exams": len(epreuves),
        "collisions": collisions,
        "longest_overall": record[0],
        "longest_sequence": record[1],
        "longest_exam": record[2],
        "per_exam": lignes,
        "clean": collisions == 0 and len(epreuves) > 0,
    }


def report(r: dict, verbeux: bool = False) -> str:
    lignes = [
        f"corpus : {r['corpus_words']:,} words, {r['corpus_ngrams']:,} distinct "
        f"{r['n']}-grams",
        f"exams  : {r['exams']} text(s)\n",
    ]
    for e in sorted(r["per_exam"], key=lambda x: -x["longest"]):
        if not verbeux and e["collisions"] == 0 and e["longest"] < 6:
            continue
        marque = "✗" if e["collisions"] else ("!" if e["longest"] >= 6 else "·")
        detail = ""
        if e["collisions"]:
            detail = f"  ← {e['collisions']} collision(s): « {e['example']} »"
        elif e["longest"] >= 6:
            detail = f"  ← « {e['sequence']} »"
        lignes.append(f"  {marque} {e['exam']:<34} max {e['longest']:>2} words{detail}")

    if r["exams"] == 0:
        return "\n".join(lignes + [
            "✗ no exam text was read. Nothing was compared, so this is not a pass.",
            "  Check the paths, and that the files hold prompts rather than results:",
            "  strings shorter than 8 words are skipped, since they cannot collide at n=8.",
        ])

    lignes.append(f"\nlongest shared run, all exams : {r['longest_overall']} words "
                  f"({r['longest_exam']})")
    if r["longest_sequence"]:
        lignes.append(f"  « {r['longest_sequence']} »")

    if r["clean"]:
        lignes.append(
            f"\n✓ no shared {r['n']}-gram. The corpus and the evaluation sets are "
            f"disjoint,\n  so what you measure after recalibration is a real effect.")
    else:
        lignes.append(
            f"\n✗ {r['collisions']} shared {r['n']}-gram(s). Fix the corpus before "
            f"computing anything:\n  a corpus containing its own exam marks its own paper.")
    return "\n".join(lignes)
