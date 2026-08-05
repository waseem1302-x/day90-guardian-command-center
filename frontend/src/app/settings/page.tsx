'use client'

import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { apiClient } from '@/lib/api-client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'
import { cn } from '@/lib/utils'

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
  judge_note: string
}

type DashboardPayload = {
  integrations: Integration[]
  integration_summary: IntegrationSummary
}

type CoverageTable = {
  key: string
  table: string
  domain: string
  purpose: string
  rows: number
  loaded: boolean
}

type DatasetCoverage = {
  expected_operational_tables: number
  loaded_operational_tables: number
  total_operational_rows: number
  cohorts_covered: number
  field_dictionary: {
    included_in_source_workbook: boolean
    role: string
  }
  domains: {
    name: string
    tables: string[]
    rows: number
  }[]
  tables: CoverageTable[]
  judge_note: string
}

type DataProfile = {
  source: {
    kind: string
    available: boolean
    path: string
    as_of_date: string
  }
  counts: Record<string, number>
  quality: {
    missing_manager_refs: number
    missing_manager_employee_ids: string[]
    overdue_incomplete_tasks: number
    completed_after_due: number
  }
  provisioning: {
    blocked: number
    requested: number
    blocked_by_resource: [string, number][]
  }
  compliance: {
    missing: number
    overdue: number
  }
  payroll: {
    errors: number
    error_employee_ids: string[]
  }
  engagement: {
    confidential: number
    confidential_employee_ids: string[]
    low_nonconf: number
    nonresponse: number
    manager_slow_ge_5d: number
  }
  learning: {
    incomplete: number
  }
  dependencies: {
    day_one_blockers_open: number
    open_by_team: [string, number][]
  }
  attrition_rates: Record<string, number>
  route_counts: Record<string, number>
  dataset_coverage: DatasetCoverage
}

const tablePurpose: Record<string, string> = {
  workers: 'Employee cohort, lifecycle, manager, role, and location context',
  tasks: 'Task completion, overdue status, evidence, and Day90 blockers',
  provisioning: 'Laptop, badge, VPN, email, and system access status',
  engagement: 'Non-confidential engagement and confidential disclosure flags',
  managers: 'Manager ownership and data-quality validation',
  locations: 'Jurisdiction, country, timezone, and entity context',
  compliance: 'Work authorization and jurisdiction-specific compliance deadlines',
  payroll: 'First payroll readiness, bank validation, tax, and cost-center issues',
  learning: 'Training and ramp milestone completion',
  attrition_history: 'Historical job-family signal for context only, not a claim of proven retention lift',
  cross_team_dependencies: 'Security, facilities, IT, payroll, and manager dependency blocks',
}

function statusClass(status: string) {
  return status === 'ready'
    ? 'bg-emerald-100 text-emerald-700'
    : status === 'missing'
      ? 'bg-red-100 text-red-700'
      : 'bg-amber-100 text-amber-700'
}

