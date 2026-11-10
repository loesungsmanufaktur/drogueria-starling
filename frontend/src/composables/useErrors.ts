import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { errorCode, errorDetail } from '@/services/http'

/** Translate API error codes; fall back to the server's message. */
export function useErrors() {
  const { t, te } = useI18n()
  const message = ref('')

  function describe(error: unknown): string {
    const code = errorCode(error)
    const key = `errors.${code}`
    if (te(key)) return t(key)
    return errorDetail(error) || t('errors.UNKNOWN_ERROR')
  }

  function show(error: unknown): void {
    message.value = describe(error)
  }

  function clear(): void {
    message.value = ''
  }

  /** Run an async action, capturing its error message. Returns success. */
  async function run(action: () => Promise<unknown>): Promise<boolean> {
    clear()
    try {
      await action()
      return true
    } catch (error) {
      show(error)
      return false
    }
  }

  return { message, describe, show, clear, run }
}
