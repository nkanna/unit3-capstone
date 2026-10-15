"""Read-only access to the selected existing OpenSearch index; no creation/remapping."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from backends import safe_diagnostic

ROOT = Path(__file__).resolve().parent


def configuration():
    selection = json.loads((ROOT / 'selected-corpus.json').read_text())
    config = {k: selection[k] for k in ['index', 'region', 'domain', 'endpoint', 'bucket']}
    if os.getenv('OPENSEARCH_ENDPOINT'):
        config['endpoint'] = os.environ['OPENSEARCH_ENDPOINT']
    if os.getenv('OPENSEARCH_INDEX'):
        config['index'] = os.environ['OPENSEARCH_INDEX']
    return config


def get_opensearch_client(session, config):
    from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
    endpoint = config['endpoint']
    parsed = urlsplit(endpoint if '://' in endpoint else 'https://' + endpoint)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/') or not (parsed.hostname or '').endswith('.es.amazonaws.com')):
        raise ValueError('Expected a managed OpenSearch HTTPS endpoint.')
    credentials = session.get_credentials()
    if credentials is None:
        raise ValueError('AWS credentials are unavailable.')
    return OpenSearch(hosts=[{'host': parsed.hostname, 'port': 443}],
        http_auth=AWSV4SignerAuth(credentials, config['region'], 'es'),
        use_ssl=True, verify_certs=True, connection_class=RequestsHttpConnection,
        timeout=30, max_retries=0, retry_on_timeout=False)


def create_index_readonly(client, index):
    info = client.info()
    mapping = client.indices.get_mapping(index=index)[index]['mappings']
    vector = mapping.get('properties', {}).get('embedding', {})
    if (mapping.get('_meta', {}).get('embedding_model') != 'sentence-transformers/all-MiniLM-L6-v2'
            or vector.get('dimension') != 384 or vector.get('type') != 'knn_vector'
            or vector.get('method', {}).get('name') != 'hnsw'
            or vector.get('method', {}).get('space_type') != 'cosinesimil'
            or vector.get('method', {}).get('engine') != 'lucene'):
        raise ValueError('The existing 384-dimensional Lucene cosine mapping must be preserved.')
    return {'version': info.get('version', {}).get('number'), 'engine': 'lucene', 'dimension': 384}


safe_error = safe_diagnostic
