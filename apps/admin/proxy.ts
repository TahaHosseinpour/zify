import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { jwtVerify } from "jose"
import { appSecretBytes } from "./lib/secret"
import { ADMIN_COOKIE, verifyAdminToken } from "./lib/admin-token"

const PROTECTED_PREFIXES = ["/dashboard", "/onboarding"]

// The platform admin panel has its own login and its own session
// (lib/admin-auth.ts), checked here on its own terms: a shop owner's session
// neither grants nor affects access to it. The panel's layout and every admin
// API route check again against the database.
const ADMIN_PREFIX = "/admin"
const ADMIN_LOGIN = "/admin/login"

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (pathname === ADMIN_PREFIX || pathname.startsWith(`${ADMIN_PREFIX}/`)) {
    const adminToken = request.cookies.get(ADMIN_COOKIE)?.value
    const isAdmin = adminToken ? (await verifyAdminToken(adminToken)) !== null : false
    if (pathname === ADMIN_LOGIN) {
      return isAdmin ? NextResponse.redirect(new URL(ADMIN_PREFIX, request.url)) : NextResponse.next()
    }
    return isAdmin ? NextResponse.next() : NextResponse.redirect(new URL(ADMIN_LOGIN, request.url))
  }

  const token = request.cookies.get("auth-token")?.value

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p))

  let isAuthenticated = false
  if (token) {
    try {
      const { payload } = await jwtVerify(token, appSecretBytes())
      isAuthenticated = typeof payload.userId === "string"
    } catch {
      isAuthenticated = false
    }
  }

  if (isProtected && !isAuthenticated) {
    return NextResponse.redirect(new URL("/login", request.url))
  }

  if (isAuthenticated && (pathname === "/" || pathname === "/login")) {
    return NextResponse.redirect(new URL("/dashboard", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|fonts).*)"],
}
