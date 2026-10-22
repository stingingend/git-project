import test from "node:test";
import assert from "node:assert/strict";
import { workspaceAccess, crossSiteMutation } from "../lib/workspace-access.ts";

const env = {
  WORKSPACE_AUTH_REQUIRED: "1",
  WORKSPACE_USERNAME: "owner",
  WORKSPACE_PASSWORD: "a-long-test-password",
};
const basic = (text) => `Basic ${Buffer.from(text).toString("base64")}`;
test("local workspace remains available when authentication is explicitly unused", () => {
  assert.equal(workspaceAccess(null, {}), "allow");
});
test("hosted workspace fails closed for missing or incomplete credentials", () => {
  for (const config of [
    { WORKSPACE_AUTH_REQUIRED: "1" },
    { WORKSPACE_USERNAME: "owner" },
    { ...env, WORKSPACE_PASSWORD: "short" },
    { ...env, WORKSPACE_USERNAME: "bad:user" },
  ])
    assert.equal(workspaceAccess(null, config), "unconfigured");
});
test("workspace requires exact credentials and rejects malformed headers", () => {
  assert.equal(
    workspaceAccess(basic("owner:a-long-test-password"), env),
    "allow",
  );
  for (const header of [
    null,
    "Bearer token",
    "Basic !!!!",
    basic("wrong:a-long-test-password"),
    basic("owner:wrong"),
    `Basic ${"a".repeat(5000)}`,
  ])
    assert.equal(workspaceAccess(header, env), "challenge");
});
test("browser mutations must come from the same origin", () => {
  assert.equal(
    crossSiteMutation(
      "POST",
      "https://evil.example",
      "https://code.example",
      null,
    ),
    true,
  );
  assert.equal(
    crossSiteMutation("POST", null, "https://code.example", "cross-site"),
    true,
  );
  assert.equal(
    crossSiteMutation(
      "POST",
      "https://code.example",
      "https://code.example",
      "same-origin",
    ),
    false,
  );
  assert.equal(
    crossSiteMutation(
      "GET",
      "https://evil.example",
      "https://code.example",
      "cross-site",
    ),
    false,
  );
  assert.equal(
    crossSiteMutation("POST", null, "https://code.example", null),
    false,
  );
});
