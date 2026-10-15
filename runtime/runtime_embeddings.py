"""Compatibility adapter for the verified retrieval code, using local ONNX assets."""
from onnx_embed import encoded_ids, get_embedding

MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'


class Model:
    max_seq_length = 256

    def tokenizer(self, text, **kwargs):
        return {'input_ids': encoded_ids(text).ids}


def get_model():
    return Model()


def test_search(query, client, *, index, ingestion_ids, k=3, model=None):
    if not isinstance(query, str) or not query.strip() or type(k) is not int or not 1 <= k <= 10 or not ingestion_ids:
        raise ValueError('Supply a question, selected IDs, and top-k from 1 to 10.')
    vector = get_embedding(query)
    response = client.search(index=index, body={'size': k,
        '_source': ['content', 'source', 'chunk_number', 'page_number', 'ingestion_id', 'embedding_model'],
        'query': {'knn': {'embedding': {'vector': vector, 'k': k,
                                     'filter': {'terms': {'ingestion_id': ingestion_ids}}}}}})
    hits = []
    for hit in response.get('hits', {}).get('hits', []):
        source = hit['_source']
        if source.get('ingestion_id') not in ingestion_ids or source.get('embedding_model') != MODEL_NAME:
            raise ValueError('Search returned a document outside the selected corpus or model.')
        hits.append({'id': hit['_id'], 'score': hit['_score'], **source})
    return {'query': query, 'hits': hits}
