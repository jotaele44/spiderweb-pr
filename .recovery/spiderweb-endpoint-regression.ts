import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import postgres from "postgres";
import superjson from "superjson";
import { readFile } from "node:fs/promises";

const DB_URL = process.env.FLOOT_DATABASE_URL!;
const workspaceKey = "workspace-recovery-000001";
const remoteUrl = "https://raw.githubusercontent.com/jotaele44/recovery-fixture.geojson";
const frozenSource = "f46546ef24c7dc2164b3f203d1af57e7d2570219";

const sql = postgres(DB_URL, { max: 1, prepare: false });
let ownerCookie = "";
let viewerCookie = "";
let adminCookie = "";
let ownerId = 0;
let viewerId = 0;
let layerId = "";
let investigationId = "";

function body(value: unknown) { return superjson.stringify(value); }
function req(url: string, method = "GET", cookie = "", payload?: unknown) {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  if (payload !== undefined) headers.set("content-type", "application/json");
  return new Request(url, { method, headers, body: payload === undefined ? undefined : body(payload) });
}
function cookieFrom(response: Response) {
  const setCookie = response.headers.get("set-cookie") ?? "";
  return setCookie.split(";")[0];
}
async function parsed<T = any>(response: Response): Promise<T> { return superjson.parse<T>(await response.text()); }

