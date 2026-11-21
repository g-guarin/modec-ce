# MODEC-CE: cost and evidence for multi-agent LLM orchestration

[![Tests](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml/badge.svg)](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

> English summary. The full documentation is in Spanish: [README.md](README.md).

**MODEC-CE measures how much you save in a multi-agent LLM workload when prompts are laid out to hit the provider's prefix cache, and it seals every measurement in an evidence chain that a third party can verify.**

## What it does

1. **Cache-aware layout.** Prompt segments are ordered from most stable to most volatile: `FOUNDATION → CONTEXT → HISTORY → ROLE → TASK → VOLATILE`. Content is identical across arms, the configurations being compared (checked with a SHA-256 fingerprint); only the order changes. Providers bill cache-hit input at a fraction of the normal price.
2. **History as Super-Tokens.** Each earlier output is replaced by an `artifact://sha256:…` reference, a fragment of at most 350 characters (truncated, not a semantic summary) and its `[H-nnn]` anchors, copied from the full output.
3. **Sealed evidence.** Each measurement goes into a SHA-256 chain, each record linked to the previous one through `hash_previo`, with an optional HMAC. A usage field the provider does not report is recorded as ABSENT, never as "0 cache hits", and the run stops (fail closed: when in doubt, it stops instead of assuming).

Putting static content first is something providers already recommend. What MODEC-CE adds is **measuring it** on a multi-agent workload with identical content in both arms, and **leaving the measurement verifiable**.

## Real pilot: DeepSeek, 2026-11-21

| | Baseline (`ingenua_rol`: each agent's prompt starts with its role) | MODEC-CE (`modec`: most stable content first) |
|---|---|---|
| Input tokens served from cache (reported by DeepSeek) | 39.0 % | 82.5 % |
| Cost of the 3 runs (standard-rate tariff, i.e. the non-discounted `peak` slot; derived) | USD 0.0347 | USD 0.0121 |
| **Savings per run** | | **65.3 % / 65.3 % / 65.3 %** |

- 3 runs × 16 calls = 48 calls, all HTTP 200, all usage fields present. Synthetic workload: orchestrator + 3 agents, 2 steps, a corpus generated with the nominal parameter `tokens_corpus` = 3000 (about 5,100 tokens by the project's estimator; DeepSeek billed 5,846 to 8,939 input tokens per call). This is the second real DeepSeek run that day: the first, sealed with another evidence engine that is not published, gave an equivalent result (65.4 % / 65.3 % / 65.4 %).
- Tokens are **measured** (provider `usage` fields). Cost is **derived** from the tariff declared in `datos/precios.json`; it is not an invoice.
- **Latency: no improvement.** Total latency was 37.1 s (baseline) vs 38.3 s (MODEC-CE), about 3 % slower; network noise was not measured. The measured benefit is cost, not speed.
- The log, sealed with the built-in minimal chain, is in [`evidencia/piloto_deepseek_20261121/`](evidencia/piloto_deepseek_20261121/). It holds fingerprints, counts, latencies and costs only (plus, if a call fails, up to 300 characters of the provider's error message): no prompts, responses or keys.

**Verify it yourself**, with the Python standard library only (no install):

```bash
git clone https://github.com/g-guarin/modec-ce.git
cd modec-ce
python herramientas/verificar_independiente.py evidencia/piloto_deepseek_20261121
```

It recomputes the SHA-256 digest of every record, every chain link and each run's savings from the costs recorded in the individual calls. It does not recompute cost from tokens and tariff.

**Limits, stated up front**
- One provider so far. Anthropic and OpenAI pilots are pending, and the Anthropic, OpenAI and OpenRouter adapters have only been tested with simulated responses.
- The log was sealed without an HMAC key: integrity is checkable, authorship is not.
- No external anchor: truncating the end of the chain, or rewriting it whole without the HMAC key, would not be detectable.
- The simulation (59.0 % against a strong baseline) is an estimate under DeepSeek's documented cache rules (R1–R3; R4 is not modelled), not a measurement and not a bound: in the real pilot DeepSeek hit the cache more than the simulation predicted. Its workload differs from the pilot's (3 steps, orchestrator + 4 agents, `tokens_corpus` = 4000) and its cost includes 300 assumed output tokens per request, so the two figures are not directly comparable.

## Quick start (no keys, no network)

```bash
python -B -m unittest discover -s tests      # tests, no network
python -B -m modec_ce simular                # 4 variants
python -B -m modec_ce sensibilidad           # 2/4/8 agents × 1k/4k/12k corpus
python -B -m modec_ce informe                # resultados/informe.html
```

Requirements: Python 3.10+ and the standard library only. The optional local pilot with a real CPU transformer needs `torch`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Reproductions of the DeepSeek result, new provider adapters and tariff checks are especially welcome: look for the `good first issue` and `help wanted` labels.

## License

Apache 2.0 (`LICENSE`, `NOTICE`). The optional PESD core mentioned in `NOTICE` is proprietary, is not part of this repository and is not required: MODEC-CE ships its own minimal evidence chain.

Author: Giovany Guarín Ramírez.
