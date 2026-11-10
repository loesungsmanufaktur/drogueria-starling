<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { setLocale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types/api'

const auth = useAuthStore()
const router = useRouter()
const { t, locale } = useI18n()

const links: { to: string; label: string; roles?: Role[] }[] = [
  { to: '/pos', label: 'nav.pos' },
  { to: '/sales', label: 'nav.sales' },
  { to: '/catalog', label: 'nav.catalog' },
  { to: '/customers', label: 'nav.customers' },
  { to: '/inventory', label: 'nav.inventory', roles: ['admin', 'pharmacist'] },
  { to: '/purchasing', label: 'nav.purchasing', roles: ['admin', 'pharmacist'] },
  { to: '/reports', label: 'nav.reports', roles: ['admin', 'pharmacist'] },
  { to: '/admin', label: 'nav.admin', roles: ['admin'] },
]
const visible = computed(() => links.filter((l) => !l.roles || auth.can(...l.roles)))

function logout(): void {
  auth.logout()
  router.push({ name: 'login' })
}

function switchLocale(event: Event): void {
  setLocale((event.target as HTMLSelectElement).value as 'es' | 'en')
}
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <strong class="brand">{{ t('app.name') }}</strong>
      <nav class="nav">
        <RouterLink v-for="link in visible" :key="link.to" :to="link.to">
          {{ t(link.label) }}
        </RouterLink>
      </nav>
      <div class="row user">
        <select :value="locale" :aria-label="t('app.language')" @change="switchLocale">
          <option value="es">ES</option>
          <option value="en">EN</option>
        </select>
        <span v-if="auth.user" class="muted">
          {{ auth.user.full_name }} · {{ t(`roles.${auth.user.role}`) }}
        </span>
        <button class="link" @click="logout">{{ t('app.logout') }}</button>
      </div>
    </header>
    <main class="content">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.brand {
  color: var(--primary);
}

.nav {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
  flex: 1;
}

.nav a {
  padding: 0.35rem 0.65rem;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text);
}

.nav a.router-link-active {
  background: var(--surface-2);
  color: var(--primary);
  font-weight: 600;
}

.user select {
  padding: 0.2rem 0.3rem;
}

.content {
  padding: 1rem;
  flex: 1;
}

@media (max-width: 640px) {
  .content {
    padding: 0.75rem;
  }
}
</style>
