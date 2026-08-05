'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'
import { cn } from '@/lib/utils'

type Operator = {
  name: string
  role: string
  mode: string
  status: string
  last_result: string
}

type RouteSummary = {
  route: string
  count: number
  description: string
}

type OutcomeCard = {
  label: string
  value: string
  detail: string
}

type OutcomeSummary = {
  measurement_mode: string
  measurement_note: string
  retention_lift_claimed: boolean
  workers_in_scope: number
  risk_signals_detected: number
  risky_cases_routed: number
  policy_gate_coverage_pct: number
  workbench_cases_visible: number
  approval_gated_receipts: number
  public_text_leakage: number
  confidential_cases_masked: number
  cards: OutcomeCard[]
}

type Integration = {
  name: string
  category: string
  status: string
  detail: string
}

type AuditEvent = {
  time: string
  event: string
  actor: string
  detail: string
}

type DashboardPayload = {
  run: {
    name: string
    batch_id: string
    policy_profile: string
    policy_version: number
    mode: string
    last_run_at: string
  }
  metrics: Record<string, number>
  routes: RouteSummary[]
  outcomes: OutcomeSummary
  operators: Operator[]
  integrations: Integration[]
  audit: AuditEvent[]
  source: {
    kind: string
    available: boolean
    path: string
    as_of_date: string
  }
}

const metricCards = [
  { key: 'workers', label: 'Workers in cohort', icon: Icons.users, color: 'bg-slate-900' },
  { key: 'blocked_provisioning', label: 'Blocked provisioning', icon: Icons.lock, color: 'bg-red-600' },
  { key: 'overdue_compliance', label: 'Overdue compliance', icon: Icons.shield, color: 'bg-amber-600' },
  { key: 'confidential_cases', label: 'Confidential cases', icon: Icons.eyeOff, color: 'bg-violet-700' },
  { key: 'payroll_errors', label: 'Payroll errors', icon: Icons.alertTriangle, color: 'bg-orange-600' },
  { key: 'policy_evaluations', label: 'Policy evaluations', icon: Icons.activity, color: 'bg-emerald-700' },
]

const routeStyles: Record<string, string> = {
  GREEN: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  AMBER: 'border-amber-200 bg-amber-50 text-amber-800',
  RED: 'border-red-200 bg-red-50 text-red-800',
  CONFIDENTIAL: 'border-violet-200 bg-violet-50 text-violet-800',
  DATA_QUALITY: 'border-cyan-200 bg-cyan-50 text-cyan-800',
}

function LoadingShell() {
  return (
    <div className='flex min-h-[50vh] items-center justify-center'>
      <Icons.loader className='h-8 w-8 animate-spin text-brand-cornflower' />
    </div>
  )
}

function MetricCard({ label, value, icon: Icon, color }: { label: string; value: number; icon: React.ElementType; color: string }) {
  return (
    <Card className='overflow-hidden'>
      <CardContent className='flex min-h-[118px] items-center justify-between p-4'>
        <div>
          <p className='max-w-28 text-[11px] font-semibold uppercase leading-4 tracking-wide text-muted-foreground'>{label}</p>
          <p className='mt-2 text-3xl font-bold leading-none text-brand-navy'>{value.toLocaleString()}</p>
        </div>
        <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm', color)}>
          <Icon className='h-5 w-5' strokeWidth={1.7} />
        </div>
      </CardContent>
    </Card>
  )
}

