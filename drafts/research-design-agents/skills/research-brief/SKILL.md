---
name: research-brief
description: Open or update a research brief before any market research, research design, or evidence review begins. Use when someone asks a research question, asks to "research", "size", "study", "survey", "test a concept", "scope a study", or brings a decision that needs evidence, and no versioned brief exists yet. Records the question, the decision it informs, jurisdictions, timeframe, data sensitivity, scope limits, reviewers and output format.
---

# Research brief

Every research project starts from a brief. The brief is the specification:
work outside it is out of scope until the brief changes, and a change is a new
version, never a silent edit.

## Fields

Record each field. Write "not given" rather than leaving one blank.

| Field | What to capture |
|---|---|
| Project and domain | Who the work is for and the market or category |
| Research question | One sentence, narrow enough to be answered |
| Decision supported | The decision this informs and who owns it |
| Intended users and affected people | Who uses the output; whose data or interests are involved |
| Jurisdictions | Countries, states or regions whose law or market applies |
| Time period | The period the evidence must cover, and how fresh it must be |
| Data involved | Personal, health, financial, children's or other regulated data |
| Intended product use | How the findings will be used (pitch, launch, pricing, filing) |
| Out of scope | Questions this project will not answer |
| Required or excluded sources | Sources the owner insists on or forbids |
| Reviewers and gates | Who must review before the output is used |
| Output format | Report, deck, ledger only, study plan, instrument |
| Date of research | Today's date; the brief's version starts at v1 |

## Steps

1. Fill what the request already answers. Do not ask for those again.
2. For each missing field, decide whether its absence could change a legal,
   privacy, safety or decision-critical conclusion.
   - If it could: ask, in one message, only those questions. Do not draw a
     firm conclusion until they are answered.
   - If it could not: write a bounded assumption ("Assumed: US only, 2023 to
     present") in the field and mark it `ASSUMPTION`.
3. Restate the research question in one sentence and the decision it informs.
   If the question cannot inform the stated decision, say so before starting.
4. Write the brief at the top of the output (or to `brief.md` if files are
   being kept) with a version line: `Brief v1 · YYYY-MM-DD`.

## Changing a brief

When the question, assumptions, sources or scope change, write `Brief v2`
with a change line naming what changed and why. Keep v1. List every claim in
the ledger that the change puts in doubt so it can be rechecked.
