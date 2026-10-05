import { createContext, useContext } from 'react'
export type Confirmation = {
  title: string
  message: string
  confirmLabel?: string
  destructive?: boolean
}
export const ConfirmationContext = createContext<
  ((options: Confirmation) => Promise<boolean>) | null
>(null)
export function useConfirmation() {
  const confirm = useContext(ConfirmationContext)
  return confirm ?? (async () => false)
}
