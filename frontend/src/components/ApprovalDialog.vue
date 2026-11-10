<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useApproval } from '@/composables/useApproval'
import { useErrors } from '@/composables/useErrors'
import { authApi } from '@/services/api'

const { t } = useI18n()
const { visible, reason, resolve } = useApproval()
const { message, run, clear } = useErrors()

const dialog = ref<HTMLDialogElement | null>(null)
const userInput = ref<HTMLInputElement | null>(null)
const username = ref('')
const password = ref('')
const busy = ref(false)

watch(visible, async (open) => {
  if (open) {
    username.value = ''
    password.value = ''
    clear()
    dialog.value?.showModal()
    await nextTick()
    userInput.value?.focus()
  } else {
    dialog.value?.close()
  }
})

async function submit(): Promise<void> {
  busy.value = true
  let token: string | null = null
  const ok = await run(async () => {
    token = (await authApi.approve(username.value, password.value)).approval_token
  })
  busy.value = false
  password.value = ''
  if (ok) resolve(token)
}
</script>

<template>
  <dialog ref="dialog" @cancel.prevent="resolve(null)">
    <form class="stack" @submit.prevent="submit">
      <h2>{{ t('approval.title') }}</h2>
      <p class="muted">{{ reason }}</p>
      <p class="muted">{{ t('approval.hint') }}</p>
      <label>
        {{ t('login.username') }}
        <input ref="userInput" v-model="username" autocomplete="off" required />
      </label>
      <label>
        {{ t('login.password') }}
        <input v-model="password" type="password" autocomplete="off" required />
      </label>
      <p v-if="message" class="error" role="alert">{{ message }}</p>
      <div class="row">
        <button type="submit" class="primary" :disabled="busy">{{ t('approval.submit') }}</button>
        <button type="button" @click="resolve(null)">{{ t('common.cancel') }}</button>
      </div>
    </form>
  </dialog>
</template>
