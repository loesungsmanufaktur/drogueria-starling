<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { customersApi } from '@/services/api'
import type { Customer } from '@/types/api'
import { CF, isValidTaxId, normalizeTaxId } from '@/utils/taxId'

const props = defineProps<{
  /** Customer to edit; omit to create a new one. */
  customer?: Customer | null
  /** Pre-filled NIT/CUI for a new customer (e.g. the number the POS did not find). */
  taxId?: string
}>()
const emit = defineEmits<{ saved: [customer: Customer]; cancel: [] }>()

const { t } = useI18n()
const errors = useErrors()

const fullName = ref(props.customer?.full_name ?? '')
const documentId = ref(props.customer?.document_id ?? props.taxId ?? '')
const phone = ref(props.customer?.phone ?? '')
const email = ref(props.customer?.email ?? '')
// SAL-13: the NIT/CUI is mandatory; the toggle records the customer as CF.
const isCf = ref(normalizeTaxId(documentId.value) === CF && documentId.value !== '')
const nameInput = ref<HTMLInputElement | null>(null)
const taxInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)

const taxIdValid = computed(
  () => isCf.value || (documentId.value.trim() !== '' && isValidTaxId(documentId.value)),
)

function toggleCf(): void {
  documentId.value = isCf.value ? CF : ''
  if (!isCf.value) nextTick(() => taxInput.value?.focus())
}

function nullable(value: string): string | null {
  return value.trim() ? value.trim() : null
}

async function save(): Promise<void> {
  if (!taxIdValid.value) return
  busy.value = true
  const body = {
    full_name: fullName.value.trim(),
    document_id: isCf.value ? CF : normalizeTaxId(documentId.value),
    phone: nullable(phone.value),
    email: nullable(email.value),
  }
  let saved: Customer | null = null
  await errors.run(async () => {
    saved = props.customer
      ? await customersApi.update(props.customer.id, body)
      : await customersApi.create(body)
  })
  busy.value = false
  if (saved) emit('saved', saved)
}

onMounted(() => nameInput.value?.focus())
</script>

<template>
  <form class="stack" @submit.prevent="save">
    <label>
      {{ t('customers.fullName') }}
      <input ref="nameInput" v-model="fullName" required maxlength="160" />
    </label>
    <div class="stack tax-id">
      <label>
        {{ t('customers.documentId') }}
        <input
          ref="taxInput"
          v-model="documentId"
          :disabled="isCf"
          :required="!isCf"
          :aria-invalid="!taxIdValid"
          maxlength="30"
          autocomplete="off"
        />
      </label>
      <label class="check">
        <input v-model="isCf" type="checkbox" role="switch" @change="toggleCf" />
        {{ t('customers.markCf') }}
      </label>
      <span v-if="!taxIdValid && documentId" class="error">{{ t('customers.invalidTaxId') }}</span>
    </div>
    <label>{{ t('customers.phone') }}<input v-model="phone" maxlength="40" /></label>
    <label>{{ t('customers.email') }}<input v-model="email" type="email" maxlength="120" /></label>
    <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>
    <div class="row">
      <button class="primary" type="submit" :disabled="busy || !taxIdValid">
        {{ t('common.save') }}
      </button>
      <button type="button" @click="emit('cancel')">{{ t('common.cancel') }}</button>
    </div>
  </form>
</template>

<style scoped>
.tax-id {
  gap: 0.35rem;
}
</style>
