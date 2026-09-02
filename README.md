https://kafka2306.github.io/multiomics/

# multiomics

ARK Big Ideas 2026 の **Multiomics** を一次情報で検証するための正準repositoryです。

予測値と観測事実を分離し、sequencing economics、clinical trials、approvals / regulatory eventsを一次資料へ戻れる形で保持します。ARKのforecastは観測値として保存しません。

公開ページは、保存済みの正準データを読み込み、承認・臨床試験・シーケンシング費用を同じ「最新値」にまとめず、観測時点と一次情報を分けて表示します。データ取得に失敗した場合は古い値へfallbackしません。

## Canonical data

- data: [`data/multiomics-v1.json`](data/multiomics-v1.json)
- schema: [`schema/multiomics-v1.schema.json`](schema/multiomics-v1.schema.json)
- API index: [`api/v1/multiomics/index.json`](api/v1/multiomics/index.json)
- normalized metrics: [`api/v1/multiomics/metrics.json`](api/v1/multiomics/metrics.json)
- API builder: [`scripts/build_api.py`](scripts/build_api.py)
- ClinicalTrials.gov refresh: [`scripts/refresh_clinical_trials.py`](scripts/refresh_clinical_trials.py)
- NHGRI sequencing-cost refresh: [`scripts/refresh_sequencing_costs.py`](scripts/refresh_sequencing_costs.py)
- scheduled primary-source refresh: [`.github/workflows/refresh-primary-sources.yml`](.github/workflows/refresh-primary-sources.yml)

現在のpersisted primary-source observations:

- sequencing economics: NHGRIの公式Sequencing Costs 2022 Excel表。merge後の定期取得で2001年以降の全観測時点を保存する
- clinical trial: ClinicalTrials.gov `NCT06264180` (IGNYTE-3), Recruiting, Phase 3, sponsor Replimune, Inc.
- approval: FDA August 6, 2026 accelerated approval of vusolimogene oderparepvec-wtpg (Tudriqev) with nivolumab

`api/v1/multiomics/metrics.json` は上記canonical dataから決定的に生成するread-only viewです。downstreamはこのviewを参照し、事実の正本を複製しません。

## Primary sources

- NHGRI DNA Sequencing Costs: https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data
- ClinicalTrials.gov study: https://clinicaltrials.gov/study/NCT06264180
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- FDA approval notification: https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma

ClinicalTrials.govのデータとNHGRIのシーケンシング費用表は、同じ一次情報更新workflowで取得します。ClinicalTrials.govのstudy JSONとNHGRIの公式Excelは `data/raw/` にcontent-addressed snapshotとして保存し、SHA-256と原本pathを正準データへ残します。外部の二次APIや推定値へfallbackしません。

## Reproduce

```bash
python -m pip install xlrd==2.0.2
python scripts/refresh_clinical_trials.py --nct-id NCT06264180
python scripts/refresh_sequencing_costs.py
python scripts/build_api.py
python -m unittest discover -s tests -v
```

ClinicalTrials.govのJSON取得とAPI生成はPython標準ライブラリだけで動作します。NHGRIが配布する`.xls`原本の読み取りには`xlrd==2.0.2`を使用します。
