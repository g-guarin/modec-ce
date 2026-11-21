# MODEC-CE: cost and evidence for multi-agent LLM orchestration

[![Tests](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml/badge.svg)](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

> English summary. The full documentation is in Spanish: [README.md](README.md).

**MODEC-CE measures how much you save in a multi-agent LLM workload when prompts are laid out to hit the provider's prefix cache, and it seals every measurement in an evidence chain that a third party can verify.**

## What it does

1. **Cache-aware layout.** Prompt segments are ordered from most stable to most volatile: `FOUNDATION → CONTEXT → HISTORY → ROLE → TASK → VOLATILE`. Content is identical across arms (checked with a SHA-256 fingerprint); only the order changes. Providers bill cache-hit input at a fraction of the normal price.
2. **History as Super-Tokens.** Each earlier output is replaced by an `artifact://sha256:…` reference, a summary of at most 350 characters and its `[H-nnn]` anchors.
3. **Sealed evidence.** Each measurement goes into a SHA-256 chain with `hash_previo` and an optional HMAC. A usage field the provider does not report is recorded as ABSENT, never as "0 cache hits", and the run stops (fail closed).

Putting static content first is something providers already recommend. What MODEC-CE adds is **measuring it** on a multi-agent workload with identical content in both arms, and **leaving the measurement verifiable**.

## Real pilot: DeepSeek, 2026-11-21

| | Baseline (`ingenua_rol`) | MODEC-CE (`modec`) |
|---|---|---|
| Input tokens served from cache (reported by DeepSeek) | 39.0 % | 82.5 % |
| Cost of the 3 runs (peak-rate tariff, derived) | USD 0.0347 | USD 0.0121 |
| **Savings per run** | | **65.3 % / 65.3 % / 65.3 %** |

- 3 runs × 16 calls = 48 calls, all HTTP 200, all usage fields present. Synthetic workload: orchestrator + 3 agents, 2 steps, a corpus of about 3,000 estimated tokens.
- Tokens are **measured** (provider `usage` fields). Cost is **derived** from the tariff declared in `datos/precios.json`; it is not an invoice.
- **Latency: no improvement.** Total latency was 37.1 s (baseline) vs 38.3 s (MODEC-CE), about 3 % slower; network noise was not measured. The measured benefit is cost, not speed.
- The log, sealed with the built-in minimal chain, is in [`evidencia/piloto_deepseek_20261121/`](evidencia/piloto_deepseek_20261121/). It holds fingerprints, counts, latencies and costs only: no prompts, responses or keys.

**Verify it yourself**, with the Python standard library only (no install):

```bash
git clone https://github.com/g-guarin/modec-ce.git
cd modec-ce
python herramientas/verificar_independiente.py evidencia/piloto_deepseek_20261121
```

It recomputes every hash, every chain link and each run's savings from the individual calls.

**Limits, stated up front**
- One provider so far. Anthropic and OpenAI pilots are pending.
- The log was sealed without an HMAC key: integrity is checkable, authorship is not.
- No external anchor: rewriting the whole chain would not be detectable.
- The simulation (59.0 % against a strong baseline) is an upper bound under DeepSeek's documented cache rules, not a measurement. Its workload is different from the pilot's (3 steps, orchestrator + 4 agents, 4,000-token corpus), so the two figures are not directly comparable.

## Quick start (no keys, no network)

```bash
python -B -m unittest discover -s tests      # tests, no network
python -B -m modec_ce simular                # 4 prompt layouts
python -B -m modec_ce sensibilidad           # 2/4/8 agents × 1k/4k/12k corpus
python -B -m modec_ce informe                # resultados/informe.html
```

Requirements: Python 3.10+ and the standard library only. The optional local pilot with a real CPU transformer needs `torch`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Reproductions of the DeepSeek result, new provider adapters and tariff checks are especially welcome: look for the `good first issue` and `help wanted` labels.

## License

Apache 2.0 (`LICENSE`, `NOTICE`). The optional PESD core mentioned in `NOTICE` is proprietary, is not part of this repository and is not required: MODEC-CE ships its own minimal evidence chain.

Author: Giovany Guarín Ramírez.
