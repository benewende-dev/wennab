"""Tests for the three commands that need no model file.

`twin` is exercised against real GGUFs in the case study rather than here: a
fixture GGUF would be either a toy that proves nothing or a gigabyte in the
repository.
"""
from __future__ import annotations

import json
import math
import pathlib
import textwrap

import pytest

from wennab import cli, corpus, guard, paired

RACINE = pathlib.Path(__file__).resolve().parent.parent


# ————————————————————————————————— corpus —————————————————————————————————

def test_meme_graine_meme_corpus():
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    a, _ = corpus.generate(registre, 20_000, 42)
    b, _ = corpus.generate(registre, 20_000, 42)
    assert a == b, "the seed must make the corpus reproducible byte for byte"


def test_graine_differente_corpus_different():
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    a, _ = corpus.generate(registre, 20_000, 1)
    b, _ = corpus.generate(registre, 20_000, 2)
    assert a != b


def test_diversite_baisse_quand_le_corpus_s_allonge():
    """The claim the README makes about corpus size, kept honest by a test."""
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    _, court = corpus.generate(registre, 60_000, 7)
    _, long = corpus.generate(registre, 240_000, 7)
    assert court["diversity_4gram"] > long["diversity_4gram"]


def test_genres_equilibres():
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    _, stats = corpus.generate(registre, 180_000, 20260803)
    compte = list(stats["per_genre"].values())
    assert max(compte) - min(compte) <= 1, "drawing without replacement must keep genres level"


def test_registre_incomplet_rejete(tmp_path):
    mauvais = tmp_path / "r.toml"
    mauvais.write_text('name = "x"\n[entities]\nville = ["Abidjan"]\n')
    with pytest.raises(corpus.RegistryError):
        corpus.load(mauvais)


def test_diversite_texte_repete():
    assert corpus.diversity("a b c d " * 50) < 0.1
    assert corpus.diversity(" ".join(str(i) for i in range(500))) == 1.0


# ————————————————————————————————— guard ——————————————————————————————————

EXTRAIT = ("Le chef de service dispose de cinq jours ouvrés pour valider ou refuser "
           "la demande déposée par le collaborateur.")


def test_collision_detectee(tmp_path):
    epreuve = tmp_path / "epreuve.txt"
    epreuve.write_text(EXTRAIT)
    r = guard.check(f"En-tête quelconque. {EXTRAIT} Suite du document.",
                    guard.load_exams([epreuve]))
    assert not r["clean"]
    assert r["collisions"] > 0


def test_corpus_disjoint_accepte(tmp_path):
    epreuve = tmp_path / "epreuve.txt"
    epreuve.write_text(EXTRAIT)
    r = guard.check("Un texte entièrement différent, sur un tout autre sujet, "
                    "rédigé sans aucun emprunt.", guard.load_exams([epreuve]))
    assert r["clean"]


def test_normalisation_ignore_ponctuation_et_casse(tmp_path):
    epreuve = tmp_path / "e.txt"
    epreuve.write_text("un deux trois quatre cinq six sept huit")
    r = guard.check("UN, DEUX ; TROIS — QUATRE. CINQ! SIX? SEPT: HUIT",
                    guard.load_exams([epreuve]))
    assert not r["clean"], "punctuation and case must not hide a collision"


def test_json_lu_en_profondeur(tmp_path):
    fichier = tmp_path / "prompts.json"
    fichier.write_text(json.dumps({"a": [{"b": {"prompt": EXTRAIT}}]}))
    epreuves = guard.load_exams([fichier])
    assert any(EXTRAIT in t for _, t in epreuves)


def test_aucune_epreuve_lue_nest_pas_un_succes(tmp_path):
    """The failure that would make this tool worse than useless.

    A results dump instead of the prompts, or a path that expanded to nothing,
    yields zero collisions. Answering "clean" there is the exact lie `guard`
    exists to prevent.
    """
    resultats = tmp_path / "samples.jsonl"
    resultats.write_text('{"doc_id": 0, "acc_norm": 1.0}\n')
    r = guard.check("Un corpus quelconque, en français, de longueur raisonnable.",
                    guard.load_exams([resultats]))
    assert r["exams"] == 0
    assert not r["clean"], "zero exams read must not report as a pass"
    assert "not a pass" in guard.report(r)


def test_plus_longue_sequence_rapportee(tmp_path):
    epreuve = tmp_path / "e.txt"
    epreuve.write_text("alpha bravo charlie delta echo foxtrot")
    r = guard.check("zoulou alpha bravo charlie yankee", guard.load_exams([epreuve]))
    assert r["longest_overall"] == 3
    assert r["clean"]


