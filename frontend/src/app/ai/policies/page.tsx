'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'

type Day90Policy = {
  id: string
  name: string
  description: string
  is_active: boolean
  threshold: string
  route: string
  owner: string
  last_evaluated_at: string
  evaluations: number
}

type RoutePreview = {
  route: string
  count: number
  description: string
}

export default function AIPoliciesPage() {
  const [policies, setPolicies] = useState<Day90Policy[]>([])
  const [routingPreview, setRoutingPreview] = useState<RoutePreview[]>([])
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [savingId, setSavingId] = useState<string | null>(null)

  const loadPolicies = async () => {
    const payload = await apiClient.get<{ policies: Day90Policy[]; routing_preview: RoutePreview[] }>('/api/day90/policies')
    setPolicies(payload.policies)
    setRoutingPreview(payload.routing_preview)
    setEditing(Object.fromEntries(payload.policies.map((policy) => [policy.id, policy.threshold])))
  }

  useEffect(() => {
    loadPolicies()
  }, [])

  const updatePolicy = async (policy: Day90Policy, changes: Partial<Day90Policy>) => {
    setSavingId(policy.id)
    try {
      const payload = await apiClient.patch<{ policy: Day90Policy; routing_preview: RoutePreview[] }>(`/api/day90/policies/${policy.id}`, {
        is_active: changes.is_active,
        threshold: changes.threshold,
        route: changes.route,
      })
      setPolicies((items) => items.map((item) => (item.id === policy.id ? payload.policy : item)))
      setRoutingPreview(payload.routing_preview)
      setEditing((items) => ({ ...items, [policy.id]: payload.policy.threshold }))
    } finally {
      setSavingId(null)
    }
  }

  return (
    <motion.div className='space-y-6' initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div>
        <p className='text-sm font-semibold uppercase tracking-wide text-brand-cornflower'>Business-editable gates</p>
        <h1 className='mt-2 text-4xl font-bold tracking-tight text-brand-navy'>AI Policies</h1>
        <p className='mt-3 max-w-3xl text-muted-foreground'>
          These are the no-code controls that change how Day90 Guardian routes cases on the next run. Every save records an evaluation event in the audit trail.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <Icons.activity className='h-5 w-5 text-brand-cornflower' />
            Routing impact preview
          </CardTitle>
        </CardHeader>
        <CardContent className='grid gap-2 sm:grid-cols-2 lg:grid-cols-5'>
          {routingPreview.map((route) => (
            <div key={route.route} className='rounded-xl border border-border bg-white p-3'>
              <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>{route.route}</p>
              <p className='mt-2 text-2xl font-bold text-brand-navy'>{route.count}</p>
              <p className='mt-1 text-xs leading-5 text-muted-foreground'>{route.description}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className='grid gap-4 lg:grid-cols-2'>
        {policies.map((policy) => (
          <Card key={policy.id}>
            <CardHeader>
              <div className='flex items-start justify-between gap-4'>
                <div>
                  <CardTitle className='text-xl'>{policy.name}</CardTitle>
                  <p className='mt-2 text-sm text-muted-foreground'>{policy.description}</p>
                </div>
                <button
                  onClick={() => updatePolicy(policy, { is_active: !policy.is_active })}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${policy.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}
                >
                  {policy.is_active ? 'Active' : 'Inactive'}
                </button>
              </div>
            </CardHeader>
            <CardContent className='space-y-4'>
              <div className='grid gap-3 md:grid-cols-2'>
                <div className='rounded-lg border border-border p-3'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Route</p>
                  <select
                    value={policy.route}
                    disabled={policy.id === 'policy-confidential-isolation'}
                    onChange={(event) => updatePolicy(policy, { route: event.target.value })}
                    className='mt-2 w-full rounded-md border border-input bg-white px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-500'
                  >
                    <option>GREEN</option>
                    <option>AMBER</option>
                    <option>RED</option>
                    <option>CONFIDENTIAL</option>
                    <option>DATA_QUALITY</option>
                  </select>
                  {policy.id === 'policy-confidential-isolation' && (
                    <p className='mt-2 text-xs leading-5 text-muted-foreground'>Locked fail-closed so confidential disclosures never become public actions.</p>
                  )}
                </div>
                <div className='rounded-lg border border-border p-3'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Owner</p>
                  <p className='mt-2 text-sm font-medium text-brand-navy'>{policy.owner}</p>
                </div>
              </div>

              <div>
                <label className='text-sm font-medium text-brand-navy'>Editable threshold</label>
                <textarea
                  value={editing[policy.id] ?? policy.threshold}
                  onChange={(event) => setEditing((items) => ({ ...items, [policy.id]: event.target.value }))}
                  rows={2}
                  className='mt-2 w-full rounded-lg border border-input bg-white p-3 font-mono text-sm outline-none focus:ring-2 focus:ring-brand-cornflower/40'
                />
              </div>

              <div className='flex flex-wrap items-center justify-between gap-3'>
                <div className='text-xs text-muted-foreground'>
                  {policy.evaluations} evaluations. Last: {new Date(policy.last_evaluated_at).toLocaleString()}
                </div>
                <Button
                  variant='gradient'
                  disabled={savingId === policy.id}
                  onClick={() => updatePolicy(policy, { threshold: editing[policy.id] ?? policy.threshold })}
                >
                  {savingId === policy.id ? <Icons.loader className='mr-2 h-4 w-4 animate-spin' /> : <Icons.check className='mr-2 h-4 w-4' />}
                  Save and Evaluate
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </motion.div>
  )
}
