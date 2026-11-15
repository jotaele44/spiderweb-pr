export const PROGRAM_ACTIVITY_EVENT_VERSION = "PROGRAM_ACTIVITY_EVENT/v1" as const;

export type ActivityState =
  | "NOW"
  | "NEXT"
  | "QUEUED"
  | "BLOCKED"
  | "COMPLETED"
  | "SUPERSEDED"
  | "CONTRADICTED"
  | "UNRESOLVED";

export type ActivityPriority = 0 | 1 | 2 | 3 | 4;
export type ActivitySourceType =
  | "DECLARED_WORKFLOW"
  | "AUTHORITATIVE_RUNTIME"
  | "SOURCE_MANIFESTATION"
  | "FEDERATION_RECEIPT";

export interface ActivityProvenance {
  sourceId: string;
  sourceType: ActivitySourceType;
  sourceRef?: string;
  manifestationSha256?: string | null;
}

export interface ProgramActivityEvent {
  schema: typeof PROGRAM_ACTIVITY_EVENT_VERSION;
  eventId: string;
  producerId: string;
  functionId: string;
  eventType: string;
  title: string;
  detail: string;
  category: string;
  state: ActivityState;
  priority: ActivityPriority;
  scheduledAt: string | null;
  observedAt: string | null;
  canonicalRoute?: string;
  provenance: ActivityProvenance;
  source: "DECLARED" | "LIVE";
  supersedesEventId?: string;
  conflictKey?: string;
}

export interface DeclaredActivity {
  id: string;
  phase: "NOW" | "NEXT" | "QUEUED" | "BLOCKED";
  title: string;
  detail: string;
  category: string;
  href?: string;
}

export type TimelineActivity = ProgramActivityEvent & {
  phase: ActivityState;
  href?: string;
};

const PREFIX = "federation.programActivity.v1.";
const PRIORITY: Record<DeclaredActivity["phase"], ActivityPriority> = {
  NOW: 0,
  NEXT: 1,
  QUEUED: 2,
  BLOCKED: 3,
};

const VALID_STATES = new Set<ActivityState>([
  "NOW", "NEXT", "QUEUED", "BLOCKED",
  "COMPLETED", "SUPERSEDED", "CONTRADICTED", "UNRESOLVED",
]);

const VALID_PROVENANCE_TYPES = new Set<ActivitySourceType>([
  "DECLARED_WORKFLOW",
  "AUTHORITATIVE_RUNTIME",
  "SOURCE_MANIFESTATION",
  "FEDERATION_RECEIPT",
]);

function validRoute(value?: string): boolean {
  return value === undefined || (/^\/(?!\/)/.test(value) && !value.includes("://"));
}

