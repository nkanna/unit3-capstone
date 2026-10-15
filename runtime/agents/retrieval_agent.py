"""Registry adapter preserving honest refusals and citation-check limitations."""
from backends import retrieval_backend, safe_diagnostic


def run_retrieval_agent(question):
    if not isinstance(question, str) or not question.strip():
        return {'success': False, 'answer': 'Supply a nonempty question.', 'sources': [],
                'metadata': {'status': 'INVALID_INPUT'}}
    try:
        returned = retrieval_backend().run_retrieval_agent(question)
        metadata = dict(returned['metadata'])
        chunks = metadata.get('chunks', [])
        check = metadata.get('citation_check') or {}
        metadata.update(chunk_count=len(chunks), chunk_scores=[c.get('score') for c in chunks],
                        grounded=bool(check.get('passed', False)),
                        grounding_check_kind='citation format/range only; manual factual review is separate')
        return {'success': bool(returned['success']), 'answer': returned['answer'],
                'sources': returned['sources'], 'metadata': metadata}
    except Exception as error:
        return {'success': False, 'answer': 'The document request could not be completed.', 'sources': [],
                'metadata': {'status': 'ERROR', 'safe_error': safe_diagnostic(error)}}
