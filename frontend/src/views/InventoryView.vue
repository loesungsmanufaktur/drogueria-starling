<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { catalogApi, inventoryApi } from '@/services/api'
import type { Lot, Movement, Product } from '@/types/api'
import { formatMoney } from '@/utils/money'

const { t } = useI18n()
const errors = useErrors()

const q = ref('')
const products = ref<Product[]>([])
const product = ref<Product | null>(null)
const lots = ref<Lot[]>([])
const movements = ref<Movement[]>([])
const today = new Date().toISOString().slice(0, 10)

const opening = ref({ lot_number: '', expiry_date: '', quantity: 1, unit_cost: '', reason: '' })
const adjust = ref<{ lot: Lot; quantity: number; reason: string } | null>(null)

async function search(): Promise<void> {
  await errors.run(async () => {
    products.value = await catalogApi.search({ q: q.value || undefined, limit: 30 })
  })
}

async function select(p: Product): Promise<void> {
  product.value = p
  adjust.value = null
  await errors.run(async () => {
    ;[lots.value, movements.value] = await Promise.all([
      inventoryApi.lots({ product_id: p.id, include_empty: true }),
      inventoryApi.movements({ product_id: p.id, limit: 50 }),
    ])
  })
}

async function addOpening(): Promise<void> {
  if (!product.value) return
  const ok = await errors.run(() =>
    inventoryApi.openingLot({ product_id: product.value!.id, ...opening.value }),
  )
  if (ok) {
    opening.value = { lot_number: '', expiry_date: '', quantity: 1, unit_cost: '', reason: '' }
    await select(product.value)
  }
}

async function saveAdjustment(): Promise<void> {
  const a = adjust.value
  if (!a || !product.value) return
  const ok = await errors.run(() =>
    inventoryApi.adjust({ lot_id: a.lot.id, quantity: a.quantity, reason: a.reason }),
  )
  if (ok) await select(product.value)
}

async function writeOff(lot: Lot): Promise<void> {
  const reason = prompt(t('common.reason'))
  if (!reason || !product.value) return
  await errors.run(() => inventoryApi.writeOff(lot.id, reason))
  await select(product.value)
}

onMounted(search)
</script>

<template>
  <div class="inventory">
    <section class="card stack">
      <h1>{{ t('inventory.title') }}</h1>
      <form class="row" @submit.prevent="search">
        <input v-model="q" class="grow" :placeholder="t('pos.scan')" />
        <button type="submit">{{ t('common.search') }}</button>
      </form>
      <ul class="list">
        <li v-for="p in products" :key="p.id">
          <button class="link" @click="select(p)">{{ p.name }}</button>
          <span class="muted">{{ p.stock }}</span>
        </li>
      </ul>
    </section>

    <section v-if="product" class="stack">
      <div class="card stack">
        <h2>{{ product.name }} · {{ t('inventory.lots') }}</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('inventory.lotNumber') }}</th>
                <th>{{ t('inventory.expiry') }}</th>
                <th class="num">{{ t('common.quantity') }}</th>
                <th class="num">{{ t('inventory.unitCost') }}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="lot in lots" :key="lot.id">
                <td>{{ lot.lot_number }}</td>
                <td>
                  {{ lot.expiry_date }}
                  <span v-if="lot.expiry_date <= today" class="badge danger">{{
                    t('inventory.expired')
                  }}</span>
                </td>
                <td class="num">{{ lot.quantity }}</td>
                <td class="num">{{ formatMoney(lot.unit_cost) }}</td>
                <td>
                  <button class="link" @click="adjust = { lot, quantity: 0, reason: '' }">
                    {{ t('inventory.adjust') }}
                  </button>
                  <button
                    v-if="lot.expiry_date <= today && lot.quantity > 0"
                    class="link danger"
                    @click="writeOff(lot)"
                  >
                    {{ t('inventory.writeOff') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <form v-if="adjust" class="row" @submit.prevent="saveAdjustment">
          <strong>{{ adjust.lot.lot_number }}</strong>
          <label
            >{{ t('inventory.adjustment')
            }}<input v-model.number="adjust.quantity" type="number" required
          /></label>
          <label class="grow"
            >{{ t('common.reason') }}<input v-model="adjust.reason" minlength="3" required
          /></label>
          <button class="primary" type="submit">{{ t('common.save') }}</button>
          <button type="button" @click="adjust = null">{{ t('common.cancel') }}</button>
        </form>
      </div>

      <form class="card stack" @submit.prevent="addOpening">
        <h2>{{ t('inventory.openingStock') }}</h2>
        <div class="grid-2">
          <label
            >{{ t('inventory.lotNumber') }}<input v-model="opening.lot_number" required
          /></label>
          <label
            >{{ t('inventory.expiry') }}<input v-model="opening.expiry_date" type="date" required
          /></label>
          <label
            >{{ t('common.quantity')
            }}<input v-model.number="opening.quantity" type="number" min="1" required
          /></label>
          <label
            >{{ t('inventory.unitCost')
            }}<input v-model="opening.unit_cost" inputmode="decimal" required
          /></label>
        </div>
        <label
          >{{ t('common.reason') }}<input v-model="opening.reason" minlength="3" required
        /></label>
        <button class="primary" type="submit">{{ t('common.add') }}</button>
      </form>

      <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>

      <div class="card table-wrap">
        <h2>{{ t('inventory.movements') }}</h2>
        <table>
          <thead>
            <tr>
              <th>{{ t('common.date') }}</th>
              <th>{{ t('inventory.type') }}</th>
              <th class="num">{{ t('common.quantity') }}</th>
              <th>{{ t('common.reason') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in movements" :key="m.id">
              <td>{{ new Date(m.created_at).toLocaleString() }}</td>
              <td>{{ t(`inventory.types.${m.type}`) }}</td>
              <td class="num">{{ m.quantity > 0 ? '+' : '' }}{{ m.quantity }}</td>
              <td>{{ m.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.inventory {
  display: grid;
  grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

@media (max-width: 860px) {
  .inventory {
    grid-template-columns: minmax(0, 1fr);
  }
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.list li {
  display: flex;
  justify-content: space-between;
}
</style>
