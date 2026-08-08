'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Icons } from '@/components/ui/icons'

interface Capability {
  icon: React.ElementType
  label: string
  query: string
}

const CAPABILITIES: Capability[] = [
  { icon: Icons.zap, label: 'Run Guardian Review', query: 'Run Guardian Review' },
  { icon: Icons.activity, label: 'Show readiness proof', query: 'Show me the live operating proof path' },
  { icon: Icons.helpCircle, label: 'What can you help with?', query: 'What can you help me with?' },
  { icon: Icons.users, label: 'Summarize Workbench', query: 'Summarize the Workbench queue and human approval gate' },
  { icon: Icons.brain, label: 'Explain policy gates', query: 'Explain current policy gates and routing thresholds' },
  { icon: Icons.lightbulb, label: 'Summarize outcomes', query: 'Summarize outcome measurement and retention risk signals' },
  { icon: Icons.shield, label: 'Check privacy controls', query: 'Explain confidential routing and privacy controls' },
  { icon: Icons.activity, label: 'Check integrations', query: 'Summarize connected systems, Supervity, Supabase, Slack, and Asana status' },
  { icon: Icons.info, label: 'Explain this page', query: 'Explain this page to me' },
]

interface CapabilityBubblesProps {
  onSelect: (query: string) => void
}

export function CapabilityBubbles({ onSelect }: CapabilityBubblesProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2 p-2">
      {CAPABILITIES.map((cap, i) => {
        const Icon = cap.icon
        return (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06, duration: 0.25, ease: 'easeOut' }}
            onClick={() => onSelect(cap.query)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-full',
              'bg-white border border-brand-cornflower/20',
              'text-sm text-brand-navy',
              'shadow-sm',
              'transition-all duration-200',
              'hover:bg-brand-cornflower/10 hover:border-brand-cornflower/40 hover:shadow-md',
              'focus:outline-none focus:ring-2 focus:ring-brand-cornflower/50'
            )}
          >
            <Icon className="h-4 w-4 text-brand-cornflower" strokeWidth={1.5} />
            <span className="text-xs sm:text-sm font-medium">{cap.label}</span>
          </motion.button>
        )
      })}
    </div>
  )
}
