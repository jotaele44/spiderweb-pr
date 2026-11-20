import { Pill, type Tone } from "../../components/Badges";
import { downloadJson } from "../../export/download";
import {
  ASSERTION_RUNGS,
  EVIDENCE_DIMENSIONS,
  shortHash,
  words,
  type AccessPointEvidence,
  type AccessPointFeature,
  type AssertionRung,
  type EvidenceTierName,
  type RegistryStatus,
} from "./accessPointsApi";
import type { EvidenceState } from "./useAccessPointsController";

/** What each step of the ladder needs. Shown beside the step it guards. */
export const RUNG_REQUIREMENT: Record<AssertionRung, string> = {
  ANOMALY: "Something was noticed. Nothing more is established.",
  FEATURE: "Needs supporting or direct evidence that a physical feature exists there.",
  OPENING: "Needs a directly observed physical opening. Shape alone cannot provide one.",
  PASSAGE: "Needs directly observed accessibility: the opening can be entered.",
  CONNECTION: "Needs directly observed connectivity of a stated kind to somewhere else.",
};

export const PROVISIONAL_SENTENCE =
  "Provisional discovery. No coordinates, depth, opening or connection is recorded.";

const STATUS_TONE: Record<RegistryStatus, Tone> = {
  PROVISIONAL_DISCOVERY: "warn",
  CANDIDATE: "info",
  UNDER_REVIEW: "info",
  VERIFIED: "ok",
  REJECTED: "alert",
  SUPERSEDED: "alert",
};

const TIER_TONE: Record<EvidenceTierName, Tone> = {
  UNRESOLVED: "info",
  CANDIDATE: "warn",
  SUPPORTING: "info",
  DIRECT: "ok",
  CONTRADICTED: "alert",
};

/** A date that is absent is said to be absent; it is never left blank. */
function dated(label: string, value: string | null | undefined) {
  return (
    <span className="ap-date">
      <span className="subtle">{label}</span> {value ?? "not recorded"}
    </span>
  );
}

