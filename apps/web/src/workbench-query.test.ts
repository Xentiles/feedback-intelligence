import { describe, expect, it } from 'vitest'
import {
  emptyResultFilters,
  facetChoice,
  resultQuery,
  selectFacet,
} from './workbench-query'

describe('result query semantics', () => {
  it('uses explicit All defaults and excludes paging from cohort/export identity', () => {
    const empty = emptyResultFilters()
    expect(resultQuery(empty)).toBe('page=1')
    expect(resultQuery(empty, false)).toBe('')
    expect(facetChoice(empty, 'topic')).toBe('')
    const selection = { ...selectFacet(empty, 'language', 'sv'), page: 3 }
    expect(new URLSearchParams(resultQuery(selection)).get('page')).toBe('3')
    expect(resultQuery(selection, false)).toBe('language=sv')
  })

  it('distinguishes literal None from missing metadata and resets pagination', () => {
    const literal = selectFacet(
      { ...emptyResultFilters(), page: 4 },
      'product',
      'None',
    )
    expect(facetChoice(literal, 'product')).toBe('"None"')
    expect(resultQuery(literal)).toBe('product=None&page=1')
    const missing = selectFacet(literal, 'product', null)
    expect(facetChoice(missing, 'product')).toBe('null')
    expect(resultQuery(missing)).toBe('missing=product&page=1')
    expect(selectFacet(missing, 'product', undefined)).toEqual(
      emptyResultFilters(),
    )
  })

  it('retains other selections and serializes inclusive date boundaries without timezone guesses', () => {
    const first = selectFacet(emptyResultFilters(), 'language', null)
    const next = selectFacet(first, 'sentiment', null)
    const result = selectFacet(
      { ...next, dateFrom: '2026-09-01', dateTo: '2026-09-30' },
      'group',
      'General / support & returns',
    )
    const query = new URLSearchParams(resultQuery(result, false))
    expect(query.get('missing')).toBe('language,sentiment')
    expect(query.get('group')).toBe('General / support & returns')
    expect(query.get('dateFrom')).toBe('2026-09-01')
    expect(query.get('dateTo')).toBe('2026-09-30')
    expect(first.missing).toEqual(['language'])
    expect(facetChoice(result, 'sentiment')).toBe('null')
  })
})
