"""One bounded startup probe inside the pinned Hermes image; no AWS/user data."""
import json
import os
import sys
from pathlib import Path


def failure(status=None, message=''):
    text = message.lower()
    if 'context' in text and any(x in text for x in ('length', 'window', 'maximum')):
        return 'CE-MODEL-CONTEXT: Request exceeds model context. Configure a reasoning model with 64k+ context in Hermes.'
    if status in (401, 403):
        return 'CE-MODEL-AUTH: Provider denied access. Check the key, account permissions and endpoint.'
    if status == 404:
        return 'CE-MODEL-ENDPOINT: Check the model ID and API base URL in Hermes.'
    if status == 429:
        return 'CE-MODEL-QUOTA: Provider rate/quota limit. Check quota, rate limits and permitted plan usage; no automatic retry.'
    return 'CE-MODEL-CONNECTION: Probe failed. Check endpoint/network and Hermes provider configuration; no credentials logged.'


def main():
    import hermes_yaml as yaml
    from openai import OpenAI
    retained, seed = (Path(p) for p in sys.argv[1:3])
    config = yaml.safe_load((retained if retained.is_file() else seed).read_text())
    model = config.get('model', {})
    if model.get('provider') != 'custom':
        raise SystemExit('CE-MODEL-PROVIDER: CE startup probe supports the custom OpenAI-compatible configuration. See docs/MODELS.md and Hermes provider setup.')
    key = os.environ.get(model.get('key_env', 'MODEL_API_KEY'), '')
    if not key:
        raise SystemExit('CE-MODEL-AUTH: Configured key environment variable is missing. Check key delivery; no values logged.')
    tool = {'type':'function','function':{'name':'ce_probe','description':'Confirm tool calling works. No side effects.','parameters':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}}}
    try:
        client = OpenAI(api_key=key, base_url=model['base_url'], max_retries=0, timeout=40)
        response = client.chat.completions.create(model=model['default'],
            messages=[{'role':'user','content':'Call ce_probe with ok=true. This is a startup connectivity test.'}],
            tools=[tool], tool_choice='auto', max_tokens=1024)
        calls = response.choices[0].message.tool_calls or []
        if not any(c.function.name == 'ce_probe' and json.loads(c.function.arguments) == {'ok':True} for c in calls):
            raise SystemExit('CE-MODEL-TOOLS: Model did not return the required tool call. Use a reasoning model with reliable tool calling.')
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(failure(getattr(exc, 'status_code', None), str(exc))) from None
    print('CE model probe PASS: one tool-call request; no evidence or knowledge sent. This does not prove the full context capacity.')


if __name__ == '__main__':
    main()
