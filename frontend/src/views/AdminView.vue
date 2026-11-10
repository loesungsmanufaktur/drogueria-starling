<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { posApi, usersApi } from '@/services/api'
import type { AuditEntry, Register, Role, User } from '@/types/api'

const { t } = useI18n()
const errors = useErrors()

const tab = ref<'users' | 'registers' | 'audit'>('users')
const users = ref<User[]>([])
const registers = ref<Register[]>([])
const audit = ref<AuditEntry[]>([])
const auditEntity = ref('')
const roles: Role[] = ['admin', 'pharmacist', 'cashier']

const userForm = ref<{ username: string; full_name: string; role: Role; password: string } | null>(
  null,
)
const registerForm = ref<{ code: string; name: string; is_active: boolean } | null>(null)

async function load(): Promise<void> {
  await errors.run(async () => {
    ;[users.value, registers.value] = await Promise.all([usersApi.list(), posApi.registers()])
  })
}

async function loadAudit(): Promise<void> {
  await errors.run(async () => {
    audit.value = await usersApi.audit({ entity: auditEntity.value || undefined, limit: 100 })
  })
}

async function createUser(): Promise<void> {
  if (!userForm.value) return
  const ok = await errors.run(() => usersApi.create(userForm.value!))
  if (ok) {
    userForm.value = null
    await load()
  }
}

async function updateUser(
  user: User,
  change: Partial<{ role: Role; is_active: boolean }>,
): Promise<void> {
  await errors.run(() => usersApi.update(user.id, change))
  await load()
}

async function resetPassword(user: User): Promise<void> {
  const password = prompt(t('admin.newPassword'))
  if (!password) return
  await errors.run(() => usersApi.update(user.id, { password }))
}

async function createRegister(): Promise<void> {
  if (!registerForm.value) return
  const ok = await errors.run(() => posApi.createRegister(registerForm.value!))
  if (ok) {
    registerForm.value = null
    await load()
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <h1>{{ t('admin.title') }}</h1>
    <div class="tabs">
      <button :class="{ active: tab === 'users' }" @click="tab = 'users'">
        {{ t('admin.users') }}
      </button>
      <button :class="{ active: tab === 'registers' }" @click="tab = 'registers'">
        {{ t('admin.registers') }}
      </button>
      <button :class="{ active: tab === 'audit' }" @click="((tab = 'audit'), loadAudit())">
        {{ t('admin.audit') }}
      </button>
    </div>
    <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>

    <template v-if="tab === 'users'">
      <button
        class="primary"
        @click="userForm = { username: '', full_name: '', role: 'cashier', password: '' }"
      >
        {{ t('admin.newUser') }}
      </button>
      <form v-if="userForm" class="card grid-2" @submit.prevent="createUser">
        <label>{{ t('login.username') }}<input v-model="userForm.username" required /></label>
        <label>{{ t('customers.fullName') }}<input v-model="userForm.full_name" required /></label>
        <label>
          {{ t('admin.role') }}
          <select v-model="userForm.role">
            <option v-for="r in roles" :key="r" :value="r">{{ t(`roles.${r}`) }}</option>
          </select>
        </label>
        <label
          >{{ t('login.password')
          }}<input
            v-model="userForm.password"
            type="password"
            minlength="8"
            required
            autocomplete="new-password"
        /></label>
        <div class="row">
          <button class="primary" type="submit">{{ t('common.save') }}</button>
          <button type="button" @click="userForm = null">{{ t('common.cancel') }}</button>
        </div>
      </form>
      <div class="card table-wrap">
        <table>
          <tbody>
            <tr v-for="u in users" :key="u.id" :class="{ muted: !u.is_active }">
              <td>{{ u.username }}</td>
              <td>{{ u.full_name }}</td>
              <td>
                <select
                  :value="u.role"
                  :aria-label="t('admin.role')"
                  @change="
                    updateUser(u, { role: ($event.target as HTMLSelectElement).value as Role })
                  "
                >
                  <option v-for="r in roles" :key="r" :value="r">{{ t(`roles.${r}`) }}</option>
                </select>
              </td>
              <td>
                <label class="check">
                  <input
                    type="checkbox"
                    :checked="u.is_active"
                    @change="updateUser(u, { is_active: !u.is_active })"
                  />
                  {{ t('common.active') }}
                </label>
              </td>
              <td>
                <button class="link" @click="resetPassword(u)">{{ t('admin.newPassword') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="tab === 'registers'">
      <button class="primary" @click="registerForm = { code: '', name: '', is_active: true }">
        {{ t('admin.newRegister') }}
      </button>
      <form v-if="registerForm" class="card row" @submit.prevent="createRegister">
        <label>{{ t('admin.code') }}<input v-model="registerForm.code" required /></label>
        <label class="grow"
          >{{ t('common.name') }}<input v-model="registerForm.name" required
        /></label>
        <button class="primary" type="submit">{{ t('common.save') }}</button>
        <button type="button" @click="registerForm = null">{{ t('common.cancel') }}</button>
      </form>
      <div class="card table-wrap">
        <table>
          <tbody>
            <tr v-for="r in registers" :key="r.id">
              <td>{{ r.code }}</td>
              <td>{{ r.name }}</td>
              <td>{{ r.is_active ? t('common.active') : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else>
      <form class="row" @submit.prevent="loadAudit">
        <input v-model="auditEntity" :placeholder="t('admin.entity')" />
        <button type="submit">{{ t('common.search') }}</button>
      </form>
      <div class="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('common.date') }}</th>
              <th>{{ t('admin.action') }}</th>
              <th>{{ t('admin.entity') }}</th>
              <th>ID</th>
              <th>{{ t('admin.users') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in audit" :key="e.id">
              <td>{{ new Date(e.created_at).toLocaleString() }}</td>
              <td>{{ e.action }}</td>
              <td>{{ e.entity }}</td>
              <td>{{ e.entity_id }}</td>
              <td>{{ e.user_id ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
