# wennab

**Prove that a model optimisation did something — or that it did not.**

Four command-line tools for anyone quantising or recalibrating a model to run on an Arm laptop,
phone or single-board machine. They do not quantise anything and they do not run a model: you keep
`llama-quantize` and `lm-evaluation-harness`. They exist for the part in between, where
optimisation results quietly turn into fiction.

```bash
pip install git+https://github.com/benewende-dev/wennab
```

---

## The problem, stated plainly

An optimisation report almost always looks like this: *"our build scores 0.68 against the
baseline's 0.67 at the same size."* Three things are usually wrong with it, and none of them is
visible in the number.

**The two files differ by more than the thing under test.** We rebuilt a 2 B model with our own
importance matrix and it came out 23 MB heavier than the file we meant to beat. It would have been
easy to credit our calibration for the accuracy difference. A tensor-by-tensor check showed the
extra weight came from somewhere else entirely — the reference's publisher had used a different
**type map**, dropping `attn_qkv` to IQ4_XS and lifting `ssm_out`, `ssm_alpha`, `ssm_beta`, on
every layer except those congruent to 3 modulo 4. Two causes, one number, and no measurement taken
afterwards could have separated them.

**The calibration corpus contains the exam.** A matrix calibrated on a text protects the weights
that text activates. Put your evaluation prompts in the corpus and the rebuild improves its own
marks without improving the model. Writing the corpus yourself makes this *more* likely, not less:
the templates and the test prompts come from the same hand, the same register, the same example
cities. Ours collided on eight consecutive words. We only knew because we checked.

**Two totals are not a comparison.** The standard error of a 0.67 score over 200 questions is 3.3
points. A four-question gap is inside the noise, and reporting it as an improvement is the most
common way a null result gets published as a win.

`wennab` is the four instruments that catch these.

---

## `wennab twin` — is this even a valid pair?

Reads the tensor type map off two GGUF files and tells you whether they differ by anything other
than their values.

```console
$ wennab twin reference.gguf candidate.gguf
4 type group(s) differ — these files are NOT a valid pair

  tensor                   candidate → reference  layers          bytes
  attn_qkv.weight               Q5_K → IQ4_XS    18 of them    -35,389,440
  ssm_alpha.weight            IQ4_XS → Q8_0      18 of them       +313,344
  ssm_beta.weight             IQ4_XS → Q8_0      18 of them       +313,344
  ssm_out.weight              IQ4_XS → Q5_K      18 of them    +11,796,480

  reference 1,162,034,432 B
  candidate 1,185,000,704 B
  difference +22,966,272 B

Measuring these two against each other mixes the type map with whatever
else you changed. Rebuild the candidate with:
  wennab twin reference.gguf --emit types.txt
  llama-quantize --imatrix yours.imatrix --tensor-type-file types.txt \
      source-BF16.gguf candidate.gguf <TYPE>
```

Then replay the reference's map so the two builds differ by one thing only:

```console
$ wennab twin reference.gguf --emit types.txt
$ llama-quantize --imatrix yours.imatrix --tensor-type-file types.txt \
      source-BF16.gguf candidate.gguf IQ4_XS

$ wennab twin reference.gguf candidate.gguf
identical type maps (320 tensors)
  reference 1,162,034,432 B
  candidate 1,162,034,432 B
  difference +0 B

These two files differ only in tensor *values*. Any measured difference between them
is attributable to whatever produced those values.
```

That second run is the one that makes everything downstream mean something.

Both blocks are the command's own output against the two 1.16 GB files of the case study —
the published build and our rebuild — with nothing removed and the paths shortened. They are
the one thing here you cannot rerun from a clone: a repository has no business shipping a
gigabyte of weights.

## `wennab corpus` — a calibration corpus you can reproduce and read

Generates a corpus for a register from a registry of hand-written templates, under a fixed seed.
No real documents, so nothing unpublishable; no scraped legal text, so no licensing fog.

```console
$ wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt
  184 documents, 180,329 bytes, 27,895 words
  4-gram diversity : 0.495
  en : 81/184 documents (44 %)
  fr : 103/184 documents (56 %)
```

Diversity is printed, not assumed, because it is the ceiling on what this method can do.
**Hand-written text is a fixed quantity: lengthening the corpus only repeats it**, and a matrix
estimated on repetition over-weights whatever repeats. Measured on ours — 330 kB → 0.387,
240 kB → 0.439, 180 kB → 0.495 — so we shipped the shortest of the three, which still gives 88
chunks against the 80 of the calibration we were replacing.

`registries/enterprise-fr.toml` ships as a worked example: 18 genres of francophone West African
business document — supply contracts, minutes, service memos, quotations, tenders, acceptance
records, HR postings, budget analysis — in French and English, spread across 18 cities so the
matrix does not learn one town.

## `wennab guard` — refuse a corpus that contains its own exam

**The seventeen exam texts ship in this repository**, so this runs from a clone with nothing to
install and nothing to download: the two published evaluation prompts and the fifteen in-domain
control tasks, in [`case-study/exams/`](case-study/exams/).

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

The longest shared run is printed on a pass too, because a clean result at n=8 does not tell you
whether you cleared it by a mile or by one word. Here it is five words of ordinary administrative
formula, and that is the answer you want: not zero — zero would suggest the corpus is not in the
register — but nowhere near eight.