# ————————————————————————————————— paired —————————————————————————————————

def _run(tmp_path, nom, resultats):
    p = tmp_path / f"samples_{nom}.jsonl"
    p.write_text("\n".join(
        json.dumps({"doc_id": i, "acc_norm": float(v)}) for i, v in enumerate(resultats)))
    return p


def test_accord_total_p_egal_un(tmp_path):
    a = _run(tmp_path, "a", [1, 0, 1, 1, 0])
    b = _run(tmp_path, "b", [1, 0, 1, 1, 0])
    r = paired.mcnemar(paired.outcomes(a), paired.outcomes(b))
    assert r["discordant"] == 0
    assert r["p_value"] == 1.0


def test_desaccord_franc_est_significatif(tmp_path):
    a = _run(tmp_path, "a", [0] * 12 + [1] * 8)
    b = _run(tmp_path, "b", [1] * 12 + [1] * 8)
    r = paired.mcnemar(paired.outcomes(a), paired.outcomes(b))
    assert r["candidate_only"] == 12
    assert r["p_value"] < 0.05


def test_petit_desequilibre_reste_du_hasard(tmp_path):
    a = _run(tmp_path, "a", [1, 0, 0, 1] + [1] * 96)
    b = _run(tmp_path, "b", [0, 1, 1, 1] + [1] * 96)
    r = paired.mcnemar(paired.outcomes(a), paired.outcomes(b))
    assert r["discordant"] == 3
    assert r["p_value"] > 0.05, "3 discordant answers can never be significant"


def test_p_exact_connu(tmp_path):
    """5 discordant, all one way: p = 2 × (1/2)^5 = 0.0625."""
    a = _run(tmp_path, "a", [0] * 5 + [1] * 20)
    b = _run(tmp_path, "b", [1] * 5 + [1] * 20)
    r = paired.mcnemar(paired.outcomes(a), paired.outcomes(b))
    assert math.isclose(r["p_value"], 2 * 0.5 ** 5)


def test_runs_de_tailles_differentes_refuses(tmp_path):
    a = _run(tmp_path, "a", [1] * 10)
    b = _run(tmp_path, "b", [1] * 5)
    with pytest.raises(paired.MismatchedRuns):
        paired.mcnemar(paired.outcomes(a), paired.outcomes(b))


def test_appariement_par_doc_id_pas_par_position(tmp_path):
    """Two runs that ordered their documents differently must still pair."""
    (tmp_path / "samples_a.jsonl").write_text("\n".join(
        json.dumps({"doc_id": i, "acc_norm": v}) for i, v in [(0, 1.0), (1, 0.0), (2, 1.0)]))
    (tmp_path / "samples_b.jsonl").write_text("\n".join(
        json.dumps({"doc_id": i, "acc_norm": v}) for i, v in [(2, 1.0), (0, 1.0), (1, 0.0)]))
    r = paired.mcnemar(paired.outcomes(tmp_path / "samples_a.jsonl"),
                       paired.outcomes(tmp_path / "samples_b.jsonl"))
    assert r["discordant"] == 0


def test_dossier_accepte_a_la_place_du_fichier(tmp_path):
    dossier = tmp_path / "run"
    dossier.mkdir()
    _run(dossier, "x", [1, 1, 0])
    assert len(paired.outcomes(dossier)) == 3


# —————————————————————————————————— cli ———————————————————————————————————

@pytest.mark.parametrize("commande", ["twin", "guard", "paired"])
def test_sans_argument_affiche_l_usage(commande, capsys):
    """No command may answer a missing argument with a traceback."""
    assert cli.main([commande]) == 2
    assert "usage:" in capsys.readouterr().err


def test_commande_inconnue(capsys):
    assert cli.main(["quantize"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_diversite_annoncee_dans_le_readme():
    """The three figures the README and the case study publish, recomputed."""
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    attendu = {330_000: 0.387, 240_000: 0.439, 180_000: 0.495}
    for octets, valeur in attendu.items():
        _, stats = corpus.generate(registre, octets, 20260803)
        assert stats["diversity_4gram"] == valeur, f"{octets} B no longer yields {valeur}"


def test_cas_reel_du_depot():
    """The case study's own numbers: 196/200 identical, p = 0.625."""
    resultats = RACINE / "case-study" / "results"
    r = paired.mcnemar(
        paired.outcomes(resultats / "reference-arc_easy-200.jsonl"),
        paired.outcomes(resultats / "candidate-arc_easy-200.jsonl"))
    assert r["questions"] == 200
    assert r["agree"] == 196
    assert r["reference_right"] == 134
    assert r["candidate_right"] == 136
    assert math.isclose(r["p_value"], 0.625)
