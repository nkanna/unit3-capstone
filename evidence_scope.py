"""Conservative AST evidence checks for the Acme memory exercise."""
import sqlglot
from sqlglot import exp


def conjuncts(node):
    if isinstance(node, exp.Paren):
        return conjuncts(node.this)
    if isinstance(node, exp.And):
        return conjuncts(node.this) + conjuncts(node.expression)
    # Never treat a predicate inside OR, NOT, EXISTS or another scope as a
    # mandatory filter for this SELECT.
    return [node]


def acme_scope(sql, client_id):
    """Recognize name/ID filters bound to real root tables and project joins.

    This deliberately supports a narrow set of provable shapes; complex
    equivalent SQL remains a manual-review case, never an automatic pass.
    """
    try:
        tree = sqlglot.parse_one(sql, read='postgres')
        if not isinstance(tree, exp.Select) or not tree.args.get('where'):
            return False
        direct = []
        from_ = tree.args.get('from_')
        if from_:
            direct.append(from_.this)
        direct += [j.this for j in tree.args.get('joins', [])]
        tables = [t for t in direct if isinstance(t, exp.Table)]
        clients = {t.alias_or_name.lower() for t in tables if t.name.lower() == 'clients'}
        projects = {t.alias_or_name.lower() for t in tables if t.name.lower() == 'projects'}
        where = conjuncts(tree.args['where'].this)
        join_terms = []
        for join in tree.args.get('joins', []):
            if join.args.get('on') is not None:
                join_terms += conjuncts(join.args['on'])
        def column(value):
            if not isinstance(value, exp.Column):
                return None
            table = value.table.lower()
            if not table and len(tables) == 1:
                table = tables[0].alias_or_name.lower()
            return table, value.name.lower()
        def related(client):
            if not projects:
                return True
            for term in where + join_terms:
                if isinstance(term, exp.EQ):
                    pair = {column(term.this), column(term.expression)}
                    if any(pair == {(client, 'id'), (p, 'client_id')} for p in projects):
                        return True
            return False
        for term in where:
            if not isinstance(term, exp.EQ):
                continue
            for left, right in [(term.this, term.expression), (term.expression, term.this)]:
                ref = column(left)
                if ref is None or not isinstance(right, exp.Literal):
                    continue
                table, field = ref
                if table in clients and related(table):
                    if field == 'id' and not right.is_string and str(right.this) == str(client_id):
                        return True
                    if field == 'name' and right.is_string and right.this == 'Acme Corp':
                        return True
                if table in projects and field == 'client_id' and not right.is_string and str(right.this) == str(client_id):
                    return True
        return False
    except (ValueError, TypeError, sqlglot.errors.ParseError):
        return False


def verify_scope(sql, directory):
    """Verify the ID with a separate validated lookup; never execute flagged SQL."""
    from capstone import configure_local, save
    configure_local()
    from agents.sql_agent import execute_validated_sql
    lookup = "SELECT id, name FROM clients WHERE name = 'Acme Corp';"
    result = execute_validated_sql(lookup)
    rows = result.get('rows') or []
    valid = (result.get('success') is True and result.get('validation') == 'PASSED'
             and len(rows) == 1 and rows[0][1] == 'Acme Corp' and type(rows[0][0]) is int)
    matched = valid and acme_scope(sql, rows[0][0])
    from pathlib import Path
    save(Path(directory) / 'acme-scope-evidence.json', {
        'lookup_sql': lookup, 'lookup_validation': result.get('validation'),
        'actual_lookup_rows': rows, 'flagged_sql': sql,
        'scope_check_passed': matched, 'flagged_query_executed_by_this_check': False,
        'method': 'Mandatory root WHERE predicate, verified client ID/name and project/client join binding.'})
    return matched
