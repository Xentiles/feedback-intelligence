const integerFormatter = new Intl.NumberFormat('en-US')
const percentFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
})

export function formatCount(value: number) {
  return integerFormatter.format(value)
}

export function formatRate(value: number | null) {
  return value === null ? '—' : `${percentFormatter.format(value)}%`
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(value))
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value))
}

export function formatMonth(value: string) {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    year: '2-digit',
    timeZone: 'UTC',
  }).format(new Date(value))
}
