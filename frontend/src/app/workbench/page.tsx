'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'
import { cn } from '@/lib/utils'

type ReviewCase = {
  id: string
  case_key: string
  employee_id: string
  route: 'AMBER' | 'RED' | 'CONFIDENTIAL' | 'DATA_QUALITY'
  risk_band: string
  summary: string
  reason: string
  recommended_action: string
  assignee: string
  status: string
  security: string
  evidence: string[]
  updated_at: string
}

type ActionReceipt = {
  system: string
  ok: boolean
  detail: string
}

const actionReceiptUrlPattern = /https?:\/\/\S+/

function getActionReceiptUrl(detail: string) {
  return detail.match(actionReceiptUrlPattern)?.[0]
}

function getActionReceiptMessage(action: ActionReceipt) {
  const system = action.system.toLowerCase()
  const hasUrl = Boolean(getActionReceiptUrl(action.detail))

  if (action.ok && system.includes('asana') && hasUrl) return 'Task created in Asana.'
  if (action.ok && system.includes('slack')) return 'Masked Slack notification sent.'

  const cleanedDetail = action.detail.replace(actionReceiptUrlPattern, '').replace(/^ok\s*-?\s*/i, '').trim()
  if (cleanedDetail) return cleanedDetail

  return action.ok ? 'Action completed.' : 'Action attempted; review integration configuration.'
}

function getActionReceiptLinkLabel(action: ActionReceipt) {
  return action.system.toLowerCase().includes('asana') ? 'Open task' : 'Open artifact'
}

const routeStyles: Record<string, string> = {
  AMBER: 'bg-amber-100 text-amber-800 border-amber-200',
  RED: 'bg-red-100 text-red-800 border-red-200',
  CONFIDENTIAL: 'bg-violet-100 text-violet-800 border-violet-200',
  DATA_QUALITY: 'bg-cyan-100 text-cyan-800 border-cyan-200',
}

