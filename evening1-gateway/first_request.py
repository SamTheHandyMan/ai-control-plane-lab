"""Step 1.2 - first request through the local Portkey gateway.

The app code is the stock OpenAI SDK. The ONLY two things that make it talk to
the gateway (and through it, to Groq) are `base_url` and one header.
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")  # keys live in the repo-root .env (git-ignored)

client = OpenAI(
    base_url="http://localhost:8787/v1",          # the gateway, not api.groq.com
    api_key=os.environ["GROQ_API_KEY"],            # SDK sends this as "Authorization: Bearer ..."; gateway forwards it to the provider
    default_headers={"x-portkey-provider": "groq"},  # tells the gateway WHICH provider to translate for
)

resp = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "In one sentence, what is an AI gateway?"}],
)

print("provider model :", resp.model)
print("answer         :", resp.choices[0].message.content)
print("tokens in/out  :", resp.usage.prompt_tokens, "/", resp.usage.completion_tokens)
