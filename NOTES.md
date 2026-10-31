# Learning log

Format for each step: heading, the command(s), what happened, and 1–2 sentences on how I'd explain it in an interview.

## Setup

### Prerequisites check (2026-10-31)

- Node 22.0.0, Python 3.11.1, git 2.31 already installed.
- GitHub CLI, Docker and uv not installed. Only `gh` is needed (to create the repo from the terminal).

---

## Evening 1 — gateway, routing, guardrails, logs

### Step 1.1 — Run the open-source Portkey gateway locally

Docs used: Portkey gateway README (github.com/Portkey-AI/gateway), docs/installation-deployments.md in that repo, and the route table in `src/index.ts`.

**Commands**

```bash
npx @portkey-ai/gateway          # terminal 1, stays in the foreground
curl.exe http://localhost:8787/  # terminal 2
```

**What happened**

- Gateway started on port 8787 and printed `Ready for connections!` plus a UI link at `http://localhost:8787/public/`.
- `GET /` returned the plain text `AI Gateway says hey!`. There is no dedicated `/health` route in the OSS gateway; the root path is what you poll.
- The gateway is a single Node process. It holds no state and no keys yet; it only becomes useful once a request tells it which provider to talk to.

**How I'd explain it in an interview**

An AI gateway is a reverse proxy between every app and every model provider: apps speak one API, the gateway translates and is the one place to enforce keys, routing, guardrails and logging. Consumers never hold provider keys because a key in fifty repos cannot be rotated or attributed; a key in one gateway can.


**Concept: "stateless"**

The gateway remembers nothing between requests. Each request carries everything it needs (provider header, key, config); the gateway forwards it, streams the reply, writes a log line and forgets. Consequences: any replica can serve any request (no sticky sessions), a crashed replica loses nothing permanent, Kubernetes can scale pods freely, and the same code runs as a Cloudflare Worker, a container or a plain Node process. Stateless does not mean "no data": logs and metrics are written *out* to another system, and policy is read *in* from config at request time; nothing lives only inside the process. Contrast with the LangGraph agent in evening 2, which is stateful by design (a checkpointer remembers where a run paused). Clean split for interviews: the gateway is a stateless policy enforcement point; the agent runtime is where state lives.

### Step 1.2 — First request through the gateway

Docs used: Portkey headers reference (portkey.ai/docs/api-reference/inference-api/headers), provider slugs in gateway `src/globals.ts`, Groq model list (console.groq.com/docs/models).

**Command**

```bash
cd evening1-gateway
.\.venv\Scripts\python.exe first_request.py
```

Script: stock `openai` SDK with `base_url="http://localhost:8787/v1"`, `api_key=GROQ_API_KEY` (sent as `Authorization: Bearer`, forwarded to the provider) and one header `x-portkey-provider: groq`.

**What happened**

- First attempt failed with `404 - groq error: The model llama-3.1-8b-instant does not exist or you do not have access to it`. Groq now labels the Llama models "Enterprise", so the free key cannot use them. Switched to `openai/gpt-oss-20b`.
- That 404 was itself informative: the error text was Groq's, relayed verbatim, so app → gateway → Groq was already authenticated and working. The gateway passes upstream errors through transparently.
- Second attempt: `provider model: openai/gpt-oss-20b`, 81 tokens in / 104 out, a one-sentence answer. (The model described an IoT edge gateway rather than an LLM gateway. A small model misreading an ambiguous prompt is exactly the kind of thing the evening-2 evals are for.)

**Why the client is called `OpenAI` when we talk to Groq**

"OpenAI" names the wire format, not the company. The chat-completions request/response shape is the de facto standard; Groq's API is natively compatible, and the gateway accepts it on the way in and translates it for providers with their own formats (Anthropic `/v1/messages`, Gemini `generateContent`). Standardising every app on one SDK and one shape is what makes the gateway drop-in: an existing OpenAI-SDK app needs a one-line `base_url` change.

**How I'd explain it in an interview**

Unified API: the app speaks one request shape and changes nothing when the provider changes; the gateway owns the translation. I proved it by sending an OpenAI-SDK request to a Groq model through a local gateway with a single header to pick the provider.
