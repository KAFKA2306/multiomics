# multiomics

ARK Big Ideas 2026 の **Multiomics** を一次情報で検証するための正準ターゲットrepositoryです。

現時点では実装・datasetはまだ移行されていません。既存の計画では `KAFKA2306/kafin3` の旧AI金融prototypeを置き換え、次の観測事実を収集・構造化する対象として定義されています。

- sequencing economics: cost per genome / sequencing cost
- clinical trials: study / phase / status / sponsor / intervention / dates
- approvals: drug / biologic approvals and regulatory events
- modality / phase / sponsor aggregates
- provenance manifest with source URL and observation time

想定する一次情報は、NHGRIのsequencing cost data、ClinicalTrials.gov、FDA Drugs@FDA等です。ARKの予測値は観測事実へ混ぜず、仮説として別に扱います。

## Current state

- repository implementation: **not yet materialized**
- canonical scope: defined
- data collection: pending
- migration source/planning repository: `KAFKA2306/kafin3`

したがって、このREADMEはデータ取得や分析がすでに完成していることを意味しません。実データ・schema・collector・workflowが追加されるまで、成果物の存在を主張しません。

## Project evidence

- ARK 2026 cross-repository plan: https://github.com/KAFKA2306/investor2/issues/111
- repository rename/responsibility map: https://github.com/KAFKA2306/investor2/issues/110
- Multiomics implementation plan: https://github.com/KAFKA2306/kafin3/issues/6