function validIso(value: string | null): boolean {
  return value === null || Number.isFinite(Date.parse(value));
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value !== null && typeof value === "object") {
    return "{" + Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, nested]) => JSON.stringify(key) + ":" + canonical(nested))
      .join(",") + "}";
  }
  return JSON.stringify(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isActivityPriority(value: unknown): value is ActivityPriority {
  return Number.isInteger(value) && typeof value === "number" && value >= 0 && value <= 4;
}

function isActivityState(value: unknown): value is ActivityState {
  return typeof value === "string" && VALID_STATES.has(value as ActivityState);
}

function isActivitySourceType(value: unknown): value is ActivitySourceType {
  return typeof value === "string" && VALID_PROVENANCE_TYPES.has(value as ActivitySourceType);
}

function parseProgramActivityEvent(value: unknown): ProgramActivityEvent | null {
  if (!isRecord(value)) return null;
  const provenance = value.provenance;
  if (!isRecord(provenance)) return null;

  const canonicalRoute = value.canonicalRoute;
  const supersedesEventId = value.supersedesEventId;
  const conflictKey = value.conflictKey;

  if (
    value.schema !== PROGRAM_ACTIVITY_EVENT_VERSION ||
    typeof value.eventId !== "string" ||
    typeof value.producerId !== "string" ||
    typeof value.functionId !== "string" ||
    typeof value.eventType !== "string" ||
    typeof value.title !== "string" ||
    typeof value.detail !== "string" ||
    typeof value.category !== "string" ||
    !isActivityState(value.state) ||
    !isActivityPriority(value.priority) ||
    !isNullableString(value.scheduledAt) ||
    !isNullableString(value.observedAt) ||
    (canonicalRoute !== undefined && typeof canonicalRoute !== "string") ||
    (supersedesEventId !== undefined && typeof supersedesEventId !== "string") ||
    (conflictKey !== undefined && typeof conflictKey !== "string") ||
    typeof provenance.sourceId !== "string" ||
    !isActivitySourceType(provenance.sourceType) ||
    (provenance.sourceRef !== undefined && typeof provenance.sourceRef !== "string") ||
    (provenance.manifestationSha256 !== undefined &&
      provenance.manifestationSha256 !== null &&
      typeof provenance.manifestationSha256 !== "string") ||
    (value.source !== "DECLARED" && value.source !== "LIVE")
  ) {
    return null;
  }

  const event: ProgramActivityEvent = {
    schema: PROGRAM_ACTIVITY_EVENT_VERSION,
    eventId: value.eventId,
    producerId: value.producerId,
    functionId: value.functionId,
    eventType: value.eventType,
    title: value.title,
    detail: value.detail,
    category: value.category,
    state: value.state,
    priority: value.priority,
    scheduledAt: value.scheduledAt,
    observedAt: value.observedAt,
    provenance: {
      sourceId: provenance.sourceId,
      sourceType: provenance.sourceType,
    },
    source: value.source,
  };

  if (canonicalRoute !== undefined) event.canonicalRoute = canonicalRoute;
  if (supersedesEventId !== undefined) event.supersedesEventId = supersedesEventId;
  if (conflictKey !== undefined) event.conflictKey = conflictKey;
  if (typeof provenance.sourceRef === "string") event.provenance.sourceRef = provenance.sourceRef;
  if (provenance.manifestationSha256 === null || typeof provenance.manifestationSha256 === "string") {
    event.provenance.manifestationSha256 = provenance.manifestationSha256;
  }
  return event;
}

export function declaredEvents(
  producerId: string,
  items: readonly DeclaredActivity[],
): ProgramActivityEvent[] {
  return items.map((item) => ({
    schema: PROGRAM_ACTIVITY_EVENT_VERSION,
    eventId: `declared:${producerId}:${item.id}`,
    producerId,
    functionId: item.id,
    eventType: "DECLARED_WORKFLOW",
    title: item.title,
    detail: item.detail,
    category: item.category,
    state: item.phase,
    priority: PRIORITY[item.phase],
    scheduledAt: null,
    observedAt: null,
    canonicalRoute: validRoute(item.href) ? item.href : undefined,
    provenance: {
      sourceId: `dashboard-declared:${producerId}:${item.id}`,
      sourceType: "DECLARED_WORKFLOW",
    },
    source: "DECLARED",
  }));
}

export function validateProgramActivityEvent(event: ProgramActivityEvent): string[] {
  const errors: string[] = [];
  if (event.schema !== PROGRAM_ACTIVITY_EVENT_VERSION) errors.push("schema");
  if (!event.eventId) errors.push("eventId");
  if (!event.producerId) errors.push("producerId");
  if (!event.functionId) errors.push("functionId");
  if (!event.eventType) errors.push("eventType");
  if (!event.title) errors.push("title");
  if (!event.category) errors.push("category");
  if (!isActivityPriority(event.priority)) errors.push("priority");
  if (!validIso(event.scheduledAt)) errors.push("scheduledAt");
  if (!validIso(event.observedAt)) errors.push("observedAt");
  if (!validRoute(event.canonicalRoute)) errors.push("canonicalRoute");
  if (!event.provenance.sourceId || !event.provenance.sourceType) errors.push("provenance");
  return errors;
}

export function readLiveProgramActivity(
  producerId: string,
  storage: Pick<Storage, "getItem"> = localStorage,
): ProgramActivityEvent[] {
  try {
    const raw = storage.getItem(PREFIX + producerId);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const events: ProgramActivityEvent[] = [];
    for (const candidate of parsed) {
      const event = parseProgramActivityEvent(candidate);
      if (
        event?.producerId === producerId &&
        event.source === "LIVE" &&
        validateProgramActivityEvent(event).length === 0
      ) {
        events.push(event);
      }
    }
    return events;
  } catch {
    return [];
  }
}

export function appendProgramActivityEvent(
  event: ProgramActivityEvent,
  storage: Pick<Storage, "getItem" | "setItem"> = localStorage,
): boolean {
  const errors = validateProgramActivityEvent(event);
  if (event.source !== "LIVE") errors.push("source");
  if (errors.length) throw new Error("INVALID_PROGRAM_ACTIVITY_EVENT:" + errors.join(","));

  const rows = readLiveProgramActivity(event.producerId, storage);
  const existing = rows.find((row) => row.eventId === event.eventId);
  if (existing) {
    if (canonical(existing) === canonical(event)) return false;
    throw new Error("PROGRAM_ACTIVITY_EVENT_ID_COLLISION");
  }
  storage.setItem(PREFIX + event.producerId, JSON.stringify([...rows, event]));
  return true;
}

function eventTime(event: ProgramActivityEvent): string {
  return event.observedAt ?? event.scheduledAt ?? "";
}

export function mergeProgramActivity(
  producerId: string,
  declared: readonly DeclaredActivity[],
  live: readonly ProgramActivityEvent[],
  nowMs = Date.now(),
  staleAfterMs = 7 * 86_400_000,
): TimelineActivity[] {
  const liveRows = live.filter(
    (event) =>
      event.producerId === producerId &&
      event.source === "LIVE" &&
      validateProgramActivityEvent(event).length === 0,
  );
  const combined = [...declaredEvents(producerId, declared), ...liveRows];
  const byId = new Map<string, ProgramActivityEvent>();

  for (const event of combined) {
    const prior = byId.get(event.eventId);
    if (!prior) {
      byId.set(event.eventId, event);
    } else if (canonical(prior) !== canonical(event)) {
      byId.set(event.eventId, {
        ...prior,
        state: "UNRESOLVED",
        detail: prior.detail + " · event ID collision",
      });
    }
  }

  const rows = [...byId.values()];
  const supersededIds = new Set<string>();
  for (const event of rows) {
    if (event.supersedesEventId) supersededIds.add(event.supersedesEventId);
  }

  const groups = new Map<string, ProgramActivityEvent[]>();
  for (const event of rows) {
    const current = groups.get(event.functionId) ?? [];
    groups.set(event.functionId, [...current, event]);
  }

  const output: TimelineActivity[] = [];
  for (const group of groups.values()) {
    const candidates = group
      .filter((event) => event.source === "LIVE" && !supersededIds.has(event.eventId))
      .sort((a, b) =>
        eventTime(b).localeCompare(eventTime(a)) ||
        a.priority - b.priority ||
        a.eventId.localeCompare(b.eventId)
      );

    const chosen = candidates[0] ?? group.find((event) => event.source === "DECLARED");
    if (!chosen) continue;

    const tied = candidates.filter(
      (event) =>
        eventTime(event) === eventTime(chosen) &&
        event.priority === chosen.priority,
    );
    const signatures = new Set(
      tied.map((event) =>
        [
          event.state,
          event.title,
          event.canonicalRoute,
          event.eventType,
          event.conflictKey ?? "",
        ].join("|")
      ),
    );

    let state: ActivityState =
      tied.length > 1 && signatures.size > 1 ? "UNRESOLVED" : chosen.state;

    if (
      chosen.source === "LIVE" &&
      chosen.observedAt &&
      state !== "COMPLETED" &&
      state !== "SUPERSEDED" &&
      nowMs - Date.parse(chosen.observedAt) > staleAfterMs
    ) {
      state = "UNRESOLVED";
    }

    output.push({
      ...chosen,
      state,
      phase: state,
      href: chosen.canonicalRoute,
    });
  }

  return output.sort((a, b) =>
    a.priority - b.priority ||
    eventTime(a).localeCompare(eventTime(b)) ||
    a.functionId.localeCompare(b.functionId) ||
    a.eventId.localeCompare(b.eventId)
  );
}

export function verifyCanonicalRoutes(
  events: readonly Pick<ProgramActivityEvent, "eventId" | "canonicalRoute">[],
  routePaths: readonly string[],
): { eventId: string; route: string }[] {
  const allowed = new Set(routePaths);
  const issues: { eventId: string; route: string }[] = [];
  for (const event of events) {
    if (event.canonicalRoute && !allowed.has(event.canonicalRoute)) {
      issues.push({ eventId: event.eventId, route: event.canonicalRoute });
    }
  }
  return issues;
}
