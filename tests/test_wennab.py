"""Tests for the commands that need no model file.

L'*analyse* de `twin` — quel groupe de tenseurs a bougé, de combien d'octets —
s'éprouve contre les deux vrais GGUF de l'étude de cas, pas ici : un fichier
d'essai serait un jouet qui ne prouve rien, et le vrai pèse un gigaoctet.

Son **code de sortie**, lui, se teste ici, parce qu'il ne dépend d'aucune
propriété du modèle : deux tenseurs de quatre par quatre suffisent à ce que les
cartes de types diffèrent, et c'est tout ce que la décision regarde. C'est la
même leçon que la garde `__main__` plus bas — ce qui casse, ce n'est pas le
calcul, c'est le câblage autour.
"""
from __future__ import annotations

import json
import math
import pathlib
import subprocess
import sys
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


def test_le_filtre_de_longueur_suit_le_n_demande(tmp_path):
    """Le faux « clean » le plus grave trouvé dans ce dépôt.

    `load_exams` écartait les chaînes JSON de moins de **huit** mots quel que
    soit le n demandé. Avec `--n=5`, une épreuve de six mots posée entière dans
    le corpus n'était donc pas lue du tout : une épreuve sur deux, zéro
    collision, une coche, code 0. Et le garde-fou « zéro épreuve n'est pas un
    succès » ne rattrapait rien, puisqu'une autre épreuve, elle, avait été lue.
    """
    courte = "le chef de service dispose"                       # 5 mots
    longue = " ".join(f"mot{i}" for i in range(30))             # 30 mots, absente
    (tmp_path / "exams.json").write_text(
        json.dumps({"a": longue, "b": courte}), encoding="utf-8")

    epreuves = guard.load_exams([tmp_path / "exams.json"], n=5)
    assert len(epreuves) == 2, "l'épreuve de cinq mots doit être lue quand n=5"

    r = guard.check("bla bla " + courte + " bla bla", epreuves, n=5)
    assert not r["clean"], "une épreuve entièrement présente ne peut pas passer"


def test_plus_longue_sequence_rapportee(tmp_path):
    epreuve = tmp_path / "e.txt"
    epreuve.write_text("alpha bravo charlie delta echo foxtrot")
    r = guard.check("zoulou alpha bravo charlie yankee", guard.load_exams([epreuve]))
    assert r["longest_overall"] == 3
    assert not r["longest_truncated"]
    assert r["clean"]


def test_sequence_plus_longue_que_le_plafond_est_annoncee_comme_telle():
    """A search ceiling must not read as a measurement.

    Pasting a whole exam into the corpus gives a shared run of seventy words.
    Reporting "40" — the bound — understates it with the composure of an exact
    figure.
    """
    suite = [f"m{i}" for i in range(60)]
    longueur, _, tronquee = guard.longest_shared(suite, suite, plafond=10)
    assert (longueur, tronquee) == (10, True)


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


def test_sans_doc_id_le_fichier_est_refuse(tmp_path):
    """Sans identifiant, `outcomes` numérotait par ordre d'arrivée.

    C'est-à-dire l'appariement par position, que la docstring de la fonction
    déconseille deux lignes au-dessus de la ligne qui le faisait. Silencieux :
    deux exécutions ordonnées différemment se comparaient question contre
    question sans rapport, et le rapport paraissait sain.
    """
    (tmp_path / "samples_x.jsonl").write_text(
        "\n".join(json.dumps({"acc_norm": v}) for v in (1, 0, 1)), encoding="utf-8")
    with pytest.raises(paired.MismatchedRuns, match="doc_id"):
        paired.outcomes(tmp_path / "samples_x.jsonl")


def test_dossier_accepte_a_la_place_du_fichier(tmp_path):
    dossier = tmp_path / "run"
    dossier.mkdir()
    _run(dossier, "x", [1, 1, 0])
    assert len(paired.outcomes(dossier)) == 3


# —————————————————————————————————— cli ———————————————————————————————————

