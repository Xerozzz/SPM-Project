import { useEffect, useRef, useState } from 'react'

/** Open a notification's event only after it appears in this user's fetched list. */
export function useEventSelection(
  eventId: string | null,
  rows?: { id: string; event_request_id?: string }[],
) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const handled = useRef<string | null>(null)
  const availableId = rows?.find((row) => (row.event_request_id ?? row.id) === eventId)?.id
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
