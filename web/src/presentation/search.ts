/** A display filter over data the API has already allowed the viewer to read. */
export function matchesSearch(query: string, ...values: (string | null | undefined)[]) {
  const text = values.filter(Boolean).join(' ').toLowerCase()
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .every((word) => text.includes(word))
}
