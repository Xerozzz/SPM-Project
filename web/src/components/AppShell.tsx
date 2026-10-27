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
}: Props) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const active = items.find((item) => item.id === activeId) ?? items[0]
  const groups = [...new Set(items.map((item) => item.group))]

  function navigate(id: string) {
    onNavigate(id)
    setMobileOpen(false)
  }

  return (
    <div className="min-h-screen bg-[#f5f5f5] p-0 lg:p-6 text-slate-900">
      <aside
        aria-label="Primary navigation"
        className={`${mobileOpen ? 'fixed inset-y-0 left-0 z-40 w-72 shadow-2xl' : 'hidden'} border-r border-slate-100 bg-white text-slate-700 lg:fixed lg:inset-y-6 lg:left-6 lg:z-30 lg:block lg:w-64 lg:rounded-l-[28px] lg:shadow-sm`}
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
        <nav className="space-y-6 p-3">
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
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation overlay"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-30 bg-slate-950/50 lg:hidden"
        />
      )}

      <div className="lg:pl-64 lg:pr-6 lg:pb-6">
        <div className="min-h-screen bg-white lg:rounded-r-[28px]">
        <header className="sticky top-0 z-20 border-b border-slate-100 bg-white/95 backdrop-blur">
          <div className="flex min-h-16 items-center gap-3 px-4 sm:px-6">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
              className="rounded-lg border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 lg:hidden"
            >
              ☰
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-lg font-semibold tracking-tight text-slate-950">
                {active.label}
              </h1>
              <p className="hidden truncate text-sm text-slate-500 sm:block">
                {active.description}
              </p>
            </div>
            <div className="hidden flex-wrap justify-end gap-1 sm:flex">
              {roles.map((role) => (
                <span
                  key={role}
                  className="px-1 py-1 text-xs font-medium text-slate-500"
                >
                  {role.replace('_', ' ')}
                </span>
              ))}
            </div>
            <p className="sr-only">Signed in as: {roles.join(', ')}</p>
            <button type="button" onClick={onSignOut} className="cs-button-secondary shrink-0">
              Sign out
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</main></div>
      </div>
    </div>
  )
}
