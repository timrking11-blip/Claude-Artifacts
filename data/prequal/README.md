# Prequalification request queue

Each JSON file in `requests/` asks the account-research agents for one
prequalification proposal. Committing a file here starts the
**Prequalification proposal** GitHub Actions workflow on that branch
(`.github/workflows/prequal-proposal.yml`). The workflow researches the
account and writes `data/proposals/<account>-<date>.{json,md}`. It then marks
the request done by adding `proposal_id`, `proposal_path` and `completed_at`,
and commits both files back.

```json
{
  "account": "Acme Mechanical",
  "domain": "acmemechanical.com",
  "request_text": "The LinkedIn message or inbound request, verbatim. Leave empty for a proactive note.",
  "lead_source": "linkedin",
  "requested_at": "2026-09-24",
  "crm_account_id": "crm_20260924_xxxxxx"
}
```

- `account` or `domain` is required; give both when you have them.
- `lead_source: "linkedin"` means the Monday CRM push tags the account
  `source: linkedin` and ticks its pre-qual box, if neither is set yet.
- `crm_account_id` is optional and for reference only. The CRM push matches
  accounts by domain.

The agents read the ledger, fetch the company's site from the GitHub runner,
and research the open web with Claude's server-side web search and fetch tools.
The proposal follows SMI's proposal shape in short form, with no prices:
engagement summary, what we heard, the problem in front of the account,
approach, qualifying questions, next step and sources. The runner needs the
`ANTHROPIC_API_KEY` repository secret.
