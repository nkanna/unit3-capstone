# Ten-query tokenomics summary

| Query | Route | Input | Output | Calculated USD |
|---|---|---:|---:|---:|
| Q1 | sql | 2891 | 150 | 0.0120153 |
| Q2 | sql | 2928 | 202 | 0.0129954 |
| Q3 | retrieval | 5095 | 519 | 0.025377 |
| Q4 | retrieval | 4956 | 445 | 0.0236973 |
| Q5 | both | 7522 | 540 | 0.0337326 |
| Q6 | both | 7763 | 863 | 0.0398574 |
| Q7 | sql | 0 | 0 | 0.0 |
| Q8 | neither | 447 | 37 | 0.0020856 |
| Q9 | sql | 3037 | 220 | 0.0136521 |
| Q10 | sql | 2910 | 111 | 0.0114345 |

Total calculated token cost: $0.1748472. Most tokens: synthesis.

| Component | Calls | Input | Output | Total tokens | Calculated USD |
|---|---:|---:|---:|---:|---:|
| classification | 9 | 4073 | 385 | 4458 | 0.019793400 |
| sql_generation | 6 | 12000 | 172 | 12172 | 0.042438000 |
| sql_interpretation | 6 | 732 | 334 | 1066 | 0.007926600 |
| synthesis | 8 | 13805 | 1722 | 15527 | 0.073969500 |
| retrieval_generation | 4 | 6939 | 474 | 7413 | 0.030719700 |

Rates verified 2026-10-15: US geographic Sonnet 4.6 Standard, $3.30/M input and $16.50/M output. These are calculated token charges under the documented pricing assumptions, not an AWS invoice.
Sources: https://aws.amazon.com/bedrock/pricing/ and https://platform.claude.com/docs/en/about-claude/pricing . Cache and nonstandard-tier usage remain unpriced until supported.
