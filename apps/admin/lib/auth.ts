import { SignJWT, jwtVerify } from "jose"
import { cookies } from "next/headers"
import { appSecretBytes } from "./secret"

const COOKIE_NAME = "auth-token"

export interface JwtPayload {
  userId: string
  mobile: string
  [key: string]: unknown
}

export async function signToken(payload: JwtPayload): Promise<string> {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("7d")
    .setIssuedAt()
    .sign(appSecretBytes())
}

export async function verifyToken(token: string): Promise<JwtPayload | null> {
  try {
    const { payload } = await jwtVerify(token, appSecretBytes())
    // Every token this app signs shares one secret, so a valid signature is
    // not enough: it has to be an owner session specifically. A platform
    // admin's token (lib/admin-auth.ts) carries no userId and stops here.
    if (typeof payload.userId !== "string") return null
    return payload as unknown as JwtPayload
  } catch {
    return null
  }
}

export async function getSession(): Promise<JwtPayload | null> {
  const cookieStore = await cookies()
  const token = cookieStore.get(COOKIE_NAME)?.value
  if (!token) return null
  return verifyToken(token)
}

export async function setSession(payload: JwtPayload): Promise<void> {
  const token = await signToken(payload)
  const cookieStore = await cookies()
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  })
}

export async function clearSession(): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(COOKIE_NAME)
}
