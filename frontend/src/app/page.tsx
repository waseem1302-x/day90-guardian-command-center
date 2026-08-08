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
  proof_role: string
  counts_as_live: boolean
  status: string
  detail: string
}

type IntegrationSummary = {
  ready_live_integrations: number
  total_live_integrations: number
  ready_fallbacks: number
  total_fallbacks: number
  live_names: string[]
  fallback_names: string[]
  live_categories: string[]
  meets_round2_minimum: boolean
  operational_note: string
}

type AuditEvent = {
  time: string
  event: string
  actor: string
  detail: string
}

type GuardianRunResponse = {
  status: string
  message?: string
  run_tag: string
  orchestrator?: {
    status?: string
    workflow_id?: string | null
    run_id?: string | null
    status_code?: number
    events_observed?: string[]
    policy_snapshot_sent?: boolean
    policy_snapshot?: {
      profile?: string
      version?: number
      active_policy_count?: number
      confidential_route_locked?: boolean
      policies?: {
        name?: string
        route?: string
        threshold?: string
        active?: boolean
      }[]
    }
    detail?: string
  }
  external_actions?: unknown[]
  audit?: {
    event?: string
  }
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
  integration_summary: IntegrationSummary
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

function integrationDisplayDetail(integration: Integration) {
  if (!integration.counts_as_live || integration.category === 'source data fallback') {
    return 'Resilience fallback ready for local recovery and source validation.'
  }
  return integration.detail
}

function statusLabel(value?: string) {
  return value?.replaceAll('_', ' ') ?? 'not reported'
}

function DashboardRunReceipt({
  receipt,
  latestAutoProof,
  latestTrigger,
  onClear,
}: {
  receipt: GuardianRunResponse | null
  latestAutoProof?: AuditEvent
  latestTrigger?: AuditEvent
  onClear: () => void
}) {
  const externalActionCount = receipt?.external_actions?.length ?? 0
  const policySnapshot = receipt?.orchestrator?.policy_snapshot
  const activePolicyRoutes = policySnapshot?.policies
    ?.filter((policy) => policy.active)
    .map((policy) => `${policy.route}: ${policy.name}`)
    .join('; ')
  const receiptRows = receipt
    ? [
        ['Run tag', receipt.run_tag],
        ['Command Center status', statusLabel(receipt.status)],
        ['Auto status', statusLabel(receipt.orchestrator?.status)],
        ['Auto run ID', receipt.orchestrator?.run_id],
        ['Supervity workflow ID', receipt.orchestrator?.workflow_id],
        ['Supervity HTTP status', typeof receipt.orchestrator?.status_code === 'number' ? String(receipt.orchestrator.status_code) : undefined],
        ['Stream events observed', receipt.orchestrator?.events_observed?.join(', ')],
        ['Policy snapshot sent', receipt.orchestrator?.policy_snapshot_sent ? 'Yes - included in Supervity trigger input' : policySnapshot ? 'Prepared - not included in Supervity input' : undefined],
        ['Policy profile', policySnapshot ? `${policySnapshot.profile ?? 'policy'} v${policySnapshot.version ?? 'not reported'} (${policySnapshot.active_policy_count ?? 0} active policies)` : undefined],
        ['Policy safety lock', policySnapshot?.confidential_route_locked ? 'Confidential route locked fail-closed' : undefined],
        ['Active policy routes', activePolicyRoutes],
        ['External actions created', String(externalActionCount)],
        ['Workbench gate', 'Approval remains required'],
        ['Audit event', receipt.audit?.event],
      ].filter((row): row is [string, string] => Boolean(row[1]))
    : []

  return (
    <div className='flex h-[270px] flex-col rounded-2xl border border-brand-cornflower/20 bg-white/85 p-3 text-left shadow-sm' role='status'>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <p className='text-xs font-bold uppercase tracking-[0.16em] text-brand-cornflower'>Last Guardian Run</p>
          <p className='mt-1 text-xs leading-5 text-muted-foreground'>Supervity receipt and Workbench gate status stay contained here.</p>
        </div>
        {receipt && (
          <button
            type='button'
            className='rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-muted-foreground transition hover:border-brand-cornflower/40 hover:text-brand-navy'
            onClick={onClear}
          >
            Clear
          </button>
        )}
      </div>
      <div className='mt-3 min-h-0 flex-1 overflow-y-auto pr-1'>
        {receipt ? (
          <>
            <p className='text-xs leading-5 text-brand-navy'>{receipt.message ?? 'Guardian Review trigger captured.'}</p>
            <dl className='mt-3 space-y-2'>
              {receiptRows.map(([label, value]) => (
                <div key={label} className='grid gap-1 rounded-xl bg-brand-navy/5 px-3 py-2 sm:grid-cols-[135px_1fr]'>
                  <dt className='text-[11px] font-semibold uppercase tracking-wide text-muted-foreground'>{label}</dt>
                  <dd className='break-words font-mono text-[11px] leading-5 text-brand-navy'>{value}</dd>
                </div>
              ))}
            </dl>
            {receipt.orchestrator?.detail && (
              <p className='mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800'>
                {receipt.orchestrator.detail}
              </p>
            )}
          </>
        ) : (
          <div className='rounded-xl bg-brand-navy/5 px-3 py-3 text-xs leading-5 text-brand-navy'>
            <p className='font-semibold'>No live run receipt in this browser session yet.</p>
            <p className='mt-1 text-muted-foreground'>Run Guardian Review and the latest Supervity run ID, workflow ID, status, audit event, and Workbench gate will appear in this fixed panel.</p>
            {(latestAutoProof ?? latestTrigger) && (
              <p className='mt-3 border-t border-brand-cornflower/10 pt-3 text-muted-foreground'>
                Latest dashboard audit: {(latestAutoProof ?? latestTrigger)?.detail}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
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
  const [runReceipt, setRunReceipt] = useState<GuardianRunResponse | null>(null)

  useEffect(() => {
    apiClient
      .get<DashboardPayload>('/api/day90/dashboard')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load Day90 dashboard'))
  }, [])

  const triggerRun = async () => {
    setIsTriggering(true)
    setRunNotice(null)
    setRunReceipt(null)
    try {
      const result = await apiClient.post<GuardianRunResponse>('/api/day90/runs/trigger')
      setRunReceipt(result)
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

  const integrationSummary = data.integration_summary
  const liveReadyCount = integrationSummary?.ready_live_integrations ?? data.integrations.filter((integration) => integration.counts_as_live && integration.status === 'ready').length
  const liveTotalCount = integrationSummary?.total_live_integrations ?? data.integrations.filter((integration) => integration.counts_as_live).length
  const fallbackReadyCount = integrationSummary?.ready_fallbacks ?? data.integrations.filter((integration) => !integration.counts_as_live && integration.status === 'ready').length
  const fallbackTotalCount = integrationSummary?.total_fallbacks ?? data.integrations.filter((integration) => !integration.counts_as_live).length
  const latestSlack = data.audit.find((event) => event.event === 'External action: slack')
  const latestAsana = data.audit.find((event) => event.event === 'External action: asana')
  const latestTrigger = data.audit.find((event) => event.event === 'Manual trigger requested')
  const latestAutoProof = data.audit.find((event) => event.event === 'Auto orchestration proof')
  const supervityIntegration = data.integrations.find((integration) => integration.name === 'Supervity Auto')
  const outcomeCards = data.outcomes?.cards ?? []

  return (
    <motion.div className='mx-auto w-full max-w-[1440px] overflow-x-hidden space-y-4' initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <section className='overflow-hidden rounded-3xl border border-brand-cornflower/20 bg-gradient-to-br from-white via-white to-brand-cornflower/10 p-5 shadow-soft'>
        <div className='flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between'>
          <div className='max-w-4xl'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className='rounded-full bg-brand-navy px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white'>Live HR control plane</span>
              <span className='rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700'>Supabase system of record</span>
              <span className='rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700'>{liveReadyCount}/{liveTotalCount} live integrations</span>
              <span className='rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700'>{fallbackReadyCount}/{fallbackTotalCount} fallback ready</span>
            </div>
            <h1 className='mt-3 text-3xl font-bold tracking-tight text-brand-navy lg:text-4xl'>Day90 Guardian Command Center</h1>
            <p className='mt-2 max-w-3xl text-sm leading-6 text-muted-foreground lg:text-base'>
              A governed AI employee for People Ops teams: it monitors new-hire readiness, access gaps, compliance misses, payroll exceptions, and engagement signals before they turn into retention risk.
            </p>
          </div>
          <div className='flex w-full shrink-0 flex-col gap-3 xl:w-[460px]'>
            <div className='rounded-2xl border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur'>
              <Button variant='gradient' className='h-12 w-full justify-center rounded-2xl text-sm font-semibold' onClick={triggerRun} disabled={isTriggering}>
                {isTriggering ? <Icons.loader className='mr-2 h-4 w-4 animate-spin' /> : <Icons.zap className='mr-2 h-4 w-4' />}
                Run Guardian Review
              </Button>
              <p className='mt-2 text-center text-[11px] font-medium text-muted-foreground'>Creates a privacy-safe escalation with auditable evidence.</p>
              {runNotice && <p className='mt-2 rounded-lg bg-brand-navy/5 px-3 py-2 text-center text-xs leading-5 text-brand-navy' role='status'>{runNotice}</p>}
            </div>
            <DashboardRunReceipt receipt={runReceipt} latestAutoProof={latestAutoProof} latestTrigger={latestTrigger} onClear={() => setRunReceipt(null)} />
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
            <p className='mt-1 text-xl font-bold text-blue-950'>{liveReadyCount}/{liveTotalCount} live</p>
            <p className='mt-1 text-xs leading-5 text-blue-800'>Primary systems connect source records, orchestration, notifications, and reviewer tasks. CSV remains a resilience fallback.</p>
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
            <p className='text-sm font-semibold text-brand-navy'>Operational impact measurement</p>
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
          <CardContent className='space-y-3'>
            <div className='rounded-3xl border border-brand-cornflower/25 bg-gradient-to-br from-brand-navy via-slate-900 to-brand-cornflower p-5 text-white shadow-soft'>
              <div className='flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between'>
                <div>
                  <p className='text-xs font-bold uppercase tracking-[0.2em] text-white/70'>Top-level controller</p>
                  <h3 className='mt-2 text-2xl font-bold'>Supervity Auto Orchestrator</h3>
                  <p className='mt-2 max-w-2xl text-sm leading-6 text-white/80'>
                    Coordinates the Day90 Guardian flow across data quality, onboarding/access, engagement/privacy, policy routing, and approved intervention operators.
                  </p>
                </div>
                <div className='flex flex-wrap gap-2 lg:justify-end'>
                  <span className='rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white'>{data.operators.length} operators coordinated</span>
                  <span className='rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white'>{statusLabel(supervityIntegration?.status)} integration</span>
                  <span className='rounded-full bg-emerald-300/20 px-3 py-1 text-xs font-semibold text-emerald-100'>Workbench gated</span>
                </div>
              </div>
              <div className='mt-4 grid gap-3 md:grid-cols-3'>
                <div className='rounded-2xl bg-white/10 p-3'>
                  <p className='text-[11px] font-semibold uppercase tracking-wide text-white/60'>Flow model</p>
                  <p className='mt-1 text-sm font-bold text-white'>1 Orchestrator + {data.operators.length} Operators</p>
                </div>
                <div className='rounded-2xl bg-white/10 p-3'>
                  <p className='text-[11px] font-semibold uppercase tracking-wide text-white/60'>Latest proof</p>
                  <p className='mt-1 text-sm font-bold text-white'>{latestAutoProof ? 'Auto orchestration captured' : latestTrigger ? 'Manual trigger captured' : 'Ready for Guardian run'}</p>
                </div>
                <div className='rounded-2xl bg-white/10 p-3'>
                  <p className='text-[11px] font-semibold uppercase tracking-wide text-white/60'>Safety boundary</p>
                  <p className='mt-1 text-sm font-bold text-white'>External actions require Workbench approval</p>
                </div>
              </div>
              <p className='mt-4 rounded-2xl bg-white/10 px-3 py-2 text-xs leading-5 text-white/80'>
                {latestAutoProof?.detail ?? 'Run Guardian Review to capture a Supervity receipt while keeping Slack and Asana actions behind human approval.'}
              </p>
            </div>

            <div className='grid min-w-0 gap-3 lg:grid-cols-2'>
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
            </div>
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
                    <div className='min-w-0'>
                      <p className='text-sm font-semibold text-brand-navy'>{integration.name}</p>
                      <p className='text-xs uppercase tracking-wide text-muted-foreground'>{integration.category}</p>
                    </div>
                    <span className={cn('rounded-full px-2 py-1 text-xs font-semibold', integration.status === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700')}>
                      {integration.status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <p className={cn('mt-2 w-fit rounded-full px-2 py-1 text-[11px] font-semibold', integration.counts_as_live ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-700')}>
                    {integration.counts_as_live ? 'Primary system' : 'Resilience fallback'}
                  </p>
                  <p className='mt-2 text-xs leading-5 text-muted-foreground' title={integration.detail}>
                    {integrationDisplayDetail(integration)}
                  </p>
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
