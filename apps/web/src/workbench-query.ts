export const facetFields = [
  'topic',
  'sentiment',
  'language',
  'product',
  'group',
] as const
export type FacetField = (typeof facetFields)[number]
export type ResultFilters = Record<FacetField, string> & {
  missing: string[]
  dateFrom: string
  dateTo: string
  page: number
}
export const emptyResultFilters = (): ResultFilters => ({
  topic: '',
  sentiment: '',
  language: '',
  product: '',
  group: '',
  missing: [],
  dateFrom: '',
  dateTo: '',
  page: 1,
})
export function resultQuery(filters: ResultFilters, includePage = true) {
  const query = new URLSearchParams()
  for (const field of facetFields)
    if (filters[field]) query.set(field, filters[field])
  if (filters.missing.length)
    query.set('missing', [...filters.missing].sort().join(','))
  if (filters.dateFrom) query.set('dateFrom', filters.dateFrom)
  if (filters.dateTo) query.set('dateTo', filters.dateTo)
  if (includePage) query.set('page', String(filters.page))
  return query.toString()
}
export function selectFacet(
  filters: ResultFilters,
  field: FacetField,
  value: string | null | undefined,
): ResultFilters {
  return {
    ...filters,
    [field]: typeof value === 'string' ? value : '',
    missing: [
      ...filters.missing.filter((key) => key !== field),
      ...(value === null ? [field] : []),
    ],
    page: 1,
  }
}
export function facetChoice(filters: ResultFilters, field: FacetField) {
  return filters.missing.includes(field)
    ? 'null'
    : filters[field]
      ? JSON.stringify(filters[field])
      : ''
}