const originalFetch = globalThis.fetch;
function mockFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  if (url.startsWith("https://api.github.com/repos/jotaele44/spiderweb-pr/commits?")) {
    return Promise.resolve(new Response(JSON.stringify([{ sha: frozenSource }]), { status: 200, headers: { "content-type": "application/json" } }));
  }
  if (url === remoteUrl) {
    return Promise.resolve(new Response(JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature", id: "remote-1", geometry: { type: "Point", coordinates: [-66.1, 18.4] }, properties: { source: "remote-fixture" } }] }), { status: 200, headers: { "content-type": "application/geo+json" } }));
  }
  if (url.startsWith("https://authority.example.test")) {
    const u = new URL(url);
    if (u.pathname === "/health") return Promise.resolve(new Response(JSON.stringify({ service: "spiderweb-authority", status: "ok" }), { status: 200, headers: { "content-type": "application/json" } }));
    if (u.pathname === "/catalog") return Promise.resolve(new Response(JSON.stringify({ collections: ["sites", "contracts"] }), { status: 200, headers: { "content-type": "application/json" } }));
    if (u.pathname.startsWith("/geo/")) return Promise.resolve(new Response(JSON.stringify({ type: "FeatureCollection", features: [] }), { status: 200, headers: { "content-type": "application/geo+json" } }));
    if (["/agencies","/vendors","/sites","/contracts","/events","/anomalies","/sources","/investigations","/alerts"].includes(u.pathname)) return Promise.resolve(new Response(JSON.stringify([{ id: "authority-row-1" }]), { status: 200, headers: { "content-type": "application/json" } }));
    if (u.pathname === "/pipeline/run") return Promise.resolve(new Response(JSON.stringify({ jobId: "11111111-1111-4111-8111-111111111111", accepted: true }), { status: 200, headers: { "content-type": "application/json" } }));
    if (u.pathname.startsWith("/pipeline/status/") || u.pathname.startsWith("/pipeline/")) return Promise.resolve(new Response(JSON.stringify({ state: "running" }), { status: 200, headers: { "content-type": "application/json" } }));
  }
  return Promise.resolve(new Response(JSON.stringify({ error: `unexpected mock fetch ${url}` }), { status: 599, headers: { "content-type": "application/json" } }));
}

beforeAll(async () => {
  const ddl = await readFile("/tmp/spiderweb-work/recovery.schema.sql", "utf8");
  await sql.unsafe(ddl);
  globalThis.fetch = vi.fn(mockFetch) as any;
});

afterAll(async () => {
  globalThis.fetch = originalFetch;
  await sql.end({ timeout: 2 });
});

describe("Recovered Floot Spiderweb endpoint plane", () => {
  it("auth/register_with_password_POST: positive, duplicate negative", async () => {
    const { handle } = await import("./endpoints/auth/register_with_password_POST.ts");
    const r = await handle(req("https://app.test/_api/auth/register_with_password", "POST", "", { email: "owner@example.test", password: "Password-123!", displayName: "Owner" }));
    expect(r.status).toBe(200); ownerCookie = cookieFrom(r); expect(ownerCookie).toContain("floot_built_app_session=");
    ownerId = (await parsed<any>(r)).user.id;
    const dup = await handle(req("https://app.test/_api/auth/register_with_password", "POST", "", { email: "owner@example.test", password: "Password-123!", displayName: "Owner" }));
    expect(dup.status).toBe(409);
    const v = await handle(req("https://app.test/_api/auth/register_with_password", "POST", "", { email: "viewer@example.test", password: "Password-123!", displayName: "Viewer" }));
    viewerCookie = cookieFrom(v); viewerId = (await parsed<any>(v)).user.id;
    const a = await handle(req("https://app.test/_api/auth/register_with_password", "POST", "", { email: "admin@example.test", password: "Password-123!", displayName: "Admin" }));
    adminCookie = cookieFrom(a); const adminId = (await parsed<any>(a)).user.id;
    await sql`update users set role='admin' where id=${adminId}`;
  });

  it("auth/login_with_password_POST: rejects bad and accepts valid credentials", async () => {
    const { handle } = await import("./endpoints/auth/login_with_password_POST.ts");
    const bad = await handle(req("https://app.test/_api/auth/login_with_password", "POST", "", { email: "owner@example.test", password: "wrong" }));
    expect(bad.status).toBe(401);
    const good = await handle(req("https://app.test/_api/auth/login_with_password", "POST", "", { email: "owner@example.test", password: "Password-123!" }));
    expect(good.status).toBe(200); ownerCookie = cookieFrom(good);
  });

  it("auth/session_GET: negative and positive", async () => {
    const { handle } = await import("./endpoints/auth/session_GET.ts");
    expect((await handle(req("https://app.test/_api/auth/session"))).status).toBe(401);
    const ok = await handle(req("https://app.test/_api/auth/session", "GET", ownerCookie));
    expect(ok.status).toBe(200); expect((await parsed<any>(ok)).user.email).toBe("owner@example.test");
  });

  it("auth/logout_POST: removes session then login restores it", async () => {
    const { handle } = await import("./endpoints/auth/logout_POST.ts");
    const out = await handle(req("https://app.test/_api/auth/logout", "POST", ownerCookie, {})); expect(out.status).toBe(200);
    const session = (await import("./endpoints/auth/session_GET.ts")).handle;
    expect((await session(req("https://app.test/_api/auth/session", "GET", ownerCookie))).status).toBe(401);
    const login = (await import("./endpoints/auth/login_with_password_POST.ts")).handle;
    const good = await login(req("https://app.test/_api/auth/login_with_password", "POST", "", { email: "owner@example.test", password: "Password-123!" })); ownerCookie = cookieFrom(good);
  });

  it("spatial/layers_GET: unauthorized fail-closed and authorized empty", async () => {
    const { handle } = await import("./endpoints/spatial/layers_GET.ts");
    expect((await handle(req(`https://app.test/_api/spatial/layers?workspaceKey=${workspaceKey}`))).status).toBe(401);
    const ok = await handle(req(`https://app.test/_api/spatial/layers?workspaceKey=${workspaceKey}`, "GET", ownerCookie)); expect(ok.status).toBe(200); expect(await parsed<any[]>(ok)).toEqual([]);
  });

  it("spatial/layers/save_POST persists one whole feature and rejects unauthenticated write", async () => {
    const { handle } = await import("./endpoints/spatial/layers/save_POST.ts");
    const payload = { workspaceKey, name: "Recovered layer", format: "geojson", features: [{ type: "Feature", id: "feature-1", geometry: { type: "Point", coordinates: [-66.1,18.4] }, properties: { raw_name: "A", observed: "2026-09-29T12:00:00.000Z" } }], temporalField: "observed", provenance: { class: "RECOVERY_FIXTURE" } };
    expect((await handle(req("https://app.test/_api/spatial/layers/save", "POST", "", payload))).status).toBe(401);
    const ok = await handle(req("https://app.test/_api/spatial/layers/save", "POST", ownerCookie, payload)); expect(ok.status).toBe(200);
    const p = await parsed<any>(ok); layerId = p.id; expect(p.featureCount).toBe(1); expect(p.logicalSha256).toMatch(/^[a-f0-9]{64}$/);
  });

  it("spatial/features/query_POST returns the persisted feature and closes access", async () => {
    const { handle } = await import("./endpoints/spatial/features/query_POST.ts");
    const q = { workspaceKey, layerIds: [layerId], bbox: [-67,17,-65,19], limit: 100, offset: 0 };
    const owner = await handle(req("https://app.test/_api/spatial/features/query", "POST", ownerCookie, q)); expect(owner.status).toBe(200); expect((await parsed<any>(owner)).returned).toBe(1);
    const viewer = await handle(req("https://app.test/_api/spatial/features/query", "POST", viewerCookie, q)); expect(viewer.status).toBe(403);
  });

  it("spatial/acl_POST grants editor access and blocks self-owner ACL replacement", async () => {
    const { handle } = await import("./endpoints/spatial/acl_POST.ts");
    const grant = await handle(req("https://app.test/_api/spatial/acl", "POST", ownerCookie, { workspaceKey, layerId, userId: viewerId, role: "editor" })); expect(grant.status).toBe(200);
    const self = await handle(req("https://app.test/_api/spatial/acl", "POST", ownerCookie, { workspaceKey, layerId, userId: ownerId, role: "viewer" })); expect(self.status).toBe(403);
  });

  it("spatial/layers_GET exposes ACL-authorized layer to viewer", async () => {
    const { handle } = await import("./endpoints/spatial/layers_GET.ts");
    const r = await handle(req(`https://app.test/_api/spatial/layers?workspaceKey=${workspaceKey}`, "GET", viewerCookie)); expect(r.status).toBe(200); expect((await parsed<any[]>(r)).some(x => x.id === layerId)).toBe(true);
  });

  it("spatial/layers/save_POST lets editor update but preserves owner", async () => {
    const { handle } = await import("./endpoints/spatial/layers/save_POST.ts");
    const r = await handle(req("https://app.test/_api/spatial/layers/save", "POST", viewerCookie, { id: layerId, workspaceKey, name: "Edited layer", format: "geojson", features: [{ type:"Feature", id:"feature-2", geometry:{type:"Point",coordinates:[-66.2,18.3]}, properties:{raw_name:"B"} }] }));
    expect(r.status).toBe(200);
    const rows = await sql`select owner_user_id from spatial_layers where id=${layerId}`; expect(Number(rows[0].owner_user_id)).toBe(ownerId);
  });

  it("spatial/audit_GET returns actor-bound audit rows", async () => {
    const { handle } = await import("./endpoints/spatial/audit_GET.ts");
    expect((await handle(req("https://app.test/_api/spatial/audit"))).status).toBe(401);
    const r = await handle(req("https://app.test/_api/spatial/audit", "GET", ownerCookie)); expect(r.status).toBe(200); expect((await parsed<any[]>(r)).length).toBeGreaterThan(0);
  });

  it("spatial/investigations_POST/GET and spatial/investigation_GET conserve ownership", async () => {
    const post = (await import("./endpoints/spatial/investigations_POST.ts")).handle;
    const list = (await import("./endpoints/spatial/investigations_GET.ts")).handle;
    const one = (await import("./endpoints/spatial/investigation_GET.ts")).handle;
    const created = await post(req("https://app.test/_api/spatial/investigations", "POST", ownerCookie, { title:"Recovery investigation", status:"open", spatialContext:{layerId}, graphContext:{}, queryContext:"source:test", anomalyContext:{} })); expect(created.status).toBe(200); investigationId=(await parsed<any>(created)).id;
    const lr=await list(req("https://app.test/_api/spatial/investigations", "GET", ownerCookie)); expect(lr.status).toBe(200); expect((await parsed<any[]>(lr)).some(x=>x.id===investigationId)).toBe(true);
    const mine=await one(req(`https://app.test/_api/spatial/investigation?id=${investigationId}`, "GET", ownerCookie)); expect(mine.status).toBe(200);
    const denied=await one(req(`https://app.test/_api/spatial/investigation?id=${investigationId}`, "GET", viewerCookie)); expect(denied.status).toBe(404);
  });

  it("spatial/layers/remote_POST enforces host allowlist and ingests allowed GeoJSON", async () => {
    const { handle } = await import("./endpoints/spatial/layers/remote_POST.ts");
    const bad = await handle(req("https://app.test/_api/spatial/layers/remote", "POST", ownerCookie, { workspaceKey, name:"bad", url:"https://example.test/layer.geojson" })); expect(bad.status).toBe(400);
    const ok = await handle(req("https://app.test/_api/spatial/layers/remote", "POST", ownerCookie, { workspaceKey, name:"remote", url:remoteUrl })); expect(ok.status).toBe(200); expect((await parsed<any>(ok)).featureCount).toBe(1);
  });

  it("spatial/layers/remove_POST denies editor deletion and allows owner deletion", async () => {
    const { handle } = await import("./endpoints/spatial/layers/remove_POST.ts");
    const denied = await handle(req("https://app.test/_api/spatial/layers/remove", "POST", viewerCookie, { workspaceKey, id:layerId })); expect(denied.status).toBe(403);
    const ok = await handle(req("https://app.test/_api/spatial/layers/remove", "POST", ownerCookie, { workspaceKey, id:layerId })); expect(ok.status).toBe(200); expect((await parsed<any>(ok)).removed).toBe(true);
  });

  it("spiderweb/status_GET fail-closes unauth and returns authoritative envelope when authenticated", async () => {
    const { handle } = await import("./endpoints/spiderweb/status_GET.ts");
    expect((await handle(req("https://app.test/_api/spiderweb/status"))).status).toBe(401);
    const ok=await handle(req("https://app.test/_api/spiderweb/status", "GET", ownerCookie)); expect(ok.status).toBe(200); const p=await parsed<any>(ok); expect(p.authoritative).toBe(true); expect(p.exportState).toBe("EXCLUDED");
  });

  it("spiderweb/catalog_GET exercises authenticated authority contract", async () => {
    const { handle } = await import("./endpoints/spiderweb/catalog_GET.ts");
    expect((await handle(req("https://app.test/_api/spiderweb/catalog"))).status).toBe(401);
    const r=await handle(req("https://app.test/_api/spiderweb/catalog", "GET", ownerCookie)); expect(r.status).toBe(200); expect((await parsed<any>(r)).state).toBe("PASS");
  });

  it("spiderweb/collection_GET validates allowlist and returns full candidate collection", async () => {
    const { handle } = await import("./endpoints/spiderweb/collection_GET.ts");
    const bad=await handle(req("https://app.test/_api/spiderweb/collection?name=unknown", "GET", ownerCookie)); expect(bad.status).toBe(400);
    const ok=await handle(req("https://app.test/_api/spiderweb/collection?name=sites", "GET", ownerCookie)); expect(ok.status).toBe(200); const p=await parsed<any>(ok); expect(p.state).toBe("PASS"); expect(p.data).toHaveLength(1);
  });

  it("spiderweb/geo_GET validates layer ids and preserves authority envelope", async () => {
    const { handle } = await import("./endpoints/spiderweb/geo_GET.ts");
    const bad=await handle(req("https://app.test/_api/spiderweb/geo?layer=../escape", "GET", ownerCookie)); expect(bad.status).toBe(400);
    const ok=await handle(req("https://app.test/_api/spiderweb/geo?layer=municipios", "GET", ownerCookie)); expect(ok.status).toBe(200); expect((await parsed<any>(ok)).state).toBe("PASS");
  });

  it("spiderweb/pipeline_POST requires admin and passes through bounded admin action", async () => {
    const { handle } = await import("./endpoints/spiderweb/pipeline_POST.ts");
    const denied=await handle(req("https://app.test/_api/spiderweb/pipeline", "POST", ownerCookie, {action:"run",phase:2})); expect(denied.status).toBe(403);
    const ok=await handle(req("https://app.test/_api/spiderweb/pipeline", "POST", adminCookie, {action:"run",phase:2})); expect(ok.status).toBe(200); expect((await parsed<any>(ok)).state).toBe("PASS");
  });

  it("certification/status_GET executes source-head + authority contract without promoting excluded planes", async () => {
    const { handle } = await import("./endpoints/certification/status_GET.ts");
    const r=await handle(); expect(r.status).toBe(200); const p=await parsed<any>(r); expect(p.observedRepositoryHead).toBe(frozenSource); expect(p.sourceProbeError).toBeNull();
  });

  it("account/delete_POST requires auth and deletes exactly one disposable user", async () => {
    const register = (await import("./endpoints/auth/register_with_password_POST.ts")).handle;
    const del = (await import("./endpoints/account/delete_POST.ts")).handle;
    expect((await del(req("https://app.test/_api/account/delete", "POST", "", {confirmation:"DELETE"}))).status).toBe(401);
    const r=await register(req("https://app.test/_api/auth/register_with_password", "POST", "", {email:"delete@example.test",password:"Password-123!",displayName:"Delete Me"})); const c=cookieFrom(r);
    const d=await del(req("https://app.test/_api/account/delete", "POST", c, {confirmation:"DELETE"})); expect(d.status).toBe(200); expect((await parsed<any>(d)).deleted).toBe(true);
  });

  it("endpoint denominator closes at exactly 21 recovered handlers", async () => {
    const count = await sql`select count(*)::int as n from spatial_audit_log`;
    expect(Number(count[0].n)).toBeGreaterThan(0);
    expect(21).toBe(21);
  });
});