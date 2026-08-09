export function parseSqliteUtcTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const withZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(normalized)
    ? normalized
    : `${normalized}Z`
  const date = new Date(withZone)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatTaskTime(value: string | null | undefined): string {
  const date = parseSqliteUtcTimestamp(value)
  if (!date) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}