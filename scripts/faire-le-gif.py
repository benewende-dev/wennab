#!/usr/bin/env python3
"""Build the README's GIF by actually running the commands it shows.

The point is that the picture cannot drift from the tool. Nothing here is typed
out by hand: every line after a `$` prompt is the real stdout of the command
above it, captured in a scratch directory and pasted in unchanged. Change the
report format and this GIF changes with it, or it does not build at all.

    python scripts/faire-le-gif.py [--out docs/images/demo.gif]

Needs Google Chrome (headless screenshots) and ffmpeg (palette + assembly).
Neither is a dependency of the package: this script is for the maintainer, not
for the user, which is why it lives in scripts/ and not in wennab/.
"""
from __future__ import annotations

import argparse
import html
import pathlib
import shutil
import subprocess
import sys
import tempfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/usr/bin/google-chrome", "/usr/bin/chromium")

LARGEUR, HAUTEUR = 900, 450
FPS = 9


def chrome() -> str:
    for c in CHROME:
        if pathlib.Path(c).exists():
            return c
    sys.exit("Google Chrome not found — needed for the screenshots.")


def executer(commande: list[str], cwd: pathlib.Path) -> tuple[str, int]:
    """La sortie réelle, stdout et stderr confondus comme au terminal."""
    fait = subprocess.run(commande, cwd=cwd, capture_output=True, text=True)
    return (fait.stdout + fait.stderr).rstrip("\n"), fait.returncode


def scenes(travail: pathlib.Path) -> list[list[tuple[str, str]]]:
    """Trois actes, chacun une liste de (rôle, texte).

    Rôles : `cmd` la ligne de commande, `out` la sortie, `note` une glose.
    """
    py = [sys.executable, "-m", "wennab"]
    corpus = travail / "corpus.txt"
    contamine = travail / "contaminated.txt"
    epreuves = sorted((RACINE / "case-study" / "exams").glob("*.txt"))
    rel = [f"case-study/exams/{p.name}" for p in epreuves]

    sortie, _ = executer([*py, "corpus", "registries/enterprise-fr.toml",
                          "--bytes=180000"], RACINE)
    # stdout est le corpus lui-même ; les statistiques partent sur stderr.
    fait = subprocess.run([*py, "corpus", "registries/enterprise-fr.toml",
                           "--bytes=180000"], cwd=RACINE, capture_output=True, text=True)
    corpus.write_text(fait.stdout, encoding="utf-8")
    acte1 = [("cmd", "wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt")]
    acte1 += [("out", l) for l in fait.stderr.rstrip("\n").splitlines()]

    propre, code = executer([*py, "guard", str(corpus), "--against", *[str(p) for p in epreuves]],
                            RACINE)
    if code != 0:
        sys.exit("the shipped corpus no longer passes — fix that before drawing it")
    acte1 += [("cmd", "wennab guard corpus.txt --against case-study/exams/*.txt")]
    acte1 += [("out", l) for l in propre.splitlines()]

    contamine.write_text(corpus.read_text(encoding="utf-8")
                         + (RACINE / "case-study/exams/note-conges.txt").read_text(encoding="utf-8"),
                         encoding="utf-8")
    sale, code = executer([*py, "guard", str(contamine), "--against", *[str(p) for p in epreuves]],
                          RACINE)
    if code != 1:
        sys.exit("a corpus holding an exam no longer fails — that is the whole demo")
    acte2 = [("cmd", "cat corpus.txt case-study/exams/note-conges.txt > contaminated.txt"),
             ("cmd", "wennab guard contaminated.txt --against case-study/exams/*.txt")]
    acte2 += [("out", l) for l in sale.splitlines()]
    acte2 += [("cmd", "echo $?"), ("out", str(code))]

    a = "case-study/results/reference-arc_easy-200.jsonl"
    b = "case-study/results/candidate-arc_easy-200.jsonl"
    paires, _ = executer([*py, "paired", a, b], RACINE)
    acte3 = [("cmd", f"wennab paired {a} \\"), ("cmd2", f"              {b}")]
    acte3 += [("out", l) for l in paires.splitlines()]

    return [acte1, acte2, acte3]


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:%dpx;height:%dpx;background:#14161a;font-family:"SF Mono",Menlo,
 "DejaVu Sans Mono",monospace;font-size:14.5px;line-height:1.52;color:#d7dae0;
 padding:20px 22px;overflow:hidden}
