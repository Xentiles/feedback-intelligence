import type {
  DashboardFilters,
  EvidenceDetailResponse,
  EvidencePageResponse,
  EvaluationComparisonResponse,
  MetadataResponse,
  OverviewResponse,
  PresentationContext,
  SignalResponse,
  TrendOverviewResponse,
} from './dashboard-types'

export interface RequestOptions {
  signal?: AbortSignal
}

export interface DashboardClient {
  metadata(
    context: PresentationContext,
    options?: RequestOptions,
  ): Promise<MetadataResponse>
  overview(
    context: PresentationContext,
    filters: DashboardFilters | null,
    options?: RequestOptions,
  ): Promise<OverviewResponse>
  trends(
    context: PresentationContext,
    options?: RequestOptions,
  ): Promise<TrendOverviewResponse>
  evaluation(
    context: PresentationContext,
    options?: RequestOptions,
  ): Promise<EvaluationComparisonResponse>
  signal(
    context: PresentationContext,
    signalId: string,
    filters: DashboardFilters,
    options?: RequestOptions,
  ): Promise<SignalResponse>
  evidence(
    context: PresentationContext,
    signalId: string,
    filters: DashboardFilters,
    page: number,
    pageSize: number,
    options?: RequestOptions,
  ): Promise<EvidencePageResponse>
  detail(
    context: PresentationContext,
    feedbackId: string,
    decisionId: string,
    options?: RequestOptions,
  ): Promise<EvidenceDetailResponse>
}

export class DashboardRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = 'DashboardRequestError'
  }
}

function appendFilters(
  params: URLSearchParams,
  filters: DashboardFilters | null,
) {
  if (!filters) return

  params.set('sourceKey', filters.sourceKey)
  params.set('from', filters.from)
  params.set('toExclusive', filters.toExclusive)
  for (const key of [
    'topic',
    'product',
    'category',
    'language',
    'channel',
  ] as const) {
    const value = filters[key]
    if (value) params.set(key, value)
  }
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    signal: options?.signal,
  })

  if (!response.ok) {
    let message = `Dashboard request failed (${response.status})`
    try {
      const problem = (await response.json()) as {
        title?: string
        detail?: string
      }
      message = problem.detail ?? problem.title ?? message
    } catch {
      // Preserve the status-based fallback when a proxy returns a non-JSON error.
    }
    throw new DashboardRequestError(message, response.status)
  }

  return (await response.json()) as T
}

function query(
  context: PresentationContext,
  filters: DashboardFilters | null = null,
) {
  const params = new URLSearchParams({ context })
  appendFilters(params, filters)
  return params
}

export const dashboardClient: DashboardClient = {
  metadata(context, options) {
    return request<MetadataResponse>(
      `/api/v1/dashboard/metadata?${query(context)}`,
      options,
    )
  },
  overview(context, filters, options) {
    return request<OverviewResponse>(
      `/api/v1/dashboard/overview?${query(context, filters)}`,
      options,
    )
  },
  trends(context, options) {
    return request<TrendOverviewResponse>(
      `/api/v1/dashboard/trends?${query(context)}`,
      options,
    )
  },
  evaluation(context, options) {
    return request<EvaluationComparisonResponse>(
      `/api/v1/dashboard/evaluation?${query(context)}`,
      options,
    )
  },
  signal(context, signalId, filters, options) {
    return request<SignalResponse>(
      `/api/v1/dashboard/signals/${encodeURIComponent(signalId)}?${query(context, filters)}`,
      options,
    )
  },
  evidence(context, signalId, filters, page, pageSize, options) {
    const params = query(context, filters)
    params.set('page', String(page))
    params.set('pageSize', String(pageSize))
    return request<EvidencePageResponse>(
      `/api/v1/dashboard/signals/${encodeURIComponent(signalId)}/evidence?${params}`,
      options,
    )
  },
  detail(context, feedbackId, decisionId, options) {
    const params = query(context)
    params.set('decisionId', decisionId)
    return request<EvidenceDetailResponse>(
      `/api/v1/dashboard/evidence/${encodeURIComponent(feedbackId)}?${params}`,
      options,
    )
  },
}
