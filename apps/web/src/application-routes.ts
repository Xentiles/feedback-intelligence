export const workbenchPages = [
  'Datasets',
  'Classification',
  'Runs',
  'Results',
  'Connections',
] as const
export type WorkbenchPage = (typeof workbenchPages)[number]
export type ApplicationRoute = {
  area: 'showcase' | 'workbench'
  page: WorkbenchPage
}
export function readRoute(hash: string): ApplicationRoute | null {
  if (hash === '' || hash === '#' || hash === '#showcase')
    return { area: 'showcase', page: 'Datasets' }
  if (hash === '#workbench') return { area: 'workbench', page: 'Datasets' }
  if (hash.startsWith('#workbench/')) {
    const page = workbenchPages.find(
      (name) => name.toLowerCase() === hash.slice(11).toLowerCase(),
    )
    if (page) return { area: 'workbench', page }
  }
  return null
}
