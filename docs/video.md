# La vidéo — moins de trois minutes

Pour l'**Arm Create: AI Optimization Challenge**, échéance **14 août 2026,
16 h 00 PDT**. Ce fichier dit *quoi filmer* ;
[`docs/narration.md`](narration.md) dit *quoi dire*, mot à mot.

## Ce que le règlement exige, et ce qu'il n'exige pas

La vidéo est **optionnelle**. Elle est faite quand même, pour deux raisons
lisibles dans le barème et dans le texte du concours :

- **« WOW factor » vaut vingt-cinq points sur cent** — le reste étant
  implémentation technique 40, impact 20, expérience 15. C'est le seul de ces
  quatre postes qu'un dépôt seul ne peut pas gagner.
- Le règlement demande, pour toute vidéo soumise, « *footage that shows the
  Project functioning on the device for which it was built* ». Wennab est fait
  pour un portable Arm de huit gigaoctets ; la vidéo n'est donc pas une
  présentation, c'est la preuve que l'outil tourne là où il prétend servir.

Autres contraintes retenues du règlement : moins de trois minutes, publique sur
YouTube, aucune marque tierce ni musique sous droits. Il n'y a donc **aucune
musique** — le fond sonore serait le seul élément de la vidéo qu'on ne pourrait
pas justifier.

## Règle qui tient tout

**Rien d'affirmé qui ne soit montré à l'écran, et rien à l'écran qui n'ait été
exécuté.** `scripts/faire-la-video.py` ne dessine pas des captures : il lance les
commandes, photographie leur sortie réelle et refuse de continuer si l'une d'elles
change de comportement. Six refus sont câblés :

| il s'arrête si | parce que |
|---|---|
| `twin` ne voit plus deux cartes de types différentes | le segment 2 dirait le contraire de ce qu'il montre |
| le témoin n'a plus la carte de la référence | le rejeu n'aurait plus rien prouvé |
| le corpus livré ne passe plus `guard` | on filmerait un défaut en le présentant comme un contrôle |
| un corpus contenant son examen ne échoue plus | c'est toute la démonstration |
| `paired` échoue | le résultat nul n'est plus mesuré |
| la suite de tests ne passe plus | le montrer serait mentir |

C'est la même exigence que `scripts/faire-le-gif.py`, et c'est la raison d'être du
dépôt appliquée à sa propre vidéo : un outil qui refuse les résultats invérifiables
ne peut pas s'annoncer par une promesse.

**Personne à l'image.** Voix de synthèse, capture d'écran, rien d'autre. Pas de
logo, pas de titre animé, pas de présentation de soi : la première phrase est le
problème.

## Le montage, tel qu'il est

Cinq segments, chacun de la durée exacte de son audio.

| | plan | à l'écran |
|---|---|---|
| s1 | carte | la phrase du rapport, puis les trois défauts qu'elle cache |
| s2 | terminal | `twin` sur deux vrais GGUF de 1,16 Go, puis le témoin à zéro octet près |
| s3 | terminal | `corpus`, `guard` qui passe, `guard` qui refuse avec le code 1 |
| s4 | terminal | `paired` : 196 sur 200, p = 0,625 |
| s5 | terminal, puis carte | les trois outils chronométrés sur le M1, les 32 tests, et la machine |

Chaque segment se révèle par paliers — un palier par phrase de la narration —
et chaque palier reste affiché jusqu'au suivant. Un palier pèse ce qu'il ajoute
de lignes : une sortie longue reste plus longtemps à l'écran qu'une commande
d'une ligne.

## Le piège qui a coûté une prise sur un tournage précédent

**La fenêtre de lignes.** Le premier montage affichait tout l'historique
accumulé ; le segment 3 dépassait le cadre de trois lignes, et ce qui tombait
dessous était exactement ce que la voix annonçait — `echo $?` et son `1`. Rien ne
le signale : l'image reste plausible, elle a juste perdu sa conclusion.

La fenêtre est donc **calculée**, pas estimée : hauteur utile divisée par
l'interligne, et une ligne trop longue compte pour le nombre de lignes qu'elle
occupera après repli (`fenetre()`). Le dernier palier d'un segment est toujours
celui qui porte le chiffre — `+0 B`, `exit code 1`, `p = 0.625` — et il doit être
lisible en entier.

## Voix et sous-titres

Les cinq pistes s'enregistrent **séparément**, une par segment, dans
`voix/seg1.mp3` … `voix/seg5.mp3` : un segment à refaire coûte trente secondes,
pas trois minutes. C'est la longueur de la piste qui fixe celle du plan, jamais
l'inverse.

`--brouillon <voix macOS>` fabrique des pistes jetables avec `say` pour juger le
rythme avant d'enregistrer pour de bon. Elles ne servent qu'au cadrage.

Les sous-titres sont **générés depuis le texte prononcé**, pas depuis une
transcription automatique : le texte est déjà écrit, autant qu'il soit exact. Ils
font le chemin inverse de la voix — la narration écrit *zero point six two five*
pour que le moteur le prononce bien, le sous-titre affiche `0.625` pour que l'œil
le retrouve à l'écran.

**Les générer avant de valider le montage.** Sur un tournage précédent, ce sont
eux qui ont attrapé la seule erreur de fond — un segment dont la voix nommait
encore un jeu de données abandonné. À l'oreille, ça passait.

## Fabrication

```bash
python scripts/faire-la-video.py \
    --ref    <reference.gguf> \
    --cand   <candidate.gguf> \
    --temoin <control.gguf> \
    --voix ~/Desktop/wennab-video/voix
```

Les trois GGUF sont exigés : le segment 2 montre `twin` sur deux fichiers de
1,16 Go, et un dépôt n'a pas à embarquer un gigaoctet de poids. Sans eux le
script s'arrête au lieu de dessiner une sortie qu'il n'a pas obtenue — c'est la
même raison qui fait que le README appelle ces deux blocs « the one thing here
you cannot rerun from a clone ».

Sortent `wennab.mp4` (1080p, H.264) et `wennab.srt`. Le script rend un code
d'erreur si le montage dépasse trois minutes.
