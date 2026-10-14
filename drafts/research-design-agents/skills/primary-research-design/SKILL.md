---
name: primary-research-design
description: Design a primary market research study that collects new data - surveys, in-depth interviews, focus groups, concept tests, pricing studies (Van Westendorp, Gabor-Granger, conjoint/MaxDiff), usability and diary studies, A/B or field experiments. Use when someone asks to "design a survey", "plan customer interviews", "test this concept", "validate demand", "find willingness to pay", "write a screener" or "how many respondents do we need".
---

# Primary research design

Primary research collects new data for this question. Design it so another
researcher could run it and get comparable results, and so its limits are
written down before any data arrives.

Start from a research brief (the `research-brief` skill). If secondary
evidence could answer the question more cheaply, say so first and record what
was checked in the evidence ledger.

## 1. Objectives to measures

For each decision in the brief, write:

- the research objective;
- the hypothesis or question, phrased so the data could contradict it;
- the measure that answers it, and the threshold that would change the decision.

An objective with no measure, or a measure with no decision, is cut.

## 2. Method choice

Pick the method from what must be learned, not from habit:

| Need | Usual method |
|---|---|
| Why, how, language, unmet needs | In-depth interviews, contextual inquiry |
| How many, how much, which segment | Quantitative survey |
| Which option wins | Monadic or sequential concept test; A/B test |
| Willingness to pay | Van Westendorp or Gabor-Granger for range; conjoint for trade-offs |
| Feature priority | MaxDiff, Kano |
| Behaviour over time | Diary study, panel, product analytics |
| Causal effect of a change | Randomized experiment; say plainly if only observational data exists |

State why the rejected methods were rejected. Self-reported intent overstates
behaviour: never present stated purchase intent as forecast demand without a
calibration step, and say which one.

## 3. Population and sampling

- Target population, defined so a screener can apply it.
- Sampling frame and its coverage gaps (who the frame misses).
- Sampling method: probability, quota, convenience or snowball, and what each
  means for generalizing.
- Sample size with the arithmetic shown: for a proportion,
  n = z² · p(1−p) / e², adjusted for finite population and design effect;
  for qualitative work, the saturation rationale (typically 12 to 30
  interviews per distinct segment) stated as a judgement, not a rule.
- Expected incidence and response rates, labelled as assumptions unless sourced.
- Quotas, weighting plan and the variables weighting will use.

## 4. Instruments

- Screener: qualifying and terminating questions, and attention checks.
- Survey or discussion guide, in order, with each question mapped to an objective.
- Review each item for leading wording, double-barrelled questions, loaded
  terms, missing "don't know" or "none" options, unbalanced scales, order
  effects (randomize where order is not meaningful), and recall periods longer
  than people can report.
- Pilot plan: who, how many, what would trigger a revision.

## 5. Analysis plan (written before fieldwork)

Primary metrics, cuts and segments, statistical tests and the minimum
detectable difference, how missing data and speeders are handled, how
qualitative data will be coded, and which comparisons are exploratory.

## 6. Ethics, consent and data

- Consent wording, incentives, and the right to stop.
- Personal data collected, why each item is needed, retention and deletion.
- Special categories (health, children, financial, biometric, precise
  location): flag for privacy or legal review. Give issue-spotting questions,
  never a compliance conclusion. Do not ask for identifiable health
  information unless the owner confirms the environment and handling are
  approved for it.
- Jurisdictions where respondents live, since recruitment and consent rules
  follow the respondent.

## 7. Output

1. Study summary: objective, method, sample, timeline, budget drivers.
2. Objectives-to-measures table.
3. Sampling plan with arithmetic.
4. Instruments (screener, questionnaire or guide).
5. Analysis plan.
6. Risks and limits: biases this design cannot remove.
7. Decisions for a human owner: budget, panel vendor, incentive, reviews.

Costs and timelines are estimates. Label any vendor price as a quoted or list
price with its date, never as a cost incurred.
