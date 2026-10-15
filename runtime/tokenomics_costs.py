"""Price each actual LLM record once; unknown usage or unsupported billing stays unknown."""
import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUPS = ['router', 'sql_agent', 'retrieval_agent', 'synthesis', 'unclassified']


def load_pricing():
    return json.loads((ROOT / 'pricing.json').read_text())


def count(value):
    return type(value) is int and value >= 0


def number(value):
    return float(value.quantize(Decimal('0.000000001')))


def group(record):
    component = record.get('component')
    if component in {'sql_generation', 'sql_interpretation'}:
        return 'sql_agent'
    if component == 'retrieval_generation':
        return 'retrieval_agent'
    if component == 'synthesis':
        return 'synthesis'
    if component in {'router', 'routing', 'classification'}:
        return 'router'
    return 'unclassified'


def rate_for(model, pricing):
    if not isinstance(model, str):
        return None
    profile = model.rsplit('/', 1)[-1]
    match = re.fullmatch(r'(global|us|eu|apac|au|jp)\.anthropic\.claude-sonnet-4-6', profile)
    if not match:
        return None
    multiplier = Decimal('1') if match[1] == 'global' else Decimal(pricing['regional_multiplier'])
    return {'input_per_million': Decimal(pricing['global_input_per_million']) * multiplier,
            'output_per_million': Decimal(pricing['global_output_per_million']) * multiplier,
            'profile_scope': match[1]}


def price_records(records, *, complete=True, pricing=None):
    pricing = pricing or load_pricing()
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError('Supply a list of individual actual LLM usage records.')
    totals = {g: Decimal('0') for g in GROUPS}
    rows = []
    unknown_groups = set()
    for index, record in enumerate(records):
        incoming = record.get('input_tokens', record.get('input'))
        outgoing = record.get('output_tokens', record.get('output'))
        category = group(record)
        rate = rate_for(record.get('model'), pricing)
        errors = []
        if not count(incoming) or not count(outgoing):
            errors.append('missing or invalid actual token counts')
        if rate is None:
            errors.append('model/profile is outside the verified price table')
        raw = record.get('usage')
        if isinstance(raw, dict):
            if any(raw.get(k, 0) not in (0, None) for k in ['cache_creation_input_tokens', 'cache_read_input_tokens']):
                errors.append('cache tokens require a separate cache price calculation')
            if raw.get('service_tier') not in {None, 'standard'}:
                errors.append('service tier differs from assumed standard pricing')
        row = {'record_number': index + 1, 'component': record.get('component'), 'group': category,
            'model': record.get('model'), 'input_tokens': incoming, 'output_tokens': outgoing,
            'raw_billing_telemetry_present': isinstance(raw, dict), 'pricing_errors': errors}
        if errors:
            row['calculated_cost_usd'] = None
            unknown_groups.add(category)
        else:
            amount = (Decimal(incoming) * rate['input_per_million'] +
                      Decimal(outgoing) * rate['output_per_million']) / Decimal('1000000')
            totals[category] += amount
            row.update(calculated_cost_usd=number(amount),
                input_per_million_usd=str(rate['input_per_million']),
                output_per_million_usd=str(rate['output_per_million']), profile_scope=rate['profile_scope'])
        rows.append(row)
    all_priced = complete is True and not unknown_groups
    subtotal = sum(totals.values())
    costs = {g + '_cost': None if g in unknown_groups else number(totals[g]) for g in GROUPS}
    return {**costs, 'currency': 'USD', 'total_cost': number(subtotal) if all_priced else None,
        'known_priced_subtotal_usd': number(subtotal), 'complete': all_priced,
        'cost_per_1000_queries': number(subtotal * 1000) if all_priced else None,
        'projection_note': '1000 repetitions with identical actual token volumes and the same assumed prices; not a measured future bill.',
        'actual_reported_llm_calls': len(records),
        'actual_known_input_tokens': sum(r.get('input_tokens', r.get('input', 0)) for r in records
                                       if count(r.get('input_tokens', r.get('input')))),
        'actual_known_output_tokens': sum(r.get('output_tokens', r.get('output', 0)) for r in records
                                        if count(r.get('output_tokens', r.get('output')))),
        'unpriced_groups': sorted(unknown_groups), 'usage_completeness_from_orchestrator': complete is True,
        'records': rows, 'pricing_verified_date': pricing['verified_date'],
        'billing_assumptions': pricing['billing_assumptions'], 'pricing_sources': pricing['sources'],
        'most_expensive_group': max(totals, key=totals.get) if all_priced and subtotal else None}


def _records(tokens, default_component):
    if tokens is None:
        return []
    if isinstance(tokens, dict) and 'records' in tokens:
        raise ValueError('This is whole-query usage. Use calculate_state_cost(state), or pass state["synthesis_usage"] for synthesis only.')
    rows = tokens if isinstance(tokens, list) else [tokens]
    if any(not isinstance(r, dict) for r in rows):
        raise ValueError('Usage must be a dictionary or list of dictionaries.')
    return [{'component': default_component, **r} for r in rows]


def calculate_full_query_cost(sql_tokens=None, retrieval_tokens=None, synthesis_tokens=None,
                              router_tokens=None, *, pricing=None, complete=True):
    """Lesson-compatible interface. A SQL list includes BOTH generation and interpretation."""
    records = (_records(sql_tokens, 'sql_generation') + _records(retrieval_tokens, 'retrieval_generation')
               + _records(synthesis_tokens, 'synthesis') + _records(router_tokens, 'router'))
    return price_records(records, pricing=pricing, complete=complete)


def calculate_state_cost(state, *, pricing=None):
    """The existing top-level records already contain each worker + synthesis call once."""
    aggregate = state.get('token_usage') or {}
    if not isinstance(aggregate.get('records'), list):
        return price_records([], complete=False, pricing=pricing)
    result = price_records(aggregate['records'], complete=aggregate.get('complete') is True, pricing=pricing)
    # Do not silently accept mismatches between summary counts and itemized records.
    for total_key, known_key in [('input', 'actual_known_input_tokens'), ('output', 'actual_known_output_tokens')]:
        total = aggregate.get(total_key)
        if total is not None and total != result[known_key]:
            result.update(complete=False, total_cost=None, cost_per_1000_queries=None,
                accounting_error='Orchestrator aggregate disagrees with its individual records.')
    return result
