'use client'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/ui/avatar'
import { Icons } from '@/components/ui/icons'
import { useAI } from '@/context/AIContext'
import { NotificationCenter } from '@/components/NotificationCenter'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/** Opens the real global command palette owned by CommandPalette. */
function openCommandPalette() {
  const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform)
  document.dispatchEvent(
    new KeyboardEvent('keydown', {
      key: 'k',
      bubbles: true,
      ctrlKey: !isMac,
      metaKey: isMac,
    })
  )
}

function SearchInput() {
  return (
    <button
      type='button'
      onClick={openCommandPalette}
      aria-label='Open search and navigation'
      className={cn(
        'group flex h-10 w-52 items-center gap-2 px-3 xl:w-60',
        'rounded-full border border-border/50 bg-white/50',
        'text-sm text-muted-foreground',
        'transition-all duration-300 ease-out',
        'hover:border-brand-cornflower/40 hover:bg-white/90 hover:shadow-sm',
        'hover:w-72',
        'focus:outline-none focus:ring-2 focus:ring-brand-cornflower/50'
      )}
    >
      <Icons.search
        className='h-4 w-4 transition-transform duration-200 group-hover:scale-110'
        strokeWidth={1.5}
      />
      <span className='flex-1 text-left'>Search or jump to...</span>
      <kbd
        className={cn(
          'hidden h-5 items-center gap-1 rounded px-1.5 sm:inline-flex',
          'border border-border/50 bg-muted/50 text-[10px] font-medium text-muted-foreground',
          'transition-all duration-200',
          'group-hover:border-brand-cornflower/30 group-hover:bg-brand-cornflower/10 group-hover:text-brand-navy'
        )}
      >
        <Icons.command className='h-3 w-3' />K
      </kbd>
    </button>
  )
}

function AIManagerTrigger() {
  const { openManager, isManagerOpen } = useAI()

  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <button
            type='button'
            onClick={openManager}
            className={cn(
              'relative flex h-10 items-center gap-2 rounded-full px-4',
              'bg-gradient-to-r from-brand-navy to-brand-purple',
              'text-sm font-medium text-white shadow-md shadow-brand-navy/20',
              'transition-all duration-200 hover:scale-[1.02] hover:shadow-lg hover:shadow-brand-purple/30',
              isManagerOpen && 'ring-2 ring-brand-cornflower ring-offset-2',
              'focus:outline-none focus:ring-2 focus:ring-brand-cornflower focus:ring-offset-2'
            )}
            aria-label='Open AI Workbench'
          >
            <Icons.sparkles className='h-4 w-4 text-white' strokeWidth={1.5} />
            <span className='hidden sm:inline'>AI Workbench</span>
            <kbd
              className={cn(
                'hidden items-center gap-0.5 rounded bg-white/20 px-1.5 py-0.5 sm:inline-flex',
                'text-[10px] font-medium text-white/90'
              )}
            >
              <Icons.command className='h-2.5 w-2.5' />J
            </kbd>
          </button>
        </TooltipTrigger>
        <TooltipContent side='bottom' className='sm:hidden'>
          <span>AI Workbench</span>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function UserMenu() {
  const user = { name: 'Team Zero', email: 'day90-guardian@teamzero.io' }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type='button'
          aria-label='Open workspace profile'
          className={cn(
            'group flex items-center gap-1 rounded-full',
            'transition-transform duration-200',
            'focus:outline-none focus:ring-2 focus:ring-brand-cornflower/50 focus:ring-offset-2'
          )}
        >
          <div className='flex items-center gap-3'>
            <div className='hidden min-w-0 max-w-40 flex-col text-right 2xl:flex'>
              <span className='text-sm font-semibold leading-tight text-foreground'>
                {user.name}
              </span>
              <span className='max-w-44 truncate text-xs leading-tight text-muted-foreground'>
                {user.email}
              </span>
            </div>
            <Avatar fallback={user.name} size='md' showRing />
            <Icons.chevronDown
              className={cn(
                'h-4 w-4 text-muted-foreground transition-transform duration-200',
                'group-data-[state=open]:rotate-180 group-hover:translate-y-0.5'
              )}
            />
          </div>
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align='end' className='w-64'>
        <div className='px-3 py-3'>
          <div className='flex items-center gap-3'>
            <Avatar fallback={user.name} size='md' />
            <div className='min-w-0 flex-1'>
              <p className='truncate text-sm font-medium text-foreground'>{user.name}</p>
              <p className='truncate text-xs text-muted-foreground'>{user.email}</p>
            </div>
          </div>
        </div>
        <div className='border-t border-border/50 px-3 py-2.5'>
          <div className='flex items-center gap-2 text-xs text-muted-foreground'>
            <span className='h-2 w-2 rounded-full bg-emerald-500' aria-hidden='true' />
            <span>Workspace connected</span>
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface HeaderProps {
  onOpenMobileMenu?: () => void
}

export function Header({ onOpenMobileMenu }: HeaderProps) {
  return (
    <header
      role='banner'
      className={cn(
        'fixed right-4 top-4 z-sticky left-4 md:left-[calc(16rem+1rem)]',
        'flex h-16 min-w-0 items-center justify-between gap-2 rounded-2xl px-4 lg:px-6',
        'border border-white/60 bg-white/70 shadow-float ring-1 ring-black/[0.03] backdrop-blur-xl'
      )}
    >
      {/* Search is the only general utility retained in the header; navigation stays in the sidebar. */}
      <div className='flex min-w-0 flex-1 items-center gap-3 overflow-hidden'>
        <Button
          variant='ghost'
          size='icon-sm'
          onClick={onOpenMobileMenu}
          className='-ml-1 text-muted-foreground hover:text-foreground md:hidden'
          aria-label='Open navigation menu'
        >
          <Icons.menu className='h-5 w-5' strokeWidth={1.5} />
        </Button>
        <div className='hidden min-w-0 sm:block'>
          <SearchInput />
        </div>
      </div>

      <div className='flex shrink-0 items-center gap-2'>
        <Button
          variant='ghost'
          size='icon-sm'
          className='text-muted-foreground hover:text-foreground sm:hidden'
          aria-label='Open search and navigation'
          onClick={openCommandPalette}
        >
          <Icons.search className='h-5 w-5' strokeWidth={1.5} />
        </Button>
        <AIManagerTrigger />
        <NotificationCenter />
        <div className='mx-1 hidden h-6 w-px bg-border/60 lg:block' />
        <UserMenu />
      </div>
    </header>
  )
}
