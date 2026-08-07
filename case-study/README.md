# Case study — recalibrating a 2 B model, and finding nothing

Every tool in this repository exists because of a question we could not answer: had our
recalibration worked? This is the full record of how we found out that it had not.

**Machine.** Apple M1, 8 GB, integrated graphics, macOS. CPU only (`-ngl 0`) throughout, which is
the constraint the target hardware imposes anyway.

**Model.** Qwen3.5-2B, 1.88 B parameters, GGUF IQ4_XS, running under llama.cpp.

**The change under test.** The shipped file is an importance-matrix quantisation whose calibration
is inherited — generic English, 80 chunks, computed by a third party. We rebuilt the matrix on a
corpus of francophone enterprise documents, the register the model was actually for.

---

## 1. The corpus

Generated with `wennab corpus` from
[`registries/enterprise-fr.toml`](../registries/enterprise-fr.toml): 184 documents, 180 kB,
56 % French, 18 genres across 18 West and Central African cities, fixed seed.

Size was chosen by measurement, not preference. Hand-written text is a fixed quantity, so
lengthening the corpus only repeats it. Reproduce the table with
`wennab corpus registries/enterprise-fr.toml --bytes=N --seed=20260803`:

| corpus size | documents | 4-gram diversity |
|---|---|---|
| 330 kB | 338 | 0.387 |
| 240 kB | 246 | 0.439 |
| **180 kB** | **184** | **0.495** |

We kept the shortest, which still yields 88 chunks of 512 tokens against the 80 of the calibration
being replaced. A matrix estimated on repetition over-weights whatever repeats.

## 2. The contamination check caught a real fault

`wennab guard` compared the corpus against all 17 evaluation prompts — the 2 published test
prompts and 15 in-domain control tasks. All seventeen are in [`exams/`](exams/), so this step
is the one part of the case study that reruns end to end from a clone:

```console
$ wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt
$ wennab guard corpus.txt --against case-study/exams/*.txt
corpus : 28,291 words, 17,880 distinct 8-grams
exams  : 17 text(s)

longest shared run, all exams : 5 words (note-conges.txt)
  « note de service n 2026 »

✓ no shared 8-gram. The corpus and the evaluation sets are disjoint,
  so what you measure after recalibration is a real effect.
```

It did not pass the first time. An earlier draft of the memo template shared **eight consecutive
words** with `note-conges.txt` — the sentence giving a manager five working days to approve or
refuse a leave request — because the template and the task had been written by the same person, in
the same register, weeks apart. Neither text was copied from the other; that is the point. The
template was rewritten and the longest shared run fell to five words, an ordinary administrative
formula. Only then did we compute anything.

The corpus that ships is the rewritten one, so the collision no longer reproduces — a fixed fault
does not. What reproduces is the check, in both directions: paste `exams/note-conges.txt` back into
the corpus and `guard` refuses it with exit code 1, quoting the run word for word.

## 3. The first rebuild was not comparable, and it looked good

The rebuilt file came out **23 MB heavier** than the reference. `wennab twin` said why:

| tensor | candidate → reference | layers | bytes |
|---|---|---|---|
| `attn_qkv.weight` | Q5_K → IQ4_XS | 18 | −35,389,440 |
| `ssm_alpha.weight` | IQ4_XS → Q8_0 | 18 | +313,344 |
| `ssm_beta.weight` | IQ4_XS → Q8_0 | 18 | +313,344 |
| `ssm_out.weight` | IQ4_XS → Q5_K | 18 | +11,796,480 |

Not our calibration — the publisher's **type map**, applied to every layer except those congruent
to 3 modulo 4. Against that file our rebuild scored **+4 points of `arc_easy` and +3 criteria out
of 81** on the domain control. Published as-is, that would have been a lie of omission: two causes
in one number.

## 4. Two more builds, so that only one thing varies

| build | type map | calibration |
|---|---|---|
| **shipped** | publisher's | inherited, generic English |
| **control** | `llama-quantize` default | inherited |
| **rebuild v1** | `llama-quantize` default | enterprise fr/en |
| **rebuild v2** | publisher's, replayed via `twin --emit` | enterprise fr/en |

`v2` lands **32 bytes** from the shipped file — the length of a filename recorded in the metadata —
with an identical peak RSS on all three runs. Between those two, only the calibration differs.

## 5. Throughput and memory: no effect

Three alternating runs on an otherwise idle machine, median reported.

| build | throughput | three runs | peak RSS |
|---|---|---|---|
| shipped | 34.99 t/s | 34.4 / 35.0 / 35.0 | 1 787 MB |
| control | 33.58 t/s | 32.9 / 33.6 / 34.2 | 1 937 MB |
| rebuild v1 | 33.46 t/s | 33.5 / 34.1 / 33.2 | 1 997 MB |

Control against rebuild: **0.12 t/s**, smaller than the spread between three runs of the same file.
Expected — calibration changes rounded values, not file structure.

Separate series, same day, six alternating measurements:

| build | throughput | three runs | peak RSS |
|---|---|---|---|
| shipped | 34.78 t/s | 35.4 / 34.6 / 34.8 | 1 868 MB (all three) |
| rebuild v2 | 34.41 t/s | 34.4 / 34.4 / 34.9 | 1 868 MB (all three) |

## 6. Accuracy: the totals, then what they hide

| build | `arc_easy`, 200 q | domain control 1.00 / 1.05 / 1.10 | fabricated numbers |
|---|---|---|---|
| shipped | 0.670 | 91 / 90 / 91 % | 0 |
| control | 0.640 | 92 / 90 / 87 % | 1 |
| rebuild v1 | 0.680 | 92 / 93 / 93 % | 0 |
| rebuild v2 | 0.680 | 93 / 88 / 89 % | 0 |

Read quickly, this argues for the recalibration: against its exact control it gains four points and
makes the lot's only fabricated amount disappear — on one summarising task the control wrote
42,000,000 and 52,000,000 where the source says 41,500,000.

Read properly, it proves nothing. **Four points over two hundred questions is eight answers**, for
a standard error of 3.4. And on the domain control `v2` gains two points at penalty 1.00 and loses
two at 1.05: an effect that flips sign with an unrelated setting is the signature of chance.

## 7. What settled it

```console
$ wennab paired runs/shipped runs/rebuild-v2
200 questions, paired by document id

  reference   134/200  (0.670)
  candidate   136/200  (0.680)

  agree       196/200  (98%)
  reference only right : 1
  candidate only right : 3

  p = 0.625
```

Per-question outcomes for both runs are in [`results/`](results/), so this table can be
recomputed rather than believed.

**Four questions out of two hundred separate the two files.** At equal size, speed and memory,
recalibrating the importance matrix on the target register does not change what the model decides.

## 8. Decision

We kept the shipped weights. The rebuild is neither demonstrably better nor worse, and swapping a
file that has already been downloaded, measured three times and cited for one that is statistically
indistinguishable would be motion, not progress.

## What this does not show

That importance-matrix calibration is pointless in general. One corpus, one model, one format, 200
questions, 15 tasks. An authentic corpus rather than a generated one, or a format more aggressive
than IQ4_XS — where fewer bits remain to allocate, so more is at stake in allocating them well —
could behave differently. What is measured here is that **on this file, this lever is flat**.

That is a smaller claim than we set out to make. It is the one the measurements support.
