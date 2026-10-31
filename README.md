# AI Control Plane Lab

A small hands-on lab to understand what an enterprise **AI control plane** does, by running the pieces locally:

- **Evening 1 — gateway:** open-source Portkey gateway, unified API, fallback routing, guardrail hooks, request logs.
- **Evening 2 — agent:** a LangGraph agent calling the model *through* the gateway, one MCP tool, human-in-the-loop, tracing, a tiny eval.
- **Evening 3 (optional) — Google ADK quickstart.**

The goal is understanding, not a polished product. Everything is minimal and heavily commented.

The learning log, step by step, is in [NOTES.md](NOTES.md).

## Setup

1. Copy `.env.example` to `.env` and fill in your keys. `.env` is git-ignored and must never be committed.
2. Each `eveningN-*/` folder has its own `requirements.txt`.
