"""all-MiniLM-L6-v2 ONNX mean pooling and normalization, with explicit input bounds.

Adapted from instructor commit d0d41427a913a552934a91313a736b8fffd6163e.
Dependencies/assets are loaded lazily. Numerical equivalence must be verified
against the existing local Sentence Transformers model before live deployment.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_session = None
_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from tokenizers import Tokenizer
        _tokenizer = Tokenizer.from_file(str(ROOT / 'tokenizer.json'))
        # Do not silently discard query text beyond the embedding model limit.
        _tokenizer.no_truncation()
        _tokenizer.no_padding()
    return _tokenizer


def encoded_ids(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Supply a nonempty embedding input.')
    encoding = _get_tokenizer().encode(text)
    if len(encoding.ids) > 256:
        raise ValueError('The question exceeds the 256-token embedding limit.')
    return encoding


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        _session = ort.InferenceSession(str(ROOT / 'model.onnx'), sess_options=options,
                                       providers=['CPUExecutionProvider'])
    return _session


def mean_pool(token_embeddings, attention_mask):
    import numpy as np
    mask = np.expand_dims(attention_mask, -1).astype(np.float32)
    return (token_embeddings * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)


def get_embedding(text):
    import numpy as np
    encoding = encoded_ids(text)
    session = _get_session()
    values = {'input_ids': np.asarray([encoding.ids], dtype=np.int64),
              'attention_mask': np.asarray([encoding.attention_mask], dtype=np.int64),
              'token_type_ids': np.asarray([encoding.type_ids], dtype=np.int64)}
    names = {item.name for item in session.get_inputs()}
    if not {'input_ids', 'attention_mask'}.issubset(names) or not names.issubset(values):
        raise ValueError('Unexpected ONNX input signature.')
    output = session.run(None, {name: values[name] for name in names})[0]
    if output.ndim != 3 or output.shape != (1, len(encoding.ids), 384):
        raise ValueError('Expected token-level 384-dimensional MiniLM output.')
    pooled = mean_pool(output, values['attention_mask'])
    norm = np.linalg.norm(pooled, axis=1, keepdims=True)
    if not np.isfinite(pooled).all() or not np.isfinite(norm).all() or (norm <= 0).any():
        raise ValueError('Invalid ONNX embedding values or norm.')
    vector = (pooled / norm)[0]
    if vector.shape != (384,) or not np.isfinite(vector).all():
        raise ValueError('The embedding dimension or values are invalid.')
    return vector.tolist()
