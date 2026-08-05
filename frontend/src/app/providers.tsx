'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState } from 'react'
import { SessionProvider } from 'next-auth/react'
import { ToastProvider } from '@/components/ui/toast'
import { AIProvider } from '@/context/AIContext'
import { useAI } from '@/context/AIContext'

const CommandPalette = dynamic(
  () => import('@/components/CommandPalette').then((mod) => mod.CommandPalette),
  { ssr: false, loading: () => null }
)

const AIManager = dynamic(
  () => import('@/components/ai/AIManager').then((mod) => mod.AIManager),
  { ssr: false, loading: () => null }
)

// Mock session — all components see an authenticated admin user
const mockSession: {
  user: { name: string; email: string }
  roles: string[]
  expires: string
} = {
  user: {
    name: 'Dev User',
    email: 'dev@autopilot.local',
  },
  roles: ['admin', 'user'],
  expires: '2099-12-31T23:59:59.999Z',
}

function DeferredCommandPalette() {
  const [isLoaded, setIsLoaded] = useState(false)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setIsLoaded(true)
        setIsOpen((open) => !open)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  if (!isLoaded) return null

  return (
    <CommandPalette
      open={isOpen}
      onOpenChange={setIsOpen}
      registerShortcut={false}
    />
  )
}

function DeferredAIManager() {
  const { isManagerOpen } = useAI()
  if (!isManagerOpen) return null
  return <AIManager />
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider
      session={mockSession}
      basePath={`${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api/auth`}
      refetchInterval={0}
      refetchOnWindowFocus={false}
    >
      <AIProvider>
        {children}
        <DeferredAIManager />
        <ToastProvider />
        <DeferredCommandPalette />
      </AIProvider>
    </SessionProvider>
  )
}
