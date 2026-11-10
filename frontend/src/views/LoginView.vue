<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useErrors } from '@/composables/useErrors'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { message, run } = useErrors()

const username = ref('')
const password = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  const ok = await run(() => auth.login(username.value, password.value))
  busy.value = false
  password.value = ''
  if (ok) {
    const next = typeof route.query.next === 'string' ? route.query.next : '/pos'
    router.replace(next)
  }
}
</script>

<template>
  <div class="login">
    <form class="card stack" @submit.prevent="submit">
      <h1>{{ t('app.name') }}</h1>
      <p class="muted">{{ t('login.title') }}</p>
      <label>
        {{ t('login.username') }}
        <input v-model="username" autocomplete="username" autofocus required />
      </label>
      <label>
        {{ t('login.password') }}
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="message" class="error" role="alert">{{ message }}</p>
      <button class="primary" type="submit" :disabled="busy">{{ t('login.submit') }}</button>
    </form>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1rem;
}

form {
  width: min(360px, 100%);
}
</style>
