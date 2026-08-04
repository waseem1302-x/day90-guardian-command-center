'use client'

import { signIn } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CardWatermark } from '@/components/ui/card-watermark'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/ui/icons'
import { Logomark } from '@/components/brand'

function SignInContent() {
  const searchParams = useSearchParams()
  const callbackUrl = searchParams.get('callbackUrl') || '/'
  const demoAuthRequired = process.env.NEXT_PUBLIC_DEMO_AUTH_REQUIRED === 'true'
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!demoAuthRequired) signIn('autopilot-dev', { callbackUrl, redirect: true })
  }, [callbackUrl, demoAuthRequired])

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    const result = await signIn('autopilot-dev', {
      password,
      callbackUrl,
      redirect: false,
    })
    if (result?.error) {
      setError('The demo access password is not correct.')
      setSubmitting(false)
      return
    }
    window.location.assign(result?.url || callbackUrl)
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
      className='w-full max-w-md'
    >
      <Card className='relative overflow-hidden bg-white shadow-float-lg'>
        <CardWatermark opacity={4} scale={1} />
        <CardHeader className='relative z-10 space-y-4 pb-6 text-center'>
          <motion.div
            className='mx-auto flex h-20 w-20 items-center justify-center rounded-2xl bg-brand-navy shadow-xl'
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 200, damping: 15 }}
          >
            <Logomark variant='light' size={48} />
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.4 }}>
            <CardTitle className='text-display-5 font-bold text-brand-navy'>Day90 Guardian</CardTitle>
            <p className='mt-2 text-muted-foreground'>
              {demoAuthRequired ? 'Enter the access password provided by Team Zero.' : 'Preparing your local command center…'}
            </p>
          </motion.div>
        </CardHeader>
        <CardContent className='relative z-10 space-y-4 px-8 pb-8'>
          {demoAuthRequired ? (
            <form className='space-y-4' onSubmit={submit}>
              <label className='block text-sm font-medium text-brand-navy' htmlFor='demo-password'>
                Demo access password
              </label>
              <input
                id='demo-password'
                type='password'
                autoComplete='current-password'
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className='w-full rounded-lg border border-border bg-white px-3 py-2.5 text-brand-navy outline-none transition focus:border-brand-cornflower focus:ring-2 focus:ring-brand-cornflower/20'
                required
              />
              {error && <p className='text-sm text-red-600'>{error}</p>}
              <Button type='submit' variant='gradient' size='lg' className='group w-full py-6 text-base' disabled={submitting}>
                {submitting ? 'Checking access…' : 'Enter Command Center'}
                <Icons.arrowRight className='ml-2 h-4 w-4 transition-transform group-hover:translate-x-1' />
              </Button>
            </form>
          ) : (
            <div className='flex justify-center py-4'>
              <div className='h-8 w-8 animate-spin rounded-full border-4 border-brand-navy border-t-transparent' />
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}

export default function SignInPage() {
  return (
    <Suspense fallback={<div className='flex min-h-screen items-center justify-center bg-background'><div className='h-8 w-8 animate-spin rounded-full border-4 border-brand-navy border-t-transparent' /></div>}>
      <SignInContent />
    </Suspense>
  )
}