@pytest.mark.parametrize("commande", ["corpus", "twin", "guard", "paired"])
def test_sans_argument_affiche_l_usage(commande, capsys):
    """No command may answer a missing argument with a traceback.

    `corpus` manquait à cette liste, et c'est pour ça qu'il rendait 1 — le code
    d'un contrôle qui a échoué — en imprimant la première ligne de sa docstring
    au lieu d'un usage.
    """
    assert cli.main([commande]) == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["corpus", "absent.toml"],
    ["corpus", "registries/enterprise-fr.toml", "--bytes=abc"],
    ["guard", "absent.txt", "--against", "README.md"],
    ["guard", "README.md", "--against", "absent.txt"],
    ["guard", "--against", "README.md"],
    ["guard", "README.md", "--against", "README.md", "--n=abc"],
    ["paired", "absent-a", "absent-b"],
    ["paired", "README.md", "README.md"],
])
def test_ce_qui_na_pas_pu_tourner_sort_2(argv, capsys):
    """2 et 1 ne veulent pas dire la même chose, et c'est tout l'enjeu.

    Ces huit chemins remontaient la pile de Python, donc **code 1** : celui
    d'un contrôle qui a tourné et a échoué. Dans un journal de CI, un chemin
    mal tapé devenait indiscernable d'une vraie contamination — la panne
    prenait l'apparence exacte du résultat.
    """
    chemins = [str(RACINE / a) if a.endswith((".toml", ".md", ".txt")) and "absent" not in a
               else a for a in argv]
    assert cli.main(chemins) == 2, f"{argv} devrait rendre 2"
    err = capsys.readouterr().err
    assert err.strip(), f"{argv} sort 2 sans rien dire"
    assert "Traceback" not in err


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


def _corpus_du_depot() -> str:
    registre = corpus.load(RACINE / "registries" / "enterprise-fr.toml")
    return corpus.generate(registre, 180_000, 20260803)[0]


def _epreuves_du_depot() -> list[pathlib.Path]:
    return sorted((RACINE / "case-study" / "exams").glob("*.txt"))


def test_les_dix_sept_epreuves_sont_bien_la():
    """The number the README prints is a file count, not a claim.

    `guard` was the only one of the four whose published example rested on files
    the repository did not ship: the command could not be run at all.
    """
    epreuves = _epreuves_du_depot()
    assert len(epreuves) == 17, [p.name for p in epreuves]
    assert all(len(p.read_text(encoding="utf-8").split()) >= 30 for p in epreuves)


def test_le_corpus_livre_est_disjoint_des_epreuves_livrees():
    """The README's figures, recomputed from the files this repository ships."""
    r = guard.check(_corpus_du_depot(), guard.load_exams(_epreuves_du_depot()))
    assert r["exams"] == 17
    assert r["corpus_words"] == 28_291
    assert r["corpus_ngrams"] == 17_880
    assert r["clean"]
    assert r["longest_overall"] == 5, r["longest_sequence"]
    assert r["longest_exam"] == "note-conges.txt"


def test_une_epreuve_recollee_dans_le_corpus_est_refusee(tmp_path):
    """The replay the README offers, down to the exit code.

    This is the fault that actually happened — a template and an exam written by
    the same hand — reproduced the only honest way: by causing it.
    """
    epreuve = RACINE / "case-study" / "exams" / "note-conges.txt"
    contamine = tmp_path / "contaminated.txt"
    contamine.write_text(_corpus_du_depot() + epreuve.read_text(encoding="utf-8"),
                         encoding="utf-8")

    code = cli.main(["guard", str(contamine), "--against",
                     *[str(p) for p in _epreuves_du_depot()]])
    assert code == 1, "a corpus holding an exam must fail, and loudly"


def test_les_resultats_ne_passent_pas_pour_des_epreuves():
    """The refusal the README publishes, against this repository's results file."""
    resultats = RACINE / "case-study" / "results" / "reference-arc_easy-200.jsonl"
    r = guard.check(_corpus_du_depot(), guard.load_exams([resultats]))
    assert r["exams"] == 0 and not r["clean"]


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


# —————————————————————————————————— twin ——————————————————————————————————

def _gguf(chemin: pathlib.Path, dtype, couches=(0, 1)) -> pathlib.Path:
    """Le plus petit GGUF valide qui porte une carte de types lisible.

    Deux tenseurs de 4×4, écrits par `gguf` lui-même : ce que `twin` regarde
    est le nom du type, jamais une valeur.
    """
    import numpy as np
    from gguf import GGUFWriter

    w = GGUFWriter(str(chemin), "test")
    for couche in couches:
        w.add_tensor(f"blk.{couche}.attn_qkv.weight", np.zeros((4, 4), dtype=dtype))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return chemin


