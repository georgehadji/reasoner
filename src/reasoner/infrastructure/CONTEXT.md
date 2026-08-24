# Context: Infrastructure

## Directory: `src/reasoner/infrastructure`

## Description
Platform and infrastructure adapters implementing the abstract application ports (databases, search, cache).

## Files
- **`__init__.py`**: Infrastructure Layer
- **`auth_legacy.py`**: Default scope sets for common roles
- **`cached_quota_repo.py`**: Redis-backed quota repository with graceful DB fallback.
- **`circuit_breaker.py`**: Reasoner Pipeline - Circuit Breaker Pattern
- **`clients.py`**: Shared HTTP clients with connection pooling.
- **`metrics.py`**: Prometheus metrics for Reasoner.
- **`rate_limiter.py`**: Production-Ready Rate Limiter
- **`renderer.py`**: Reasoner Pipeline - Output Renderer
- **`scraper.py`**: Reasoner - Web Scraper Module
- **`server_check.py`**: Reasoner - Server Startup Test
- **`token_cache.py`**: Approximate: $0.000001 per token (average across providers)
- **`uploader.py`**: Content-hash deduplication index, scoped per tenant: {user_id: {sha256: file_id}}.
- **`verbalized_sampling.py`**: Also handle generic ``` fences if json-specific didn't match
- **`widgets_legacy.py`**: Widgets Backend Engine

## Subfolders
- **`auth`**: Adapters and providers managing API key verification, user sessions, and JWT tokens.
- **`benchmarks`**: Implementations for executing benchmarking suites and aggregating performance metadata.
- **`billing`**: Payment gateway adapters (PayPal, Stripe) and billing credit ledger managers.
- **`documents`**: Implementations for reading and extracting contents from specialized document types (PDFs, Docx, HTML).
- **`email`**: Email delivery adapters (SMTP, SendGrid) for transaction and notification alerts.
- **`execution`**: Execution environments, containerized execution workers, and sandboxing infrastructure.
- **`learning`**: Database and algorithm adapters supporting neuro-symbolic feedback loops and recall memory systems.
- **`llm`**: Language model provider clients, extraction parsers, and constraint checkers.
- **`observability`**: Telemetry exporters, structured loggers, and distributed tracing adapters.
- **`persistence`**: Relational database adapters, SQLAlchemy models, and session management configurations.
- **`prism`**: Adapter layer for unified formatting and syntax highlighting of parsed outputs.
- **`redis`**: Redis cache adapters, session stores, and rate-limiting helper implementations.
- **`search`**: Search API clients (Perplexity, Tavily, Google, Bing) executing context-vetting queries.
- **`telemetry`**: Telemetry collectors and logging pipelines sending metrics to external monitoring backends.
- **`translation`**: Translation adapter wrappers utilized during the classification or synthesis phases to adapt response languages.
- **`valkey`**: Valkey in-memory key-value database adapters and cache managers.
- **`watermark`**: Concrete utilities for watermarking generated texts, images, or documents.
- **`websocket`**: Websocket server managers handling real-time, bi-directional event broadcasts with clients.
- **`widgets`**: Adapters and renderers for injecting rich UI widgets and dashboards in terminal/web flows.
