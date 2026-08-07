#!/usr/bin/env python3
"""Monte la vidéo de soumission en *exécutant* les commandes qu'elle montre.

Même principe que `faire-le-gif.py`, poussé à la vidéo : aucune ligne affichée
n'est tapée à la main. Chaque plan est la sortie réelle d'une commande lancée
sur cette machine, photographiée par Chrome, et tenue à l'écran exactement le
temps de la phrase qui la commente.

    python scripts/faire-la-video.py \\
        --ref  <reference.gguf> --cand <candidate.gguf> --temoin <control.gguf> \\
        [--voix voix/] [--brouillon Daniel] [--out ~/Desktop/wennab-video]

`--ref/--cand/--temoin` sont exigés : le segment 2 montre `twin` sur deux vrais
fichiers de 1,16 Go, et un dépôt n'a pas à embarquer un gigaoctet de poids. Sans
eux le script s'arrête au lieu de dessiner une sortie qu'il n'a pas obtenue.

Durées. La longueur d'un plan est celle de sa piste voix (`voix/segN.mp3`), pas
une estimation : c'est la voix qui commande l'image. Sans piste, `--brouillon
<voix macOS>` en fabrique une jetable avec `say`, pour juger le rythme avant
d'enregistrer pour de bon.

Sort : `wennab.mp4` (1080p, H.264) et `wennab.srt`, les sous-titres écrits
depuis le texte prononcé — jamais depuis une transcription automatique.

Demande Google Chrome et ffmpeg. Outil de maintenance : il vit dans scripts/,
pas dans wennab/.
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/usr/bin/google-chrome", "/usr/bin/chromium")

LARGEUR, HAUTEUR = 1920, 1080
POLICE = 27
INTERLIGNE = 1.5
MARGE_V, MARGE_H = 48, 56
# Largeur d'un caractère en SF Mono : 0,6 cadratin. C'est ce rapport qui décide
# combien de lignes une sortie longue occupe vraiment une fois repliée.
CHASSE = 0.6
FPS = 25
BLANC_FIN = 0.6          # respiration après la dernière phrase d'un segment
MOTS_PAR_SECONDE = 2.45  # mesuré sur les narrations déjà tournées, faute de piste


# --------------------------------------------------------------------------
# exécution

def chrome() -> str:
    for c in CHROME:
        if pathlib.Path(c).exists():
            return c
    sys.exit("Google Chrome introuvable — il fait les captures.")


def python_du_projet() -> str:
    """Le venv du dépôt s'il existe : `twin` a besoin de `gguf`."""
    venv = RACINE / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def executer(commande: list[str], cwd: pathlib.Path = RACINE) -> tuple[str, str, int]:
    fait = subprocess.run(commande, cwd=cwd, capture_output=True, text=True)
    return fait.stdout, fait.stderr, fait.returncode


def lancer(commande: list[str]) -> None:
    """Comme `subprocess.run(check=True)`, mais qui dit *pourquoi* ffmpeg refuse.

    Sans cela l'échec se résume à un code de sortie, et les vingt lignes qui
    nomment la cause restent dans le tampon capturé."""
    fait = subprocess.run(commande, capture_output=True, text=True)
    if fait.returncode != 0:
        sys.exit(f"échec de {commande[0]} :\n"
                 + "\n".join(fait.stderr.rstrip().splitlines()[-15:]))


def duree(fichier: pathlib.Path) -> float:
    sortie, _, _ = executer(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "csv=p=0", str(fichier)])
    return float(sortie.strip())


# --------------------------------------------------------------------------
# le contenu des plans, obtenu en lançant les outils

def lignes(texte: str) -> list[tuple[str, str]]:
    return [("out", l) for l in texte.rstrip("\n").splitlines()]


