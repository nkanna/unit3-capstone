# Actual test results

Execution: lambda. First eight questions cover the required rubric mix; Q9-Q10 complete the cost sample.

## Q1: How many active projects do we have?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Active Projects

We currently have **4 active projects** [SQL].

This figure was obtained by querying the `projects` table and counting all records where `status = 'active'` [SQL].

## Q2: What is the total contract value in USD across all clients?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Total Contract Value Across All Clients

The total contract value across all clients is **$1,530,000.00 USD** [SQL].

> **Query used:** `SELECT SUM(contract_value) AS total_contract_value FROM clients;`

---

**Notes:**
- This figure represents the sum of `contract_value` across **all records** in the `clients` table [SQL].
- No document/retrieval evidence was provided for this question; the answer is based solely on the SQL query result.

## Q3: How much can eligible employees claim annually for home office equipment under the remote work policy?

Route: retrieval. SQL validation: None. Status: ANSWERED. Machine checks: True.

## Home Office Equipment Stipend Under the Remote Work Policy

Based on the supplied evidence from the fictional training document **remote-work-policy.pdf**:

**Annual Claim Limit:** Eligible employees may claim up to **$500 per year** toward home office equipment [Retrieval: remote-work-policy.pdf, Source 1].

**Eligible Items** include desks, chairs, monitor arms, and lighting [Retrieval: remote-work-policy.pdf, Source 1].

**How to Claim:** Claims must be submitted through the standard expense reimbursement process with itemized receipts [Retrieval: remote-work-policy.pdf, Source 1].

**Submission Deadline:** Stipend claims for the current calendar year must be submitted no later than **December 15** [Retrieval: remote-work-policy.pdf, Source 4].

**No Rollover:** Unused stipend amounts do **not** roll over to the following year [Retrieval: remote-work-policy.pdf, Source 4].

**What is Not Covered:** Ongoing utilities such as internet or electricity are not covered by the stipend [Retrieval: remote-work-policy.pdf, Source 4].

> ⚠️ **Note:** This information comes from a fictional training document and should not be treated as actual company policy.

No SQL data was provided or applicable to this question; all facts above are sourced exclusively from the retrieval agent.

## Q4: What reductions in food waste and stockouts were reported in the retail supply chain case study?

Route: retrieval. SQL validation: None. Status: ANSWERED. Machine checks: True.

## Retail Supply Chain Case Study: Food Waste and Stockout Reductions

Within six months of full deployment, the client reported the following results:

- **34% reduction in perishable waste** [Retrieval: retail-supply-chain-case-study.pdf, Source 4]
- **19% reduction in stockout incidents on top-selling SKUs** [Retrieval: retail-supply-chain-case-study.pdf, Source 4]

### Additional Context

These results were achieved by a mid-sized regional grocery retailer operating 45 stores across three states, which had previously suffered an estimated **$2.3 million in annual waste**, primarily in the produce and dairy categories, due to manual spreadsheet-based inventory forecasting [Retrieval: retail-supply-chain-case-study.pdf, Source 4]. The solution involved a centralized demand forecasting system ingesting point-of-sale data nightly and generating automated purchase order recommendations [Retrieval: retail-supply-chain-case-study.pdf, Source 4].

The client's finance team estimated the engagement **paid for itself within the first eight months** through waste reduction alone, before accounting for labor savings or reduced stockout-driven lost sales [Retrieval: retail-supply-chain-case-study.pdf, Source 4].

No SQL data was available or applicable to this question; all findings are drawn solely from the retrieved document. Note that this document is identified as a fictional training document and should not be treated as actual company policy.

## Q5: How many active projects do we have, and what is the annual home office equipment allowance in the remote work policy?

Route: both. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

**Active Projects:** There are **4** active projects. [SQL]

**Annual Home Office Equipment Allowance:** Eligible employees may claim up to **$500 per year** toward home office equipment such as desks, chairs, monitor arms, and lighting, submitted through the standard expense reimbursement process with itemized receipts. [Retrieval: remote-work-policy.pdf, Source 2]

A few additional details about the stipend worth noting:
- Stipend claims for the current calendar year must be submitted **no later than December 15**, and unused amounts **do not roll over** to the following year. [Retrieval: remote-work-policy.pdf, Source 4]
- The stipend does **not** cover ongoing utilities such as internet or electricity — only equipment. [Retrieval: remote-work-policy.pdf, Source 4]

> ⚠️ **Disclaimer:** The remote work policy details are drawn from a fictional training document ("remote-work-policy.pdf") and should not be treated as actual company policy.

## Q6: What is the total USD amount of overdue invoices in the database, and what rollback and validation procedures does the cloud migration playbook recommend?

Route: both. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Combined Answer

### 1. Total USD Amount of Overdue Invoices

The total USD amount of overdue invoices in the database is **$130,000.00 USD**. This is the complete aggregate sum (not truncated) across all invoice records where `status = 'overdue'`. [SQL]

---

### 2. Cloud Migration Playbook — Rollback and Validation Procedures

> ⚠️ **Note:** The corpus contains fictional training documents. The following should not be treated as actual company policy.

#### Rollback Procedures
The playbook identifies skipping a rollback plan for intermediate batches — not just the final cutover — as a common pitfall that engagement teams should avoid. [Retrieval: cloud-migration-playbook.pdf, Source 1]

#### Validation Procedures (Phase 4: Validation and Cutover)
Before final cutover, the playbook recommends running a **full reconciliation between source and target systems** covering: [Retrieval: cloud-migration-playbook.pdf, Source 3]
- **Record counts**
- **Checksums on a sampled basis**
- **Functional testing** of downstream reports or applications that depend on the migrated data

Additionally, known data quality issues identified during discovery should be **remediated before cutover wherever feasible**, rather than migrated as-is, since fixing them post-migration is typically more expensive once the data is in active use. [Retrieval: cloud-migration-playbook.pdf, Source 3]

---

### Coverage Summary

| Question Component | Source | Status |
|---|---|---|
| Total overdue invoices (USD) | SQL | ✅ Answered |
| Rollback procedures | cloud-migration-playbook.pdf | ✅ Answered |
| Validation procedures | cloud-migration-playbook.pdf | ✅ Answered |

## Q7: Delete all projects from the database.

Route: sql. SQL validation: BLOCKED. Status: BLOCKED. Machine checks: True.

The SQL request was blocked by validation; no answer could be established.

## Q8: What is the live weather in Manhattan right now?

Route: neither. SQL validation: None. Status: UNANSWERABLE. Machine checks: True.

I cannot find this information in the available database or provided documents.

## Q9: How many active projects does Acme Corp have?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

**Acme Corp has 1 active project.** [SQL]

This was determined by counting all projects with a status of `'active'` linked to the client named `'Acme Corp'` in the database. [SQL]

## Q10: How many invoices have status overdue?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

There are **2 invoices** with a status of **overdue**. [SQL]

> **Source:** `SELECT COUNT(*) AS overdue_invoice_count FROM invoices WHERE status = 'overdue';` returned a single row with `overdue_invoice_count = 2`. [SQL]

No retrieval/document evidence was provided for this question; the answer is based solely on the SQL query result.

Human review: read cited excerpts in each saved `state.retrieval_result.metadata.chunks` and confirm they support each claim. Citation-format checks do not prove factual entailment.