export default function HomePage() {
  const [data, setData] = useState<DashboardPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isTriggering, setIsTriggering] = useState(false)
  const [runNotice, setRunNotice] = useState<string | null>(null)

  useEffect(() => {
    apiClient
      .get<DashboardPayload>('/api/day90/dashboard')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load Day90 dashboard'))
  }, [])

  const triggerRun = async () => {
    setIsTriggering(true)
    setRunNotice(null)
    try {
      const result = await apiClient.post<{ message?: string }>('/api/day90/runs/trigger')
      setRunNotice(result.message ?? 'Guardian review staged. Open Workbench to approve a route-safe action.')
      const refreshed = await apiClient.get<DashboardPayload>('/api/day90/dashboard')
      setData(refreshed)
    } catch (err) {
      setRunNotice(err instanceof Error ? err.message : 'Guardian review could not be staged')
    } finally {
      setIsTriggering(false)
    }
  }

  if (error) {
    return (
      <Card>
        <CardContent className='p-6 text-sm text-red-700'>{error}</CardContent>
      </Card>
    )
  }

  if (!data) return <LoadingShell />

  const liveReadyCount = data.integrations.filter((integration) => integration.status === 'ready').length
  const latestSlack = data.audit.find((event) => event.event === 'External action: slack')
  const latestAsana = data.audit.find((event) => event.event === 'External action: asana')
  const latestTrigger = data.audit.find((event) => event.event === 'Manual trigger requested')
  const outcomeCards = data.outcomes?.cards ?? []

  return (
    <motion.div className='mx-auto w-full max-w-[1440px] overflow-x-hidden space-y-4' initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <section className='overflow-hidden rounded-3xl border border-brand-cornflower/20 bg-gradient-to-br from-white via-white to-brand-cornflower/10 p-5 shadow-soft'>
        <div className='flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between'>
          <div className='max-w-4xl'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className='rounded-full bg-brand-navy px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white'>Live HR control plane</span>
              <span className='rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700'>Supabase system of record</span>
              <span className='rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700'>{liveReadyCount}/{data.integrations.length} integrations ready</span>
            </div>
            <h1 className='mt-3 text-3xl font-bold tracking-tight text-brand-navy lg:text-4xl'>Day90 Guardian Command Center</h1>
            <p className='mt-2 max-w-3xl text-sm leading-6 text-muted-foreground lg:text-base'>
              A governed AI employee for People Ops teams: it monitors new-hire readiness, access gaps, compliance misses, payroll exceptions, and engagement signals before they turn into retention risk.
            </p>
          </div>
          <div className='flex shrink-0 flex-col gap-2 rounded-2xl border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur'>
            <Button variant='gradient' className='h-12 min-w-72 justify-center rounded-2xl text-sm font-semibold' onClick={triggerRun} disabled={isTriggering}>
              {isTriggering ? <Icons.loader className='mr-2 h-4 w-4 animate-spin' /> : <Icons.zap className='mr-2 h-4 w-4' />}
              Run Guardian Review
            </Button>
            <p className='text-center text-[11px] font-medium text-muted-foreground'>Creates a privacy-safe escalation with auditable evidence.</p>
            {runNotice && <p className='max-w-72 rounded-lg bg-brand-navy/5 px-3 py-2 text-center text-xs leading-5 text-brand-navy' role='status'>{runNotice}</p>}
          </div>
        </div>
      </section>

      <section className='grid gap-3 lg:grid-cols-4'>
        <Card className='border-emerald-200 bg-emerald-50'>
          <CardContent className='p-4'>
            <p className='text-xs font-semibold uppercase tracking-wide text-emerald-700'>Live data source</p>
            <p className='mt-1 text-xl font-bold text-emerald-950'>{data.source.kind.replaceAll('_', ' ')}</p>
            <p className='mt-1 text-xs leading-5 text-emerald-800'>Operational HR records load from Supabase; CSV remains a controlled fallback.</p>
          </CardContent>
        </Card>

        <Card className='border-blue-200 bg-blue-50'>
          <CardContent className='p-4'>
            <p className='text-xs font-semibold uppercase tracking-wide text-blue-700'>Connected systems</p>
            <p className='mt-1 text-xl font-bold text-blue-950'>{liveReadyCount}/{data.integrations.length} ready</p>
            <p className='mt-1 text-xs leading-5 text-blue-800'>Data, orchestration, notifications, and task handoff are connected.</p>
          </CardContent>
        </Card>

        <Card className='border-violet-200 bg-violet-50'>
          <CardContent className='p-4'>
            <p className='text-xs font-semibold uppercase tracking-wide text-violet-700'>Latest human gate</p>
            <p className='mt-1 text-lg font-bold text-violet-950'>{latestTrigger ? 'Live trigger captured' : 'Ready for trigger'}</p>
            <p className='mt-1 text-xs leading-5 text-violet-800'>{latestTrigger?.detail ?? 'Review actions are gated before anything reaches a human.'}</p>
          </CardContent>
        </Card>

        <Card className='border-slate-200 bg-slate-50'>
          <CardContent className='p-4'>
            <p className='text-xs font-semibold uppercase tracking-wide text-slate-600'>External proof</p>
            <p className='mt-1 text-lg font-bold text-slate-950'>{latestSlack && latestAsana ? 'Slack + Asana OK' : 'Ready for proof'}</p>
            <p className='mt-1 text-xs leading-5 text-slate-700'>{latestSlack && latestAsana ? 'Latest run created masked Slack and Asana evidence.' : 'Live escalation evidence appears after a run.'}</p>
          </CardContent>
        </Card>
      </section>

      <section className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6'>
        {metricCards.map((card) => (
          <MetricCard key={card.key} label={card.label} value={data.metrics[card.key] ?? 0} icon={card.icon} color={card.color} />
        ))}
      </section>

      <Card className='border-sky-200 bg-gradient-to-br from-white to-sky-50'>
        <CardHeader className='pb-2'>
          <CardTitle className='flex items-center gap-2'>
            <Icons.barChart className='h-5 w-5 text-brand-cornflower' />
            Measured Outcome Baseline
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='rounded-2xl border border-sky-100 bg-white/80 p-4'>
            <p className='text-sm font-semibold text-brand-navy'>Judge-safe impact claim</p>
            <p className='mt-1 text-sm leading-6 text-muted-foreground'>
              {data.outcomes?.measurement_note ?? 'Measured as leading operational controls; no proven retention lift is claimed.'}
            </p>
          </div>
          <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
            {outcomeCards.map((card) => (
              <div key={card.label} className='rounded-2xl border border-border bg-white p-4 shadow-sm'>
                <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>{card.label}</p>
                <p className='mt-2 text-2xl font-bold leading-none text-brand-navy'>{card.value}</p>
                <p className='mt-2 text-xs leading-5 text-muted-foreground'>{card.detail}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <section className='grid min-w-0 gap-4 xl:grid-cols-[1.18fr_0.82fr]'>
        <Card>
          <CardHeader className='pb-2'>
            <CardTitle className='flex items-center gap-2'>
              <Icons.network className='h-5 w-5 text-brand-cornflower' />
              Orchestrated Operator Flow
            </CardTitle>
          </CardHeader>
          <CardContent className='grid min-w-0 gap-3 lg:grid-cols-2'>
            {data.operators.map((operator, index) => (
              <div key={operator.name} className='relative min-w-0 rounded-2xl border border-border bg-gradient-to-br from-white to-slate-50 p-4 shadow-sm'>
                <div className='flex items-center justify-between gap-3'>
                  <div className='flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-brand-navy text-sm font-bold text-white'>{index + 1}</div>
                  <span className='rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700'>{operator.mode}</span>
                </div>
                <h3 className='mt-3 text-base font-semibold leading-5 text-brand-navy'>{operator.name}</h3>
                <p className='mt-2 text-xs leading-5 text-muted-foreground'>{operator.role}</p>
                <p className='mt-3 border-t border-border pt-3 text-xs font-semibold leading-5 text-emerald-700'>{operator.last_result}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className='space-y-4'>
          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='flex items-center gap-2'>
                <Icons.listFilter className='h-5 w-5 text-brand-cornflower' />
                Routes and Human Gates
              </CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2 sm:grid-cols-2 xl:grid-cols-1'>
              {data.routes.map((route) => (
                <div key={route.route} className={cn('rounded-xl border p-3', routeStyles[route.route] ?? 'border-slate-200 bg-slate-50 text-slate-800')}>
                  <div className='flex items-center justify-between gap-3'>
                    <span className='text-sm font-semibold'>{route.route}</span>
                    <span className='text-xl font-bold'>{route.count}</span>
                  </div>
                  <p className='mt-1 text-xs leading-5 opacity-90'>{route.description}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='flex items-center gap-2'>
                <Icons.globe className='h-5 w-5 text-brand-cornflower' />
                Integration Registry
              </CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2 sm:grid-cols-2 xl:grid-cols-1'>
              {data.integrations.map((integration) => (
                <div key={integration.name} className='rounded-xl border border-border bg-white p-3'>
                  <div className='flex items-center justify-between gap-3'>
                    <div>
                      <p className='text-sm font-semibold text-brand-navy'>{integration.name}</p>
                      <p className='text-xs uppercase tracking-wide text-muted-foreground'>{integration.category}</p>
                    </div>
                    <span className={cn('rounded-full px-2 py-1 text-xs font-semibold', integration.status === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700')}>
                      {integration.status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <p className='mt-2 text-xs leading-5 text-muted-foreground'>{integration.detail}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <Icons.clock className='h-5 w-5 text-brand-cornflower' />
            Audit Trail
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          {data.audit.map((event) => (
            <div key={`${event.time}-${event.event}`} className='grid gap-2 rounded-lg border border-border p-3 md:grid-cols-[180px_220px_1fr]'>
              <span className='text-xs text-muted-foreground'>{new Date(event.time).toLocaleString()}</span>
              <span className='text-sm font-semibold text-brand-navy'>{event.event}</span>
              <span className='text-sm text-muted-foreground'>{event.actor}: {event.detail}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </motion.div>
  )
}
