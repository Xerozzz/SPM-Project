import { useEffect } from 'react'

/** Warn on reload or closing a tab; workspace/back buttons use the same dirty flag. */
export function useUnsavedChanges(dirty: boolean, onDirtyChange?: (dirty: boolean) => void) {
  useEffect(() => {
    onDirtyChange?.(dirty)
    if (!dirty) return
    function beforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload)
      onDirtyChange?.(false)
    }
  }, [dirty, onDirtyChange])
}
