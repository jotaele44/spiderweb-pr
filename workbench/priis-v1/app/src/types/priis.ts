export type EvidenceTier = "T1" | "T2" | "T3" | "T4";
export type Confidence = 1 | 2 | 3;
export type ModuleId = "command" | "finance" | "spatial" | "anomaly" | "graph" | "query";
export type SelectionKind = "agency" | "vendor" | "contract" | "site" | "event" | "anomaly" | "source" | "investigation" | "finding";

export interface Selection {
  kind: SelectionKind;
  id: string;
}

export interface Agency {
  id: string;
  code: string;
  name: string;
}

export interface Vendor {
  id: string;
  name: string;
  risk: number;
  tier: EvidenceTier;
}

export interface Site {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lng: number;
  sensitive?: boolean;
  infrastructure_class?: string;
  /** TIGER county GEOID (PR STATEFP=72), joined by ingest_tiger_pr.py */
  municipio_geoid?: string;
  /** TIGER tract GEOID, joined by ingest_tiger_pr.py */
  tract_geoid?: string;
}

export interface Contract {
  id: string;
  agency: string;
  vendor: string;
  site: string;
  amount: number;
  signed: string;
  status: "planned" | "executed" | "amended" | "flagged" | "closed" | "unknown";
  tier: EvidenceTier;
  note?: string;
  procurement_method?: "competitive" | "sole_source" | "emergency" | "amendment" | "unknown";
}

export interface EventRecord {
  id: string;
  kind: "contract" | "imagery" | "flight" | "report" | "outage" | "permit" | "field" | "other";
  at: string;
  siteId: string;
  refId?: string;
  label: string;
  tier?: EvidenceTier;
}

export interface AnomalyFactor {
  tag: "finance" | "spatial" | "temporal" | "infra" | "report" | "imagery" | "flight" | "source";
  note: string;
}

export interface Anomaly {
  id: string;
  title: string;
  category: "financial" | "spatial" | "temporal" | "infrastructure" | "flight" | "imagery" | "report" | "cross-domain";
  score: number;
  band: "lo" | "md" | "hi";
  siteId: string;
  summary: string;
  factors: AnomalyFactor[];
  contracts: string[];
  events: string[];
  confidence: Confidence;
  contradictions: string[];
}

export interface SourceRecord {
  id: string;
  name: string;
  tier: EvidenceTier;
  kind: "technical" | "operational" | "eyewitness" | "secondary" | "derived";
  status: "online" | "partial" | "offline";
}

export interface Investigation {
  id: string;
  title: string;
  active_vector: string;
  status: "active" | "paused" | "closed" | "needs_review";
}

export interface AlertRecord {
  id: string;
  at: string;
  kind: "finance" | "spatial" | "source" | "anomaly" | "report";
  title: string;
  tier: EvidenceTier;
  investigation?: string;
}

export interface PriisData {
  agencies: Agency[];
  vendors: Vendor[];
  sites: Site[];
  contracts: Contract[];
  events: EventRecord[];
  anomalies: Anomaly[];
  sources: SourceRecord[];
  investigations: Investigation[];
  alerts: AlertRecord[];
  watchlist: Selection[];
}

export interface QueryResponse {
  finding: string;
  evidence: Array<{ tier: EvidenceTier; label: string; detail: string; entity?: Selection }>;
  sourceTierBreakdown: Record<EvidenceTier, number>;
  confidence: Confidence;
  contradictions: string[];
  missingData: string[];
  recommendedAction: string;
}
