import { createContext, useContext, type ReactNode } from 'react'

export type InspectionDetail = {
  title: string
  scopeLabel?: string
  description?: string
  fields?: { label: string; value: ReactNode }[]
  content?: ReactNode
  action?: { label: string; onClick: () => void }
}

export type PreviewPoint = { x: number; y: number }
export type PreviewAnchor = PreviewPoint | (() => PreviewPoint | null)

/** SVG coordinates must become viewport coordinates, including responsive scaling. */
export function chartAnchor(
  svg: SVGSVGElement | null,
  x: number,
  y: number,
): PreviewPoint | null {
  if (!svg) return null
  const transform = svg.getScreenCTM?.()
  if (transform)
    return {
      x: transform.a * x + transform.c * y + transform.e,
      y: transform.b * x + transform.d * y + transform.f,
    }
  const bounds = svg.getBoundingClientRect()
  const box = (svg.getAttribute('viewBox') || '0 0 720 280')
    .split(/\s+/)
    .map(Number)
  return {
    x: bounds.left + (x / box[2]!) * bounds.width,
    y: bounds.top + (y / box[3]!) * bounds.height,
  }
}

export type InspectionControls = {
  inspect: (detail: InspectionDetail, trigger?: HTMLElement) => void
  dismiss: () => void
  preview: (
    detail: InspectionDetail,
    trigger: HTMLElement,
    anchor?: PreviewAnchor,
  ) => void
  clearPreview: () => void
}

type InspectionContextValue = InspectionControls & { previewId?: string }
const noop = () => undefined
export const InspectionContext = createContext<InspectionContextValue>({
  inspect: noop,
  dismiss: noop,
  preview: noop,
  clearPreview: noop,
})

export function useInspection(): InspectionContextValue {
  return useContext(InspectionContext)
}
