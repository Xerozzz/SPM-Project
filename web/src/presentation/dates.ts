const date = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Singapore',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})
const time = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Singapore',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
})

export function singaporeDay(value: string): string {
  return new Date(new Date(value).getTime() + 8 * 3_600_000).toISOString().slice(0, 10)
}

/** Calendar filtering only; a session ending at midnight belongs to the preceding day. */
export function sessionOnDay(start: string, end: string, day: string): boolean {
  const midnight = new Date(`${day}T00:00:00+08:00`).getTime()
  return new Date(start).getTime() < midnight + 86_400_000 && new Date(end).getTime() > midnight
}

export function formatDisplayTime(value: string): string {
  const instant = new Date(value)
  return `${date.format(instant)} · ${time.format(instant)} SGT`
}

export function formatDateRange(start: string, end: string): string {
  if (singaporeDay(start) !== singaporeDay(end))
    return `${formatDisplayTime(start)} – ${formatDisplayTime(end)}`
  return `${date.format(new Date(start))} · ${time.format(new Date(start))}–${time.format(new Date(end))} SGT`
}
