import { NextRequest, NextResponse } from "next/server";
import { crossSiteMutation, workspaceAccess } from "./lib/workspace-access";

function forward(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete("authorization");
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Cache-Control", "private, no-store");
  response.headers.set("X-Robots-Tag", "noindex, nofollow");
  return response;
}

export function proxy(request: NextRequest) {
  // This is the only anonymous API endpoint: a minimal database readiness check.
  if (
    request.nextUrl.pathname === "/api/ready" &&
    ["GET", "HEAD"].includes(request.method)
  )
    return forward(request);
  const access = workspaceAccess(
    request.headers.get("authorization"),
    process.env,
  );
  if (access === "unconfigured")
    return new NextResponse("Workspace access is not configured.", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  if (access === "challenge")
    return new NextResponse("Sign in to your CodeAtlas workspace.", {
      status: 401,
      headers: {
        "WWW-Authenticate":
          'Basic realm="CodeAtlas workspace", charset="UTF-8"',
        "Cache-Control": "no-store",
      },
    });
  // Render terminates TLS before the container; compare against the browser's
  // Host and forwarded protocol, rather than the internal Node listening URL.
  const protocol =
    request.headers.get("x-forwarded-proto") === "https"
      ? "https:"
      : request.nextUrl.protocol;
  const browserOrigin = `${protocol}//${request.headers.get("host") || request.nextUrl.host}`;
  if (
    crossSiteMutation(
      request.method,
      request.headers.get("origin"),
      browserOrigin,
      request.headers.get("sec-fetch-site"),
    )
  ) {
    return new NextResponse("Cross-site requests are not allowed.", {
      status: 403,
    });
  }
  return forward(request);
}

export const config = { matcher: ["/workspace/:path*", "/api/:path*"] };
