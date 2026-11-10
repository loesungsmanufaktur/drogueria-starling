<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { catalogApi, purchasingApi } from '@/services/api'
import type { Product, PurchaseOrder, Supplier } from '@/types/api'
import { formatMoney, toCents } from '@/utils/money'

const { t } = useI18n()
const errors = useErrors()

const tab = ref<'orders' | 'suppliers'>('orders')
const suppliers = ref<Supplier[]>([])
const orders = ref<PurchaseOrder[]>([])
const supplierForm = ref<(Omit<Supplier, 'id'> & { id?: number }) | null>(null)

const orderForm = ref<{
  supplier_id: number
  notes: string
  lines: { product: Product; quantity: number; unit_cost: string }[]
} | null>(null)
const productQuery = ref('')
const productResults = ref<Product[]>([])

const receiving = ref<PurchaseOrder | null>(null)
const receipt = ref<
  {
    line_id: number
    product_name: string
    lot_number: string
    expiry_date: string
    quantity: number
    unit_cost: string
  }[]
>([])

async function load(): Promise<void> {
  await errors.run(async () => {
    ;[suppliers.value, orders.value] = await Promise.all([
      purchasingApi.suppliers(),
      purchasingApi.orders({}),
    ])
  })
}

async function saveSupplier(): Promise<void> {
  const form = supplierForm.value
  if (!form) return
  const { id, ...body } = form
  const ok = await errors.run(() => purchasingApi.saveSupplier(body, id))
  if (ok) {
    supplierForm.value = null
    await load()
  }
}

async function searchProducts(): Promise<void> {
  productResults.value = await catalogApi.search({ q: productQuery.value, limit: 10 })
}

function addLine(product: Product): void {
  orderForm.value?.lines.push({ product, quantity: 1, unit_cost: product.cost })
  productResults.value = []
  productQuery.value = ''
}

async function saveOrder(): Promise<void> {
  const form = orderForm.value
  if (!form) return
  const ok = await errors.run(() =>
    purchasingApi.createOrder({
      supplier_id: form.supplier_id,
      notes: form.notes || null,
      lines: form.lines.map((l) => ({
        product_id: l.product.id,
        quantity: l.quantity,
        unit_cost: l.unit_cost,
      })),
    }),
  )
  if (ok) {
    orderForm.value = null
    await load()
  }
}

function startReceipt(order: PurchaseOrder): void {
  receiving.value = order
  receipt.value = order.lines.map((l) => ({
    line_id: l.id,
    product_name: l.product_name,
    lot_number: '',
    expiry_date: '',
    quantity: l.quantity,
    unit_cost: l.unit_cost,
  }))
}

function splitLine(index: number): void {
  const line = receipt.value[index]
  if (line)
    receipt.value.splice(index + 1, 0, { ...line, lot_number: '', expiry_date: '', quantity: 0 })
}

async function confirmReceipt(): Promise<void> {
  if (!receiving.value) return
  const lines = receipt.value
    .filter((l) => l.quantity > 0)
    .map(({ line_id, lot_number, expiry_date, quantity, unit_cost }) => ({
      line_id,
      lot_number,
      expiry_date,
      quantity,
      unit_cost,
    }))
  const ok = await errors.run(() => purchasingApi.receive(receiving.value!.id, lines))
  if (ok) {
    receiving.value = null
    await load()
  }
}

function orderTotal(order: PurchaseOrder): number {
  return order.lines.reduce((sum, l) => sum + toCents(l.unit_cost) * l.quantity, 0)
}

