import { ref } from 'vue'

import { errorCode } from '@/services/http'

const APPROVAL_CODES = new Set([
  'DISCOUNT_APPROVAL_REQUIRED',
  'CONTROLLED_APPROVAL_REQUIRED',
  'FEFO_OVERRIDE_APPROVAL_REQUIRED',
  'BELOW_COST_APPROVAL_REQUIRED',
  'VOID_APPROVAL_REQUIRED',
  'RETURN_APPROVAL_REQUIRED',
])

// One shared dialog: any screen can ask a pharmacist/admin to authorize.
const visible = ref(false)
const reason = ref('')
let resolver: ((token: string | null) => void) | null = null

export function useApproval() {
  function request(why: string): Promise<string | null> {
    reason.value = why
    visible.value = true
    return new Promise((resolve) => (resolver = resolve))
  }

  function resolve(token: string | null): void {
    visible.value = false
    resolver?.(token)
    resolver = null
  }

  /**
   * Run an action; if the API answers that an approval is needed, open the
   * dialog and retry once with the approval token.
   */
  async function withApproval<T>(
    action: (token: string | null) => Promise<T>,
    describe: (error: unknown) => string,
  ): Promise<T> {
    try {
      return await action(null)
    } catch (error) {
      if (!APPROVAL_CODES.has(errorCode(error))) throw error
      const token = await request(describe(error))
      if (!token) throw error
      return await action(token)
    }
  }

  return { visible, reason, request, resolve, withApproval }
}
