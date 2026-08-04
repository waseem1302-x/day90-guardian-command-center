import { getToken } from 'next-auth/jwt'
import { NextRequest, NextResponse } from 'next/server'

export async function middleware(request: NextRequest) {
  // Local Docker retains its credential-free development flow. Hosted demos
  // explicitly enable this password gate with environment variables.
  if (process.env.DEMO_AUTH_REQUIRED !== 'true') return NextResponse.next()

  if (!process.env.DEMO_ACCESS_PASSWORD || !process.env.NEXTAUTH_SECRET) {
    return new NextResponse('Hosted demo authentication is not configured.', { status: 503 })
  }

  const { pathname } = request.nextUrl
  if (pathname.startsWith('/auth/signin') || pathname.startsWith('/api/auth')) {
    return NextResponse.next()
  }

  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET })
  if (token) return NextResponse.next()

  const signInUrl = new URL('/auth/signin', request.url)
  signInUrl.searchParams.set('callbackUrl', request.nextUrl.pathname + request.nextUrl.search)
  return NextResponse.redirect(signInUrl)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.svg|.*\\.png|.*\\.ico).*)',
  ],
}
