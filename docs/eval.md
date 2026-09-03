# Evaluation

Local-only repo: no self-PRs. Score Harpy on labelled **external** public PRs.

```bash
make review REPO=<owner/name> PR=<n>
```

## Metrics

- Top-3 recall: human-important logical changes in the first 3 rows
- Top-5 recall
- Noise reduction: lockfile/generated/snapshot not in the top 5 unless unexpected
- Grouping quality: one product decision → one logical change

## Labels

For each PR record:

| PR | Important changes | Noise | Unexpected | Top-5 recall |
|---|---|---|---|---|
| _example acme/app#1842_ | org-admin delete | lockfile regen | none | _pending_ |

Fill rows after real runs. Do not tune weights until at least five labelled PRs exist.
