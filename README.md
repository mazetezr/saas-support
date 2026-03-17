<div align="center">

# 🤖 Jarvis — AI Support Agent for Telegram

**Deploy a smart, document-aware AI support bot to your Telegram community in minutes.**  
No coding. No dashboards. Just upload your docs and go live.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-@zifrettasupportbot-blue?style=for-the-badge&logo=telegram)](https://t.me/zifrettasupportbot)
[![Track](https://img.shields.io/badge/AI%20Hackathon-User--Facing%20AI%20Agents-orange?style=for-the-badge)](https://github.com/mazetezr/saas-support)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge)](./LICENSE)

</div>

---

## 🌟 What is Jarvis?

**Jarvis** is a production-ready, multi-tenant AI support agent platform built natively for Telegram.

Any project with a Telegram community and documentation — SaaS products, Web3 ecosystems, developer tools, e-commerce platforms, or any niche community — can connect Jarvis to their group and instantly get an intelligent support bot trained on their own knowledge base. The bigger and more complex the documentation, the more Jarvis shines.

The project owner goes through a simple **7-step onboarding entirely inside Telegram** — no external dashboards, no code. They upload their docs (PDF, Word, TXT), configure the bot's persona and rate limits, and Jarvis is live. From that moment, every user question is handled by AI — 24/7.

---

## ✅ Live in Production

> Jarvis MVP is currently running **24/7** as the support bot for **Zifretta Ecosystem** —  
> a TON-based crypto project on Telegram.(Language-Agnostic responses available only in SaaS-version)

👉 Try it: [@zifrettasupportbot](https://t.me/zifrettasupportbot)

This validates the core mechanics: real users, real questions, real-time AI responses on a live TON project.

---

## 🧠 How It Works

```
User sends a question in Telegram group
        │
        ▼
┌──────────────────┐
│  Tenant Resolver │  ← identifies which project this group belongs to
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Rate Limiter    │  ← Redis-based per-user limits (per minute / per day)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────┐
│           RAG Pipeline               │
│                                      │
│  1. Encode query (multilingual-e5)   │
│  2. Cosine similarity search         │
│     in pgvector (top-5 chunks)       │
│  3. Build context from:              │
│     - Retrieved doc chunks           │
│     - Conversation history           │
│     - LLM-compacted summaries        │
│  4. Generate response via LLM        │
│     (OpenRouter, per-tenant key)     │
└────────┬─────────────────────────────┘
         │
         ▼
   Answer sent to Telegram
   in the language the user asked
```

---

## ⚡ Key Features

| Feature | Description |
|---------|-------------|
| 🧠 **RAG Pipeline** | Documents → chunks → embeddings → pgvector → cosine similarity search |
| 🏢 **True Multi-tenancy** | Complete data isolation per project (knowledge base, history, persona, limits) |
| 💬 **Conversation Memory** | Per-user dialogue history with LLM-based summarization for long conversations |
| 🌍 **Language-Agnostic Responses** | Bot replies in whatever language the user writes in — no configuration needed |
| 💳 **Flexible Payments** | Subscriptions paid natively in crypto via Cryptocloud; card payments via Lavatop for non-Web3 projects — no manual processing either way |
| 🔐 **Security First** | API keys encrypted with Fernet, JWT-verified webhooks, Redis rate limiting |
| ⚙️ **Zero-Code Onboarding** | Full setup via 7-step FSM inside Telegram — no dashboard needed |
| 🔄 **Background Workers** | arq-based async jobs for subscription expiry checks and notifications |

---

## 💼 Subscription Plans

| Plan | Price | Knowledge Base |
|------|-------|---------------|
| **Lite** | $5 / mo | 20 chunks |
| **Standard** | $9 / mo | 50 chunks |
| **Pro** | $19 / mo | 100 chunks |
| **Business** | $39 / mo | 200 chunks |

All plans include a **7-day free trial**. Payments processed in crypto via Cryptocloud.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Bot                       │
│              (aiogram 3, async/webhook)              │
└───────────────────────┬─────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌────────────┐ ┌────────────────┐
│  Middleware  │ │  Handlers  │ │  Webhook Server │
│  - Tenant    │ │  - Onboard │ │  (aiohttp)      │
│  - RateLimit │ │  - Menu    │ │  Cryptocloud    │
│  - Language  │ │  - Group   │ │  callbacks      │
│  - Logging   │ │  - Private │ └────────────────┘
└──────┬───────┘ └─────┬──────┘
       │               │
       ▼               ▼
┌─────────────────────────────────┐
│         Service Layer           │
│  - KnowledgeBaseService (RAG)   │
│  - ConversationService          │
│  - LLMService (OpenRouter)      │
│  - SubscriptionService          │
│  - PaymentService               │
└──────────┬──────────────────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌────────┐  ┌──────────────────────────┐
│ Redis  │  │      PostgreSQL 16        │
│        │  │  + pgvector extension     │
│ Cache  │  │                          │
│ FSM    │  │  tenants / plans         │
│ Limits │  │  subscriptions           │
│ Queue  │  │  documents / chunks      │
└────────┘  │  messages / summaries    │
            └──────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.13 |
| **Telegram Framework** | aiogram 3.4+ (async) |
| **Database** | PostgreSQL 16 + pgvector |
| **Cache / Queue** | Redis 7 |
| **LLM** | OpenRouter API (model-agnostic) |
| **Embeddings** | `intfloat/multilingual-e5-small` |
| **Background Jobs** | arq (Redis-based) |
| **Migrations** | Alembic |
| **Document Parsing** | PyMuPDF · python-docx |
| **Payments** | Cryptocloud (crypto) · Lavatop (card) |
| **Encryption** | Fernet (cryptography) |
| **Infrastructure** | Docker · Docker Compose |

---

## 🗄️ Database Schema (8 tables)

```
tenants ──────────── subscriptions ──── plans
   │                      │
   ├──── documents ──── chunks (vector embeddings)
   │
   ├──── messages
   ├──── conversation_summaries
   ├──── user_settings
   └──── faq_candidates
```

- **chunks** — stores `vector(384)` embeddings with HNSW index (`m=16`, `ef_construction=64`)
- **messages** — full conversation history per user per tenant
- **conversation_summaries** — LLM-compacted message batches (triggers at 50+ messages)

---

## 🚀 SaaS Platform Status

The full multi-tenant SaaS version is **architecturally complete**:
- ✅ PostgreSQL schema with full tenant isolation
- ✅ Subscription lifecycle (trial → active → expired)
- ✅ Flexible payment flow (invoice → webhook → activation)
- ✅ 7-step onboarding FSM inside Telegram
- ✅ Background workers for subscription management
- ✅ Redis caching and rate limiting
- ✅ Working MVP running 24/7 in production

**Currently seeking partners and early adopters to launch.**

---

## 🤝 Contact & Partnership

Interested in partnering, investing, or becoming an early adopter?

- **Telegram:** [@mazetezr](https://t.me/mazetezr)
- **GitHub:** [mazetezr](https://github.com/mazetezr)

---

<div align="center">

*Built for the TON AI Hackathon — User-Facing AI Agents track*

</div>
