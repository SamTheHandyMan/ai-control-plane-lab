"""Step 1.3 - routing config: Groq primary, Gemini fallback, retries, timeout.

Compare with first_request.py: the app no longer names a provider, a model or a
provider key. All of that moved into fallback_config.json. In production that
config lives in the gateway (or a config store) and the app only sends an ID;
here we send the JSON inline in the `x-portkey-config` header so you can see it.
"""
import json, os, string
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")

# The committed JSON holds ${PLACEHOLDERS}; real keys are filled in from .env at
# runtime so no secret is ever written to the repo.
config = string.Template(open("fallback_config.json").read()).substitute(os.environ)

client = OpenAI(
    base_url="http://localhost:8787/v1",
    api_key="not-used",                                  # SDK insists on a value; the gateway uses the keys in the config
    default_headers={"x-portkey-config": json.dumps(json.loads(config))},
    max_retries=0,                                       # let the GATEWAY own retries, not the SDK
)

resp = client.chat.completions.create(
    model="ignored-see-config",                          # override_params in the config sets the real model per target
    messages=[{"role": "user", "content": "Reply with the single word: pong"}],
)

print("served by      :", resp.model)
print("answer         :", resp.choices[0].message.content)
print("tokens in/out  :", resp.usage.prompt_tokens, "/", resp.usage.completion_tokens)
