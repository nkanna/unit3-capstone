# Demo sequence

Use the actual outputs from `python capstone.py lambda`. The runner itself is also a live demo and records raw AWS CLI responses.

1. Show the populated-table and selected document count evidence.
2. Show both tool contracts and the four LangGraph nodes.
3. Explain Q1's SQL-only route, Q3's retrieval-only route, and Q5's both-source route. Show that synthesis received both raw results and attributed its claims.
4. Show Q7's blocked destructive request and the separate AST validation tests, including two stacked SELECTs and `deleted_at`.
5. Show Q8's honest decline.
6. Show `TOKENOMICS.md`: ten queries, every component including classification, actual input/output tokens, total calculated cost and the component with the most tokens.
7. Show the deployed two-turn Acme count then contract-value exchange. The second SQL must retain the Acme filter. Explain the three-turn memory cap and controlled replay-cost measurement.
8. Continue with the context-aware request for all project columns without a row limit. Show the SQL and review reason, `needs_confirmation: true`, and `execution_attempted: false`. Show the altered SQL rejection, then the exact reviewed query's confirmation and repeated validation.
9. Show the trusted signed unsafe-SQL test still blocked by validation.
10. Show the matching CloudWatch trace and the reflection. Explain that citation-format checks do not prove factual entailment, and that stateless receipts can be replayed before expiry.

After presenting, run `python capstone.py finalize` and truthfully record whether the demo is complete. Run `python capstone.py package` to create the submission archive.