def test_paire_invalide_sort_1(tmp_path, capsys):
    """La phrase « NOT a valid pair » doit pouvoir arrêter une chaîne.

    La première version l'imprimait et sortait 0 : la seule commande qui voit
    une comparaison déjà faussée était incapable de la stopper. Vérifié qu'il
    échoue sur l'ancien code, qui rendait 0 avec exactement cette sortie.
    """
    import numpy as np

    a = _gguf(tmp_path / "reference.gguf", np.float32)
    b = _gguf(tmp_path / "candidate.gguf", np.float16)
    assert cli.main(["twin", str(a), str(b)]) == 1
    assert "NOT a valid pair" in capsys.readouterr().out


def test_paire_valide_sort_0(tmp_path, capsys):
    import numpy as np

    a = _gguf(tmp_path / "reference.gguf", np.float32)
    b = _gguf(tmp_path / "candidate.gguf", np.float32)
    assert cli.main(["twin", str(a), str(b)]) == 0
    assert "identical type maps" in capsys.readouterr().out


def test_fichier_absent_sort_2_sans_trace_d_appels(tmp_path, capsys):
    """2 veut dire « n'a pas pu tourner », et se distingue de 1.

    Sans ce contrôle, un chemin mal tapé remontait la pile du lecteur GGUF :
    illisible, et impossible à distinguer d'un échec de contrôle dans un
    journal de CI.
    """
    import numpy as np

    a = _gguf(tmp_path / "reference.gguf", np.float32)
    assert cli.main(["twin", str(a), str(tmp_path / "absent.gguf")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_tenseur_en_trop_nest_pas_une_carte_identique(tmp_path, capsys):
    """« identical type maps » au-dessus de « difference +64 B ».

    `differences()` ne parcourait que les tenseurs de la référence : ceux que
    le candidat avait en plus n'existaient pas. Deux fichiers d'architectures
    différentes ressortaient donc « differ only in values », code 0 — le titre
    démentant le chiffre imprimé deux lignes plus bas.
    """
    import numpy as np

    a = _gguf(tmp_path / "reference.gguf", np.float32, couches=(0,))
    b = _gguf(tmp_path / "candidate.gguf", np.float32, couches=(0, 1))
    assert cli.main(["twin", str(a), str(b)]) == 1
    sortie = capsys.readouterr().out
    assert "identical type maps" not in sortie
    assert "absent" in sortie


def test_emit_n_exige_pas_que_sa_cible_existe(tmp_path):
    """La cible de `--emit` est écrite, pas lue.

    Le contrôle des chemins l'a d'abord prise pour une entrée manquante et
    rendait 2 sans rien produire.
    """
    import numpy as np

    a = _gguf(tmp_path / "reference.gguf", np.float32)
    cible = tmp_path / "types.txt"
    assert cli.main(["twin", str(a), "--emit", str(cible)]) == 0
    assert cible.is_file()


# ———————————————————————————— les points d'entrée ————————————————————————————

@pytest.mark.parametrize("module", ["wennab", "wennab.cli"])
def test_le_module_lance_vraiment_quelque_chose(module):
    """Les deux formes de `python -m` doivent afficher l'aide.

    `wennab/cli.py` n'avait pas de garde `__main__` : la ligne que le README
    donnait pour lancer l'outil depuis un clone importait le module, n'écrivait
    rien et **sortait avec le code 0**. Un succès muet — le mode de panne que
    tout ce dépôt existe pour attraper, dans le dépôt lui-même.

    Le test passe par un sous-processus à dessein : appeler `cli.main()` en
    Python aurait réussi tout du long, puisque la fonction n'a jamais été en
    cause. C'est *l'invocation* qui était cassée.
    """
    fait = subprocess.run([sys.executable, "-m", module, "--help"],
                          cwd=RACINE, capture_output=True, text=True)
    assert fait.returncode == 0, fait.stderr
    assert "wennab corpus" in fait.stdout, (
        f"`python -m {module} --help` n'a rien affiché : {fait.stdout!r}")