def segments(travail: pathlib.Path, gguf: dict[str, pathlib.Path]) -> list[dict]:
    """Cinq segments. Chacun : un genre, et des *temps* — un temps par phrase.

    Un temps est une liste de (rôle, texte) qui s'ajoute aux précédents. Le
    segment se révèle donc par paliers, et chaque palier reste affiché jusqu'au
    suivant.
    """
    py = [python_du_projet(), "-m", "wennab"]
    corpus = travail / "corpus.txt"
    contamine = travail / "contaminated.txt"
    epreuves = sorted((RACINE / "case-study" / "exams").glob("*.txt"))

    # ---- s1 : une carte, pas un terminal
    s1 = {"genre": "carte", "temps": [
        [("titre", "“our build scores 0.68 against the baseline’s 0.67, at the same size.”")],
        [("faute", "the two files differ by more than the thing under test")],
        [("faute", "the calibration corpus contains the exam")],
        [("faute", "two totals are not a comparison")],
    ]}

    # ---- s2 : twin, sur les deux vrais fichiers
    sortie, err, code = executer([*py, "twin", str(gguf["ref"]), str(gguf["cand"])])
    if code != 0:
        sys.exit(f"`twin` a échoué sur la paire réelle :\n{err}")
    if "NOT a valid pair" not in sortie:
        sys.exit("la paire de référence ne diffère plus par sa carte des types — "
                 "le segment 2 raconterait le contraire de ce qu'il montre")
    temoin, err, code = executer([*py, "twin", str(gguf["ref"]), str(gguf["temoin"])])
    if code != 0 or "identical type maps" not in temoin:
        sys.exit(f"le témoin n'a plus la même carte des types que la référence :\n{err or temoin}")

    haut, bas = sortie.split("Measuring these two", 1)
    s2 = {"genre": "terminal", "temps": [
        [("cmd", "wennab twin reference.gguf candidate.gguf"), *lignes(haut)],
        [("dim", "Measuring these two" + bas.rstrip("\n").split("Rebuild")[0].rstrip())],
        [("cmd", "wennab twin reference.gguf --emit types.txt"),
         ("cmd", "llama-quantize --imatrix yours.imatrix --tensor-type-file types.txt \\"),
         ("cmd2", "    source-BF16.gguf candidate.gguf IQ4_XS"),
         ("cmd", "wennab twin reference.gguf candidate.gguf"),
         *lignes(temoin)],
    ]}

    # ---- s3 : corpus, guard qui passe, guard qui refuse
    fait = subprocess.run([*py, "corpus", "registries/enterprise-fr.toml", "--bytes=180000"],
                          cwd=RACINE, capture_output=True, text=True)
    corpus.write_text(fait.stdout, encoding="utf-8")
    propre, err, code = executer([*py, "guard", str(corpus), "--against",
                                  *[str(p) for p in epreuves]])
    if code != 0:
        sys.exit("le corpus livré ne passe plus — le réparer avant de le filmer")
    contamine.write_text(corpus.read_text(encoding="utf-8")
                         + (RACINE / "case-study/exams/note-conges.txt").read_text(encoding="utf-8"),
                         encoding="utf-8")
    sale, err, code = executer([*py, "guard", str(contamine), "--against",
                                *[str(p) for p in epreuves]])
    if code != 1:
        sys.exit("un corpus contenant son examen ne échoue plus — c'est toute la démonstration")

    s3 = {"genre": "terminal", "temps": [
        [("cmd", "wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt"),
         *lignes(fait.stderr)],
        [("cmd", "wennab guard corpus.txt --against case-study/exams/*.txt"), *lignes(propre)],
        [("cmd", "cat corpus.txt case-study/exams/note-conges.txt > contaminated.txt"),
         ("cmd", "wennab guard contaminated.txt --against case-study/exams/*.txt"),
         *lignes(sale), ("cmd", "echo $?"), ("out", str(code))],
    ]}

    # ---- s4 : paired
    a = "case-study/results/reference-arc_easy-200.jsonl"
    b = "case-study/results/candidate-arc_easy-200.jsonl"
    paires, err, code = executer([*py, "paired", a, b])
    if code != 0:
        sys.exit(f"`paired` a échoué :\n{err}")
    tete, queue = paires.split("  agree", 1)
    s4 = {"genre": "terminal", "temps": [
        [("cmd", f"wennab paired {a} \\"), ("cmd2", f"              {b}"), *lignes(tete)],
        [*lignes("  agree" + queue)],
    ]}

    # ---- s5 : les trois outils chronométrés, puis la carte de clôture
    chrono = []
    for etiquette, argv in (
        # Sans redirection dans l'étiquette : la mesure n'en fait pas, et une
        # commande affichée doit être celle qui a tourné.
        ("wennab corpus registries/enterprise-fr.toml --bytes=180000",
         ["corpus", "registries/enterprise-fr.toml", "--bytes=180000"]),
        ("wennab guard corpus.txt --against case-study/exams/*.txt",
         ["guard", str(corpus), "--against", *[str(p) for p in epreuves]]),
        (f"wennab paired {a} {b}", ["paired", a, b]),
    ):
        mesure = subprocess.run(["/usr/bin/time", "-p", *py, *argv], cwd=RACINE,
                                capture_output=True, text=True,
                                env={**__import__("os").environ, "LC_ALL": "C"})
        reel = next(l for l in mesure.stderr.splitlines() if l.startswith("real"))
        chrono += [("cmd", f"time {etiquette}"), ("out", f"  {reel}")]

    tests = subprocess.run([python_du_projet(), "-m", "pytest", "tests/", "-q"],
                           cwd=RACINE, capture_output=True, text=True)
    resume = next((l for l in reversed(tests.stdout.splitlines()) if "passed" in l), "")
    if tests.returncode != 0:
        sys.exit("la suite de tests ne passe plus — la filmer serait mentir")

    s5 = {"genre": "terminal", "temps": [
        chrono[:4],
        chrono[4:] + [("cmd", "python -m pytest tests/ -q"), ("ok", "  " + resume.strip())],
        [("carte", "Apple M1 · 8 GB · CPU only")],
    ]}

    return [s1, s2, s3, s4, s5]


