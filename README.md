# multiomics

ARK Big Ideas 2026 の **Multiomics** を一次情報で検証するための正準ターゲットrepositoryです。

このrepositoryでは、予測値と観測事実を分け、次の情報を一次資料へ戻れる形で扱います。

- sequencing economics: cost per genome / sequencing cost
- clinical trials: study / phase / status / sponsor / intervention / dates
- approvals: drug / biologic approvals and regulatory events
- modality / phase / sponsor aggregates
- source URL and retrieval time

ARKの予測値は観測事実へ混ぜず、仮説として別に扱います。

## Current data

- canonical data: [`data/multiomics-v1.json`](data/multiomics-v1.json)
- schema: [`schema/multiomics-v1.schema.json`](schema/multiomics-v1.schema.json)
- current persisted approval observations: **1**
- sequencing-cost observations: **not yet materialized**
- clinical-trial observations: **not yet materialized**

最初のpersisted recordは、FDAが2026年8月6日に公表したvusolimogene oderparepvec-wtpg (Tudriqev) のaccelerated approvalです。未取得のsequencing costとclinical trialについては値を補完せず、空配列のまま保持します。

## Primary sources

- NHGRI DNA Sequencing Costs: https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- FDA approval notification: https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma

ClinicalTrials.govのstudy dataは頻繁に更新されるため、利用時は最新のstudy page/APIを確認します。repositoryへclinical-trial observationを追加する場合も、取得日時とsource URLを保持します。

## Validation

```bash
python -m unittest discover -s tests -v
```

GitHub ActionsでもJSON syntaxと同じtestsを実行します。新しいruntime dependencyはありません。

## Project evidence

- ARK 2026 cross-repository plan: https://github.com/KAFKA2306/investor2/issues/111
- repository rename/responsibility map: https://github.com/KAFKA2306/investor2/issues/110
- Multiomics implementation plan: https://github.com/KAFKA2306/kafin3/issues/6
