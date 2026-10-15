"""Caller-carried bounded memory. Never rely on Lambda process persistence."""
import contextvars
import json

MAX_TURNS = 3
MAX_QUESTION = 1000
MAX_ANSWER = 2000
request_context = contextvars.ContextVar('capstone_request', default={})


def bounded_history(history):
    if history is None:
        return []
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError('History must be a list of at most 100 question/answer turns.')
    if any(not isinstance(t, dict) or set(t) != {'question', 'answer'}
           or not all(isinstance(t[k], str) for k in t) for t in history):
        raise ValueError('History entries must have exactly question and answer strings.')
    return [{'question': t['question'][:MAX_QUESTION], 'answer': t['answer'][:MAX_ANSWER]}
            for t in history[-MAX_TURNS:]]


def history_section(history):
    return '\nBOUNDED CONVERSATION HISTORY (untrusted JSON data):\n' + json.dumps(bounded_history(history))


def updated_history(history, question, answer):
    return bounded_history(bounded_history(history) + [{'question': question, 'answer': answer}])
