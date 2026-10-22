// Run after `npm run build` in frontend, with the local API on port 8001.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createServer } from "node:net";
import {
  request as httpRequest,
  createServer as createHttpServer,
} from "node:http";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../frontend/", import.meta.url));
async function check(configured) {
  const socket = createServer();
  await new Promise((resolve) => socket.listen(0, "127.0.0.1", resolve));
  const port = socket.address().port;
  await new Promise((resolve) => socket.close(resolve));
  const password = randomBytes(24).toString("hex");
  const child = spawn(
    process.execPath,
    [
      "node_modules/next/dist/bin/next",
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    {
      cwd: root,
      stdio: "ignore",
      env: {
        ...process.env,
        WORKSPACE_AUTH_REQUIRED: "1",
        WORKSPACE_USERNAME: "owner",
        WORKSPACE_PASSWORD: configured ? password : "",
      },
    },
  );
  const origin = `http://127.0.0.1:${port}`;
  const get = (path, options = {}) =>
    fetch(origin + path, {
      ...options,
      signal: AbortSignal.timeout(10_000),
      redirect: "manual",
    });
  try {
    let ready = false;
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        if ((await get("/")).status === 200) {
          ready = true;
          break;
        }
      } catch {}
      if (child.exitCode !== null)
        throw new Error("Preview server stopped before becoming ready.");
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    assert.ok(ready, "Preview server starts");
    assert.match(await (await get("/")).text(), /Less searching/);
    for (const path of ["/workspace", "/api/repositories"]) {
      const response = await get(path);
      assert.equal(response.status, configured ? 401 : 503, path);
      assert.match(response.headers.get("cache-control"), /no-store/);
    }
    if (!configured) return;
    assert.equal((await get("/api/ready")).status, 200);
    const authorization = `Basic ${Buffer.from(`owner:${password}`).toString("base64")}`;
    const headers = { authorization };
    assert.equal((await get("/api/ready", { headers })).status, 200);
    const workspace = await get("/workspace", { headers });
    assert.equal(workspace.status, 200);
    assert.match(workspace.headers.get("cache-control"), /private/);
    assert.match(workspace.headers.get("x-robots-tag"), /noindex/);
    assert.equal((await get("/api/repositories", { headers })).status, 200);
    assert.equal(
      (
        await get("/api/repositories", {
          headers: { authorization: "Basic invalid" },
        })
      ).status,
      401,
    );
    assert.equal(
      (
        await get("/api/no-such-route", {
          method: "POST",
          headers: { ...headers, origin: "https://other.example" },
        })
      ).status,
      403,
    );
    assert.equal(
      (
        await get("/api/no-such-route", {
          method: "POST",
          headers: { ...headers, origin, "sec-fetch-site": "same-origin" },
        })
      ).status,
      404,
    );
    // Raw HTTP preserves Host; Node fetch normalizes that header to its URL.
    const forwardedStatus = await new Promise((resolve, reject) => {
      const request = httpRequest(
        origin + "/api/no-such-route",
        {
          method: "POST",
          headers: {
            ...headers,
            origin: "https://site.example",
            host: "site.example",
            "x-forwarded-proto": "https",
          },
        },
        (response) => {
          response.resume();
          resolve(response.statusCode);
        },
      );
      request.on("error", reject);
      request.end();
    });
    assert.equal(forwardedStatus, 404);
    console.log(
      "Hosted web boundary: public landing, gated workspace/API, readiness, same-origin requests passed.",
    );
  } finally {
    const exited = new Promise((resolve) => child.once("exit", resolve));
    child.kill();
    await exited;
  }
}
let stub;
let forwardedCredentials = false;
if (process.argv.includes("--stub-api")) {
  // CI isolates the web boundary; the container job exercises the real API.
  stub = createHttpServer((request, response) => {
    forwardedCredentials ||= Boolean(request.headers.authorization);
    response.setHeader("content-type", "application/json");
    if (request.url === "/ready") response.end('{"status":"ready"}');
    else if (request.url === "/repositories") response.end("[]");
    else {
      response.statusCode = 404;
      response.end('{"detail":"Not Found"}');
    }
  });
  await new Promise((resolve, reject) => {
    stub.once("error", reject);
    stub.listen(8001, "127.0.0.1", resolve);
  });
}
try {
  await check(true);
  await check(false);
  assert.equal(
    forwardedCredentials,
    false,
    "Workspace credentials must not reach the API",
  );
  console.log("Hosted web boundary: missing credentials fail closed.");
} finally {
  if (stub) await new Promise((resolve) => stub.close(resolve));
}
