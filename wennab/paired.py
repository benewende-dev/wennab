"""Compare two models question by question, not by their totals.

Why totals mislead. Two models scoring 0.670 and 0.680 on 200 questions look
four questions apart, and the standard error of a 0.67 score over 200 draws is
3.3 points — so the gap proves nothing. Publishing it as an improvement is the
single most common way an optimisation result turns out to be noise.

But the two models answered the *same* questions, and they fail on mostly the
same ones. The information is in the questions where they disagree, and nowhere
else. That is McNemar's test: among the discordant questions, if the change had
no effect, each direction is equally likely — a repeated coin flip. We compute
the exact probability of a split at least this lopsided.

Input is the `samples_*.jsonl` that lm-evaluation-harness writes with
`--log_samples`, so nothing here is tied to a particular runner:

    lm_eval --model ... --tasks arc_easy --limit 200 --log_samples \\
            --output_path runs/reference
    lm_eval --model ... --tasks arc_easy --limit 200 --log_samples \\
            --output_path runs/candidate

    wennab paired runs/reference runs/candidate

The 200-question run below is the one that ended our own experiment: 196
identical answers, p = 0.625, and a rebuild we did not ship.
"""
from __future__ import annotations

import glob
import json
import math
import pathlib


class MismatchedRuns(ValueError):
    """The two runs did not see the same questions, so they cannot be paired."""


def _fichier(chemin: pathlib.Path | str) -> pathlib.Path:
    """Accept a directory, a glob, or the jsonl itself."""
    chemin = pathlib.Path(chemin)
    if chemin.is_file():
        return chemin
    candidats = sorted(glob.glob(str(chemin / "**" / "samples_*.jsonl"), recursive=True))
    if not candidats:
        raise FileNotFoundError(
            f"no samples_*.jsonl under {chemin} — run lm_eval with --log_samples")
    return pathlib.Path(candidats[-1])


def outcomes(chemin: pathlib.Path | str, metric: str = "acc_norm") -> dict[str, bool]:
    """Question id → right/wrong.

    Keyed by document id rather than by position: two runs can order their
    documents differently, and pairing by position would then compare
    unrelated questions while looking perfectly healthy.
    """
    resultats: dict[str, bool] = {}
    with _fichier(chemin).open() as f:
        for ligne in f:
            if not ligne.strip():
                continue
            e = json.loads(ligne)
            valeur = e.get(metric)
            if valeur is None:
                valeur = e.get("acc")
            if valeur is None:
                continue
            cle = str(e.get("doc_id", e.get("doc_hash", len(resultats))))
            resultats[cle] = bool(round(float(valeur)))
    return resultats


def mcnemar(a: dict[str, bool], b: dict[str, bool]) -> dict:
    communes = sorted(set(a) & set(b))
    if not communes:
        raise MismatchedRuns("the two runs share no question id")
    if len(communes) < max(len(a), len(b)):
        raise MismatchedRuns(
            f"only {len(communes)} of {max(len(a), len(b))} questions are shared — "
            f"the runs used different limits or different seeds")

    a_seul = sum(1 for k in communes if a[k] and not b[k])
    b_seul = sum(1 for k in communes if b[k] and not a[k])
    n = a_seul + b_seul
    k = min(a_seul, b_seul)
    # Exact two-sided binomial test. No chi-square approximation: with a
    # handful of discordant pairs it is precisely the regime where the
    # approximation is worst, and that is the regime we are always in.
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {
        "questions": len(communes),
        "reference_right": sum(a[k] for k in communes),
        "candidate_right": sum(b[k] for k in communes),
        "agree": len(communes) - n,
        "reference_only": a_seul,
        "candidate_only": b_seul,
        "discordant": n,
        "p_value": p,
    }


def report(r: dict, noms: tuple[str, str] = ("reference", "candidate")) -> str:
    n = r["questions"]
    a, b = noms
    lignes = [
        f"{n} questions, paired by document id\n",
        f"  {a:<22} {r['reference_right']:>4}/{n}  ({r['reference_right']/n:.3f})",
        f"  {b:<22} {r['candidate_right']:>4}/{n}  ({r['candidate_right']/n:.3f})",
        "",
        f"  agree                  {r['agree']:>4}/{n}  ({r['agree']/n:.0%})",
        f"  {a} only right : {r['reference_only']}",
        f"  {b} only right : {r['candidate_only']}",
        "",
        f"  p = {r['p_value']:.3f}",
    ]
    if r["discordant"] == 0:
        lignes.append("\n  The two models never disagree. Whatever you changed changed nothing.")
    elif r["p_value"] < 0.05:
        gagnant = b if r["candidate_only"] > r["reference_only"] else a
        lignes.append(f"\n  The split does not come from chance: {gagnant} is ahead.")
    else:
        lignes.append(
            f"\n  Consistent with chance. {r['discordant']} question(s) separate these\n"
            f"  models — report that number, not the difference of the totals.")
    return "\n".join(lignes)