It did not always pass. An earlier draft of the memo template collided with `note-conges` on eight
consecutive words; it was rewritten before anything was computed, which is why the corpus shipped
here clears it. That episode is recorded in [`case-study/`](case-study/#2-the-contamination-check-caught-a-real-fault).

To watch the refusal for yourself, put an exam into the corpus and ask again:

```console
$ cat corpus.txt case-study/exams/note-conges.txt > contaminated.txt
$ wennab guard contaminated.txt --against case-study/exams/*.txt
  ✗ note-conges.txt                    max ≥40 words  ← 69 collision(s): « 04 le chef de service dispose de 5 »

✗ 69 shared 8-gram(s). Fix the corpus before computing anything:
  a corpus containing its own exam marks its own paper.
$ echo $?
1
```

Exit code 1 on a collision, so it drops straight into a pipeline.

Reading **zero** exam text is also reported as a failure, not a pass — and that one you can also
run, by handing it the per-question outcomes instead of the prompts:

```console
$ wennab guard corpus.txt --against case-study/results/reference-arc_easy-200.jsonl
exams  : 0 text(s)

✗ no exam text was read. Nothing was compared, so this is not a pass.
```

A wrong path, or a results dump handed over instead of the prompts, produces zero collisions — and
a tool that answered "clean" there would be lying in exactly the way this one exists to prevent.

## `wennab paired` — compare question by question

Reads the `samples_*.jsonl` that `lm_eval --log_samples` already writes, pairs by document id, and
runs an exact McNemar test.

```console
$ wennab paired runs/reference runs/candidate
200 questions, paired by document id

  reference               134/200  (0.670)
  candidate               136/200  (0.680)

  agree                   196/200  (98%)
  reference only right : 1
  candidate only right : 3

  p = 0.625

  Consistent with chance. 4 question(s) separate these
  models — report that number, not the difference of the totals.
```

Paired by document id rather than by position: two runs can order their documents differently, and
pairing by position then compares unrelated questions while looking perfectly healthy.

---

## The case study: it told us our own work was worthless

These tools were not written to prove a point. They were written because we were recalibrating a
2 B model's importance matrix for francophone enterprise documents, and we could not tell whether
it had worked.

With `twin`, we built a control that matched the reference to **32 bytes** — the length of a
filename in the metadata — with an identical peak RSS across three runs. With `guard`, we found and
removed a real eight-word collision between our corpus and our own test set. Then `paired` gave the
answer:

> **196 of 200 answers identical. p = 0.625.**

At equal size, speed and memory, recalibrating the importance matrix did not change what the model
decides. We shipped the original weights and published the null result. Full numbers, protocol and
the reasoning behind each control: [`case-study/`](case-study/).

An honest null result took a day to establish and would have taken ten minutes to fake. That gap
is the whole reason this repository exists.

---

## Arm

Everything above was built and measured on an **Apple M1, 8 GB, CPU only** — an Arm machine under
exactly the constraint these tools are for. The target is the class of hardware where quantisation
choices actually decide whether a model runs at all: Arm laptops, phones, tablets, boards.

Three practical notes from that machine, none of which we expected:

- **Compute the matrix from BF16, but know the price.** Requantising an already-quantised file
  stacks two roundings and measures that instead of your change. But 3.8 GB of BF16 does not fit in
  8 GB of RAM alongside anything else: `llama-imatrix` ran at **12 % CPU** — waiting on the SSD, not
  computing — 12.6 s per chunk, 18 minutes for 88 chunks. On this class of machine the bottleneck
  is paging, not precision. Starting from Q8_0 (2 GB, fits) is the first thing to try.
- **Measure with nothing else running.** Closing a browser moved swap from 9.3 GB to 992 MB on the
  same machine. Any throughput number taken without doing that measures your desktop.
- **Three runs, take the median.** We recorded 34.3 t/s and 31.2 t/s on the *same file* two weeks
  apart on a fanless laptop. Compare builds measured the same day, alternating, or you are
  measuring thermal drift.

`twin`, `guard` and `paired` all run in well under a second and hold nothing large in memory, so
they belong on the device rather than on a workstation you have to sync with.

## Install and run

```bash
pip install git+https://github.com/benewende-dev/wennab
wennab --help

# or from a clone, no install:
git clone https://github.com/benewende-dev/wennab && cd wennab
python -m wennab twin reference.gguf candidate.gguf
python -m pytest tests/          # 32 tests, well under two seconds
```

**Three of the four run against files this repository ships**, so you can see real
output before you quantise anything:

```bash
python -m wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt
python -m wennab guard corpus.txt --against case-study/exams/*.txt
python -m wennab paired case-study/results/reference-arc_easy-200.jsonl \
                        case-study/results/candidate-arc_easy-200.jsonl
```

All three reproduce the numbers printed above exactly — the corpus table, the
contamination check and the null result are not transcriptions. Only `twin` needs
something this repository cannot ship: two GGUF files.

Python 3.11+. `gguf` is the only dependency and only `twin` needs it — the other three read plain
text and JSON, deliberately, so they run on anything.

Tested on `aarch64` (Apple M1, macOS) and portable to any Arm64 Linux: nothing here compiles, and
nothing here calls a GPU.

## Licence

Apache 2.0.
