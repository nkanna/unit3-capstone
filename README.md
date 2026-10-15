# Unit 3 Capstone: Multi-Agent System on AWS

**Author:** Niranjanaa Kannan

A LangGraph orchestrator answers consulting-operations questions using a validated PostgreSQL SQL agent and an OpenSearch document-retrieval agent. It routes single-source questions to the appropriate worker and combines both sources for mixed questions. The complete application is deployed as a Python 3.12 x86_64 Lambda ZIP with local ONNX embeddings and Claude through Amazon Bedrock.

Gold extensions include caller-carried conversation history and human confirmation of unusual validated SELECT queries. Confirmation is bound to the exact SQL, conversation context, database target and expiry; the query is validated again before execution.

## Deployment

- Lambda: `multi-agent-orchestrator-nk`, `us-east-1`.
- Database: dedicated training RDS PostgreSQL, runtime user `agent_reader` with SELECT-only access.
- Retrieval: `document-ingestion-lab`, filtered to the four instructor PDFs and their 22 verified chunks.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, 384 dimensions. Lambda uses the numerically verified ONNX implementation.
- Model: Claude Sonnet 4.6 through the account's US Bedrock inference profile.

This is an IAM-invoked Lambda, so there is no public website URL. An evaluator with permission to invoke the training function can run:

```bash
aws lambda invoke --function-name multi-agent-orchestrator-nk \
  --region us-east-1 --cli-binary-format raw-in-base64-out \
  --payload '{"question":"How many active projects do we have, and what is the annual home office equipment allowance?"}' \
  response.json
```

## Architecture and safety

The four graph nodes classify, call the SQL worker when needed, call the retrieval worker when needed, and synthesize. Worker results have exactly `success`, `answer`, `sources`, and `metadata`. Source descriptions distinguish current database facts from document content.

Every SQL execution entry point validates an AST before connecting. The policy blocks writes, stacked statements, out-of-scope tables and disallowed functions. Execution uses a read-only transaction, TLS certificate verification, timeouts, a bounded preview, rollback and close. The destructive natural-language test is rejected by the request guard; independent direct-SQL tests prove the validator boundary.

Unusual reads pause before execution. The default rules flag unlimited wildcard reads, unrestricted detail reads and reads across more than two tables, with scalar aggregate-only reads exempt. An HMAC-SHA256 receipt binds the exact flagged query to its context for 30 minutes. Stateless receipts can be replayed before expiry and are not a substitute for caller authentication.

History is carried by the caller between invocations, capped at three turns and 1,000 question / 2,000 answer characters per turn. Both classification and SQL generation receive it. Paused and failed requests do not become completed history turns.

## Evidence

Start with [EVIDENCE-INDEX.md](EVIDENCE-INDEX.md), [QUALITY-REVIEW.md](QUALITY-REVIEW.md), and [REFLECTION.md](REFLECTION.md).

- Baseline: all eight required cases plus two additional questions passed locally and in Lambda.
- Deployed ten-query sample: 33 actual model calls, 37,418 input tokens and 3,010 output tokens; calculated model cost **$0.1731444**. Synthesis consumed the most tokens.
- Local ten-query sample: 33 calls; calculated model cost **$0.1748472**.
- Both local and deployed memory, review-pause, altered-query rejection, exact-query confirmation and revalidation checks passed.
- Controlled direct history replay overhead: **208 input tokens locally; 84 in Lambda**. Whole-turn differences are reported separately.
- Original deployed evidence contains **16 complete traces and 205 CloudWatch events**.
- The evidence review identified optional-detail citation misattributions and a client-row/contract-count interpretation error. Original outputs are retained; focused post-correction rechecks are stored separately.

Citation-format checks verify labels and reference ranges, not factual entailment. See the quality review for findings and the source-backed corrections. The corpus is fictional instructor-provided training material.

## Code and offline verification

The full application is in `runtime/`; wrappers, registry, graph, validator, tokenomics, history, confirmation and Lambda handler are included. Client build, deployment and evidence scripts are retained at the repository root.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python run_offline_checks.py
```

The 38 offline tests make no live cloud/model calls. The deployment dependency lock is in `requirements-linux.lock`; it targets Linux Python 3.12 x86_64 and must not be installed directly into a Mac virtualenv. The large native deployment ZIP and model binaries are excluded from Git; the build report records the deployed artifact hash. The original build procedure used a pinned Lambda Linux image, verified native files, and compared six ONNX embeddings against the cached Sentence Transformers model. The focused review changes only Python prompts, so model and native dependency bytes remain unchanged.

The working Mac deployment project and its private key/journal stay outside this submission snapshot. Rebuilding the ZIP with `build_gold.py` uses the original verified Day 4 archive as its base. To reproduce live calls from this snapshot, use the Lambda invocation above with your authorized AWS credentials. The RDS and OpenSearch endpoints, selected-corpus provenance and TLS bundle are included; passwords, AWS credentials, signing keys, private configuration and executable confirmation receipts are excluded.

## Evaluation

Use [DEMO.md](DEMO.md) for the live presentation. The instructor demo/evaluation remains a separate activity; no script fabricates its completion. Keep the training resources available until evaluation finishes, then use ownership-aware teardown for your resources.
