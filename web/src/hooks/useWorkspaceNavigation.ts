import { useEffect, useRef, useState } from 'react'

function readLocation() {
  const params = new URLSearchParams(window.location.search)
  return {
    view: params.get('view'),
    eventId: params.get('event'),
    bookingId: params.get('booking'),
  }
}

/** URL state is presentation only: callers still supply their role's allowed screens. */
export function useWorkspaceNavigation(allowedViews: string[], canLeave: () => boolean) {
  const [route, setRoute] = useState(readLocation)
  const guard = useRef(canLeave)
  guard.current = canLeave
  const index = useRef(0)
  const restoring = useRef(false)
  const currentUrl = useRef(window.location.href)
  const view = allowedViews.find((id) => id === route.view) ?? allowedViews[0] ?? 'notifications'

  useEffect(() => {
    index.current = window.history.state?.workspaceIndex ?? 0
    window.history.replaceState({ ...window.history.state, workspaceIndex: index.current }, '')
    function onPop(event: PopStateEvent) {
      if (restoring.current) {
        restoring.current = false
        return
      }
      const nextIndex = event.state?.workspaceIndex ?? 0
      if (!guard.current()) {
        const difference = index.current - nextIndex
        if (difference) {
          restoring.current = true
          window.history.go(difference)
        } else {
          window.history.pushState({ workspaceIndex: index.current }, '', currentUrl.current)
        }
        return
      }
      index.current = nextIndex
      currentUrl.current = window.location.href
      setRoute(readLocation())
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function navigate(
    nextView: string,
    eventId: string | null = null,
    bookingId: string | null = null,
  ) {
    if (!allowedViews.includes(nextView) || !guard.current()) return
    const url = new URL(window.location.href)
    url.searchParams.set('view', nextView)
    if (eventId) url.searchParams.set('event', eventId)
    else url.searchParams.delete('event')
    if (bookingId) url.searchParams.set('booking', bookingId)
    else url.searchParams.delete('booking')
    url.hash = ''
    index.current += 1
    window.history.pushState({ workspaceIndex: index.current }, '', url)
    currentUrl.current = url.href
    setRoute({ view: nextView, eventId, bookingId })
  }
  return {
    view,
    eventId: route.view === view ? route.eventId : null,
    bookingId: route.view === view ? route.bookingId : null,
    navigate,
  }
}
