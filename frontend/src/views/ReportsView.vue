<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { reportsApi } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { Alert, DailySales, ExpiringLot, LowStockRow, StockValuation } from '@/types/api'
import { formatMoney } from '@/utils/money'

const { t } = useI18n()
const auth = useAuthStore()
const errors = useErrors()

const day = ref(new Date().toISOString().slice(0, 10))
const daily = ref<DailySales | null>(null)
const expiring = ref<ExpiringLot[]>([])
const low = ref<LowStockRow[]>([])
const valuation = ref<StockValuation | null>(null)
const alerts = ref<Alert[]>([])

async function loadDaily(): Promise<void> {
  await errors.run(async () => {
    daily.value = await reportsApi.daily(day.value)
  })
}

async function loadAll(): Promise<void> {
  await errors.run(async () => {
    ;[daily.value, expiring.value, low.value, valuation.value, alerts.value] = await Promise.all([
      reportsApi.daily(day.value),
      reportsApi.expiring(),
      reportsApi.lowStock(),
      reportsApi.valuation(),
      reportsApi.alerts(),
    ])
  })
}

async function acknowledge(alert: Alert): Promise<void> {
  await errors.run(() => reportsApi.acknowledge(alert.id))
  alerts.value = await reportsApi.alerts()
}

async function runAlerts(): Promise<void> {
  await errors.run(() => reportsApi.runAlerts())
  alerts.value = await reportsApi.alerts()
}

onMounted(loadAll)
</script>

<template>
  <div class="stack">
    <h1>{{ t('reports.title') }}</h1>
    <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>

    <section class="card stack">
      <div class="row">
        <h2 class="grow">{{ t('reports.daily') }}</h2>
        <input v-model="day" type="date" :aria-label="t('common.date')" @change="loadDaily" />
      </div>
      <div v-if="daily" class="tiles">
        <div class="tile">
          <span class="muted">{{ t('reports.gross') }}</span>
          <strong>{{ formatMoney(daily.gross_total) }}</strong>
          <span class="muted">{{ daily.sales_count }} {{ t('pos.salesCount').toLowerCase() }}</span>
        </div>
        <div class="tile">
          <span class="muted">{{ t('reports.returnsTotal') }}</span>
          <strong>{{ formatMoney(daily.returns_total) }}</strong>
        </div>
        <div class="tile">
          <span class="muted">{{ t('reports.net') }}</span>
          <strong>{{ formatMoney(daily.net_total) }}</strong>
        </div>
        <div class="tile">
          <span class="muted">{{ t('pos.tax') }}</span>
          <strong>{{ formatMoney(daily.tax_total) }}</strong>
        </div>
        <div class="tile">
          <span class="muted">{{ t('reports.voidedSales') }}</span>
          <strong>{{ formatMoney(daily.voided_total) }}</strong>
          <span class="muted">{{ daily.voided_count }}</span>
        </div>
      </div>
      <table v-if="daily?.by_payment_method.length">
        <caption class="muted">
          {{
            t('reports.byMethod')
          }}
        </caption>
        <tbody>
          <tr v-for="m in daily.by_payment_method" :key="m.method">
            <td>{{ t(`pos.methods.${m.method}`) }}</td>
            <td class="num">{{ formatMoney(m.amount) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card stack">
      <div class="row">
        <h2 class="grow">{{ t('reports.alerts') }}</h2>
        <button v-if="auth.isAdmin" @click="runAlerts">{{ t('reports.runAlerts') }}</button>
      </div>
      <p v-if="!alerts.length" class="muted">{{ t('common.empty') }}</p>
      <div v-for="a in alerts" :key="a.id" class="row">
        <span :class="['badge', a.type === 'low_stock' ? 'warn' : 'danger']">{{
          a.alert_date
        }}</span>
        <span class="grow">{{ a.message }}</span>
        <button class="link" @click="acknowledge(a)">{{ t('reports.acknowledge') }}</button>
      </div>
    </section>

    <div class="grid-2">
      <section class="card table-wrap">
        <h2>{{ t('reports.expiring') }}</h2>
        <table>
          <tbody>
            <tr v-for="lot in expiring" :key="lot.lot_id">
              <td>
                {{ lot.product_name }} <span class="muted">{{ lot.lot_number }}</span>
              </td>
              <td>{{ lot.expiry_date }}</td>
              <td class="num">{{ lot.quantity }}</td>
              <td class="num">
                <span :class="['badge', lot.expired ? 'danger' : 'warn']">{{ lot.days_left }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!expiring.length" class="muted">{{ t('common.empty') }}</p>
      </section>

      <section class="card table-wrap">
        <h2>{{ t('reports.lowStock') }}</h2>
        <table>
          <tbody>
            <tr v-for="row in low" :key="row.product_id">
              <td>{{ row.product_name }}</td>
              <td class="num">{{ row.stock }} / {{ row.min_stock }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!low.length" class="muted">{{ t('common.empty') }}</p>
      </section>
    </div>

    <section v-if="valuation" class="card table-wrap">
      <div class="row">
        <h2 class="grow">{{ t('reports.valuation') }}</h2>
        <strong>{{ formatMoney(valuation.total_value) }}</strong>
      </div>
      <table>
        <tbody>
          <tr v-for="row in valuation.rows" :key="row.product_id">
            <td>{{ row.product_name }}</td>
            <td class="num">{{ row.quantity }}</td>
            <td class="num">{{ formatMoney(row.value) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.tile strong {
  font-size: 1.3rem;
  font-variant-numeric: tabular-nums;
}

caption {
  text-align: left;
  padding: 0.25rem 0;
}
</style>
