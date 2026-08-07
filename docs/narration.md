# La narration, mot à mot

**Dite le 7 août 2026 : 2 min 24, voix Liam.** Ce qui suit est le texte exact
qui a été prononcé — pas un brouillon.

Texte destiné à la vidéo de soumission de l'**Arm Create: AI Optimization
Challenge** (échéance 14 août 2026, 16 h 00 PDT). La vidéo y est *optionnelle* ;
elle est faite quand même, parce que le barème accorde vingt-cinq points sur cent
au « WOW factor » et que le règlement demande une séquence montrant l'outil
**en fonctionnement sur la machine pour laquelle il a été construit** — ici un
Apple M1, 8 Go, sans GPU.

**En anglais**, comme le README, la licence et le dépôt.

## Ce qui se prononce mal

Les nombres sont **écrits en toutes lettres** : un moteur de synthèse les
prononce autrement de façon imprévisible. Ne pas les « corriger » en repassant
aux chiffres — les sous-titres, eux, refont le chemin inverse et affichent `0.625`
là où la voix dit *zero point six two five*.

Deux mots à surveiller : **`McNemar`** s'écrit `Mc Nemar` dans le texte parlé,
sinon la voix tente un seul mot ; **`p`** s'écrit `p` et se prononce bien seul.

## Règle qui tient tout

**Rien d'affirmé qui ne soit montré à l'écran.** Chaque chiffre prononcé est
lisible dans le plan pendant qu'il est dit. C'est la règle du README appliquée à
la vidéo, et c'est aussi ce que le sujet impose : un outil dont la raison d'être
est de refuser les résultats invérifiables ne peut pas s'annoncer par une
promesse.

**Personne à l'image.** Voix de synthèse, capture d'écran, rien d'autre. Pas de
logo, pas de titre animé, pas de présentation de soi : la première phrase est le
problème.

## Les cinq segments

| segment | plan | mots | audio mesuré |
|---|---|---|---|
| s1 | 0:00 – 0:18 | 51 | 17,4 s |
| s2 | 0:18 – 0:52 | 88 | 33,7 s |
| s3 | 0:52 – 1:24 | 83 | 31,3 s |
| s4 | 1:24 – 1:55 | 72 | 30,2 s |
| s5 | 1:55 – 2:24 | 81 | 28,4 s |

**Total : 375 mots, 2 min 24.** Le règlement coupe à trois minutes
(« Judges are not required to watch beyond three minutes »), et la marge est
volontaire : la durée réelle de chaque piste est mesurée au montage, et c'est
elle qui fixe la longueur du plan, pas l'inverse.

Enregistrés **séparément**, un fichier par segment dans `voix/segN.mp3` : un
segment à refaire coûte trente secondes, pas trois minutes.

---

## s1 — le chiffre qu'on ne peut pas vérifier

**À l'écran** : la phrase du rapport, puis les trois défauts qu'elle cache.

> An optimisation report almost always looks like this: our build scores zero
> point six eight against the baseline's zero point six seven, at the same size.
> Three things are usually wrong with that sentence, and none of them is visible
> in the number. Wennab is four command-line tools that catch them.

## s2 — `twin` : les deux fichiers ne diffèrent pas par ce qu'on croit

**À l'écran** : la sortie réelle de `wennab twin` sur les deux GGUF de 1,16 Go,
puis celle du contrôle après rejeu de la carte des types.

> First: the two files differ by more than the thing under test. We rebuilt a
> two-billion-parameter model with our own importance matrix, and it came out
> twenty-three megabytes heavier than the file we meant to beat. It would have
> been easy to credit our calibration for the accuracy difference. Wennab twin
> reads the tensor type map off both files: the extra weight came from the
> publisher's map, not from us. Replay that map, rebuild, ask again — identical
> type maps, three hundred and twenty tensors, zero bytes apart.

## s3 — `guard` : un corpus qui contient son propre examen

**À l'écran** : `corpus`, puis `guard` qui passe, puis `guard` qui refuse avec le
code de sortie 1.

> Second: the calibration corpus contains the exam. A matrix calibrated on a text
> protects the weights that text activates, so evaluation prompts in the corpus
> improve the marks without improving the model. Writing the corpus yourself
> makes that more likely, not less. Wennab guard compares the two, eight words at
> a time. This one clears: the longest run shared with any of the seventeen exam
> texts is five words. Paste one exam back in and it refuses — sixty-nine
> collisions, exit code one.

## s4 — `paired` : deux totaux ne sont pas une comparaison

**À l'écran** : la sortie réelle de `wennab paired`, révélée bloc par bloc.

> Third: two totals are not a comparison. The standard error of a zero point six
> seven score over two hundred questions is three point three points. Wennab
> paired reads the per-question outcomes the harness already writes, pairs them
> by document identifier, and runs an exact Mc Nemar test. One hundred and
> ninety-six of two hundred answers identical. p equals zero point six two five.
> Four questions separate these models. Consistent with chance.

## s5 — le résultat nul, et la machine

**À l'écran** : les trois outils chronométrés sur le M1, puis la dernière phrase.

> That was our own work, and we published the null result. All of it was built
> and measured on an Apple M one with eight gigabytes, CPU only — the class of
> Arm hardware where quantisation decides whether a model runs at all. Three of
> the four tools run against files the repository ships, each in under a second.
> An honest null result took a day to establish and ten minutes to fake. That gap
> is the whole reason wennab exists.
