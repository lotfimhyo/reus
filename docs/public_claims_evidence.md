# Reus Public Claims Evidence Policy

**Project:** Reus / Reus-Veritas OS
**Founder:** Lotfi Mahiddine
**Organization:** Reulink
**Last reviewed:** 2026-08-22

## Purpose

Reus may discuss models, tools, evaluations, and external research in public
materials only when the claim has a traceable source and its scope is stated
accurately. Marketing reach must never be purchased with false performance
claims, anonymous-source speculation, or unverifiable benchmark comparisons.

## Review of the supplied social-media claim

The supplied image says that an unknown model named “0x Alpha” appeared for a
week and that developers say it outperforms “GPT-5.6 Sol” at programming. This
is **not sufficient evidence** for a Reus benchmark or endorsement claim.

| Item | Verified observation | Public communication rule |
| --- | --- | --- |
| Ox Alpha | OpenRouter describes it as a *stealth model*, developed and operated by an anonymous third-party provider during a preview. Its page listed a 1M-token context window and free access when reviewed. | Attribute this description to OpenRouter and label it as a time-bound preview. Do not claim a known developer, architecture, training set, or durable availability. |
| Prompt handling | The OpenRouter page warns that prompts and completions are retained by the third-party provider. | Do not send Reus secrets, private memory, identity material, or user data to this endpoint. It is incompatible with Reus local-first defaults without an explicit, reviewed exception. |
| GPT-5.6 Sol | OpenAI’s release page describes GPT-5.6 Sol as a limited preview and presents first-party evaluation results, with a broader evaluation suite promised later. | Attribute results to OpenAI and do not reinterpret them as proof of a head-to-head comparison with Ox Alpha. |
| “Outperforms” assertion | No disclosed, independently reproducible, like-for-like benchmark from the supplied post establishes this claim. | Prohibited in Reus public copy unless Reus publishes the task set, versions, prompts, scoring, cost/latency conditions, failures, and a reproducible evaluation record. |

## Evidence standard for future comparisons

Before publishing a model comparison, Reus must retain a dated evidence record
that identifies the model version and provider, task source and licence, exact
prompt and tool configuration, safety constraints, hardware or API conditions,
sample size, scoring method, aggregate metrics, failures, cost, latency, and a
reproduction command. A first-party announcement, an anonymous social post, a
single anecdote, or a model-router ranking alone does not meet that standard.

Public messages must distinguish between **provider-reported**,
**Reus-measured**, and **independently reproduced** results. They must also
state operational limitations, data handling, and the date on which a result
was observed.

## Sources

1. [OpenRouter — Ox Alpha](https://openrouter.ai/stealth/ox-alpha), reviewed 2026-08-22.
2. [OpenAI — Previewing GPT-5.6 Sol](https://openai.com/index/previewing-gpt-5-6-sol/), reviewed 2026-08-22.