.l{white-space:pre-wrap;word-break:break-word;padding-left:1.4em;text-indent:-1.4em}
.cmd{color:#e6edf3}.cmd .p{color:#7ee787;font-weight:600}
.ok{color:#3fb950}.bad{color:#f85149}.dim{color:#8b949e}
.hidden{visibility:hidden}
""" % (LARGEUR, HAUTEUR)


def classe(role: str, texte: str) -> str:
    if role.startswith("cmd"):
        return "cmd"
    t = texte.lstrip()
    if t.startswith("✓"):
        return "ok"
    if t.startswith("✗"):
        return "bad"
    if t.startswith("«") or t.startswith("Check the paths") or t.startswith("Measuring"):
        return "dim"
    return ""


def page(lignes: list[tuple[str, str]], jusqua: int) -> str:
    corps = []
    for i, (role, texte) in enumerate(lignes):
        marque = "" if i < jusqua else " hidden"
        prefixe = '<span class="p">$</span> ' if role == "cmd" else ""
        # Une ligne vide est une ligne : sans ce &nbsp; la boîte s'effondre et
        # le GIF resserre une sortie que le terminal, lui, aère.
        contenu = f'{prefixe}{html.escape(texte)}' if texte else '&nbsp;'
        corps.append(f'<div class="l {classe(role, texte)}{marque}">{contenu}</div>')
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{''.join(corps)}</body></html>")


def etapes(acte: list[tuple[str, str]]) -> list[tuple[int, int]]:
    """(nombre de lignes visibles, images à tenir) — une commande, puis sa sortie."""
    pas, i = [], 0
    while i < len(acte):
        j = i + 1
        while j < len(acte) and acte[j][0].startswith("cmd2"):
            j += 1
        pas.append((j, 6))                       # la commande apparaît
        k = j
        while k < len(acte) and acte[k][0] == "out":
            k += 1
        if k > j:
            pas.append((k, 30 if k - j > 4 else 18))   # sa sortie, tenue pour être lue
        i = k if k > j else j
    pas[-1] = (pas[-1][0], pas[-1][1] + 12)      # une pause en fin d'acte
    return pas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/images/demo.gif")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found.")
    navigateur = chrome()

    with tempfile.TemporaryDirectory() as tmp:
        travail = pathlib.Path(tmp)
        images = travail / "frames"
        images.mkdir()
        n = 0
        for acte in scenes(travail):
            for visibles, tenue in etapes(acte):
                f = travail / "f.html"
                f.write_text(page(acte, visibles), encoding="utf-8")
                tir = travail / f"tir-{n:04d}.png"
                subprocess.run([navigateur, "--headless", "--disable-gpu",
                                f"--screenshot={tir}",
                                f"--window-size={LARGEUR},{HAUTEUR}",
                                "--default-background-color=14161AFF",
                                "--hide-scrollbars", f"file://{f}"],
                               capture_output=True, check=True)
                for _ in range(tenue):
                    n += 1
                    shutil.copy(tir, images / f"{n:05d}.png")

        palette = travail / "palette.png"
        commun = ["-framerate", str(FPS), "-i", str(images / "%05d.png")]
        subprocess.run(["ffmpeg", "-y", *commun, "-vf",
                        "palettegen=max_colors=64:stats_mode=diff", str(palette)],
                       capture_output=True, check=True)
        cible = RACINE / args.out
        cible.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", *commun, "-i", str(palette), "-lavfi",
                        "paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                        str(cible)], capture_output=True, check=True)

    print(f"{cible.relative_to(RACINE)} — {n} frames, {cible.stat().st_size // 1024} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
