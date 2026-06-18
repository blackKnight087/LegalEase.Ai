import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/documents",
  "/matters",
  "/litigation",
  "/billing",
  "/intake",
  "/discovery",
  "/settings",
  "/admin",
  "/onboarding",
  "/tools",
  "/drafting",
  "/analytics",
];

/** Public client intake form — must not require firm login */
const PUBLIC_PATHS = ["/intake/client", "/login", "/forgot-password", "/legal/", "/portal/", "/invite/", "/esign/"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const isProtected =
    pathname === "/" ||
    PROTECTED_PREFIXES.some(
      (p) => pathname === p || pathname.startsWith(`${p}/`)
    );

  if (!isProtected) {
    return NextResponse.next();
  }

  const token = request.cookies.get("legalease_token")?.value;
  if (!token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/dashboard/:path*",
    "/documents/:path*",
    "/matters/:path*",
    "/litigation/:path*",
    "/billing/:path*",
    "/intake/:path*",
    "/discovery/:path*",
    "/settings/:path*",
    "/admin/:path*",
    "/onboarding/:path*",
    "/tools/:path*",
    "/drafting/:path*",
    "/analytics/:path*",
  ],
};
