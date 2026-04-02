import httpx

class _AttrDict(dict):
                    def __getattr__(self, item):
                        try:
                            return self[item]
                        except KeyError as err:
                            raise AttributeError(item) from err

def _to_attrdict(value):
    if isinstance(value, dict):
        return _AttrDict({k: _to_attrdict(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_attrdict(v) for v in value]
    return value

class _OpenRouterCompletions:
    def __init__(self, _api_key: str):
        self.api_key = _api_key

    def create(self,
                model: str,
                messages: list,
                tools: list | None = None,
                temperature: float | None = None):
        payload = {
            'model': model,
            'messages': messages,
        }
        if tools is not None:
            payload['tools'] = tools
        if temperature is not None:
            payload['temperature'] = temperature

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return _to_attrdict(data)

class _OpenRouterChat:
    def __init__(self, _api_key: str):
        self.completions = _OpenRouterCompletions(_api_key)

    # Keep compatibility with existing call style in _interpret_offer_llm
    def __call__(self, model: str, messages: list):
        result = self.completions.create(model=model, messages=messages)
        content = ''
        if getattr(result, 'choices', None):
            first = result.choices[0]
            content = getattr(getattr(first, 'message', None), 'content', '') or ''
        return {'message': {'content': content}}

class OpenRouterClient:
    def __init__(self, _api_key: str):
        self.chat = _OpenRouterChat(_api_key)