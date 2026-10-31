import { useEffect, useRef, useState } from 'react'

/** Open a notification's event only after it appears in this user's fetched list. */
export function useEventSelection(
  eventId: string | null,
  rows?: { id: string; event_request_id?: string }[],
) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const handled = useRef<string | null>(null)
  // A direct row ID (for example, a booking notification's source ID) is unambiguous.
  // Retain the event-request fallback for screens that select a related record by event.
  const availableId =
    rows?.find((row) => row.id === eventId)?.id ??
    rows?.find((row) => row.event_request_id === eventId)?.id
  useEffect(() => {
    if (!eventId) {
      handled.current = null
      return
    }
    if (availableId && handled.current !== eventId) {
      handled.current = eventId
      setSelectedId(availableId)
    }
  }, [eventId, availableId])
  return [selectedId, setSelectedId] as const
}
