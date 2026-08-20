# multiomics

ARK Big Ideas 2026 の **Multiomics** を一次情報で検証するための正準repositoryです。

予測値と観測事実を分離し、sequencing economics、clinical trials、approvals / regulatory eventsを一次資料へ戻れる形で保持します。ARKのforecastは観測値として保存しません。

## Canonical data

- data: [`data/multiomics-v1.json`](data/multiomics-v1.json)
- schema: [`schema/multiomics-v1.schema.json`](schema/multiomics-v1.schema.json)
- API index: [`api/v1/multiomics/index.json`](api/v1/multiomics/index.json)
- normalized metrics: [`api/v1/multiomics/metrics.json`](api/v1/multiomics/metrics.json)
- API builder: [`scripts/build_api.py`](scripts/build_api.py)
- ClinicalTrials.gov refresh: [`scripts/refresh_clinical_trials.py`](scripts/refresh_clinical_trials.py)
- scheduled refresh: [`.github/workflows/refresh-clinical-trials.yml`](.github/workflows/refresh-clinical-trials.yml)

現在のpersisted primary-source observations:

- sequencing economics: NHGRI 2021 `0.006 USD/Mb` and approximately `562 USD/human genome`
- clinical trial: ClinicalTrials.gov `NCT06264180` (IGNYTE-3), Recruiting, Phase 3, sponsor Replimune, Inc.
- approval: FDA August 6, 2026 accelerated approval of vusolimogene oderparepvec-wtpg (Tudriqev) with nivolumab

`api/v1/multiomics/metrics.json` は上記canonical dataから決定的に生成するread-only viewです。`investor2` などのdownstreamはこのviewを参照し、事実の正本を複製しません。

## Primary sources

- NHGRI DNA Sequencing Costs: https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data
- NHGRI Megabase reference containing the persisted 2021 values: https://www.genome.gov/genetics-glossary/Megabase-Mb
- ClinicalTrials.gov study: https://clinicaltrials.gov/study/NCT06264180
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- FDA approval notification: https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma

ClinicalTrials.govのデータは月曜から金曜に更新されるため、workflowは公式API v2から平日に再取得します。取得したstudy JSONは `data/raw/clinicaltrials/` にcontent-addressed snapshotとして保存し、そのSHA-256とAPI `dataTimestamp` をderived recordへ残します。外部の二次APIや推定値へfallbackしません。

## Reproduce

```bash
python scripts/refresh_clinical_trials.py --nct-id NCT06264180
python scripts/build_api.py
python -m unittest discover -s tests -v
```

runtime dependencyはPython標準ライブラリのみです。

## Project evidence

- ARK 2026 cross-repository plan: https://github.com/KAFKA2306/investor2/issues/111
- repository responsibility map: https://github.com/KAFKA2306/investor2/issues/110
- canonical materialization: https://github.com/KAFKA2306/multiomics/issues/1
