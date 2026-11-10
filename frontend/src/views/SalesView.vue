<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ReceiptView from '@/components/ReceiptView.vue'
import { useApproval } from '@/composables/useApproval'
import { useErrors } from '@/composables/useErrors'
import { posApi } from '@/services/api'
import type { PaymentMethod, Sale } from '@/types/api'
import { formatMoney } from '@/utils/money'

const { t } = useI18n()
const errors = useErrors()
const { withApproval } = useApproval()

const sales = ref<Sale[]>([])
const receiptNumber = ref<number | null>(null)
const selected = ref<Sale | null>(null)
const reason = ref('')
const refundMethod = ref<PaymentMethod>('cash')
const returnQty = ref<Record<number, number>>({})

async function load(): Promise<void> {
  await errors.run(async () => {
    sales.value = await posApi.sales({
      receipt_number: receiptNumber.value ?? undefined,
      limit: 50,
    })
  })
}

function open(sale: Sale): void {
  selected.value = sale
  reason.value = ''
  returnQty.value = {}
  errors.clear()
}

/** Units still returnable per line. */
const returnable = computed(() => {
  const sale = selected.value
  if (!sale) return {}
  const result: Record<number, number> = {}
  for (const line of sale.lines) {
    const returned = sale.returns
      .flatMap((r) => r.lines)
      .filter((l) => l.sale_line_id === line.id)
      .reduce((sum, l) => sum + l.quantity, 0)
    result[line.id] = line.quantity - returned
  }
  return result
})

async function refresh(id: number): Promise<void> {
  selected.value = await posApi.sale(id)
  await load()
}

async function voidSale(): Promise<void> {
  const sale = selected.value
  if (!sale || !reason.value) return
  const ok = await errors.run(() =>
    withApproval((token) => posApi.void(sale.id, reason.value, token), errors.describe),
  )
  if (ok) await refresh(sale.id)
}

async function processReturn(): Promise<void> {
  const sale = selected.value
  if (!sale || !reason.value) return
  const lines = Object.entries(returnQty.value)
    .filter(([, qty]) => qty > 0)
    .map(([id, qty]) => ({ sale_line_id: Number(id), quantity: qty }))
  if (!lines.length) return
  const ok = await errors.run(() =>
    withApproval(
      (token) =>
        posApi.returnSale(
          sale.id,
          { reason: reason.value, refund_method: refundMethod.value, lines },
          token,
        ),
      errors.describe,
    ),
  )
  if (ok) await refresh(sale.id)
}

onMounted(load)
</script>

<template>
  <div class="sales">
    <section class="card stack">
      <h1>{{ t('sales.title') }}</h1>
      <form class="row" @submit.prevent="load">
        <input
          v-model.number="receiptNumber"
          type="number"
          min="1"
          :placeholder="t('sales.findReceipt')"
        />
        <button type="submit">{{ t('common.search') }}</button>
      </form>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{{ t('pos.register') }}</th>
              <th>{{ t('common.date') }}</th>
              <th class="num">{{ t('common.total') }}</th>
              <th>{{ t('common.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sale in sales" :key="sale.id" class="clickable" @click="open(sale)">
              <td>{{ sale.receipt_number }}</td>
              <td>{{ sale.register_code }}</td>
              <td>{{ new Date(sale.created_at).toLocaleString() }}</td>
              <td class="num">{{ formatMoney(sale.total) }}</td>
              <td>
                <span v-if="sale.void" class="badge danger">{{ t('sales.voided') }}</span>
                <span v-else-if="sale.returns.length" class="badge warn">{{
                  t('sales.returns')
                }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!sales.length" class="muted">{{ t('common.empty') }}</p>
      </div>
    </section>

    <section v-if="selected" class="stack">
      <ReceiptView :sale="selected" />
      <div v-if="!selected.void" class="card stack">
        <label>
          {{ t('common.reason') }}
          <input v-model="reason" minlength="3" required />
        </label>
        <h2>{{ t('sales.return') }}</h2>
        <table>
          <tbody>
            <tr v-for="line in selected.lines" :key="line.id">
              <td>{{ line.product_name }}</td>
              <td class="num">{{ returnable[line.id] }} / {{ line.quantity }}</td>
              <td class="num">
                <input
                  v-model.number="returnQty[line.id]"
                  type="number"
                  min="0"
                  :max="returnable[line.id]"
                  class="qty"
                  :aria-label="t('sales.returnQty')"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <label>
          {{ t('sales.refundMethod') }}
          <select v-model="refundMethod">
            <option value="cash">{{ t('pos.methods.cash') }}</option>
            <option value="card">{{ t('pos.methods.card') }}</option>
            <option value="transfer">{{ t('pos.methods.transfer') }}</option>
          </select>
        </label>
        <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>
        <div class="row">
          <button class="primary" :disabled="reason.length < 3" @click="processReturn">
            {{ t('sales.processReturn') }}
          </button>
          <button
            class="danger"
            :disabled="reason.length < 3 || selected.returns.length > 0"
            @click="voidSale"
          >
            {{ t('sales.void') }}
          </button>
        </div>
      </div>
      <div v-for="r in selected.returns" :key="r.id" class="card">
        {{ t('sales.return') }} #{{ r.document_number }} · {{ formatMoney(r.refund_total) }} ·
        {{ r.reason }}
      </div>
    </section>
  </div>
</template>

<style scoped>
.sales {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 380px);
  gap: 1rem;
  align-items: start;
}

@media (max-width: 960px) {
  .sales {
    grid-template-columns: minmax(0, 1fr);
  }
}

.clickable {
  cursor: pointer;
}

.clickable:hover {
  background: var(--surface-2);
}

.qty {
  width: 4.5rem;
}
</style>
