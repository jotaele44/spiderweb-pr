import type { PriisData } from "../types/priis";

export const priisData: PriisData = {
  agencies: [
    { id: "AG-001", code: "PRASA", name: "Puerto Rico Aqueduct & Sewer Authority" },
    { id: "AG-002", code: "PREPA", name: "Puerto Rico Electric Power Authority" },
    { id: "AG-003", code: "COR3", name: "Central Office for Recovery & Reconstruction" },
    { id: "AG-004", code: "AAFAF", name: "Fiscal Agency & Financial Advisory Authority" },
    { id: "AG-005", code: "DTOP", name: "Dept. of Transportation & Public Works" }
  ],
  vendors: [
    { id: "V-1024", name: "Caribe Civil Works LLC", risk: 0.82, tier: "T2" },
    { id: "V-2071", name: "Atlantica Infrastructure Corp", risk: 0.74, tier: "T2" },
    { id: "V-1188", name: "Borinquen Logistics Group", risk: 0.41, tier: "T2" },
    { id: "V-3340", name: "Cordillera Engineering S.E.", risk: 0.66, tier: "T2" },
    { id: "V-1502", name: "Sargasso Marine Services", risk: 0.58, tier: "T2" },
    { id: "V-4012", name: "Vega Telecom Partners", risk: 0.71, tier: "T2" },
    { id: "V-3771", name: "Coastal Power Solutions LLC", risk: 0.69, tier: "T2" }
  ],
  sites: [
    { id: "S-001", name: "Roosevelt Roads — Ceiba", kind: "former-naval-station", lat: 18.246, lng: -65.62, sensitive: true, infrastructure_class: "military_adjacent" },
    { id: "S-002", name: "Punta Salinas Radar", kind: "radar", lat: 18.466, lng: -66.22, sensitive: true, infrastructure_class: "other" },
    { id: "S-003", name: "PRASA Caguas WTP", kind: "water-treatment", lat: 18.23, lng: -66.04, infrastructure_class: "water" },
    { id: "S-004", name: "Aguadilla — Rafael Hernández", kind: "airport", lat: 18.495, lng: -67.13, infrastructure_class: "airport" },
    { id: "S-005", name: "Ponce — Mercedita", kind: "airport", lat: 18.008, lng: -66.563, infrastructure_class: "airport" },
    { id: "S-006", name: "Aguirre Power Complex", kind: "power-plant", lat: 17.953, lng: -66.22, infrastructure_class: "power" },
    { id: "S-007", name: "Yabucoa Oil Terminal", kind: "terminal", lat: 18.058, lng: -65.836, infrastructure_class: "port" },
    { id: "S-008", name: "Toa Baja PRASA Pump 4", kind: "water-pumping", lat: 18.443, lng: -66.26, infrastructure_class: "water" },
    { id: "S-009", name: "Cabo Rojo Telecom Tower", kind: "telecom", lat: 17.985, lng: -67.155, infrastructure_class: "telecom" },
    { id: "S-010", name: "Vieques Western Reserve", kind: "former-military", lat: 18.118, lng: -65.56, sensitive: true, infrastructure_class: "military_adjacent" },
    { id: "S-011", name: "San Juan Port — Pier 15", kind: "port", lat: 18.46, lng: -66.106, infrastructure_class: "port" },
    { id: "S-012", name: "Arecibo Substation N-3", kind: "substation", lat: 18.46, lng: -66.715, infrastructure_class: "power" }
  ],
  contracts: [
    { id: "C-9241", agency: "AG-001", vendor: "V-1024", site: "S-008", amount: 12400000, signed: "2024-03-11", status: "executed", tier: "T2", note: "Emergency pump rehab — sole source.", procurement_method: "sole_source" },
    { id: "C-9301", agency: "AG-003", vendor: "V-1024", site: "S-001", amount: 24780000, signed: "2024-05-02", status: "executed", tier: "T2", note: "Site clearing + perimeter works.", procurement_method: "emergency" },
    { id: "C-9382", agency: "AG-003", vendor: "V-2071", site: "S-001", amount: 18300000, signed: "2024-06-19", status: "amended", tier: "T2", note: "Amend +2 — scope expansion, unspecified.", procurement_method: "amendment" },
    { id: "C-9421", agency: "AG-002", vendor: "V-3771", site: "S-012", amount: 6750000, signed: "2024-07-14", status: "executed", tier: "T2" },
    { id: "C-9555", agency: "AG-005", vendor: "V-1188", site: "S-004", amount: 9640000, signed: "2024-09-29", status: "amended", tier: "T2", note: "Cargo apron resurfacing — no-bid.", procurement_method: "sole_source" },
    { id: "C-9620", agency: "AG-003", vendor: "V-1024", site: "S-010", amount: 31200000, signed: "2024-10-22", status: "flagged", tier: "T2", note: "Disposal & clearing — concealed access road." },
    { id: "C-9802", agency: "AG-003", vendor: "V-2071", site: "S-001", amount: 14950000, signed: "2025-01-17", status: "flagged", tier: "T2", note: "Third amendment — no project closeout." },
    { id: "C-9920", agency: "AG-003", vendor: "V-1024", site: "S-010", amount: 19800000, signed: "2025-03-01", status: "flagged", tier: "T2", note: "Continuation works — Vieques W. Reserve." }
  ],
  events: [
    { id: "E-001", kind: "contract", at: "2024-05-02", siteId: "S-001", refId: "C-9301", label: "C-9301 signed", tier: "T2" },
    { id: "E-002", kind: "contract", at: "2024-06-19", siteId: "S-001", refId: "C-9382", label: "C-9382 amend", tier: "T2" },
    { id: "E-003", kind: "imagery", at: "2024-08-12", siteId: "S-001", label: "New clearing — 4.1 ha", tier: "T1" },
    { id: "E-005", kind: "report", at: "2024-08-17", siteId: "S-001", label: "Local sighting — Ceiba", tier: "T3" },
    { id: "E-006", kind: "contract", at: "2024-10-22", siteId: "S-010", refId: "C-9620", label: "C-9620 signed", tier: "T2" },
    { id: "E-007", kind: "imagery", at: "2024-11-04", siteId: "S-010", label: "Access road extended", tier: "T1" },
    { id: "E-009", kind: "outage", at: "2024-11-07", siteId: "S-010", label: "Local grid outage 32m", tier: "T2" },
    { id: "E-011", kind: "imagery", at: "2025-02-22", siteId: "S-010", label: "Concrete pad — 18×24m", tier: "T1" },
    { id: "E-012", kind: "report", at: "2025-02-25", siteId: "S-010", label: "Witness — light formation", tier: "T3" }
  ],
  anomalies: [
    {
      id: "A-014",
      title: "Ceiba contract concentration with imagery overlap",
      category: "cross-domain",
      score: 0.91,
      band: "hi",
      siteId: "S-001",
      summary: "Four awards to two vendors converge on Roosevelt Roads inside a 9-month window. Imagery shows new clearing near the contract-amendment window; a local report appears in the same period.",
      factors: [
        { tag: "finance", note: "Vendor concentration across linked awards" },
        { tag: "spatial", note: "Contracts converge near sensitive infrastructure" },
        { tag: "temporal", note: "Imagery and report events cluster inside one week" },
        { tag: "report", note: "One T3 local report remains uncorroborated" }
      ],
      contracts: ["C-9301", "C-9382", "C-9802"],
      events: ["E-001", "E-002", "E-003", "E-004", "E-005"],
      confidence: 3,
      contradictions: ["Witness date and technical-event date do not fully align; keep T3 claim as lead only."]
    },
    {
      id: "A-021",
      title: "Vieques amendment cluster + grid outage",
      category: "infrastructure",
      score: 0.84,
      band: "hi",
      siteId: "S-010",
      summary: "Two awards converge on Vieques western reserve with imagery and outage events in close sequence. Pattern is operationally significant but not dispositive without additional records.",
      factors: [
        { tag: "finance", note: "Large vendor concentration on restricted-adjacent site" },
        { tag: "infra", note: "New construction signature needs permit reconciliation" },
        { tag: "temporal", note: "Outage and approach event share date" }
      ],
      contracts: ["C-9620", "C-9920"],
      events: ["E-006", "E-007", "E-008", "E-009", "E-011", "E-012"],
      confidence: 3,
      contradictions: []
    },
    {
      id: "A-029",
      title: "Aguadilla apron resurfacing — no-bid",
      category: "financial",
      score: 0.62,
      band: "md",
      siteId: "S-004",
      summary: "Sole-source aviation-related award to logistics vendor requires procurement-method review.",
      factors: [
        { tag: "finance", note: "Vendor scope shift from logistics to aviation" },
        { tag: "source", note: "Bid-waiver support record not attached" }
      ],
      contracts: ["C-9555"],
      events: [],
      confidence: 2,
      contradictions: []
    }
  ],
  sources: [
    { id: "SRC-TIGER", name: "TIGER boundary layer fixture", tier: "T1", kind: "technical", status: "online" },
    { id: "SRC-IMAGERY", name: "Imagery change-detection fixture", tier: "T1", kind: "technical", status: "online" },
    { id: "SRC-CONTRACTS", name: "Procurement contract fixture", tier: "T2", kind: "operational", status: "online" },
    { id: "SRC-OUTAGE", name: "Grid outage fixture", tier: "T2", kind: "operational", status: "partial" },
    { id: "SRC-REPORTS", name: "Field report fixture", tier: "T3", kind: "eyewitness", status: "online" }
  ],
  investigations: [
    { id: "INV-007", title: "Eastern PR infrastructure convergence", active_vector: "finance → spatial → anomaly", status: "active" },
    { id: "INV-011", title: "Water/power resilience procurement", active_vector: "government → infrastructure", status: "active" }
  ],
  alerts: [
    { id: "AL-001", at: "09:14Z", kind: "anomaly", title: "A-014 score crossed high threshold", tier: "T1", investigation: "INV-007" },
    { id: "AL-002", at: "08:33Z", kind: "finance", title: "Three flagged contracts in active window", tier: "T2", investigation: "INV-007" },
    { id: "AL-003", at: "07:52Z", kind: "source", title: "Outage source is partial; confidence cap applies", tier: "T2", investigation: "INV-011" }
  ],
  watchlist: [
    { kind: "anomaly", id: "A-014" },
    { kind: "site", id: "S-001" },
    { kind: "vendor", id: "V-1024" }
  ]
};

export const fmtMoney = (value: number): string => {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

export const byId = <T extends { id: string }>(items: T[], id: string): T | undefined => items.find((item) => item.id === id);
