# Generic Source Adapter SDK

## Objective

Provide reusable source-adapter primitives for government and technical data portals used by Spiderweb workflows.

The SDK abstracts the repeated acquisition pattern introduced by the Census Partnership PR adapter:

```text
source endpoint -> expected universe -> request plan -> payload download -> hash -> manifest -> coverage ledger -> optional normalization
```

## Active vector

`SOURCE_ADAPTER_FRAMEWORK_GENERALIZATION_v1`

## Scope

Initial reuse targets:

| Source family | Adapter pattern |
| --- | --- |
| Census | HTML form, batch ZIPs, shapefile normalization |
| USGS | Direct file/API downloads, stable manifests |
| NOAA | Archive/file endpoint downloads, NetCDF/ZIP payloads |
| USACE | Document and GIS payload acquisition |
| PR GIS Portal | GeoServer/ArcGIS/download endpoints |
| USFWS | GIS/document archives |
| USDA | Geospatial and tabular downloads |

## SDK modules

| Module | Purpose |
| --- | --- |
| `core.py` | Endpoint, policy, request, result, coverage contracts |
| `form.py` | Dependency-free HTML form parsing helpers |
| `download.py` | HTTP GET/POST download engine and payload validators |
| `manifest.py` | Source, download, SHA256, expected-universe, and coverage CSV writers |

## Repository guardrails

The SDK keeps repository policy explicit:

- Raw payloads are runtime artifacts.
- Extracted payloads are runtime artifacts.
- Manifests and ledgers are small reproducibility artifacts.
- Promoted outputs must be normalized and reviewable.
- Coverage is an accounting ledger, not omniscience.

## Minimal adapter pattern

```python
from pathlib import Path

from scripts.source_adapters.sdk import (
    AdapterPolicy,
    DownloadEngine,
    ManifestEngine,
    PayloadRequest,
    SourceEndpoint,
)
from scripts.source_adapters.sdk.manifest import summarize_coverage

endpoint = SourceEndpoint(
    source_id="example_source",
    name="Example Source",
    url="https://example.gov/download.zip",
    method="GET",
)
policy = AdapterPolicy(
    raw_payload_root=Path("data/raw/example_source"),
    manifest_root=Path("manifests/example_source"),
)
policy.validate_runtime_paths()

request = PayloadRequest(
    request_id="example_payload",
    endpoint=endpoint,
    expected_content="zip",
)

result = DownloadEngine(policy.raw_payload_root).download(request)
manifest = ManifestEngine(policy.manifest_root)
manifest.write_source_manifest({"source_id": endpoint.source_id, "source_url": endpoint.url})
manifest.write_download_ledger([result])
manifest.write_sha256_manifest([result])
manifest.write_coverage_ledger(summarize_coverage(expected=1, requested=1, records=[result]))
```

## Promotion rule

A source-adapter output can be promoted only when:

1. Expected universe is declared or the source is explicitly single-payload.
2. Requests are deterministic and logged.
3. Payloads have SHA256 hashes.
4. HTML/error payloads are held, not silently accepted.
5. Coverage ledger records expected, requested, acquired, failed, hold, skipped, unresolved, and coverage percentage.
6. Raw and extracted payloads remain outside git-tracked paths.

## Relationship to specific adapters

Specific adapters may keep specialized logic. For example, Census Partnership still needs municipio-code parsing and nested ZIP normalization. The SDK only supplies the common acquisition and ledger backbone.
