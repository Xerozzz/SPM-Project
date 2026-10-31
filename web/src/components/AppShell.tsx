import { useState } from 'react'

export type NavigationItem = {
  id: string
  label: string
  description: string
  group: string
  icon: string
}

type Props = {
  activeId: string
  items: NavigationItem[]
  onNavigate: (id: string) => void
  onSignOut: () => void
  roles: string[]
  unreadCount?: number
  children: React.ReactNode
}

/** Presentation-only authenticated shell. It does not decide who may access a workflow. */
export default function AppShell({
  activeId,
  items,
  onNavigate,
  onSignOut,
  roles,
  children,
  unreadCount = 0,
}: Props) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const active = items.find((item) => item.id === activeId) ?? items[0]
  const groups = [...new Set(items.map((item) => item.group))]
  const roleSummary = roles.map(formatRole).join(', ')

  function navigate(id: string) {
    onNavigate(id)
    setMobileOpen(false)
  }

  return (
    <div className="min-h-screen bg-[#f5f5f5] p-0 text-slate-900 lg:h-screen lg:overflow-hidden lg:p-6">
      <aside
        aria-label="Primary navigation"
        className={`${mobileOpen ? 'fixed inset-y-0 left-0 z-40 flex w-72 flex-col shadow-2xl' : 'hidden'} border-r border-slate-100 bg-white text-slate-700 lg:fixed lg:inset-y-6 lg:left-6 lg:z-30 lg:flex lg:w-64 lg:flex-col lg:rounded-l-[28px] lg:shadow-sm`}
      >
        <div className="flex h-16 items-center justify-between border-b border-slate-100 px-5">
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold tracking-tight text-black">ConnectSphere</span>
          </div>
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
            className="rounded p-1 text-slate-300 hover:bg-slate-800 lg:hidden"
          >
            ×
          </button>
        </div>
        <nav className="flex-1 space-y-6 overflow-y-auto p-3">
          {groups.map((group) => (
            <div key={group}>
              <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {group}
              </p>
              <div className="space-y-1">
                {items
                  .filter((item) => item.group === group)
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-current={activeId === item.id ? 'page' : undefined}
                      onClick={() => navigate(item.id)}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                        activeId === item.id
                          ? 'bg-slate-100 text-slate-950'
                          : 'text-slate-500 hover:bg-slate-50 hover:text-slate-950'
                      }`}
                    >
                      <span aria-hidden="true" className="w-4 text-center text-base">
                        {item.icon}
                      </span>
                      {item.label}
                      {item.id === 'notifications' && unreadCount > 0 && (
                        <span
                          aria-label={`${unreadCount} unread notifications`}
                          className="ml-auto rounded-full bg-slate-900 px-2 py-0.5 text-xs text-white"
                        >
                          {unreadCount}
                        </span>
                      )}
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-4">
          <p className="text-sm font-medium text-slate-500">You are logged in as: {roleSummary}</p>
          <button type="button" onClick={onSignOut} className="cs-button-secondary mt-4 w-full">
            Sign out
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation overlay"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-30 bg-slate-950/50 lg:hidden"
        />
      )}

      {/* Contain positioned field labels here so they cannot extend the outer page. */}
      <div className="relative bg-white lg:h-[calc(100vh-3rem)] lg:overflow-y-auto lg:overscroll-y-none lg:pl-64 lg:pr-6 lg:rounded-r-[28px]">
        <div className="min-h-screen bg-white lg:min-h-[calc(100vh-3rem)]">
          <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:px-8 lg:pb-8 lg:pt-6">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
              className="mb-4 rounded-lg border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 lg:hidden"
            >
              ☰
            </button>
            <div className="mb-6 border-b border-slate-200 pb-4">
              <h1 className="text-3xl font-medium tracking-[-0.04em] text-[#202124]">
                {active.label}
              </h1>
              <p className="mt-1 text-sm text-slate-500">{active.description}</p>
            </div>
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}

function formatRole(role: string): string {
  return role
    .split('_')
    .map((word) => `${word[0].toUpperCase()}${word.slice(1)}`)
    .join(' ')
}
