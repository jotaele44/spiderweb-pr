import fs from "node:fs";
import path from "node:path";

const read = (relative: string) => fs.readFileSync(path.resolve(relative), "utf8");

describe("Spiderweb recovered auth/ACL/database parity", () => {
  it("freezes exactly eight protected non-auth POST vectors", () => {
    const protectedPosts = [
      "endpoints/account/delete_POST.ts",
      "endpoints/spatial/acl_POST.ts",
      "endpoints/spatial/features/query_POST.ts",
      "endpoints/spatial/investigations_POST.ts",
      "endpoints/spatial/layers/remote_POST.ts",
      "endpoints/spatial/layers/remove_POST.ts",
      "endpoints/spatial/layers/save_POST.ts",
      "endpoints/spiderweb/pipeline_POST.ts",
    ];
    for (const file of protectedPosts) expect(fs.existsSync(path.resolve(file))).toBeTrue();
    expect(protectedPosts.length).toBe(8);
  });

  it("requires an authenticated session for account deletion", () => {
    const source = read("endpoints/account/delete_POST.ts");
    expect(source).toContain("getServerUserSession(request)");
    expect(source).toContain("NotAuthenticatedError ? 401");
  });

  it("routes ACL mutation through authenticated SpatialAccessControl and preserves 401/403", () => {
    const source = read("endpoints/spatial/acl_POST.ts");
    expect(source).toContain("SpatialAccessControl.actor(request)");
    expect(source).toContain("SpatialAccessControl.setAcl");
    expect(source).toContain("NotAuthenticatedError?401:403");
  });

  it("enforces read permission before spatial feature queries", () => {
    const source = read("endpoints/spatial/features/query_POST.ts");
    expect(source).toContain("getServerUserSession(request)");
    expect(source).toContain("SpatialAccessControl.canRead");
    expect(source).toContain('status: 403');
  });

  it("enforces investigation ownership with admin override", () => {
    const source = read("endpoints/spatial/investigations_POST.ts");
    expect(source).toContain("SpatialAccessControl.actor(request)");
    expect(source).toContain('actor.role !== "admin"');
    expect(source).toContain("existing.ownerUserId !== actor.userId");
    expect(source).toContain("owner access");
  });

  it("enforces authenticated ownership on layer save/remove/remote ingestion", () => {
    for (const file of [
      "endpoints/spatial/layers/remote_POST.ts",
      "endpoints/spatial/layers/remove_POST.ts",
      "endpoints/spatial/layers/save_POST.ts",
    ]) {
      expect(read(file)).toContain("getServerUserSession(request)");
    }
    const remove = read("endpoints/spatial/layers/remove_POST.ts");
    expect(remove).toContain('user.role === "admin"');
    expect(remove).toContain("owner access");
  });

  it("restricts authoritative pipeline control to admins", () => {
    const source = read("endpoints/spiderweb/pipeline_POST.ts");
    expect(source).toContain("getServerUserSession(request)");
    expect(source).toContain('user.role !== "admin"');
    expect(source).toContain("Admin role required for authoritative pipeline control.");
    expect(source).toContain("status: 403");
  });

  it("preserves the exact nine-table recovered DB type denominator", () => {
    const schema = read("helpers/schema.tsx");
    const expected = [
      "loginAttempts",
      "sessions",
      "spatialAuditLog",
      "spatialInvestigations",
      "spatialLayerAcl",
      "spatialLayerFeatures",
      "spatialLayers",
      "userPasswords",
      "users",
    ];
    for (const table of expected) {
      expect(schema).toMatch(new RegExp("\\b" + table + "\\s*:"));
    }
    const dbBody = schema.match(/export interface DB\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
    const declared = [...dbBody.matchAll(/^\s{2}([A-Za-z0-9_]+):/gm)].map(match => match[1]);
    expect(declared.sort()).toEqual([...expected].sort());
  });

  it("keeps recovered user roles bounded to admin and user", () => {
    const schema = read("helpers/schema.tsx");
    expect(schema).toContain('export type UserRole = "admin" | "user"');
  });
});
