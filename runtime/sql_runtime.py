"""Self-contained SELECT execution preserving the existing AST policy and bounded reads."""
import os
from pathlib import Path

from sql_validator import validate_sql
from backends import safe_diagnostic

ROOT = Path(__file__).resolve().parent
SCHEMA_CONTEXT = (ROOT / 'SCHEMA.md').read_text()


def connect():
    import psycopg2
    cert = ROOT / 'rds-ca.pem'
    if not cert.is_file():
        raise ValueError('The RDS CA bundle must be included in the deployment package.')
    return psycopg2.connect(host=os.environ['RDS_HOST'], port=int(os.getenv('RDS_PORT', '5432')),
        dbname=os.environ['RDS_DATABASE'], user=os.environ['RDS_USER'], password=os.environ['RDS_PASSWORD'],
        connect_timeout=10, sslmode='verify-full', sslrootcert=str(cert),
        options='-c statement_timeout=30000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=30000')


def execute_query_safely(sql):
    validation = validate_sql(sql)
    if not validation['valid']:
        return {'success': False, 'validation': 'BLOCKED', 'sql': sql,
                'error': validation['reason'], 'execution_attempted': False}
    connection = None
    try:
        connection = connect()
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description is None:
                raise ValueError('The query did not return a result set.')
            rows = cursor.fetchmany(21)
            return {'success': True, 'validation': 'PASSED', 'sql': sql,
                'columns': [item[0] for item in cursor.description],
                'rows': rows[:20], 'truncated': len(rows) > 20, 'execution_attempted': True}
    except Exception as error:
        return {'success': False, 'validation': 'EXECUTION_ERROR', 'sql': sql,
                'error': safe_diagnostic(error), 'execution_attempted': True}
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()


execute_query = execute_query_safely
