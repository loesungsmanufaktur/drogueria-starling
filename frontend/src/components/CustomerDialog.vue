<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import CustomerForm from '@/components/CustomerForm.vue'
import { useErrors } from '@/composables/useErrors'
import { customersApi } from '@/services/api'
import { errorCode } from '@/services/http'
import type { Customer } from '@/types/api'
import { CF, isValidTaxId, normalizeTaxId } from '@/utils/taxId'

// Asks for the customer's NIT/CUI at the POS. Emits the customer found or
// created, or null to sell to "Consumidor Final" (CF).
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ select: [customer: Customer | null] }>()

const { t } = useI18n()
const errors = useErrors()

const dialog = ref<HTMLDialogElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const taxId = ref('')
const notFound = ref<string | null>(null)
const creating = ref(false)
const busy = ref(false)

watch(open, async (visible) => {
  if (!visible) return dialog.value?.close()
  taxId.value = ''
  notFound.value = null
  creating.value = false
  errors.clear()
  dialog.value?.showModal()
  await nextTick()
  input.value?.focus()
})

function choose(customer: Customer | null): void {
  open.value = false
  emit('select', customer)
}

async function lookup(): Promise<void> {
  const normalized = normalizeTaxId(taxId.value)
  if (normalized === CF) return choose(null)
  if (!isValidTaxId(normalized)) {
    errors.message.value = t('customers.invalidTaxId')
    return
  }
  busy.value = true
  notFound.value = null
  errors.clear()
  try {
    choose(await customersApi.lookup(normalized))
  } catch (error) {
    if (errorCode(error) === 'CUSTOMER_NOT_FOUND') notFound.value = normalized
    else errors.show(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <dialog ref="dialog" class="customer-dialog" @cancel.prevent="choose(null)">
    <div class="stack">
      <h2>{{ t('pos.customerPrompt') }}</h2>

      <template v-if="!creating">
        <form class="row" @submit.prevent="lookup">
          <input
            ref="input"
            v-model="taxId"
            class="grow"
            :placeholder="t('pos.taxIdPlaceholder')"
            :aria-label="t('customers.documentId')"
            autocomplete="off"
            maxlength="30"
          />
          <button class="primary" type="submit" :disabled="busy">{{ t('common.search') }}</button>
        </form>
        <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>

        <div v-if="notFound" class="card stack not-found" role="status">
          <span>{{ t('pos.customerNotFound', { taxId: notFound }) }}</span>
          <div class="row">
            <button class="primary" @click="creating = true">{{ t('pos.createCustomer') }}</button>
            <button @click="choose(null)">{{ t('pos.sellAsCf') }}</button>
          </div>
        </div>

        <div v-if="!notFound" class="row">
          <button @click="choose(null)">{{ t('pos.sellAsCf') }}</button>
        </div>
      </template>

      <CustomerForm v-else :tax-id="notFound ?? ''" @saved="choose" @cancel="creating = false" />
    </div>
  </dialog>
</template>

<style scoped>
.customer-dialog {
  width: min(460px, calc(100vw - 2rem));
}

.not-found {
  box-shadow: none;
}
</style>