async function cancelOrder(order: PurchaseOrder): Promise<void> {
  await errors.run(() => purchasingApi.cancel(order.id))
  await load()
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <h1>{{ t('purchasing.title') }}</h1>
    <div class="tabs">
      <button :class="{ active: tab === 'orders' }" @click="tab = 'orders'">
        {{ t('purchasing.orders') }}
      </button>
      <button :class="{ active: tab === 'suppliers' }" @click="tab = 'suppliers'">
        {{ t('purchasing.suppliers') }}
      </button>
    </div>
    <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>

    <template v-if="tab === 'suppliers'">
      <button
        class="primary"
        @click="
          supplierForm = { name: '', tax_id: null, phone: null, email: null, is_active: true }
        "
      >
        {{ t('purchasing.newSupplier') }}
      </button>
      <form v-if="supplierForm" class="card grid-2" @submit.prevent="saveSupplier">
        <label>{{ t('common.name') }}<input v-model="supplierForm.name" required /></label>
        <label>{{ t('purchasing.taxId') }}<input v-model="supplierForm.tax_id" /></label>
        <label>{{ t('purchasing.phone') }}<input v-model="supplierForm.phone" /></label>
        <label>{{ t('purchasing.email') }}<input v-model="supplierForm.email" /></label>
        <label class="check"
          ><input v-model="supplierForm.is_active" type="checkbox" />{{ t('common.active') }}</label
        >
        <div class="row">
          <button class="primary" type="submit">{{ t('common.save') }}</button>
          <button type="button" @click="supplierForm = null">{{ t('common.cancel') }}</button>
        </div>
      </form>
      <div class="card table-wrap">
        <table>
          <tbody>
            <tr v-for="s in suppliers" :key="s.id">
              <td>{{ s.name }}</td>
              <td>{{ s.tax_id }}</td>
              <td>{{ s.phone }}</td>
              <td>{{ s.email }}</td>
              <td>
                <button class="link" @click="supplierForm = { ...s }">
                  {{ t('common.edit') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else>
      <button
        class="primary"
        :disabled="!suppliers.length"
        @click="orderForm = { supplier_id: suppliers[0]!.id, notes: '', lines: [] }"
      >
        {{ t('purchasing.newOrder') }}
      </button>

      <form v-if="orderForm" class="card stack" @submit.prevent="saveOrder">
        <label>
          {{ t('purchasing.supplier') }}
          <select v-model.number="orderForm.supplier_id">
            <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <div v-for="(line, i) in orderForm.lines" :key="i" class="row">
          <span class="grow">{{ line.product.name }}</span>
          <label
            >{{ t('common.quantity')
            }}<input v-model.number="line.quantity" type="number" min="1" class="qty"
          /></label>
          <label
            >{{ t('common.cost') }}<input v-model="line.unit_cost" inputmode="decimal" class="qty"
          /></label>
          <button type="button" class="link danger" @click="orderForm.lines.splice(i, 1)">✕</button>
        </div>
        <div class="row">
          <input
            v-model="productQuery"
            class="grow"
            :placeholder="t('common.search')"
            @keydown.enter.prevent="searchProducts"
          />
          <button type="button" @click="searchProducts">{{ t('common.search') }}</button>
        </div>
        <ul class="list">
          <li v-for="p in productResults" :key="p.id">
            <button type="button" class="link" @click="addLine(p)">{{ p.name }}</button>
          </li>
        </ul>
        <label>{{ t('common.notes') }}<input v-model="orderForm.notes" /></label>
        <div class="row">
          <button class="primary" type="submit" :disabled="!orderForm.lines.length">
            {{ t('common.save') }}
          </button>
          <button type="button" @click="orderForm = null">{{ t('common.cancel') }}</button>
        </div>
      </form>

      <form v-if="receiving" class="card stack" @submit.prevent="confirmReceipt">
        <h2>{{ t('purchasing.receiveOrder') }} #{{ receiving.id }}</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('inventory.product') }}</th>
                <th>{{ t('inventory.lotNumber') }}</th>
                <th>{{ t('inventory.expiry') }}</th>
                <th class="num">{{ t('common.quantity') }}</th>
                <th class="num">{{ t('inventory.unitCost') }}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="(line, i) in receipt" :key="i">
                <td>{{ line.product_name }}</td>
                <td><input v-model="line.lot_number" :required="line.quantity > 0" /></td>
                <td>
                  <input v-model="line.expiry_date" type="date" :required="line.quantity > 0" />
                </td>
                <td class="num">
                  <input v-model.number="line.quantity" type="number" min="0" class="qty" />
                </td>
                <td class="num">
                  <input v-model="line.unit_cost" inputmode="decimal" class="qty" />
                </td>
                <td>
                  <button type="button" class="link" @click="splitLine(i)">
                    + {{ t('inventory.lotNumber') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="row">
          <button class="primary" type="submit">{{ t('purchasing.receive') }}</button>
          <button type="button" @click="receiving = null">{{ t('common.cancel') }}</button>
        </div>
      </form>

      <div class="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{{ t('purchasing.supplier') }}</th>
              <th>{{ t('common.date') }}</th>
              <th>{{ t('common.status') }}</th>
              <th class="num">{{ t('common.total') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in orders" :key="o.id">
              <td>{{ o.id }}</td>
              <td>{{ o.supplier.name }}</td>
              <td>{{ new Date(o.created_at).toLocaleDateString() }}</td>
              <td>{{ t(`purchasing.statuses.${o.status}`) }}</td>
              <td class="num">{{ formatMoney(orderTotal(o)) }}</td>
              <td>
                <template v-if="o.status === 'draft'">
                  <button class="link" @click="startReceipt(o)">
                    {{ t('purchasing.receive') }}
                  </button>
                  <button class="link danger" @click="cancelOrder(o)">
                    {{ t('common.cancel') }}
                  </button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.qty {
  width: 6rem;
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
}
</style>
