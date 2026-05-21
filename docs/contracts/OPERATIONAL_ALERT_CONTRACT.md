# Operational Alert Contract

Schema ID: `operational_alert`  
JSON Schema dialect: Draft-07  
File: `schemas/operational_alert.schema.json`

---

## Purpose

An operational alert is the primary signal surface used by the Spiderweb
pipeline to communicate anomalies, threats, or noteworthy observations to
downstream consumers (dashboards, operator queues, escalation workflows).

Every alert produced by the detection layer — whether triggered by restricted
airspace entry, unusual behavioral patterns, or infrastructure proximity —
must conform to this schema before it can be persisted or forwarded.

Required fields (`alert_id`, `callsign`, `severity`) ensure every record
is identifiable, attributable, and triageable without querying ancillary
tables. All other fields are optional and may be `null`.

`additionalProperties: true` — extra fields are permitted and ignored by
schema validation.

---

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `alert_id` | string | **yes** | Unique identifier for this alert. Must be non-empty. |
| `callsign` | string | **yes** | Aircraft callsign that triggered the alert. Must be non-empty. |
| `severity` | string enum | **yes** | Triage level. See [Severity Values](#severity-values). |
| `flight_id` | string\|null | no | Flight record identifier, if the alert is linked to a specific flight. |
| `category` | string enum\|null | no | Broad class of anomaly. See [Category Values](#category-values). |
| `title` | string\|null | no | Short human-readable headline for the alert. |
| `description` | string\|null | no | Detailed narrative explaining what was detected and why it is notable. |
| `evidence` | array of strings\|null | no | Supporting data points (e.g. coordinates, timestamps, sensor readings) cited as evidence. |
| `timestamp` | string\|null | no | ISO 8601 timestamp of the event or detection. |
| `recommended_action` | string\|null | no | Suggested operator response (e.g. `"Verify with ATC"`, `"Dispatch unit"`). |
| `auto_resolved` | integer\|boolean\|null | no | Whether the system automatically closed this alert without operator intervention. |
| `auto_resolved_reason` | string\|null | no | Explanation of why the alert was auto-resolved. |
| `acknowledged` | integer\|boolean\|null | no | Whether an operator has acknowledged receipt of the alert. |
| `acknowledged_at` | string\|null | no | ISO 8601 timestamp of operator acknowledgement. |
| `created_at` | string\|null | no | ISO 8601 timestamp when the alert record was first created. |
| `suppressed_until` | string\|null | no | ISO 8601 timestamp until which repeated alerts of this type are suppressed. |
| `suppression_reason` | string\|null | no | Explanation for why the alert is being suppressed. |
| `escalation_count` | integer\|null | no | Number of times this alert has been escalated. Must be ≥ 0. |

---

## Category Values

The `category` field classifies the type of anomaly that triggered the alert.

| Value | Description |
|-------|-------------|
| `Restricted Airspace Entry` | Aircraft entered a defined restricted or prohibited airspace zone. |
| `Unusual Flight Behavior` | Flight profile deviates significantly from expected patterns for the aircraft type. |
| `Critical Infrastructure Proximity` | Aircraft operating unusually close to power lines, pipelines, dams, or other critical infrastructure. |
| `Unknown/Unidentified Aircraft` | No corroborating identity data could be found for this callsign or transponder code. |
| `Temporal Anomaly (Physics Violation)` | Track data contains timestamps or positions that violate physical constraints (e.g. impossible speed). |
| `Pattern Deviation from Historical Norm` | Observed behavior differs materially from the aircraft's own historical baseline. |
| `Extended Operation (Possible Emergency)` | Flight duration or loiter behavior suggests a potential emergency or distress situation. |
| `Previously Unseen Aircraft` | First time this callsign or aircraft has appeared in the dataset. |
| `Night Operation (Non-Emergency Operator)` | Aircraft conducting operations at night that are unexpected for its operator classification. |
| `Behavioral Cluster Deviation` | Aircraft has shifted to a behavioral cluster inconsistent with its typical mission profile. |
| `null` | Category not determined or not applicable. |

---

## Severity Values

The `severity` field controls triage priority. Exactly one of the following
string values must be used:

| Value | Meaning |
|-------|---------|
| `INFO` | Informational — no action required; logged for situational awareness. |
| `LOW` | Low priority — worth monitoring; no immediate response needed. |
| `MEDIUM` | Moderate concern — investigate when capacity allows. |
| `HIGH` | Significant concern — timely operator review required. |
| `CRITICAL` | Immediate attention required — potential safety or security threat. |

---

## Minimal Valid Example

```json
{
  "alert_id": "ALT-2024-00001",
  "callsign": "N5854Z",
  "severity": "HIGH",
  "flight_id": "FLT-2024-03-14-001",
  "category": "Restricted Airspace Entry",
  "title": "Aircraft entered restricted zone R-9001",
  "description": "N5854Z penetrated the boundary of restricted airspace R-9001 at 14:32 UTC without a filed clearance.",
  "evidence": [
    "Position: 18.45°N 66.10°W at 14:32:07 UTC",
    "Altitude: 1,200 ft MSL",
    "Zone boundary crossed: R-9001 south perimeter"
  ],
  "timestamp": "2024-03-14T14:32:07Z",
  "recommended_action": "Verify clearance status with San Juan ARTCC",
  "auto_resolved": false,
  "acknowledged": false,
  "created_at": "2024-03-14T14:32:10Z",
  "escalation_count": 0
}
```

---

## Validation

**Programmatic validation** — use `SchemaValidator` from `schema_validation.py`:

```python
from schema_validation import SchemaValidator
v = SchemaValidator()
result = v.validate(alert_dict, "operational_alert")
if not result["valid"]:
    print(result["errors"])
```

The schema is auto-loaded by `SchemaValidator._load_schemas()` from the
`schemas/` directory — no registration step required.
