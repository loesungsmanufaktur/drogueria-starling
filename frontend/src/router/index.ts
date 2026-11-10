import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types/api'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    roles?: Role[]
  }
}

const STAFF: Role[] = ['admin', 'pharmacist']

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  { path: '/', redirect: '/pos' },
  { path: '/pos', name: 'pos', component: () => import('@/views/PosView.vue') },
  { path: '/sales', name: 'sales', component: () => import('@/views/SalesView.vue') },
  { path: '/catalog', name: 'catalog', component: () => import('@/views/CatalogView.vue') },
  { path: '/customers', name: 'customers', component: () => import('@/views/CustomersView.vue') },
  {
    path: '/inventory',
    name: 'inventory',
    component: () => import('@/views/InventoryView.vue'),
    meta: { roles: STAFF },
  },
  {
    path: '/purchasing',
    name: 'purchasing',
    component: () => import('@/views/PurchasingView.vue'),
    meta: { roles: STAFF },
  },
  {
    path: '/reports',
    name: 'reports',
    component: () => import('@/views/ReportsView.vue'),
    meta: { roles: STAFF },
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { roles: ['admin'] },
  },
  { path: '/:pathMatch(.*)*', redirect: '/pos' },
]

export const router = createRouter({ history: createWebHistory(), routes })

// Navigation follows the role, but the backend enforces every permission (SEC-2).
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (!(await auth.restore())) return { name: 'login', query: { next: to.fullPath } }
  if (to.meta.roles && !auth.can(...to.meta.roles)) return { name: 'pos' }
  return true
})
