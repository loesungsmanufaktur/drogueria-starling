<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Sale } from '@/types/api'
import { formatMoney } from '@/utils/money'

defineProps<{ sale: Sale }>()
const { t } = useI18n()
</script>

<!-- 80 mm thermal layout, printed through the browser dialog. -->
<template>
  <div class="receipt printable">
    <p class="center">
      <strong>{{ t('app.name') }}</strong>
    </p>
    <p class="center">{{ t('pos.receiptNumber', { number: sale.receipt_number }) }}</p>
    <p class="center small">
      {{ sale.register_name }} · {{ new Date(sale.created_at).toLocaleString() }}
    </p>
    <!-- SAL-10: customer name and NIT/CUI (CF for consumidor final). -->
    <p class="small">{{ t('pos.customer') }}: {{ sale.customer_name }}</p>
    <p class="small">{{ t('customers.documentId') }}: {{ sale.customer_tax_id }}</p>
    <p v-if="sale.void" class="center">
      <strong>** {{ t('sales.voided') }} **</strong>
    </p>
    <hr />
    <div v-for="line in sale.lines" :key="line.id" class="line">
      <div>{{ line.product_name }}</div>
      <div class="split small">
        <span>{{ line.quantity }} × {{ formatMoney(line.unit_price) }}</span>
        <span>{{ formatMoney(line.line_total) }}</span>
      </div>
      <div v-if="line.discount_amount !== '0.00'" class="split small">
        <span>{{ t('pos.discountTotal') }} {{ line.discount_percent }}%</span>
        <span>-{{ formatMoney(line.discount_amount) }}</span>
      </div>
    </div>
    <hr />
    <div class="split">
      <span>{{ t('pos.subtotal') }}</span
      ><span>{{ formatMoney(sale.subtotal) }}</span>
    </div>
    <div class="split">
      <span>{{ t('pos.tax') }}</span
      ><span>{{ formatMoney(sale.tax_total) }}</span>
    </div>
    <div class="split total">
      <span>{{ t('common.total') }}</span
      ><span>{{ formatMoney(sale.total) }}</span>
    </div>
    <template v-for="(p, i) in sale.payments" :key="i">
      <div class="split small">
        <span>{{ t(`pos.methods.${p.method}`) }}</span
        ><span>{{ formatMoney(p.amount) }}</span>
      </div>
      <div v-if="p.method === 'card'" class="small detail">
        {{ p.card_type ? t(`pos.cards.${p.card_type}`) : '' }} **** {{ p.card_last4 }} ·
        {{ t('pos.reference') }}
        {{ p.reference }}
      </div>
      <div v-else-if="p.method === 'transfer'" class="small detail">
        {{ p.bank_name }} · {{ t('pos.reference') }} {{ p.reference }}
      </div>
    </template>
    <div v-if="sale.cash_tendered" class="split small">
      <span>{{ t('pos.tendered') }}</span
      ><span>{{ formatMoney(sale.cash_tendered) }}</span>
    </div>
    <div v-if="sale.change_given !== '0.00'" class="split small">
      <span>{{ t('pos.change') }}</span
      ><span>{{ formatMoney(sale.change_given) }}</span>
    </div>
  </div>
</template>

<style scoped>
.receipt {
  width: 72mm;
  max-width: 100%;
  font-family: ui-monospace, 'Cascadia Mono', monospace;
  font-size: 12px;
  background: #fff;
  color: #000;
  padding: 4mm;
}

.receipt p {
  margin: 0.15rem 0;
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.split {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.total {
  font-weight: 700;
  font-size: 14px;
  margin: 0.25rem 0;
}

.line {
  margin-bottom: 0.25rem;
}

.detail {
  padding-left: 0.5rem;
}

hr {
  border: none;
  border-top: 1px dashed #000;
}
</style>
