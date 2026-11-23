# MODEC-CE: cost and evidence for multi-agent LLM orchestration

[![Tests](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml/badge.svg)](https://github.com/g-guarin/modec-ce/actions/workflows/pruebas.yml)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

> English summary. The full documentation is in Spanish: [README.md](README.md).
>
> A worked example of what a delivery made with this looks like (in Spanish): [docs/caso-de-uso.md](docs/caso-de-uso.md).

**MODEC-CE does not offer a new way to cut LLM costs. It offers a way to prove how much they were cut, so that someone else can check it.**

It measures the saving from laying prompts out to hit the provider's prefix cache in a multi-agent workload, and seals every measurement in an evidence chain verifiable with no dependencies. Every figure is marked estimated, measured or derived, and anything the provider does not report is recorded as ABSENT rather than counted as zero.

It is aimed at whoever **has to defend a cost figure to someone else** — whoever charges for it, buys it, audits it or publishes it — not only at whoever wants a smaller bill. The reason is the table below: the saving depends so much on the shape of the workload that somebody else's percentage is not a basis for a decision.

## What it does

1. **Cache-aware layout.** Prompt segments are ordered from most stable to most volatile: `FOUNDATION → CONTEXT → HISTORY → ROLE → TASK → VOLATILE`. Content is identical across arms, the configurations being compared (checked with a SHA-256 fingerprint); only the order changes. Providers bill cache-hit input at a fraction of the normal price.
2. **History as Super-Tokens.** Each earlier output is replaced by an `artifact://sha256:…` reference, a fragment of at most 350 characters (truncated, not a semantic summary) and its `[H-nnn]` anchors, copied from the full output.
3. **Sealed evidence.** Each measurement goes into a SHA-256 chain, each record linked to the previous one through `hash_previo`, with an optional HMAC. A usage field the provider does not report is recorded as ABSENT, never as "0 cache hits", and the run stops (fail closed: when in doubt, it stops instead of assuming).

Putting static content first is something providers already recommend. What MODEC-CE adds is **measuring it** on a multi-agent workload with identical content in both arms, and **leaving the measurement verifiable**.

## What this solves that the provider's docs do not

The technique is neither new nor scarce: laying out prompts from stable to volatile is what the providers themselves recommend. **MODEC-CE is not offered as a better way to save. It is offered as a way to prove how much was saved.**

That distinction matters because the saving depends so heavily on the shape of the workload that **somebody else's percentage is not a basis for a decision**. Holding the cache-hit rates exactly as measured in the real pilot (39.0 % vs 82.5 %) and changing nothing else, simply making the model write more collapses the saving:

| Output per call | Saving | Input, as a share of the bill |
|---|---|---|
| 64 tokens | 65.1 % | 94 % |
| 200 | 58.2 % | 84 % |
| 500 | 47.2 % | 68 % |
| 1,000 | 35.9 % | 52 % |
| 2,000 | 24.2 % | 35 % |
| 5,000 | 12.3 % | 18 % |

Prompt layout makes the *input* cheaper and does nothing to the output. A test checks this table against the code; regenerate it with `python -m modec_ce sensibilidad`.

So a claim like "we cut your AI spend by 65 %" is close to empty on its own: without the shape of the workload behind it, it is neither checkable nor comparable.

### Who this is for, and what it protects against

MODEC-CE serves whoever **has to defend a cost figure to someone else**, not whoever merely wants a smaller bill:

- People who **charge** for a cost optimisation and today hand over a spreadsheet they made themselves.
- People who **buy** that optimisation and have no way to audit the figure they are shown.
- People who **publish** a cost result and need someone else to reproduce it.
- People who **compare** providers or configurations and need the comparison not to rest on their word.

The threat model, stated plainly: **whoever has an incentive to inflate a savings measurement is usually whoever is being paid for achieving it.** Bad faith is not required for the figure to drift — it is enough to pick the favourable workload, the favourable tariff slot, or to drop the run that came out badly. A hashed chain prevents none of that by itself, but it does record **what was measured, in what order, at what tariff, and what could not be measured**, so the argument stops being about the good faith of whoever presents the number.

What it does **not** do is in [SECURITY.md](SECURITY.md): without a key it proves integrity, not authorship; without an external anchor a full rewrite is undetectable; and it cannot tell you whether the measured workload resembles yours. For that last one the answer is not to trust this table, but to run the pilot on your own workload.

### Where the patterns come from

Two behaviours in this repository are not improvised. They come from the author's **PESD structural-pattern** framework, and both are implemented here in the open:

- **P1, chained sealing.** Each record carries the previous record's digest, so ordering is part of what is sealed (`modec_ce/nucleo.py`). The repository ships its own independent minimal chain and uses the PESD core only when it happens to be available.
- **P2, presence sentinel.** A datum that does not arrive is never replaced by a default: it is marked ABSENT and the process stops (`modec_ce/evidencia.py`). It governs both the provider's usage fields and the seal's own provenance fields, which stay `null` and declared ABSENT when they cannot be obtained.

Both can be read, run and attacked inside this repository with no access to anything else: the test suite includes the case where P2 halts a run, and the case where a chain rewritten without signatures is rejected.

## Real pilots: DeepSeek and Anthropic

### The effect replicates across two providers that cache differently

This is the result that carries the most weight, and it is not the saving: it is that **the cache-hit rate reproduces almost exactly on two providers with different caching mechanisms**. DeepSeek caches the prefix on its own; Anthropic caches only what the client marks with `cache_control`. Same reordering, same rates:

<!-- TABLA-REPLICACION -->
| Cache-hit rate | `ingenua_rol` | `modec` | Cost saving |
|---|---|---|---|
| **DeepSeek** `deepseek-flash` (2026-11-22) | 39.0 % | 82.5 % | 65.3 % |
| **Anthropic** `claude-haiku-5-5` (2026-11-22) | 38.9 % | 84.0 % | 60.1 % |
<!-- /TABLA-REPLICACION -->

Hit rates landing within one and a half points of each other suggests that what is being measured is **the structure of the prompt**, not a quirk of one vendor. The cost saving does differ (65.3 % vs 60.1 %) because the tariffs differ: Anthropic charges cache writes at 1.25× the input price and DeepSeek does not.

With one provider this was an observation. With two, and with mechanisms that do not resemble each other, it is a replicated result. It is still one synthetic workload: **replicated across providers is not replicated across workloads**, and measuring yours is still your job.

### Detail

| | Baseline (`ingenua_rol`: each agent's prompt starts with its role) | MODEC-CE (`modec`: most stable content first) |
|---|---|---|
| Input tokens served from cache (reported by DeepSeek) | 39.0 % | 82.5 % |
| Cost of the 3 runs (standard-rate tariff, i.e. the non-discounted `peak` slot; derived) | USD 0.0347 | USD 0.0121 |
| **Savings per run** | | **65.3 % / 65.3 % / 65.3 %** |

*DeepSeek `deepseek-flash`, 2026-11-21.*

| | Baseline (`ingenua_rol`) | MODEC-CE (`modec`) |
|---|---|---|
| Input tokens served from cache (reported by Anthropic) | 38.9 % | 84.0 % |
| Cost of the 3 runs (`standard` tariff; derived) | USD 0.0217 | USD 0.0087 |
| **Savings per run** | | **60.1 % / 60.1 % / 60.1 %** |

*Anthropic `claude-haiku-5-5`, 2026-11-22, commit `62b8c05` with a clean tree; 9,154 to 14,173 input tokens per call. The `cache_control` breakpoints sit at the same positions in both arms: what changes is which content falls before them.*

- 3 runs × 16 calls = 48 calls, all HTTP 200, all usage fields present. Synthetic workload: orchestrator + 3 agents, 2 steps, a corpus generated with the nominal parameter `tokens_corpus` = 3000 (about 5,100 tokens by the project's estimator; DeepSeek billed 5,846 to 8,939 input tokens per call). This is the second real DeepSeek run that day: the first, sealed with another evidence engine that is not published, gave an equivalent result (65.4 % / 65.3 % / 65.4 %).
- Tokens are **measured** (provider `usage` fields). Cost is **derived** from the tariff declared in `datos/precios.json`; it is not an invoice.
- **Latency: no measurable effect, and now it can be shown why.** The Anthropic pilot made visible something the DeepSeek latency figures only hinted at: **the per-run total does not measure the method, it measures the worst call.** Two runs of the same pilot, half an hour apart:

  | Run | "Latency reduction" computed over totals | Medians of the 16 calls |
  |---|---|---|
  | Anthropic 21:13, run 1 | **+83.1 %** favouring `modec` | 1,754 ms vs 1,609 ms (+8 %) |
  | Anthropic 22:09, run 2 | **−99.2 %** against `modec` | 1,584 ms vs 1,629 ms (−3 %) |

  In the first, one baseline call stalled for about 63 seconds; in the second it was a `modec` call. The medians, which an outlier cannot drag, stayed between 1,555 and 1,754 ms across both arms of all six runs: −2.8 % to +5.2 %. **A number that swings from +83 % to −99 % depending on which call trips is not an effect.** The measured benefit is cost, not speed — and there is no evidence it costs speed either.
- The three logs, sealed with the built-in minimal chain, are under [`evidencia/`](evidencia/). They hold fingerprints, counts, latencies and costs only (plus, if a call fails, up to 300 characters of the provider's error message): no prompts, responses or keys.

**Verify it yourself**, with the Python standard library only (no install):

```bash
git clone https://github.com/g-guarin/modec-ce.git
cd modec-ce
python herramientas/verificar_independiente.py evidencia/piloto_anthropic_20261122_220948_bb1b11
```

It recomputes the SHA-256 digest of every record, every chain link and each run's savings from the costs recorded in the individual calls. It does not recompute cost from tokens and tariff.

**External time anchor.** Two of the three logs carry an **RFC 3161 timestamp** over the digest of their last record, issued by FreeTSA, under [`sello/`](sello/):

| Log | Attested instant |
|---|---|
| `piloto_deepseek_20261122_135846_5c1d7c` | 22 November 2026, 22:17:24 GMT |
| `piloto_anthropic_20261122_220948_bb1b11` | 23 November 2026, 03:22:02 GMT |

It attests, to someone who has no reason to take the author's word, that the chain existed no later than that instant — which is what makes a full rewrite detectable. The authority's certificates are published alongside each seal, because they would be needed to check it if that authority ever went away. Both seals were verified on two separate machines, with different operating systems and different OpenSSL versions.

```bash
cd sello/piloto_anthropic_20261122_220948_bb1b11
openssl ts -verify -in ancla.tsr -queryfile ancla.tsq -CAfile cacert.pem -untrusted tsa.crt
```

`verificar_independiente.py` checks on its own that the anchor **contains that chain's final digest** — that it is this chain's anchor and not another's — but it does **not** check the authority's signature, because that would require parsing ASN.1 and the tool has no dependencies. It says so in its output rather than letting you assume otherwise.

**Limits, stated up front**
- Two providers so far, one synthetic workload. An OpenAI pilot is pending, and the OpenAI and OpenRouter adapters have only been tested with simulated responses.
- Both logs were sealed without an HMAC key: integrity is checkable, authorship is not.
- The three logs are not equivalent, and the verifier says so itself rather than leaving it to the reader's goodwill:

  | Log | Anchor | Date and commit inside the seal | Clean tree |
  |---|---|---|---|
  | `piloto_deepseek_20261121` | no | no — the date is only in the folder name | not declared |
  | `piloto_deepseek_20261122_135846_5c1d7c` | yes | yes | yes |
  | `piloto_anthropic_20261122_220948_bb1b11` | yes | yes (`62b8c05`, published) | yes |

  On the first, the verifier adds `SIN ANCLA EXTERNA`, `SIN FECHA EN EL SELLO` and `SIN COMMIT EN EL SELLO`; on the other two, none of the three.
- The date inside the payload is the one **declared** by the machine that ran the pilot. What backs it to a third party is the anchor, not the declaration.
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
