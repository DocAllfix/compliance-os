# v2/ — transport LLM Azure OpenAI

Package superstite dello sgombero legacy AUDITORSEMI (Fase 2 consolidamento, 2026-06).

Contiene SOLO il transport verso Azure OpenAI GPT-4.1-mini (Foundry v1):

- `azure_openai_client_v2.py` — client streaming con retry/backoff
- `provider_profiles_v2.py` — profilo `gpt-4.1-mini-azure` (unico)
- `stream_buffer.py`, `yaml_stream_parser.py` — buffer/parsing dello stream
- `token_meter.py` — telemetria token per sessione

La pipeline V2 (triage funnel), il recovery, l'SSE emitter e il client/fallback
Gemini sono stati rimossi: provider Azure-ONLY per decisione utente (2026-06-12).
