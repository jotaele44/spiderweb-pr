# PRIIS V1 LLM Answer Contract

Every analytical response from the Custom LLM layer must use this structure.

## Required sections

1. **Finding** — concise statement of what the evidence supports.
2. **Evidence** — source-linked evidence items, each with source tier.
3. **Source-tier breakdown** — T1/T2/T3/T4 counts and analytical weight.
4. **Confidence** — low / medium / high with reason.
5. **Contradictions** — disputes, time conflicts, location conflicts, missing provenance, alternate explanations.
6. **Missing data** — records or sources needed to strengthen or reject the finding.
7. **Recommended action** — map query, FOIA request, source upload, contract audit, geospatial join, imagery review, graph expansion, or report export.

## Required rules

- Do not answer from memory when retrieval is available.
- Do not cite a source that was not retrieved or supplied.
- Do not promote T3/T4 evidence above T1/T2 without corroboration.
- Do not frame an anomaly as an extraordinary conclusion.
- Use pattern-convergence language for UAP-related or anomalous topics.
- Explicitly flag speculation.
- If evidence is insufficient, say so and list the missing data.

## Output skeleton

```text
Finding:

Evidence:
- [T#] Source / record / entity reference — claim supported

Source-tier breakdown:
- T1: n
- T2: n
- T3: n
- T4: n

Confidence:

Contradictions:

Missing data:

Recommended action:
```
