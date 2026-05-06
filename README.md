# Hackonomics 2026 — MyEconoCoach

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/Django_REST_Framework-3.x-red)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.x-37814A?logo=celery&logoColor=white)
![Kafka](https://img.shields.io/badge/Apache_Kafka-4.1-231F20?logo=apachekafka&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-1.9-FF4B4B)
![Gemini](https://img.shields.io/badge/Google_Gemini-AI-4285F4?logo=google&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-37%2F37_passed-brightgreen)

## 1. Project Overview

**MyEconoCoach** is a personal financial coaching platform built with Django. It helps individuals understand and optimize their finances by combining real-time economic data, AI-generated insights, and intelligent calendar planning.

### What it does

| Domain | Capability |
|--------|-----------|
| **Authentication** | Ory Kratos JWKS JWT sessions, Google OAuth 2.0, httpOnly cookie transport |
| **Financial Profile** | Store country, currency, annual income, and monthly investable amount |
| **Exchange Rates** | Live USD conversion rates and historical rate charts |
| **Investment Simulation** | Compare Dollar-Cost Averaging (USD) vs fixed-term deposit returns |
| **Business News** | Country-specific business news fetched and summarized via Google Gemini |
| **AI News Chat** | RAG-powered chat over business news with semantic + keyword hybrid search |
| **Smart Calendar** | Financial event calendar with categories, cost tracking, and Google Calendar sync |
| **AI Calendar Advice** | Upload a financial document; Gemini analyzes it and suggests calendar changes |
| **Event Streaming** | Kafka-based outbox pattern for reliable domain event publishing |

---

## 2. Tech Stack

### Core

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Web Framework | Django 5.2 |
| API Framework | Django REST Framework |
| Database | PostgreSQL 15 (psycopg3) |

### Infrastructure

| Service | Role |
|---------|------|
| Redis 7 | JWKS key cache · Celery broker/backend · distributed locks |
| Celery 5 | Async task queue (news fetch) + Beat scheduler (every 6 hours) |
| Apache Kafka 4.1 | Domain event streaming via transactional outbox pattern |
| Qdrant 1.9 | Vector database for RAG semantic search |

### AI & ML

| Library | Role |
|---------|------|
| `google-genai` | Business news generation & calendar advice via Gemini |
| `fastembed` | Text embeddings (BGE-small) + cross-encoder reranking (BGE Reranker) |
| `torch` (CPU) | PyTorch runtime for FastEmbed models |

> **⚠️ PyTorch CPU Wheel**
> `fastembed` depends on PyTorch CPU. The standard `pip install` pulls the GPU wheel by default (several GB).
> Use the CPU-only index to keep the image small:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```
> The `Dockerfile` already handles this correctly.

> **⚠️ FastEmbed First-Boot Model Download**
> On the first inference request, FastEmbed downloads the BGE-small embedding model and BGE cross-encoder reranker weights (~200 MB total) from HuggingFace. In production containers, either:
> - Pre-warm the container by running a dummy inference in the Docker `CMD`, or
> - Mount a persistent volume at `~/.cache/huggingface/` to survive restarts.
> Without this, the first `/api/news/chat/stream/` request will have elevated latency (~10–30 s).

### Developer Tools

| Tool | Role |
|------|------|
| `drf-spectacular` | Auto-generated OpenAPI 3 schema (Swagger UI + ReDoc) |
| `black` / `isort` / `flake8` | Code formatting & linting |
| `mypy` + `django-stubs` | Static type checking |
| `pytest` + `pytest-django` | Test suite |
| `django-prometheus` | `/metrics` endpoint for Prometheus scraping |
| Docker Compose | Local full-stack orchestration |

---

## 3. Features

### Authentication
- Ory Kratos-backed identity federation via Go BFF
- JWT tokens transported as `httpOnly` cookies (`access_token`, `refresh_token`)
- Google OAuth 2.0 login flow
- Token refresh endpoint
- `remember_me` support (7-day vs 30-day refresh token expiry)
- Password policy: min 8 chars, uppercase, special character required

### Financial Profile
- Store and update country code, currency, annual income, monthly investable amount
- Country/currency validated against live REST Countries data
- Auto-lookup of live USD → user's currency exchange rate on profile read

### Exchange Rates
- Live USD → any currency conversion (ExchangeRate API)
- Historical rate series for 3 months, 6 months, 1 year, 2 years (Frankfurter API)

### Investment Simulation
- Dollar-Cost Averaging (DCA into USD) vs fixed-term deposit comparison
- Uses actual historical exchange rate data for the user's currency
- Returns winner, percentage difference, and a plain-language summary

### Business News (AI + RAG)
- Country-specific business news generated by Google Gemini
- Cached in PostgreSQL, refreshed every 6 hours via Celery Beat
- Distributed Redis lock prevents duplicate concurrent refresh jobs
- News documents indexed into Qdrant for semantic retrieval
- Per-user on-demand refresh via Celery task

### AI News Chat (RAG)
- Hybrid retrieval: dense vector search (Qdrant + BGE embeddings) + BM25 keyword search
- Cross-encoder reranking (BGE Reranker) selects top-3 contexts
- Ordinal shortcut: "first news", "second news" bypasses RAG and fetches directly
- Gemini generates a grounded answer from retrieved contexts
- Streaming SSE response (`text/event-stream`)

### Smart Calendar
- Create, list, update, delete calendar events with titles, date/time range, and estimated cost
- Color-coded categories per user
- Ownership enforcement on all mutations
- Google Calendar OAuth 2.0 integration (connect / store tokens)

### AI Calendar Advice
- Submit any financial document (e.g. tax notice, pay slip) as text
- Gemini analyzes the document against the user's existing calendar events and financial profile
- Returns structured JSON advice: keep / update / delete suggestions per event
- Automatic fallback response if Gemini quota is exhausted

### Event-Driven Architecture
- Outbox pattern: domain events written to `OutboxEvent` table atomically with the business transaction
- Background relay publishes outbox events to Kafka topics
- `accounts` app consumes Kafka events to react to user sign-up events
- Management commands: `run_account_consumer`, `process_outbox`

---

## 4. API Endpoints

> All protected endpoints require a valid JWT delivered via `Authorization: Bearer <token>` header or `access_token` httpOnly cookie.

### Authentication — `/api/auth/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/refresh/` | Public | Rotate access token using refresh cookie |
| `GET` | `/api/auth/me/` | JWT | Return current user `ory_id` and email |
| `GET` | `/api/auth/google/login/` | Public | Redirect to Google OAuth consent screen |
| `GET` | `/api/auth/google/callback/` | Public | Google OAuth callback; sets auth cookies |

### Account — `/api/account/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/account/me/` | JWT | Retrieve user's financial profile |
| `PUT` | `/api/account/me/` | JWT | Update financial profile (country, currency, income) |
| `GET` | `/api/account/me/exchange-rate/` | JWT | Live USD → user's currency rate |

### Country Metadata — `/api/meta/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/meta/countries/` | Public | List all countries with currencies and flags |
| `GET` | `/api/meta/countries/<code>/` | Public | Retrieve a single country by ISO-2 code |

### Exchange Rates — `/api/exchange/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/exchange/usd-to/<currency>/` | Public | Current USD → `currency` rate |
| `GET` | `/api/exchange/history/?currency=KRW&period=6m` | Public | Historical USD rates. Periods: `3m` `6m` `1y` `2y` |

### Investment Simulation — `/api/simulation/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/simulation/compare/dca-vs-deposit/` | JWT | Compare DCA (USD) vs fixed deposit for the user's currency |

```json
// Request body
{ "period": "1y", "deposit_rate": 3.5 }
```

### Business News — `/api/news/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/news/business-news/` | JWT | Latest cached business news for user's country |
| `POST` | `/api/news/business-news/refresh/` | JWT | Queue an on-demand Celery refresh task |
| `POST` | `/api/news/chat/stream/` | JWT | RAG-powered streaming chat (SSE) |

```json
// Chat request body
{ "question": "What are the latest trends in the Korean economy?" }
```

### Calendar — `/api/calendar/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/calendar/init/` | JWT | Initialize (or retrieve) user's calendar |
| `GET` | `/api/calendar/me/` | JWT | Get user's calendar details |
| `GET` | `/api/calendar/oauth/login/` | JWT | Get Google Calendar OAuth authorization URL |
| `GET` | `/api/calendar/oauth/callback/` | JWT | Google Calendar OAuth callback |
| `POST` | `/api/calendar/categories/create/` | JWT | Create a new event category |
| `GET` | `/api/calendar/categories/` | JWT | List user's categories |
| `DELETE` | `/api/calendar/categories/<uuid>/` | JWT | Delete a category |
| `POST` | `/api/calendar/events/create/` | JWT | Create a calendar event |
| `GET` | `/api/calendar/events/` | JWT | List all user's events |
| `PUT` | `/api/calendar/events/<uuid>/` | JWT | Update an event |
| `DELETE` | `/api/calendar/events/<uuid>/` | JWT | Delete an event |
| `POST` | `/api/calendar/advisor/` | JWT | Submit a document for AI calendar advice |

```json
// Advisor request body
{ "document_text": "Your salary notice or tax document text here..." }
```

### API Documentation

| Path | Description |
|------|-------------|
| `/api/schema/` | Raw OpenAPI 3 JSON schema |
| `/api/docs/swagger/` | Swagger UI |
| `/api/docs/redoc/` | ReDoc UI |

---