import { createHash, timingSafeEqual } from "node:crypto";

export function workspaceAccess(
  authorization: string | null,
  env: Record<string, string | undefined>,
): "allow" | "challenge" | "unconfigured" {
  const user = env.WORKSPACE_USERNAME;
  const password = env.WORKSPACE_PASSWORD;
  const required = env.WORKSPACE_AUTH_REQUIRED === "1";
  if (!user && !password && !required) return "allow";
  if (!user || !password || user.includes(":") || password.length < 16)
    return "unconfigured";
  if (
    !authorization ||
    authorization.length > 4096 ||
    !/^Basic [A-Za-z0-9+/]+={0,2}$/i.test(authorization)
  )
    return "challenge";
  const supplied = Buffer.from(authorization.slice(6), "base64").toString(
    "utf8",
  );
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return timingSafeEqual(digest(supplied), digest(`${user}:${password}`))
    ? "allow"
    : "challenge";
}

export function crossSiteMutation(
  method: string,
  origin: string | null,
  requestOrigin: string,
  fetchSite: string | null,
) {
  return (
    !["GET", "HEAD", "OPTIONS"].includes(method) &&
    (fetchSite === "cross-site" ||
      (origin !== null && origin !== requestOrigin))
  );
}
