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
- Drugs@FDA oncology crosswalk: [`api/v1/multiomics/drugsfda-oncology-crosswalk.json`](api/v1/multiomics/drugsfda-oncology-crosswalk.json)
- Drugs@FDA / Orange Book product identity crosscheck: [`api/v1/multiomics/fda-product-identity-crosscheck.json`](api/v1/multiomics/fda-product-identity-crosscheck.json)
- sequencing cost analysis: [`api/v1/multiomics/sequencing-cost-analysis.json`](api/v1/multiomics/sequencing-cost-analysis.json)
- Drugs@FDA source manifest: [`data/drugsfda-source.json`](data/drugsfda-source.json)
- Orange Book source manifest: [`data/orange-book-source.json`](data/orange-book-source.json)
- API builder: [`scripts/build_api.py`](scripts/build_api.py)
- sequencing cost analysis builder: [`scripts/analyze_sequencing_costs.py`](scripts/analyze_sequencing_costs.py)
- ClinicalTrials.gov refresh: [`scripts/refresh_clinical_trials.py`](scripts/refresh_clinical_trials.py)
- Drugs@FDA refresh: [`scripts/refresh_drugsfda.py`](scripts/refresh_drugsfda.py)
- Orange Book refresh: [`scripts/refresh_orange_book.py`](scripts/refresh_orange_book.py)
- FDA oncology approval refresh: [`scripts/refresh_fda_approvals.py`](scripts/refresh_fda_approvals.py)
- NHGRI sequencing-cost refresh: [`scripts/refresh_sequencing_costs.py`](scripts/refresh_sequencing_costs.py)
- scheduled primary-source refresh: [`.github/workflows/refresh-primary-sources.yml`](.github/workflows/refresh-primary-sources.yml)

現在のpersisted primary-source observations:

- sequencing economics: NHGRIの公式Sequencing Costs 2022 Excel表。2001年9月〜2022年5月の観測を保存
- clinical trial: ClinicalTrials.gov `NCT06264180` (IGNYTE-3), Recruiting, Phase 3, sponsor Replimune, Inc.
- approvals: FDA Oncology Center of Excellenceの承認通知一覧を基準に、正準データで追跡を開始した日以降の未保存通知をすべて取得し、個別のFDA承認ページを一次情報として保存
- Drugs@FDA: FDA公式Data Files ZIPをSHA-256付きで保存し、既存のoncology承認通知とapplication、submission、action type、approval letterを実データで照合
- Orange Book: FDA公式Data Files ZIPをSHA-256付きで保存し、NDA / ANDAのapplication numberとproduct numberをDrugs@FDAと全件照合する

`api/v1/multiomics/metrics.json` は上記canonical dataから決定的に生成するread-only viewです。`api/v1/multiomics/drugsfda-oncology-crosswalk.json` はFDA Oncology approval notificationsとDrugs@FDAの実レコードを結ぶread-onlyの派生結果です。Drugs@FDAに収録されない製品へapplication numberを推測で付与せず、同一通知日に複数submissionがある場合もまとめて1件へ潰しません。`api/v1/multiomics/fda-product-identity-crosscheck.json` はDrugs@FDAとOrange BookをFDA公式のapplication number + product numberで照合し、一致範囲と片側だけに存在する製品を保存するread-onlyの派生結果です。Orange Bookの`Approval Date`はproduct-level evidenceのまま扱い、Drugs@FDA submissionの承認日へ推測で変換しません。`api/v1/multiomics/sequencing-cost-analysis.json` はNHGRIの実観測から長期低下率を再計算するread-onlyの派生結果で、因果効果は主張しません。downstreamはこれらを参照し、事実の正本を複製しません。

## Primary sources

- NHGRI DNA Sequencing Costs: https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data
- ClinicalTrials.gov study: https://clinicaltrials.gov/study/NCT06264180
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- FDA Oncology approval notifications: https://www.fda.gov/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications
- Drugs@FDA Data Files: https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files
- Orange Book Data Files: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

ClinicalTrials.gov、FDA、NHGRIの一次情報は、同じ一次情報更新workflowで取得します。ClinicalTrials.govのstudy JSON、FDA承認詳細ページのHTML、Drugs@FDA公式ZIP、Orange Book公式ZIP、NHGRIの公式Excelは `data/raw/` にcontent-addressed snapshotとして保存し、取得したFDA承認にはSHA-256と原本pathを正準データへ残します。外部の二次APIや推定値へfallbackしません。FDA一覧の日付と個別ページの日付が一致しない場合、または個別ページの主要な製品情報を解析できない場合は更新を停止します。FDA本文が複数薬剤・複数適応をまとめており `modality` や単一の `indication` に安全に分解できない場合は、推測せず `null` を保存し、FDAの承認要約本文を `approval_summary` に保持します。

## Reproduce

```bash
python -m pip install xlrd==2.0.2
python scripts/refresh_clinical_trials.py --nct-id NCT06264180
python scripts/refresh_drugsfda.py
python scripts/refresh_orange_book.py
python scripts/refresh_fda_approvals.py
python scripts/refresh_sequencing_costs.py
python scripts/build_api.py
python scripts/analyze_sequencing_costs.py
python -m unittest discover -s tests -v
```

ClinicalTrials.govのJSON取得、FDA承認ページのHTML取得、Drugs@FDA公式ZIP取得、Orange Book公式ZIP取得、API生成はPython標準ライブラリだけで動作します。NHGRIが配布する`.xls`原本の読み取りには`xlrd==2.0.2`を使用します。
