import { getToken } from 'next-auth/jwt'
import { NextRequest, NextResponse } from 'next/server'

type RouteContext = { params: Promise<{ path: string[] }> }

const proxy = async (request: NextRequest, context: RouteContext) => {
  const { path } = await context.params
  const backendOrigin = process.env.BACKEND_ORIGIN
  const serviceToken = process.env.INTERNAL_SERVICE_TOKEN
  const demoAuthRequired = process.env.DEMO_AUTH_REQUIRED === 'true'

  if (!backendOrigin || !serviceToken) {
    return NextResponse.json({ detail: 'Hosted backend is not configured.' }, { status: 503 })
  }

  if (demoAuthRequired) {
    const session = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET })
    if (!session) return NextResponse.json({ detail: 'Sign in is required.' }, { status: 401 })
  }

  const upstreamUrl = new URL(`/${path.map(encodeURIComponent).join('/')}`, backendOrigin)
  upstreamUrl.search = request.nextUrl.search

  const headers = new Headers(request.headers)
  headers.delete('host')
  headers.delete('cookie')
  headers.set('authorization', `Bearer ${serviceToken}`)
  headers.set('x-day90-proxy', 'frontend')

  const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer()
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
    redirect: 'manual',
  })

  const responseHeaders = new Headers(upstream.headers)
  responseHeaders.delete('content-encoding')
  responseHeaders.delete('content-length')
  responseHeaders.delete('transfer-encoding')

  return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders })
}

export { proxy as DELETE, proxy as GET, proxy as HEAD, proxy as OPTIONS, proxy as PATCH, proxy as POST, proxy as PUT }
