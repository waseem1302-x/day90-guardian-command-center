'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'
import { cn } from '@/lib/utils'

type Insight = {
  id: string
  type: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  description: string
  data: Record<string, string | number>
  suggested_action: string
  action_type: string
  confidence: number
  created_at: string
}

type Pattern = {
  name: string
  frequency: string
  confidence: number
  sample_size: number
  description: string
}

type ActionItem = {
  title: string
  priority: 'critical' | 'high' | 'medium'
  estimated_impact: string
  action_type: string
}

const severityStyles = {
  critical: 'border-red-200 bg-red-50 text-red-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  info: 'border-blue-200 bg-blue-50 text-blue-800',
}

export default function AIInsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [actions, setActions] = useState<ActionItem[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const router = useRouter()

  const loadInsights = async () => {
    const payload = await apiClient.get<{ insights: Insight[]; patterns: Pattern[]; actions: ActionItem[] }>('/api/day90/insights')
    setInsights(payload.insights)
    setPatterns(payload.patterns)
    setActions(payload.actions)
  }

  useEffect(() => {
    loadInsights()
  }, [])

  const analyze = async () => {
    setIsAnalyzing(true)
    try {
      await apiClient.post('/api/day90/runs/trigger')
      await loadInsights()
    } finally {
      setIsAnalyzing(false)
    }
  }

  return (
    <div className='space-y-6'>
      <div className='flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between'>
        <div>
          <p className='text-sm font-semibold uppercase tracking-wide text-brand-cornflower'>Computed from processed HR data</p>
          <h1 className='mt-2 text-4xl font-bold tracking-tight text-brand-navy'>AI Insights</h1>
          <p className='mt-3 max-w-3xl text-muted-foreground'>
            The goal is not to predict a resignation from one survey. The value is finding leading indicators early: blocked access, payroll errors, compliance risk, manager delay, and confidential escalation.
          </p>
        </div>
        <Button variant='gradient' onClick={analyze} disabled={isAnalyzing}>
          {isAnalyzing ? <Icons.loader className='mr-2 h-4 w-4 animate-spin' /> : <Icons.sparkles className='mr-2 h-4 w-4' />}
          Recompute Insights
        </Button>
      </div>

      <div className='grid gap-4 md:grid-cols-3'>
        {[
          { label: 'Critical', value: insights.filter((item) => item.severity === 'critical').length, icon: Icons.alertCircle },
          { label: 'Warnings', value: insights.filter((item) => item.severity === 'warning').length, icon: Icons.alertTriangle },
          { label: 'Patterns', value: patterns.length, icon: Icons.layers },
        ].map((item) => (
          <Card key={item.label}>
            <CardContent className='flex items-center gap-4 p-5'>
              <div className='flex h-11 w-11 items-center justify-center rounded-lg bg-slate-900 text-white'>
                <item.icon className='h-5 w-5' />
              </div>
              <div>
                <p className='text-3xl font-bold text-brand-navy'>{item.value}</p>
                <p className='text-sm text-muted-foreground'>{item.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className='grid gap-6 xl:grid-cols-[1fr_420px]'>
        <div className='space-y-4'>
          {insights.map((insight) => (
            <Card key={insight.id}>
              <CardHeader>
                <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
                  <div>
                    <CardTitle>{insight.title}</CardTitle>
                    <p className='mt-2 text-sm text-muted-foreground'>{insight.description}</p>
                  </div>
                  <span className={cn('w-fit rounded-full border px-3 py-1 text-xs font-semibold', severityStyles[insight.severity])}>{insight.severity}</span>
                </div>
              </CardHeader>
              <CardContent className='space-y-4'>
                <div className='grid gap-3 sm:grid-cols-3'>
                  {Object.entries(insight.data).slice(0, 3).map(([key, value]) => (
                    <div key={key} className='rounded-lg border border-border p-3'>
                      <p className='text-xs uppercase tracking-wide text-muted-foreground'>{key.replaceAll('_', ' ')}</p>
                      <p className='mt-1 text-lg font-bold text-brand-navy'>{value}</p>
                    </div>
                  ))}
                </div>
                <div className='flex flex-wrap items-center justify-between gap-3'>
                  <p className='text-sm font-medium text-brand-navy'>Action: {insight.suggested_action}</p>
                  <Button variant='outline' onClick={() => router.push('/workbench')}>
                    Open Workbench
                    <Icons.arrowRight className='ml-2 h-4 w-4' />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className='space-y-6'>
          <Card>
            <CardHeader>
              <CardTitle>Detected Patterns</CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              {patterns.map((pattern) => (
                <div key={pattern.name} className='rounded-lg border border-border p-3'>
                  <div className='flex items-center justify-between gap-3'>
                    <p className='font-semibold text-brand-navy'>{pattern.name}</p>
                    <span className='text-xs font-semibold text-emerald-700'>{Math.round(pattern.confidence * 100)}%</span>
                  </div>
                  <p className='mt-1 text-sm text-muted-foreground'>{pattern.description}</p>
                  <p className='mt-2 text-xs uppercase tracking-wide text-slate-500'>{pattern.frequency} - {pattern.sample_size.toLocaleString()} rows</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recommended Actions</CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              {actions.map((action) => (
                <button key={action.title} onClick={() => router.push('/workbench')} className='w-full rounded-lg border border-border p-3 text-left transition hover:border-brand-cornflower'>
                  <p className='font-semibold text-brand-navy'>{action.title}</p>
                  <p className='mt-1 text-sm text-muted-foreground'>{action.estimated_impact}</p>
                  <p className='mt-2 text-xs font-semibold uppercase tracking-wide text-brand-cornflower'>{action.priority}</p>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
