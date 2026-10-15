# Evidence index

| Requirement | Files |
|---|---|
| Four populated RDS tables and populated OpenSearch | evidence/lambda/foundation-result.json |
| Exact four-key tool interfaces | evidence/lambda/interfaces-result.json |
| Worker descriptions, LangGraph nodes and AST policy | runtime/tool_registry.py, runtime/orchestrator.py, runtime/sql_validator.py |
| Validator output including deleted_at and both stacking cases | evidence/offline/offline-check-output.txt |
| Required eight cases and ten-query cost table | evidence/lambda/TEST-RESULTS.md, evidence/lambda/TOKENOMICS.md |
| Both-source actual response and matching CloudWatch lines | evidence/lambda/Q5-response.json, evidence/lambda/cloudwatch.log |
| Local memory and confirmation, including corrected ID-based scope check | evidence/local/stretch-summary.json, evidence/local/acme-scope-evidence.json |
| Deployed memory and confirmation | evidence/lambda/stretch-summary.json; memory-turn1, memory-turn2, gold-flagged, gold-confirmed, confirmation-altered and confirmed-invalid-sql request/response pairs |
| Direct replay-cost measurement | evidence/local/memory-cost-impact.json, evidence/lambda/memory-cost-impact.json |
| Focused post-review local and Lambda results | evidence/recheck/ |
| Current deployed ZIP and runtime hash | evidence/deployment/ |
| Human source-review findings and reflection | QUALITY-REVIEW.md, REFLECTION.md |

The ten-query samples are the original measured runs. Their costs are not relabeled as post-review measurements. Focused rechecks have separate usage and costs. Receipt strings are redacted for Git; source and export file hashes are recorded in EXPORT-PROVENANCE.json. The working project's original files remain intact.

The instructor demo is a separate required activity. Machine tests and this export do not claim that the demo occurred.