function Ladder({ reached }: { reached: AssertionRung }) {
  const index = ASSERTION_RUNGS.indexOf(reached);
  return (
    <ol className="ap-ladder" aria-label="What the evidence establishes">
      {ASSERTION_RUNGS.map((rung, position) => {
        const state = position < index ? "passed" : position === index ? "reached" : "not-reached";
        return (
          <li key={rung} data-rung-state={state} aria-current={state === "reached" ? "step" : undefined}>
            <strong>{words(rung)}</strong>
            <span className="subtle">
              {state === "reached" ? " — reached. " : state === "passed" ? " — established. " : " — not established. "}
              {position > index || position === 0 ? RUNG_REQUIREMENT[rung] : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function EvidenceBody({ evidence }: { evidence: AccessPointEvidence }) {
  return (
    <>
      {evidence.promotion_blockers.length > 0 && (
        <>
          <h3>Why this record is not verified</h3>
          <ul className="ap-list">
            {evidence.promotion_blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Assertions</h3>
      {evidence.assertions.length === 0 && <p className="subtle">No assertions are recorded.</p>}
      <ul className="ap-list">
        {evidence.assertions.map((assertion, position) => (
          <li key={`${assertion.dimension}-${position}`} data-effective-tier={assertion.effective_tier}>
            <strong>{words(assertion.dimension)}</strong>{" "}
            <Pill tone={TIER_TONE[assertion.effective_tier]}>{words(assertion.effective_tier)}</Pill>
            {assertion.asserted_tier !== assertion.effective_tier && (
              <span className="ap-lowered">
                {" "}
                Asserted as {words(assertion.asserted_tier)}; the evidence rules lowered it to{" "}
                {words(assertion.effective_tier)}.
              </span>
            )}
            <div>{assertion.statement}</div>
            <div className="subtle">
              Claim: {words(assertion.claim_class)} · Basis: {assertion.basis.map(words).join(", ") || "none stated"} ·
              Review: {words(assertion.adjudication)}
            </div>
          </li>
        ))}
      </ul>
      <h3>Sources</h3>
      {evidence.sources.length === 0 && <p className="subtle">No sources are recorded.</p>}
      <ul className="ap-list">
        {evidence.sources.map((source) => (
          <li key={source.source_id} data-provenance-state={source.provenance_state}>
            <strong>{source.title}</strong>
            <div className="subtle">
              {source.provider} · {words(source.provenance_state)}
              {source.manifestation_sha256 ? ` · sha256 ${shortHash(source.manifestation_sha256)}` : " · bytes not held"}
            </div>
            <div className="ap-dates">
              {dated("Surveyed", source.survey_date)}
              {dated("Published", source.published_date)}
              {dated("Retrieved", source.retrieved_utc)}
            </div>
          </li>
        ))}
      </ul>
      <p className="subtle">
        Registry document {evidence.provenance.path} · sha256 {shortHash(evidence.provenance.sha256)}
      </p>
    </>
  );
}

/** Feature explorer and evidence view for one selected record. */
export function AccessPointDetail({
  feature,
  evidence,
  onClose,
}: {
  feature: AccessPointFeature;
  evidence: EvidenceState;
  onClose?: () => void;
}) {
  const properties = feature.properties;
  const uncertainty =
    properties.horizontal_uncertainty_m === null
      ? "unknown"
      : `±${properties.horizontal_uncertainty_m.toLocaleString()} m`;
  return (
    <section className="card ap-detail" aria-label={`Record ${properties.feature_id}`}>
      <div className="ap-detail-head">
        <h3 className="mono">{properties.feature_id}</h3>
        <Pill tone={STATUS_TONE[properties.status]}>{words(properties.status)}</Pill>
        {onClose && (
          <button type="button" className="linklike" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      <div className="subtle">
        {words(properties.registry_code === "INAP" ? "Inland Access Points" : "Off-Shore Access Points")} ·{" "}
        {words(properties.feature_class)}
      </div>
      {properties.status === "PROVISIONAL_DISCOVERY" && (
        <p className="ap-note" role="note">
          {PROVISIONAL_SENTENCE}
        </p>
      )}
      {(properties.raw_names.length > 0 || properties.provisional_labels.length > 0) && (
        <div className="subtle">
          Source labels: {[...properties.raw_names, ...properties.provisional_labels].join(", ")}
        </div>
      )}
      {properties.locality_labels.length > 0 && (
        <div className="subtle">Locality named by the source: {properties.locality_labels.join(", ")}</div>
      )}
      <dl className="ap-facts">
        <dt>Position</dt>
        <dd>{feature.geometry === null ? "no registered coordinates" : words(properties.geometry_basis)}</dd>
        <dt>Horizontal uncertainty</dt>
        <dd>{feature.geometry === null ? "not applicable" : uncertainty}</dd>
        {properties.geometry_is_modeled && (
          <>
            <dt>Geometry</dt>
            <dd>modelled, not directly measured</dd>
          </>
        )}
      </dl>
      <Ladder reached={properties.assertion_rung} />
      <h3>Evidence dimensions</h3>
      <ul className="ap-dimensions">
        {EVIDENCE_DIMENSIONS.map((dimension) => (
          <li key={dimension}>
            <span>{words(dimension)}</span>
            <Pill tone={TIER_TONE[properties.dimensions[dimension]]}>{words(properties.dimensions[dimension])}</Pill>
          </li>
        ))}
      </ul>
      {properties.notes && <p className="subtle">{properties.notes}</p>}
      {evidence.status === "loading" && <p role="status">Loading evidence…</p>}
      {evidence.status === "error" && (
        <p className="ap-alert" role="alert">
          Evidence could not be loaded: {evidence.message}
        </p>
      )}
      {evidence.status === "ready" && (
        <>
          <EvidenceBody evidence={evidence.evidence} />
          <button
            type="button"
            className="act"
            onClick={() => downloadJson(`access-point-evidence-${properties.feature_id}.json`, evidence.evidence)}
          >
            Download evidence (JSON)
          </button>
        </>
      )}
    </section>
  );
}
