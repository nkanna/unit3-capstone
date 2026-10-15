"""Package-local backend resolution. No sibling repos, host paths or import-time calls."""
from functools import lru_cache


@lru_cache(maxsize=1)
def sql_backend():
    import sql_runtime
    return sql_runtime


@lru_cache(maxsize=1)
def retrieval_backend():
    import retrieval_runtime
    return retrieval_runtime


def invoke_claude(prompt, max_tokens=500):
    from bedrock_client import invoke_claude as invoke
    return invoke(prompt, max_tokens=max_tokens)


def usage_record(component, response):
    record = {'component': component, **{key: response.get(key) for key in
              ['model', 'input_tokens', 'output_tokens', 'stop_reason', 'usage']}}
    from tokenomics_costs import price_records
    from tokenomics_logger import log_decision
    priced = price_records([record])
    log_decision('llm_call', '', {**record, 'calculated_cost_usd': priced['total_cost'],
                 'cost_complete': priced['complete']})
    return record


def safe_diagnostic(error):
    response = getattr(error, 'response', None)
    if isinstance(response, dict):
        code = response.get('Error', {}).get('Code')
        known = {'AccessDeniedException', 'ThrottlingException', 'ValidationException',
                 'ResourceNotFoundException', 'ExpiredToken', 'ExpiredTokenException'}
        return 'AWS ' + (code if code in known else 'service error')
    return type(error).__name__
