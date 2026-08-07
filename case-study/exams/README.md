# The seventeen exam texts

These are the texts the recalibrated model was graded on. They ship here for one
reason: `wennab guard` is worthless as a claim and only worth something as a
command you can run. Every collision figure in this repository comes from these
files.

```bash
wennab corpus registries/enterprise-fr.toml --bytes=180000 > corpus.txt
wennab guard corpus.txt --against case-study/exams/*.txt
```

| files | what they are |
|---|---|
| `published-tp_001.txt`, `published-tp_002.txt` | the two evaluation prompts published with the submission the model was built for — a supplier-contract extract to analyse, and an internal note to summarise in three bullets |
| the other fifteen | in-domain control tasks written for the same evaluation: five to summarise, five to draft, five to analyse, French and English, across eight cities |

Each file holds the prompt exactly as it was fed to the model — the instruction
and the source document, nothing added, nothing removed. The file name is the
task's own identifier.

**They are the exams, not the answers.** Nothing here records what any model
replied. Per-question outcomes for the 200-question `arc_easy` run are in
[`../results/`](../results/), and `guard` deliberately refuses to accept those as
exam texts — a results dump collides with nothing, and calling that a pass is the
one lie this tool exists to prevent.

## Why fifteen controls and not one

The evaluation generates hidden prompts inside the domain, specifically to catch
a model tuned to the published ones. The defence against that is not guessing —
it is breadth. Fourteen kinds of business writing, two languages, eight cities
and several tasks with no place named at all. A control set pinned to one city or
one sector would measure exactly the fault it is meant to rule out.

That breadth is also what makes the contamination check non-trivial: fifteen
in-register texts written by the same hand as the corpus templates are far more
likely to collide than any outside text would be. One of them did.
