"""Shared Bedrock helper: real usage, closed streams, no automatic generation retry."""
import json
import os
import boto3
from botocore.config import Config


def get_model_id(session=None):
    session = session or boto3.Session()
    region = os.getenv('AWS_REGION', 'us-east-1')
    configured = os.getenv('BEDROCK_MODEL_ID')
    if configured:
        if ':inference-profile/' not in configured:
            raise ValueError('Use the full Bedrock inference profile ARN.')
        return configured
    account = session.client('sts', region_name=region).get_caller_identity()['Account']
    return f'arn:aws:bedrock:{region}:{account}:inference-profile/us.anthropic.claude-sonnet-4-6'


def invoke_claude(prompt, max_tokens=500):
    session = boto3.Session()
    model = get_model_id(session)
    client = session.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'),
                            config=Config(retries={'total_max_attempts': 1}, read_timeout=180))
    response = client.invoke_model(modelId=model, contentType='application/json', accept='application/json',
        body=json.dumps({'anthropic_version': 'bedrock-2023-05-31', 'max_tokens': max_tokens,
                         'messages': [{'role': 'user', 'content': prompt}]}))
    stream = response['body']
    try:
        result = json.loads(stream.read())
    finally:
        stream.close()
    usage = result.get('usage') or {}
    return {'text': ''.join(b.get('text', '') for b in result.get('content', []) if b.get('type') == 'text').strip(),
            'model': model, 'stop_reason': result.get('stop_reason'), 'usage': usage,
            'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens')}


def safe_error(error):
    return type(error).__name__