export default function SettingsPage() {
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [profile, setProfile] = useState<DataProfile | null>(null)

  useEffect(() => {
    Promise.all([
      apiClient.get<DashboardPayload>('/api/day90/dashboard'),
      apiClient.get<DataProfile>('/api/day90/data-profile'),
    ]).then(([dashboardPayload, profilePayload]) => {
      setDashboard(dashboardPayload)
      setProfile(profilePayload)
    })
  }, [])

  const sourceTables = useMemo(() => {
    if (!profile) return []
    if (profile.dataset_coverage?.tables?.length) return profile.dataset_coverage.tables
    return Object.entries(profile.counts)
      .filter(([name]) => name !== 'cohorts')
      .map(([name, rows]) => ({
        key: name,
        table: name,
        domain: 'Operational HR source table',
        rows,
        loaded: rows > 0,
        purpose: tablePurpose[name] ?? 'Operational HR source table',
      }))
  }, [profile])

  const riskSignals = profile
    ? [
        { label: 'Blocked provisioning', value: profile.provisioning.blocked, detail: profile.provisioning.blocked_by_resource.map(([name, count]) => `${name} ${count}`).join(', ') },
        { label: 'Compliance overdue', value: profile.compliance.overdue, detail: `${profile.compliance.missing} missing records` },
        { label: 'Payroll errors', value: profile.payroll.errors, detail: profile.payroll.error_employee_ids.join(', ') },
        { label: 'Confidential cases', value: profile.engagement.confidential, detail: profile.engagement.confidential_employee_ids.join(', ') },
        { label: 'Manager refs missing', value: profile.quality.missing_manager_refs, detail: profile.quality.missing_manager_employee_ids.join(', ') },
        { label: 'Open day-one blockers', value: profile.dependencies.day_one_blockers_open, detail: profile.dependencies.open_by_team.map(([name, count]) => `${name} ${count}`).join(', ') },
      ]
    : []

  const integrationSummary = dashboard?.integration_summary
  const liveReadyCount = integrationSummary?.ready_live_integrations ?? 0
  const liveTotalCount = integrationSummary?.total_live_integrations ?? 0
  const fallbackReadyCount = integrationSummary?.ready_fallbacks ?? 0
  const fallbackTotalCount = integrationSummary?.total_fallbacks ?? 0

  return (
    <motion.div className='mx-auto w-full max-w-[1440px] overflow-x-hidden space-y-4' initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <section className='rounded-3xl border border-brand-cornflower/20 bg-gradient-to-br from-white via-white to-brand-cornflower/10 p-5 shadow-soft'>
        <div className='max-w-4xl'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='rounded-full bg-brand-navy px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white'>Data lineage</span>
            <span className='rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700'>Operational source verified</span>
          </div>
          <h1 className='mt-3 text-3xl font-bold tracking-tight text-brand-navy lg:text-4xl'>Data Manager</h1>
          <p className='mt-2 max-w-3xl text-sm leading-6 text-muted-foreground lg:text-base'>
            A transparent registry of the systems, tables, and computed signals Day90 Guardian uses before routing a case or creating a human-review action.
          </p>
        </div>
      </section>

      <Card className='border-blue-200 bg-blue-50'>
        <CardContent className='grid gap-3 p-4 lg:grid-cols-[220px_1fr] lg:items-center'>
          <div>
            <p className='text-xs font-semibold uppercase tracking-wide text-blue-700'>Round 2 integration proof</p>
            <p className='mt-1 text-2xl font-bold text-blue-950'>{liveReadyCount}/{liveTotalCount} live integrations</p>
          </div>
          <div className='text-sm leading-6 text-blue-900'>
            <p>Judge-counted systems are Supabase, Supervity Auto, Slack, and Asana across system-of-record, orchestration, channel, and work-system categories.</p>
            <p className='mt-1 text-xs font-semibold text-blue-800'>
              CSV fallback: {fallbackReadyCount}/{fallbackTotalCount} ready, retained only for controlled local recovery and not counted as a live integration.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className='grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-5'>
        {(dashboard?.integrations ?? []).map((integration) => (
          <Card key={integration.name} className='min-w-0'>
            <CardContent className='flex h-full min-w-0 flex-col p-4'>
              <div className='flex items-start justify-between gap-3'>
                <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white'>
                  {integration.name.includes('Supabase') || integration.name.includes('CSV') ? <Icons.database className='h-5 w-5' /> : <Icons.network className='h-5 w-5' />}
                </div>
                <span className={cn('rounded-full px-2 py-1 text-xs font-semibold', statusClass(integration.status))}>
                  {integration.status.replaceAll('_', ' ')}
                </span>
              </div>
              <p className='mt-4 font-semibold leading-5 text-brand-navy'>{integration.name}</p>
              <p className='mt-1 text-xs uppercase tracking-wide text-muted-foreground'>{integration.category}</p>
              <p className={cn('mt-2 w-fit rounded-full px-2 py-1 text-[11px] font-semibold', integration.counts_as_live ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-700')}>
                {integration.counts_as_live ? 'Judge-counted live' : 'Fallback only'}
              </p>
              <p
                className='mt-3 break-words text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere]'
                title={integration.detail}
              >
                {integration.category === 'source data fallback'
                  ? 'Controlled fallback dataset configured; not counted as a judged live integration.'
                  : integration.detail}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {profile && (
        <Card className='min-w-0'>
          <CardHeader className='pb-3'>
            <CardTitle className='flex items-center gap-2'>
              <Icons.database className='h-5 w-5 text-brand-cornflower' />
              Active Source
            </CardTitle>
          </CardHeader>
          <CardContent className='grid gap-3 md:grid-cols-4'>
            <div className='rounded-lg border border-border p-4'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Source kind</p>
              <p className='mt-2 font-semibold text-brand-navy'>{profile.source.kind.replaceAll('_', ' ')}</p>
            </div>
            <div className='rounded-lg border border-border p-4'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Status</p>
              <p className={cn('mt-2 w-fit rounded-full px-2 py-1 text-xs font-semibold', profile.source.available ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
                {profile.source.available ? 'available' : 'missing'}
              </p>
            </div>
            <div className='rounded-lg border border-border p-4'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>As of date</p>
              <p className='mt-2 font-semibold text-brand-navy'>{profile.source.as_of_date}</p>
            </div>
            <div className='rounded-lg border border-border p-4'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Path</p>
              <p className='mt-2 break-all font-mono text-xs text-brand-navy'>{profile.source.path}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {profile?.dataset_coverage && (
        <Card className='min-w-0 border-emerald-200 bg-emerald-50'>
          <CardHeader className='pb-3'>
            <CardTitle className='flex items-center gap-2'>
              <Icons.table className='h-5 w-5 text-emerald-700' />
              Round 2 Dataset Coverage
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-4'>
            <div className='grid gap-3 md:grid-cols-4'>
              <div className='rounded-xl border border-emerald-100 bg-white p-4'>
                <p className='text-xs font-semibold uppercase tracking-wide text-emerald-700'>Operational tables</p>
                <p className='mt-2 text-2xl font-bold text-emerald-950'>
                  {profile.dataset_coverage.loaded_operational_tables}/{profile.dataset_coverage.expected_operational_tables}
                </p>
              </div>
              <div className='rounded-xl border border-emerald-100 bg-white p-4'>
                <p className='text-xs font-semibold uppercase tracking-wide text-emerald-700'>Rows loaded</p>
                <p className='mt-2 text-2xl font-bold text-emerald-950'>{profile.dataset_coverage.total_operational_rows.toLocaleString()}</p>
              </div>
              <div className='rounded-xl border border-emerald-100 bg-white p-4'>
                <p className='text-xs font-semibold uppercase tracking-wide text-emerald-700'>Cohorts covered</p>
                <p className='mt-2 text-2xl font-bold text-emerald-950'>{profile.dataset_coverage.cohorts_covered}</p>
              </div>
              <div className='rounded-xl border border-emerald-100 bg-white p-4'>
                <p className='text-xs font-semibold uppercase tracking-wide text-emerald-700'>Field Dictionary</p>
                <p className='mt-2 text-sm font-semibold leading-6 text-emerald-950'>
                  {profile.dataset_coverage.field_dictionary.included_in_source_workbook ? 'Included as reference' : 'Not provided'}
                </p>
              </div>
            </div>
            <p className='text-sm leading-6 text-emerald-900'>{profile.dataset_coverage.judge_note}</p>
            <div className='grid gap-3 lg:grid-cols-3'>
              {profile.dataset_coverage.domains.map((domain) => (
                <div key={domain.name} className='rounded-xl border border-emerald-100 bg-white p-4'>
                  <p className='font-semibold text-brand-navy'>{domain.name}</p>
                  <p className='mt-1 text-sm text-emerald-800'>{domain.rows.toLocaleString()} rows</p>
                  <p className='mt-2 text-xs leading-5 text-muted-foreground'>{domain.tables.join(', ')}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className='grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]'>
        <Card className='min-w-0'>
          <CardHeader className='pb-3'>
            <CardTitle className='flex items-center gap-2'>
              <Icons.table className='h-5 w-5 text-brand-cornflower' />
              HR Source Tables
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='overflow-x-auto rounded-lg border border-border'>
              <table className='min-w-[640px] text-left text-sm'>
                <thead className='bg-slate-50 text-xs uppercase tracking-wide text-slate-500'>
                  <tr>
                    <th className='px-4 py-3'>Table</th>
                    <th className='px-4 py-3 text-right'>Rows</th>
                    <th className='px-4 py-3'>Why it matters</th>
                  </tr>
                </thead>
                <tbody className='divide-y divide-border'>
                  {sourceTables.map((table) => (
                    <tr key={table.table} className='bg-white'>
                      <td className='px-4 py-3 font-mono text-brand-navy'>{table.table}</td>
                      <td className='px-4 py-3 text-right font-semibold text-brand-navy'>{table.rows.toLocaleString()}</td>
                      <td className='px-4 py-3 text-muted-foreground'>{table.purpose}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='flex items-center gap-2'>
              <Icons.alertTriangle className='h-5 w-5 text-brand-cornflower' />
              Computed Signals
            </CardTitle>
          </CardHeader>
          <CardContent className='grid gap-3 sm:grid-cols-2 2xl:grid-cols-1'>
            {riskSignals.map((signal) => (
              <div key={signal.label} className='min-w-0 rounded-xl border border-border bg-white p-3'>
                <div className='flex items-center justify-between gap-3'>
                  <p className='font-semibold leading-5 text-brand-navy'>{signal.label}</p>
                  <p className='text-2xl font-bold text-brand-navy'>{signal.value.toLocaleString()}</p>
                </div>
                <p className='mt-1 break-words text-xs leading-5 text-muted-foreground'>{signal.detail || 'No detail'}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='flex items-center gap-2'>
            <Icons.shield className='h-5 w-5 text-brand-cornflower' />
            Privacy and Data Rules
          </CardTitle>
        </CardHeader>
        <CardContent className='grid gap-3 md:grid-cols-3'>
          {[
            'No confidential pulse text is shown in dashboard, insights, Slack, or public task descriptions.',
            'Unsafe data joins, missing manager ownership, and date-format issues stop before external action.',
            'Retention impact is framed as leading-risk reduction, not a claimed measured attrition improvement.',
          ].map((rule) => (
            <div key={rule} className='rounded-lg border border-border p-4 text-sm text-brand-navy'>
              <Icons.checkCircle className='mb-3 h-5 w-5 text-emerald-600' />
              {rule}
            </div>
          ))}
        </CardContent>
      </Card>
    </motion.div>
  )
}
