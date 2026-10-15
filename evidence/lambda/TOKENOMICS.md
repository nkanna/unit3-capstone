# Ten-query tokenomics summary

| Query | Route | Input | Output | Calculated USD |
|---|---|---:|---:|---:|
| Q1 | sql | 2910 | 123 | 0.0116325 |
| Q2 | sql | 2928 | 211 | 0.0131439 |
| Q3 | retrieval | 5095 | 468 | 0.0245355 |
| Q4 | retrieval | 4805 | 431 | 0.022968 |
| Q5 | both | 7523 | 504 | 0.0331419 |
| Q6 | both | 7784 | 894 | 0.0404382 |
| Q7 | sql | 0 | 0 | 0.0 |
| Q8 | neither | 447 | 31 | 0.0019866 |
| Q9 | sql | 3022 | 170 | 0.0127776 |
| Q10 | sql | 2904 | 178 | 0.0125202 |

Total calculated token cost: $0.1731444. Most tokens: synthesis.

| Component | Calls | Input | Output | Total tokens | Calculated USD |
|---|---:|---:|---:|---:|---:|
| classification | 9 | 4073 | 379 | 4452 | 0.019694400 |
| sql_generation | 6 | 12000 | 174 | 12174 | 0.042471000 |
| sql_interpretation | 6 | 734 | 335 | 1069 | 0.007949700 |
| synthesis | 8 | 13672 | 1667 | 15339 | 0.072623100 |
| retrieval_generation | 4 | 6939 | 455 | 7394 | 0.030406200 |

Rates verified 2026-10-15: US geographic Sonnet 4.6 Standard, $3.30/M input and $16.50/M output. These are calculated token charges under the documented pricing assumptions, not an AWS invoice.
Sources: https://aws.amazon.com/bedrock/pricing/ and https://platform.claude.com/docs/en/about-claude/pricing . Cache and nonstandard-tier usage remain unpriced until supported.