# --------------------------------------------------------------------------
# rendu

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:%dpx;height:%dpx;background:#14161a;font-family:"SF Mono",Menlo,
 "DejaVu Sans Mono",monospace;font-size:%dpx;line-height:%s;color:#d7dae0;
 padding:%dpx %dpx;overflow:hidden}
.l{white-space:pre-wrap;word-break:break-word;padding-left:1.4em;text-indent:-1.4em}
.cmd{color:#e6edf3}.cmd .p{color:#7ee787;font-weight:600}
.ok{color:#3fb950}.bad{color:#f85149}.dim{color:#8b949e}
.hidden{visibility:hidden}
.carte{display:flex;flex-direction:column;justify-content:center;height:100%%;
 padding:0 40px;font-size:40px;line-height:1.45}
.carte .titre{color:#e6edf3;font-size:44px;margin-bottom:56px}
.carte .faute{color:#f85149;margin:14px 0;padding-left:1.5em;text-indent:-1.5em}
.carte .faute::before{content:"— "}
.carte .seul{color:#7ee787;font-size:56px;text-align:center}
""" % (LARGEUR, HAUTEUR, POLICE, INTERLIGNE, MARGE_V, MARGE_H)


def classe(role: str, texte: str) -> str:
    if role.startswith("cmd"):
        return "cmd"
    t = texte.lstrip()
    if role == "ok" or t.startswith("✓"):
        return "ok"
    if t.startswith("✗"):
        return "bad"
    if role == "dim" or t.startswith("«") or t.startswith("Measuring") or t.startswith("These two"):
        return "dim"
    return ""


def fenetre(vues: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Ne garder que la fin qui tient dans le cadre.

    Le plan qui compte est toujours le dernier : `exit code 1`, `p = 0.625`,
    `+0 B`. Une fenêtre estimée à la louche les fait tomber sous le bord — et
    c'est invisible au montage, puisque l'image reste plausible. Elle est donc
    **calculée** : hauteur utile divisée par l'interligne, et une ligne trop
    longue compte pour le nombre de lignes qu'elle occupera après repli.
    """
    par_ligne = int((LARGEUR - 2 * MARGE_H) / (POLICE * CHASSE)) - 2
    tenables = int((HAUTEUR - 2 * MARGE_V) / (POLICE * INTERLIGNE))
    hauteur = lambda t: max(1, -(-len(t) // par_ligne))          # noqa: E731
    total = sum(hauteur(t) for _, t in vues)
    debut = 0
    while total > tenables and debut < len(vues):
        total -= hauteur(vues[debut][1])
        debut += 1
    return vues[debut:]


def page(vues: list[tuple[str, str]], genre: str) -> str:
    if genre == "carte":
        corps = []
        for role, texte in vues:
            cl = "seul" if role == "carte" else role
            corps.append(f'<div class="{cl}">{html.escape(texte)}</div>')
        interieur = f'<div class="carte">{"".join(corps)}</div>'
    else:
        corps = []
        for role, texte in vues:
            if role == "carte":
                corps.append(f'<div class="carte"><div class="seul">{html.escape(texte)}</div></div>')
                continue
            prefixe = '<span class="p">$</span> ' if role == "cmd" else ""
            # Une ligne vide est une ligne : sans &nbsp; la boîte s'effondre et
            # l'image resserre une sortie que le terminal, lui, aère.
            contenu = f'{prefixe}{html.escape(texte)}' if texte else '&nbsp;'
            corps.append(f'<div class="l {classe(role, texte)}">{contenu}</div>')
        interieur = "".join(corps)
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{interieur}</body></html>")


def photographier(navigateur: str, html_texte: str, cible: pathlib.Path,
                  travail: pathlib.Path) -> None:
    f = travail / "page.html"
    f.write_text(html_texte, encoding="utf-8")
    subprocess.run([navigateur, "--headless", "--disable-gpu", f"--screenshot={cible}",
                    f"--window-size={LARGEUR},{HAUTEUR}",
                    "--default-background-color=14161AFF", "--hide-scrollbars",
                    f"file://{f}"], capture_output=True, check=True)


# --------------------------------------------------------------------------
# narration et sous-titres

def narration() -> list[str]:
    """Le texte prononcé, un bloc par segment, lu dans docs/narration.md."""
    doc = (RACINE / "docs" / "narration.md").read_text(encoding="utf-8")
    blocs = []
    for morceau in re.split(r"^## s\d+ — ", doc, flags=re.M)[1:]:
        dit = " ".join(l[2:].strip() for l in morceau.splitlines() if l.startswith("> "))
        blocs.append(re.sub(r"\s+", " ", dit).strip())
    if len(blocs) != 5:
        sys.exit(f"docs/narration.md donne {len(blocs)} segments, il en faut cinq")
    return blocs


def en_chiffres(phrase: str) -> str:
    """Le chemin inverse de la voix : elle dit *zero point six two five*, le
    sous-titre affiche 0.625 — pour que l'œil le retrouve à l'écran."""
    for dit, ecrit in (
        ("zero point six eight", "0.68"), ("zero point six seven", "0.67"),
        ("zero point six two five", "0.625"), ("three point three", "3.3"),
        ("twenty-three megabytes", "23 MB"), ("eight gigabytes", "8 GB"),
        ("three hundred and twenty", "320"), ("two hundred questions", "200 questions"),
        ("One hundred and ninety-six of two hundred", "196 of 200"),
        ("two-billion-parameter", "2B-parameter"), ("Mc Nemar", "McNemar"),
        ("Apple M one", "Apple M1"), ("seventeen exam texts", "17 exam texts"),
        ("sixty-nine collisions", "69 collisions"), ("exit code one", "exit code 1"),
        ("eight words at a time", "8 words at a time"), ("five words", "5 words"),
        # « four command-line tools » et « three of the four » restent en lettres :
        # aucun chiffre ne leur répond à l'écran, et un nombre isolé dans une
        # phrase de prose se lit moins bien qu'il ne s'écrit.
        ("Four questions", "4 questions"),
    ):
        phrase = phrase.replace(dit, ecrit)
    return phrase


def pauses(piste: pathlib.Path | None) -> list[float]:
    """Les silences internes d'une piste, en secondes, par leur milieu.

    Un moteur de synthèse marque les fins de phrase par une pause. Les relever
    coûte un passage de ffmpeg et vaut mieux qu'un partage au prorata des
    caractères : une phrase courte et lente et une phrase longue et rapide ont
    le même nombre de signes et pas la même durée."""
    if piste is None:
        return []
    fait = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(piste), "-af",
                           "silencedetect=n=-40dB:d=0.15", "-f", "null", "-"],
                          capture_output=True, text=True)
    debuts, milieux = [], []
    for ligne in fait.stderr.splitlines():
        if "silence_start:" in ligne:
            debuts.append(float(ligne.split("silence_start:")[1].strip()))
        elif "silence_end:" in ligne and debuts:
            fin = float(ligne.split("silence_end:")[1].split("|")[0].strip())
            milieux.append((debuts.pop() + fin) / 2)
    return milieux


def horodater(secondes: float) -> str:
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def sous_titres(textes: list[str], durees: list[float],
                pistes: list[pathlib.Path | None]) -> str:
    """Un cue par phrase, calé sur les pauses réelles de la voix.

    Le prorata des caractères donne une première borne ; on la fait glisser
    jusqu'à la pause la plus proche à moins de deux secondes. Faute de pause,
    le prorata reste — il ne fait jamais pire qu'avant."""
    cues, depart, n = [], 0.0, 1
    for texte, d, piste in zip(textes, durees, pistes):
        phrases = [p.strip() for p in re.split(r"(?<=[.:—]) (?=[A-Z])", texte) if p.strip()]
        total = sum(len(p) for p in phrases)
        libres = pauses(piste)

        bornes, t = [], 0.0
        for p in phrases[:-1]:
            t += d * len(p) / total
            proche = min(libres, key=lambda m: abs(m - t), default=None)
            bornes.append(proche if proche is not None and abs(proche - t) < 2.0 else t)
        bornes.append(d)

        precedente = 0.0
        for p, fin in zip(phrases, bornes):
            cues.append(f"{n}\n{horodater(depart + precedente)} --> "
                        f"{horodater(depart + fin)}\n{en_chiffres(p)}\n")
            precedente = fin
            n += 1
        depart += d
    return "\n".join(cues)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, type=pathlib.Path)
    ap.add_argument("--cand", required=True, type=pathlib.Path)
    ap.add_argument("--temoin", required=True, type=pathlib.Path)
    ap.add_argument("--voix", type=pathlib.Path, default=None,
                    help="dossier contenant seg1.mp3 … seg5.mp3")
    ap.add_argument("--brouillon", default=None, metavar="VOIX",
                    help="fabrique des pistes jetables avec `say -v VOIX`")
    ap.add_argument("--out", type=pathlib.Path,
                    default=pathlib.Path.home() / "Desktop" / "wennab-video")
    args = ap.parse_args()

    for outil in ("ffmpeg", "ffprobe"):
        if not shutil.which(outil):
            sys.exit(f"{outil} introuvable.")
    for nom in ("ref", "cand", "temoin"):
        if not getattr(args, nom).exists():
            sys.exit(f"--{nom} : {getattr(args, nom)} n'existe pas")
    navigateur = chrome()
    args.out.mkdir(parents=True, exist_ok=True)

    textes = narration()
    with tempfile.TemporaryDirectory() as tmp:
        travail = pathlib.Path(tmp)
        gguf = {"ref": args.ref, "cand": args.cand, "temoin": args.temoin}
        actes = segments(travail, gguf)

        pistes: list[pathlib.Path | None] = []
        for i in range(5):
            piste = (args.voix / f"seg{i + 1}.mp3") if args.voix else None
            if piste and piste.exists():
                pistes.append(piste)
            elif args.brouillon:
                brut = travail / f"seg{i + 1}.aiff"
                subprocess.run(["say", "-v", args.brouillon, "-o", str(brut),
                                textes[i]], check=True)
                mp3 = travail / f"seg{i + 1}.mp3"
                lancer(["ffmpeg", "-y", "-i", str(brut), "-b:a", "128k", str(mp3)])
                pistes.append(mp3)
            elif args.voix:
                # Une piste manquante donnait un plan muet, dans un fichier de la
                # bonne durée, sans un mot d'avertissement : la panne prenait
                # l'apparence exacte du succès. C'est le défaut que ce dépôt
                # existe pour attraper ; il n'a pas sa place dans sa propre vidéo.
                sys.exit(f"{piste} manque — monter sans elle donnerait un segment "
                         f"muet qui ressemble à un segment réussi. Fournir la piste, "
                         f"ou demander --brouillon.")
            else:
                pistes.append(None)

        durees, morceaux = [], []
        for i, (acte, piste) in enumerate(zip(actes, pistes), start=1):
            mots = len(textes[i - 1].split())
            d = (duree(piste) + BLANC_FIN) if piste else (mots / MOTS_PAR_SECONDE + BLANC_FIN)
            durees.append(d)

            # Un temps pèse ce qu'il ajoute de lignes : une sortie longue reste
            # plus longtemps à l'écran qu'une commande d'une ligne.
            poids = [max(2, len(t)) for t in acte["temps"]]
            somme = sum(poids)
            vues, liste = [], []
            for j, (temps, p) in enumerate(zip(acte["temps"], poids), start=1):
                # Un temps s'ajoute aux précédents — sauf une carte, qui efface :
                # elle n'a de force que seule à l'écran.
                vues = list(temps) if temps[0][0] == "carte" else vues + list(temps)
                png = travail / f"s{i}-{j:02d}.png"
                photographier(navigateur, page(fenetre(vues), acte["genre"]), png, travail)
                liste.append((png, d * p / somme))

            concat = travail / f"liste{i}.txt"
            concat.write_text("".join(
                f"file '{png}'\nduration {t:.3f}\n" for png, t in liste)
                + f"file '{liste[-1][0]}'\n", encoding="utf-8")
            muet = travail / f"s{i}-muet.mp4"
            lancer(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    # Débit constant : les durées d'image viennent du concat, et
                    # ffmpeg 8 refuse `-r` avec un mode variable.
                    "-fps_mode", "cfr", "-r", str(FPS), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-crf", "20", str(muet)])

            sonore = travail / f"s{i}.mp4"
            son = (["-i", str(piste)] if piste
                   else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
            # `apad` : le silence de fin doit exister *dans la piste*, pas être
            # laissé au démuxeur. Sans lui, la piste d'un segment est plus courte
            # que son plan, la concaténation recolle les sons bout à bout, et la
            # voix prend six dixièmes d'avance par segment — deux secondes au
            # cinquième. Mesuré : la voix de s5 partait à 113,0 s pour un plan
            # commençant à 115,0 s. Rien ne le signale, l'image reste juste.
            lancer(["ffmpeg", "-y", "-i", str(muet), *son,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-af", f"apad=whole_dur={d:.3f}",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{d:.3f}", str(sonore)])
            morceaux.append(sonore)

        final = travail / "liste-finale.txt"
        final.write_text("".join(f"file '{m}'\n" for m in morceaux), encoding="utf-8")
        cible = args.out / "wennab.mp4"
        lancer(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(final),
                "-c", "copy", str(cible)])

    (args.out / "wennab.srt").write_text(sous_titres(textes, durees, pistes),
                                          encoding="utf-8")
    totale = duree(cible)
    print(f"{cible} — {totale:.1f} s, {cible.stat().st_size // 1024} kB")
    print(f"{args.out / 'wennab.srt'} — sous-titres depuis le texte prononcé")
    for i, d in enumerate(durees, start=1):
        print(f"  s{i} : {d:5.1f} s")
    if totale >= 180:
        print("\n⚠ plus de trois minutes — le règlement Arm coupe là.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
