import { createContext, useContext, type ReactNode } from 'react'

export type InspectionDetail = {
  title: string
  scopeLabel?: string
  description?: string
  fields?: { label: string; value: ReactNode }[]
  content?: ReactNode
  action?: { label: string; onClick: () => void }
}

export type InspectionControls = {
  inspect: (detail: InspectionDetail, trigger?: HTMLElement) => void
  dismiss: () => void
  preview: (detail: InspectionDetail, trigger: HTMLElement) => void
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
