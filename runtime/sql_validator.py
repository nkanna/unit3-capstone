"""Conservative PostgreSQL SELECT policy for the four-table training database."""
import sqlglot
from sqlglot import exp
from sqlglot.dialects import Dialect
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType

BLOCKED_KEYWORDS = {
    'DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE',
    'EXEC', 'EXECUTE', 'GRANT', 'REVOKE', 'COPY', 'CALL', 'DO',
    'CREATE', 'SET', 'RESET', 'INTO', 'LOCK',
}
ALLOWED_TABLES = {'clients', 'projects', 'consultants', 'invoices'}
# Small allow-list for this lab. Unknown or qualified functions require review.
ALLOWED_FUNCTIONS = {
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'NULLIF', 'ROUND',
    'ABS', 'LOWER', 'UPPER', 'LENGTH', 'CHAR_LENGTH', 'CAST', 'TRY_CAST',
    'EXTRACT', 'DATE_TRUNC', 'TIMESTAMP_TRUNC', 'CURRENT_DATE', 'CURRENT_TIMESTAMP',
}


def denied(reason):
    return {'valid': False, 'reason': 'Blocked: ' + reason}


def validate_sql(query):
    """Check before connecting. Original SQL is executed; no AST rewriting."""
    if not isinstance(query, str) or not query.strip():
        return denied('query is empty.')
    if len(query) > 20000:
        return denied('query exceeds the training limit of 20,000 characters.')
    try:
        tokens = Dialect.get_or_raise('postgres').tokenize(query)
        if not tokens or tokens[0].token_type != TokenType.SELECT:
            return denied('only SELECT queries are permitted; query must begin with SELECT.')
        semicolons = [i for i, token in enumerate(tokens) if token.token_type == TokenType.SEMICOLON]
        if semicolons and (len(semicolons) != 1 or semicolons[0] != len(tokens) - 1):
            return denied('multiple statements or extra statement delimiters detected.')
        for token in tokens:
            # Literal values and quoted identifiers are not executable keywords.
            if token.token_type not in (TokenType.STRING, TokenType.IDENTIFIER):
                if token.text.upper() in BLOCKED_KEYWORDS:
                    return denied(f"'{token.text.upper()}' is not permitted.")
        # Quoted callable names can be normalized by the parser into operator
        # nodes (e.g. "AND"(...)). Reject those calls before AST classification.
        for first, second in zip(tokens, tokens[1:]):
            if first.token_type == TokenType.IDENTIFIER and second.token_type == TokenType.L_PAREN:
                return denied('quoted function calls are outside the training allow-list.')
        # SQLGlot can return an empty/semicolon entry for a comment after the final
        # semicolon. Executable delimiters were checked independently above.
        trees = [tree for tree in sqlglot.parse(query, read='postgres')
                 if tree is not None and not isinstance(tree, exp.Semicolon)]
        if len(trees) != 1 or trees[0] is None:
            return denied('exactly one SELECT statement is required.')
        tree = trees[0]
        if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            return denied('only SELECT result queries are permitted.')
        for node in tree.walk():
            if isinstance(node, (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock)):
                return denied('modifying statements, SELECT INTO, and locking reads are not permitted.')
        for table in tree.find_all(exp.Table):
            if not isinstance(table.this, exp.Identifier):
                return denied('table-valued functions are not permitted.')
            if table.catalog or table.db not in ('', 'public') or table.name not in ALLOWED_TABLES:
                return denied(f'table {table.sql()} is outside the four-table training scope.')
        for function in tree.find_all(exp.Func):
            # SQLGlot includes logical operators and conditional/subquery syntax
            # in Func. These nodes do not represent callable SQL functions.
            if isinstance(function, (exp.And, exp.Or, exp.Case, exp.Exists)):
                continue
            if isinstance(function, exp.If) and isinstance(function.parent, exp.Case):
                continue
            name = function.name.upper() if isinstance(function, exp.Anonymous) else function.sql_name().upper()
            if isinstance(function.parent, exp.Dot) or name not in ALLOWED_FUNCTIONS:
                return denied(f'function {name} is outside the training allow-list.')
        return {'valid': True, 'reason': 'OK'}
    except (ParseError, TokenError, ValueError, RecursionError):
        return denied('query could not be parsed as supported PostgreSQL SQL.')
