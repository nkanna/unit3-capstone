"""Read-query review policy plus expiring, exact-byte HMAC confirmation receipts."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import sqlglot
from sqlglot import exp
from memory import bounded_history

TTL_SECONDS = 1800


def unusual_query(sql):
    """Review unrestricted detail reads, unlimited wildcard reads, or >2-table joins.

    Scalar aggregates such as COUNT/SUM without GROUP BY are routine. A lookup
    naming columns with WHERE is routine. Wildcard reads without LIMIT require
    review even with WHERE, since an entity filter can still return many rows.
    """
    tree = sqlglot.parse_one(sql, read='postgres')
    reasons = []
    for select in tree.find_all(exp.Select):
        tables = {t.sql(dialect='postgres') for t in select.find_all(exp.Table)}
        if not tables:
            continue
        limited = select.args.get('limit') is not None
        aggregate_only = (not select.args.get('group') and bool(select.expressions)
                          and all(e.find(exp.AggFunc) is not None for e in select.expressions))
        wildcards = any(e.is_star or (e.find(exp.Star) is not None and not e.find(exp.AggFunc))
                        for e in select.expressions)
        if wildcards and not limited:
            reasons.append('Wildcard projection without LIMIT, including filtered wildcard reads.')
        elif not select.args.get('where') and not limited and not aggregate_only:
            reasons.append('Detail read without WHERE or LIMIT.')
        if len(tables) > 2:
            reasons.append('Query reads more than two distinct tables.')
    return {'unusual': bool(reasons), 'reasons': sorted(set(reasons))}


def _key():
    value = os.getenv('CONFIRMATION_SIGNING_KEY', '')
    if len(value) < 43:
        raise ValueError('A persistent private confirmation signing key is required.')
    return value.encode()


def _target():
    values = [os.getenv(k, '') for k in ['RDS_HOST', 'RDS_DATABASE', 'RDS_USER']]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def issue(sql, question, history, route, resolved_question):
    data = {'v': 1, 'sql': sql, 'question': question, 'history': bounded_history(history),
            'route': route, 'resolved_question': resolved_question, 'target': _target(),
            'expires': int(time.time()) + TTL_SECONDS, 'nonce': secrets.token_hex(16)}
    body = _b64(json.dumps(data, separators=(',', ':'), sort_keys=True).encode())
    signature = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return body + '.' + signature


def verify(confirmation, history=None):
    if not isinstance(confirmation, dict) or set(confirmation) != {'token', 'sql'}:
        raise ValueError('Confirmation must contain the token and the exact flagged SQL.')
    token, sql = confirmation['token'], confirmation['sql']
    if not isinstance(token, str) or len(token) > 30000 or not isinstance(sql, str):
        raise ValueError('Invalid confirmation request.')
    try:
        body, signature = token.split('.')
        expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid signature.')
        data = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        if (data.get('v') != 1 or type(data.get('expires')) is not int
                or data['expires'] <= int(time.time()) or data.get('target') != _target()
                or data.get('route') not in {'sql', 'both'} or data.get('sql') != sql
                or not isinstance(data.get('question'), str) or not isinstance(data.get('resolved_question'), str)
                or data.get('history') != bounded_history(data.get('history'))):
            raise ValueError('Confirmation expired or its context/SQL changed.')
        if history is not None and bounded_history(history) != data['history']:
            raise ValueError('Confirmation history differs from its signed context.')
        return data
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ValueError('Confirmation rejected: signature, expiry, SQL, or context differs.') from None
