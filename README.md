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
- sequencing cost analysis: [`api/v1/multiomics/sequencing-cost-analysis.json`](api/v1/multiomics/sequencing-cost-analysis.json)
- API builder: [`scripts/build_api.py`](scripts/build_api.py)
- sequencing cost analysis builder: [`scripts/analyze_sequencing_costs.py`](scripts/analyze_sequencing_costs.py)
- ClinicalTrials.gov refresh: [`scripts/refresh_clinical_trials.py`](scripts/refresh_clinical_trials.py)
- FDA oncology approval refresh: [`scripts/refresh_fda_approvals.py`](scripts/refresh_fda_approvals.py)
- NHGRI sequencing-cost refresh: [`scripts/refresh_sequencing_costs.py`](scripts/refresh_sequencing_costs.py)
- scheduled primary-source refresh: [`.github/workflows/refresh-primary-sources.yml`](.github/workflows/refresh-primary-sources.yml)

現在のpersisted primary-source observations:

- sequencing economics: NHGRIの公式Sequencing Costs 2022 Excel表。2001年9月〜2022年5月の観測を保存
- clinical trial: ClinicalTrials.gov `NCT06264180` (IGNYTE-3), Recruiting, Phase 3, sponsor Replimune, Inc.
- approvals: FDA Oncology Center of Excellenceの承認通知一覧から最新の保存済み承認を取得し、個別のFDA承認ページを一次情報として保存

`api/v1/multiomics/metrics.json` は上記canonical dataから決定的に生成するread-only viewです。`api/v1/multiomics/sequencing-cost-analysis.json` はNHGRIの実観測から長期低下率を再計算するread-onlyの派生結果で、因果効果は主張しません。downstreamはこれらを参照し、事実の正本を複製しません。

## Primary sources

- NHGRI DNA Sequencing Costs: https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data
- ClinicalTrials.gov study: https://clinicaltrials.gov/study/NCT06264180
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- FDA Oncology approval notifications: https://www.fda.gov/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications

ClinicalTrials.gov、FDA、NHGRIの一次情報は、同じ一次情報更新workflowで取得します。ClinicalTrials.govのstudy JSON、FDA承認詳細ページのHTML、NHGRIの公式Excelは `data/raw/` にcontent-addressed snapshotとして保存し、取得したFDA承認にはSHA-256と原本pathを正準データへ残します。外部の二次APIや推定値へfallbackしません。FDAの承認ページが必要項目へ解析できない場合は更新を停止し、既存値を新しい承認として扱いません。

## Reproduce

```bash
python -m pip install xlrd==2.0.2
python scripts/refresh_clinical_trials.py --nct-id NCT06264180
python scripts/refresh_fda_approvals.py
python scripts/refresh_sequencing_costs.py
python scripts/build_api.py
python scripts/analyze_sequencing_costs.py
python -m unittest discover -s tests -v
```

ClinicalTrials.govのJSON取得、FDA承認ページのHTML取得、API生成はPython標準ライブラリだけで動作します。NHGRIが配布する`.xls`原本の読み取りには`xlrd==2.0.2`を使用します。
