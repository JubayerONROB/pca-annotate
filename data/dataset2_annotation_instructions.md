# How to label `dataset2_annotation_sheet.csv` (Task 1.5)

200 rows. Fill the **`label`** column with `1` or `0`. Use **`notes`** freely — the
disagreement analysis is only as good as the notes on the cases you found hard.

**Do not open `results/dataset2_annotation_key.json` until you are finished.** It holds
the proxy labels. Reading it first destroys the blindness that makes κ meaningful.

---

## The question you are answering

For each row, you see a moment of silence in a meeting. You know who the wearer is,
what was said in the five turns before the silence, what the wearer said next, and a
summary of what the wearer has talked about in their earlier meetings.

> **Would a private 1–3 word hint, delivered to the wearer during this silence, have
> helped them?**
>
> Label `1` if the wearer's next turn surfaces something from their own history that
> was **not** available in the immediate conversation — a name, a system, a technical
> term, a place, a prior result — such that a timely reminder would have been useful.
>
> Label `0` otherwise.

Judge the **opportunity**, not the wearer's fluency. A hint can be useful even if the
wearer recalled the item without visible difficulty.

## What counts as `1`

- The wearer names a person, project, corpus, tool, place, or technical term that they
  have discussed before and that nobody has just mentioned.
- The wearer visibly reaches for something ("um, the… the Aurora thing") and lands on
  it.
- The wearer supplies a fact only they would hold from a prior meeting.

## What counts as `0`

- The wearer's next turn is backchannel or procedural: "Yeah", "Right", "OK, so",
  "Let's move on".
- Everything the wearer says was already on the table in the preceding turns — a hint
  would only repeat what everyone just heard.
- The wearer speaks about the present moment only (the room, the recording, the agenda).
- The wearer's turn has no words at all (some rows say so explicitly).
- The content is generic enough that no specific hint could be constructed.

## Borderline cases — please note them

- **Recently mentioned.** If the item appeared a few turns earlier, lean `0`, and note
  it. This is exactly the *K* parameter and disagreements here tell us to retune it.
- **One-off.** If the item looks like something the wearer mentions rarely rather than
  a recurring part of their work, lean `0` and note it. This probes *f_min*.
- **Wrong item.** If the wearer clearly retrieves something, but the obvious hint would
  be a *different* phrase than what the profile terms suggest, label `1` and note it —
  that is a hint-selection problem, not a gating problem, and they should not be
  conflated.

## The profile column

`wearer_profile_terms` lists the wearer's 20 most frequent terms from **earlier
meetings only**, with counts. It is the same view for positive and negative rows and
is deliberately *not* filtered to the current moment — if it only showed matching
terms it would give the answer away. Treat it as background on who this person is and
what they work on.

## Practical notes

- Rows are shuffled; positives and negatives are interleaved with no pattern.
- The sample is 100 proxy-positive and 100 proxy-negative, but **you should not aim for
  a 50/50 split.** Label each row on its merits; a skew in your labels is a finding.
- Rows come from all three splits and all eight ICSI meeting series.
- If a row is genuinely undecidable from what is shown, leave `label` blank and say why
  in `notes`. Blank rows are dropped from κ and reported as a count, which is far more
  honest than a coin flip.

## After you finish

Hand it back and I will compute Cohen's κ against the proxy, a 2×2 confusion matrix,
and a qualitative breakdown of every disagreement.

Interpretation agreed in the spec: **κ above ~0.6 is defensible; below ~0.4 means the
operationalization needs rethinking** and I will say so plainly rather than proceed.
If we retune *K*, *f_min*, or the extractor in response, we re-validate on a **fresh**
200 — `build_annotation_sheet.py --exclude-key` guarantees no marker is reused.

### One caveat about what this κ covers

Negatives were sampled only from markers where the wearer actually speaks within the
horizon. 68 % of the corpus's negatives are markers where the wearer never responds —
negative by construction, and you would agree with every one of them. Including them
would have inflated κ toward 1 without testing anything. So this κ measures agreement
**only where the proxy does non-trivial work**, which makes it a conservative estimate
of agreement on the full corpus. That is the number worth reporting, and the paper
should state this sampling choice explicitly.