export default function WorkbenchPage() {
  const [cases, setCases] = useState<ReviewCase[]>([])
  const [selectedCase, setSelectedCase] = useState<ReviewCase | null>(null)
  const [note, setNote] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [actionReceipts, setActionReceipts] = useState<ActionReceipt[]>([])

  const loadCases = async () => {
    const payload = await apiClient.get<{ cases: ReviewCase[] }>('/api/day90/workbench')
    setCases(payload.cases)
    setSelectedCase((current) => current ?? payload.cases[0] ?? null)
    setIsLoading(false)
  }

  useEffect(() => {
    loadCases().catch(() => setIsLoading(false))
  }, [])

  const decide = async (decision: 'approve' | 'modify' | 'reject') => {
    if (!selectedCase) return
    setIsSaving(true)
    try {
      const result = await apiClient.post<{ case: ReviewCase; actions?: ActionReceipt[] }>(`/api/day90/workbench/${selectedCase.id}/decision`, {
        decision,
        note,
      })
      setCases((items) => items.map((item) => (item.id === selectedCase.id ? result.case : item)))
      setSelectedCase(result.case)
      setActionReceipts(result.actions ?? [])
      setNote('')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className='flex min-h-[50vh] items-center justify-center'>
        <Icons.loader className='h-8 w-8 animate-spin text-brand-cornflower' />
      </div>
    )
  }

  return (
    <motion.div className='space-y-6' initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div>
        <p className='text-sm font-semibold uppercase tracking-wide text-brand-cornflower'>Human-in-the-loop control</p>
        <h1 className='mt-2 text-4xl font-bold tracking-tight text-brand-navy'>Day90 Workbench</h1>
        <p className='mt-3 max-w-3xl text-muted-foreground'>
          Every risky action lands here first. Reviewers see the employee, reason, evidence, route, and privacy boundary before approving external Slack or Asana work.
        </p>
      </div>

      <div className='grid gap-6 xl:grid-cols-[420px_1fr]'>
        <Card>
          <CardHeader>
            <CardTitle className='flex items-center gap-2'>
              <Icons.inbox className='h-5 w-5 text-brand-cornflower' />
              Review Queue
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            {cases.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setSelectedCase(item)
                  setActionReceipts([])
                }}
                className={cn(
                  'w-full rounded-lg border p-4 text-left transition hover:border-brand-cornflower',
                  selectedCase?.id === item.id ? 'border-brand-cornflower bg-blue-50' : 'border-border bg-white'
                )}
              >
                <div className='flex items-center justify-between gap-3'>
                  <span className='font-semibold text-brand-navy'>{item.employee_id}</span>
                  <span className={cn('rounded-full border px-2 py-1 text-xs font-semibold', routeStyles[item.route])}>{item.route}</span>
                </div>
                <p className='mt-2 text-sm text-muted-foreground'>{item.summary}</p>
                <p className='mt-2 text-xs font-semibold uppercase tracking-wide text-slate-500'>{item.status.replaceAll('_', ' ')}</p>
              </button>
            ))}
          </CardContent>
        </Card>

        {selectedCase && (
          <Card>
            <CardHeader>
              <div className='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
                <div>
                  <CardTitle className='text-2xl'>Case {selectedCase.employee_id} - {selectedCase.risk_band}</CardTitle>
                  <p className='mt-2 break-all font-mono text-xs text-muted-foreground'>{selectedCase.case_key}</p>
                </div>
                <span className={cn('w-fit rounded-full border px-3 py-1 text-sm font-semibold', routeStyles[selectedCase.route])}>{selectedCase.route}</span>
              </div>
            </CardHeader>
            <CardContent className='space-y-5'>
              <div className='grid gap-4 md:grid-cols-2'>
                <div className='rounded-lg border border-border p-4'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Reason</p>
                  <p className='mt-2 text-sm text-brand-navy'>{selectedCase.reason}</p>
                </div>
                <div className='rounded-lg border border-border p-4'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Recommended Action</p>
                  <p className='mt-2 text-sm text-brand-navy'>{selectedCase.recommended_action}</p>
                </div>
                <div className='rounded-lg border border-border p-4'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Assigned Reviewer</p>
                  <p className='mt-2 text-sm text-brand-navy'>{selectedCase.assignee}</p>
                </div>
                <div className='rounded-lg border border-border p-4'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Security Boundary</p>
                  <p className='mt-2 text-sm text-brand-navy'>{selectedCase.security}</p>
                </div>
              </div>

              <div className='rounded-lg border border-border p-4'>
                <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>Evidence</p>
                <div className='mt-3 grid gap-2'>
                  {selectedCase.evidence.map((evidence) => (
                    <div key={evidence} className='flex items-center gap-2 text-sm text-brand-navy'>
                      <Icons.checkCircle className='h-4 w-4 text-emerald-600' />
                      {evidence}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className='text-sm font-medium text-brand-navy'>Reviewer note</label>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  className='mt-2 w-full rounded-lg border border-input bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-brand-cornflower/40'
                  placeholder='Example: approve safe manager nudge, no confidential text included.'
                />
              </div>

              <div className='flex flex-wrap gap-3'>
                <Button onClick={() => decide('approve')} disabled={isSaving || selectedCase.status === 'approved'} variant='gradient'>
                  <Icons.check className='mr-2 h-4 w-4' />
                  {selectedCase.status === 'approved' ? 'Approved' : 'Approve'}
                </Button>
                <Button onClick={() => decide('modify')} disabled={isSaving} variant='outline'>
                  <Icons.edit className='mr-2 h-4 w-4' />
                  Modify
                </Button>
                <Button onClick={() => decide('reject')} disabled={isSaving} variant='outline'>
                  <Icons.close className='mr-2 h-4 w-4' />
                  Reject
                </Button>
              </div>

              <p className='text-xs leading-5 text-muted-foreground'>
                {selectedCase.route === 'AMBER'
                  ? 'Approval can create a masked Slack notification and an assigned Asana review task.'
                  : selectedCase.route === 'RED'
                    ? 'Approval is restricted to the HR Asana queue; no broad Slack notification is sent.'
                    : 'This route stays inside the Workbench. No public Slack or Asana artifact is created.'}
              </p>

              {actionReceipts.length > 0 && (
                <div className='rounded-lg border border-emerald-200 bg-emerald-50 p-4' role='status'>
                  <p className='text-xs font-semibold uppercase tracking-wide text-emerald-800'>Action receipt</p>
                  <p className='mt-1 text-sm text-emerald-900'>The decision was recorded. These route-safe artifacts were attempted:</p>
                  <div className='mt-3 grid gap-2'>
                    {actionReceipts.map((action) => {
                      const actionUrl = getActionReceiptUrl(action.detail)

                      return (
                        <div key={`${action.system}-${action.detail}`} className='flex items-start gap-2 text-sm text-emerald-950'>
                          <Icons.checkCircle className={cn('mt-0.5 h-4 w-4 shrink-0', action.ok ? 'text-emerald-600' : 'text-red-600')} />
                          <span className='min-w-0 leading-5'>
                            <strong className='capitalize'>{action.system.replaceAll('_', ' ')}</strong>: {getActionReceiptMessage(action)}
                            {actionUrl && (
                              <a
                                href={actionUrl}
                                target='_blank'
                                rel='noreferrer'
                                className='ml-2 inline-flex font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-950'
                              >
                                {getActionReceiptLinkLabel(action)}
                              </a>
                            )}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </motion.div>
  )
}
