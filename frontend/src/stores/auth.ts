import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/services/api'
import { hasSession, setTokens } from '@/services/http'
import type { Role, User } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const role = computed<Role | null>(() => user.value?.role ?? null)
  const isStaff = computed(() => role.value === 'admin' || role.value === 'pharmacist')
  const isAdmin = computed(() => role.value === 'admin')

  async function login(username: string, password: string): Promise<void> {
    setTokens(await authApi.login(username, password))
    user.value = await authApi.me()
  }

  /** Restore the user after a page reload, if a token is stored. */
  async function restore(): Promise<boolean> {
    if (user.value) return true
    if (!hasSession()) return false
    try {
      user.value = await authApi.me()
      return true
    } catch {
      logout()
      return false
    }
  }

  function logout(): void {
    setTokens(null)
    user.value = null
  }

  function can(...roles: Role[]): boolean {
    return role.value !== null && (roles.length === 0 || roles.includes(role.value))
  }

  return { user, role, isStaff, isAdmin, login, restore, logout, can }
})
