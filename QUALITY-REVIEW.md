# Evidence review

The original live evidence is retained. These findings come from comparing final answers with the actual retrieved excerpts and SQL rows, rather than treating citation-format checks as factual verification.

## Verified baseline

- All 38 offline tests passed on the user's Mac; all six explicitly printed SQL validator cases passed.
- RDS contains 6 clients, 6 projects, 8 consultants and 8 invoices. The selected instructor corpus contains 4 PDFs and 22 chunks; the total index contains 45 chunks across retained ingestion versions.
- All 10 local and 10 Lambda question checks passed. The first eight cover two SQL questions, two document questions, two both-source questions, one blocked destructive request and one honest decline.
- Local and deployed memory/confirmation checks passed, including altered SQL rejection, no regeneration of the confirmed SQL, repeated validation and a trusted signed unsafe-query fixture blocked before execution.
- The Lambda evidence contains 16 completed traces and 205 CloudWatch events.
- Runtime files matched every hash in the uploaded source manifest before the review correction.

## Findings and corrections

| Case | Finding in original output | Supporting evidence / correction |
|---|---|---|
| Q3, local and Lambda | Utilities exclusion cited Source 4, which contains the deadline and rollover rule. | The utilities exclusion appears in Source 2, page 2 of remote-work-policy.pdf. The requested annual $500 answer itself is correctly supported by Source 1. |
| Q3, local | Extra eligibility details cited Source 1, which contains equipment/stipend text. | Eligibility is in Source 3; the fully remote offer-stage exception is in Source 5. These facts were not requested. |
| Q4, local | Extra client-background facts cited Source 4, which contains rollout/results. The payback qualification was cited only to Source 1. | Background is Source 2. The full payback sentence spans Sources 1 and 3. The requested 34% and 19% reductions are correctly supported by Source 4. |
| Q4, Lambda | Added client background, forecasting methodology and payback details all cited Source 4. | Background is Source 2, forecasting is Source 5, and the full payback sentence spans Sources 1 and 3. The requested 34% and 19% answer is correct. |
| Q5, local and Lambda | The core 4-project and $500-per-year answer is correct, but an added utilities exclusion cites the wrong stipend excerpt. | The utilities FAQ is Source 3 for this question's retrieved order. Extra FAQ content is unnecessary for the requested answer. |
| Q6, Lambda | Added cost-of-late-fixes qualification was cited only to Source 3, whose sentence ends before that qualification. | The continuation is in Source 1. The worker's concise answer already limited this claim to the supported pre-cutover recommendation. |
| Memory turn 2, local and Lambda | One client row was described as a single contract or contract entry. | The clients table stores one organization and its total contract_value. It does not model individual contracts. The $250,000 total is supported; a number of contracts cannot be inferred. |
| Local Gold pause check | Evidence checker initially required the literal Acme name, rejecting a valid joined `WHERE c.id = 1`. | The corrected check independently verified Acme's ID and the mandatory project/client filter. The original failed check and successful resume are preserved. No flagged SQL was executed by the scope lookup. |

The two prompt corrections limit synthesis to requested claims already present in worker answers, preserve each worker claim's original source numbers and multi-excerpt references, and prohibit inferring contract counts from client-row counts. SQL interpretation receives the same row/entity distinction. No validation, transaction, confirmation-signature, routing or memory logic changes.

Focused rechecks cover Q3-Q6 and memory turn 2 both locally and in Lambda. Their actual outcomes, usage and matching Lambda logs are saved separately from the baseline cost sample. A passing citation-format check still does not prove semantic entailment; inspect the actual new answers and excerpts before declaring the factual review complete.

## Tokenomics verified from individual records

| Run | Queries | Actual model calls | Input tokens | Output tokens | Calculated token cost | Most tokens |
|---|---:|---:|---:|---:|---:|---|
| Local baseline | 10 | 33 | 37,549 | 3,087 | $0.1748472 | Synthesis |
| Lambda baseline | 10 | 33 | 37,418 | 3,010 | $0.1731444 | Synthesis |

The controlled direct history replay overhead is 208 input tokens locally and 84 in Lambda. The difference reflects different generated prior answers, not inconsistent accounting. Whole-turn changes were 191 and 133 input tokens respectively and also include changed questions/results, so they are not labeled memory-only overhead.

Prices use the documented Standard geographic Sonnet 4.6 assumptions ($3.30/M input, $16.50/M output), verified 2026-10-15. These are calculated token charges, excluding infrastructure, discounts, credits and tax. Focused rechecks and generation-only ablations are separate from the ten-query totals.
