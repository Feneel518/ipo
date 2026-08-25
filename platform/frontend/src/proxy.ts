import { NextRequest, NextResponse } from "next/server";

function unauthorized() {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="IPO Milega Review Desk", charset="UTF-8"' },
  });
}

export function proxy(request: NextRequest) {
  const expectedUser = process.env.REVIEW_DASHBOARD_USER;
  const expectedPassword = process.env.REVIEW_DASHBOARD_PASSWORD;
  if (!expectedUser || !expectedPassword) {
    return new NextResponse("Review dashboard credentials are not configured", { status: 503 });
  }
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Basic ")) return unauthorized();
  try {
    const [user, password] = atob(authorization.slice(6)).split(":", 2);
    if (user !== expectedUser || password !== expectedPassword) return unauthorized();
  } catch {
    return unauthorized();
  }
  return NextResponse.next();
}

export const config = { matcher: ["/review/:path*"] };
