"""Shared two-tool registry; every outcome uses the same four-key contract."""
from copy import deepcopy
from agents.sql_agent import run_sql_agent
from agents.retrieval_agent import run_retrieval_agent
from backends import safe_diagnostic

TOOL_REGISTRY = {
    'sql_agent': {'function': run_sql_agent, 'schema': {
        'name': 'sql_agent',
        'description': 'Query current relational data about clients, projects, consultants, and invoices. Use for project/consultant counts, client contract values, project budgets/statuses, and invoice billing. Do not use for policy text, onboarding procedures, case-study narratives, or thresholds and allowances stated in documents.',
        'input_schema': {'type': 'object', 'properties': {'question': {'type': 'string'}},
                         'required': ['question'], 'additionalProperties': False}}},
    'retrieval_agent': {'function': run_retrieval_agent, 'schema': {
        'name': 'retrieval_agent',
        'description': 'Search instructor-provided remote-work policy, grocery retail case study, quarterly engagement report, and cloud migration playbook. Use for eligibility, core hours, equipment stipend rules, forecasting outcomes, documented migration risks, batch validation, and policy allowances or thresholds stated in documents. Do not use for current RDS project counts, client contract values, budgets, assignments, or billing totals.',
        'input_schema': {'type': 'object', 'properties': {'question': {'type': 'string'}},
                         'required': ['question'], 'additionalProperties': False}}},
}
KEYS = {'success', 'answer', 'sources', 'metadata'}


def valid_contract(value):
    return (isinstance(value, dict) and set(value) == KEYS
            and type(value['success']) is bool and isinstance(value['answer'], str)
            and isinstance(value['sources'], list) and all(isinstance(s, str) for s in value['sources'])
            and isinstance(value['metadata'], dict))


def failure(status, answer, **details):
    return {'success': False, 'answer': answer, 'sources': [], 'metadata': {'status': status, **details}}


def get_all_schemas():
    return deepcopy([tool['schema'] for tool in TOOL_REGISTRY.values()])


def call_tool(tool_name, question):
    if not isinstance(tool_name, str) or tool_name not in TOOL_REGISTRY:
        return failure('UNKNOWN_TOOL', 'The requested tool is not registered.')
    if not isinstance(question, str) or not question.strip():
        return failure('INVALID_INPUT', 'Supply a nonempty question.')
    try:
        returned = TOOL_REGISTRY[tool_name]['function'](question)
        if not valid_contract(returned):
            return failure('INVALID_TOOL_RESULT', 'The tool returned an incompatible result shape.')
        return returned
    except Exception as error:
        return failure('TOOL_ERROR', 'The tool request could not be completed.', safe_error=safe_diagnostic(error))
