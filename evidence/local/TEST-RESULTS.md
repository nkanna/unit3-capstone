# Actual test results

Execution: local. First eight questions cover the required rubric mix; Q9-Q10 complete the cost sample.

## Q1: How many active projects do we have?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Active Projects Count

We currently have **4 active projects** [SQL].

> **Query used:** `SELECT COUNT(*) AS active_project_count FROM projects WHERE status = 'active';`

*Note: No document retrieval was needed for this question, as the database query fully answered it. No retrieval evidence was supplied.*

## Q2: What is the total contract value in USD across all clients?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Total Contract Value Across All Clients

The total contract value across all clients is **$1,530,000.00 USD** [SQL].

> **Query executed:** `SELECT SUM(contract_value) AS total_contract_value FROM clients;`

No document retrieval was used for this answer. The figure is sourced entirely from the SQL query result, which returned a single row with a total of **$1,530,000.00** across all client records [SQL].

## Q3: How much can eligible employees claim annually for home office equipment under the remote work policy?

Route: retrieval. SQL validation: None. Status: ANSWERED. Machine checks: True.

## Home Office Equipment Stipend Under the Remote Work Policy

Based on the supplied evidence (fictional training documents; not actual company policy):

**Eligible employees may claim up to $500 per year** toward home office equipment [Retrieval: remote-work-policy.pdf, Source 1].

### What Is Covered
Qualifying items include desks, chairs, monitor arms, and lighting [Retrieval: remote-work-policy.pdf, Source 1]. Notably, ongoing utilities such as internet or electricity are **not** covered by the stipend [Retrieval: remote-work-policy.pdf, Source 4].

### How to Claim
Claims must be submitted through the standard expense reimbursement process with itemized receipts [Retrieval: remote-work-policy.pdf, Source 1].

### Key Deadlines and Limitations
- Stipend claims for the current calendar year must be submitted **no later than December 15** [Retrieval: remote-work-policy.pdf, Source 4].
- **Unused stipend amounts do not roll over** to the following year [Retrieval: remote-work-policy.pdf, Source 4].

### Eligibility
Employees who have completed their 90-day probationary period and whose role does not require regular physical presence on client premises are eligible for a remote work arrangement [Retrieval: remote-work-policy.pdf, Source 1]. New hires in a fully remote capacity agreed upon at the offer stage are exempt from the 90-day waiting period [Retrieval: remote-work-policy.pdf, Source 1].

No SQL data was provided for this question; all facts above derive solely from the retrieval agent.

## Q4: What reductions in food waste and stockouts were reported in the retail supply chain case study?

Route: retrieval. SQL validation: None. Status: ANSWERED. Machine checks: True.

## Retail Supply Chain Case Study: Food Waste and Stockout Reductions

**Note:** The document referenced below (retail-supply-chain-case-study.pdf) is a fictional training document and should not be treated as actual company policy.

---

Within six months of full deployment, the case study reported the following results:

- **34% reduction in perishable waste** [Retrieval: retail-supply-chain-case-study.pdf, Source 4]
- **19% reduction in stockout incidents on top-selling SKUs** [Retrieval: retail-supply-chain-case-study.pdf, Source 4] [Retrieval: retail-supply-chain-case-study.pdf, Source 1]

### Additional Context

Prior to the engagement, the client — a mid-sized regional grocery retailer operating 45 stores — was experiencing an estimated **$2.3 million in annual waste**, primarily in the produce and dairy categories, due to overstock of perishable goods early in the week and frequent stockouts of high-demand items during weekend peaks [Retrieval: retail-supply-chain-case-study.pdf, Source 4].

The finance team estimated that the engagement **paid for itself within the first eight months through waste reduction alone**, before accounting for labor savings or reduced stockout-driven lost sales [Retrieval: retail-supply-chain-case-study.pdf, Source 1].

---

No SQL agent was involved in answering this question; all findings derive solely from the retrieved document.

## Q5: How many active projects do we have, and what is the annual home office equipment allowance in the remote work policy?

Route: both. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

**1. Active Projects**

There are **4 active projects** in the system. [SQL]

**2. Annual Home Office Equipment Allowance (Remote Work Policy)**

Eligible employees may claim **up to $500 per year** toward home office equipment such as desks, chairs, monitor arms, and lighting, submitted through the standard expense reimbursement process with itemized receipts. [Retrieval: remote-work-policy.pdf, Source 2]

Additional details on the stipend:
- Stipend claims for the current calendar year must be submitted **no later than December 15**. [Retrieval: remote-work-policy.pdf, Source 4]
- **Unused stipend amounts do not roll over** to the following year. [Retrieval: remote-work-policy.pdf, Source 4]
- Internet bills and other ongoing utilities (e.g., electricity) are **not covered** by the stipend. [Retrieval: remote-work-policy.pdf, Source 2]

> ⚠️ **Note:** The remote work policy document (remote-work-policy.pdf) is a fictional training document from the corpus and should not be treated as actual company policy.

## Q6: What is the total USD amount of overdue invoices in the database, and what rollback and validation procedures does the cloud migration playbook recommend?

Route: both. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

### 1. Total USD Amount of Overdue Invoices

The total USD amount of overdue invoices in the database is **$130,000.00 USD**. This represents the sum of all invoice records with a status of `'overdue'` (1 row returned, result not truncated). [SQL]

---

### 2. Cloud Migration Playbook — Rollback and Validation Procedures

> ⚠️ **Note:** The following content is from a fictional training document and should not be treated as actual company policy.

#### Rollback Procedures
The playbook identifies the following as a **common pitfall** to avoid, implying it as a recommended practice:
- Engagement teams should **not skip a rollback plan for intermediate batches** — rollback planning should cover intermediate batches, not just the final cutover. [Retrieval: cloud-migration-playbook.pdf, Source 1]

#### Validation Procedures (Phase 4: Validation and Cutover)
Before final cutover, the playbook recommends:
- Run a **full reconciliation between source and target systems** covering **record counts** and **checksums on a sampled basis**. [Retrieval: cloud-migration-playbook.pdf, Source 3]
- Perform **functional testing** of downstream reports or applications that depend on the migrated data. [Retrieval: cloud-migration-playbook.pdf, Source 3]
- **Remediate known data quality issues identified during discovery before cutover wherever feasible**, rather than migrating them as-is, since fixing them post-migration is typically more expensive once the data is in active use. [Retrieval: cloud-migration-playbook.pdf, Source 3] [Retrieval: cloud-migration-playbook.pdf, Source 1]

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

This figure represents a complete, untruncated count of all projects with a status of `'active'` linked to the client named `'Acme Corp'` in the database. [SQL]

> **Note:** No retrieval/document evidence was available or relevant for this question; the answer is based solely on the SQL query result.

## Q10: How many invoices have status overdue?

Route: sql. SQL validation: PASSED. Status: ANSWERED. Machine checks: True.

## Answer

There are **2 invoices** with a status of **overdue** [SQL].

Human review: read cited excerpts in each saved `state.retrieval_result.metadata.chunks` and confirm they support each claim. Citation-format checks do not prove factual entailment.
