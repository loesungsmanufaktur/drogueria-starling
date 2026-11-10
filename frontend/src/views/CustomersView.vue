<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import CustomerForm from '@/components/CustomerForm.vue'
import { useErrors } from '@/composables/useErrors'
import { catalogApi, customersApi } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { Customer, Prescription, Product } from '@/types/api'

const { t } = useI18n()
const auth = useAuthStore()
const errors = useErrors()

const q = ref('')
const results = ref<Customer[]>([])
const selected = ref<Customer | null>(null)
const prescriptions = ref<Prescription[]>([])
// null: closed; 'new': creating; a customer: editing it.
const customerForm = ref<Customer | 'new' | null>(null)

const rxForm = ref<{
  prescriber_name: string
  prescriber_license: string
  issued_on: string
  notes: string
  items: { product: Product; max_quantity: number }[]
} | null>(null)
const rxFile = ref<File | null>(null)
const productQuery = ref('')
const productResults = ref<Product[]>([])

async function search(): Promise<void> {
  if (!q.value.trim()) return
  await errors.run(async () => {
    results.value = await customersApi.search(q.value)
  })
}

async function select(customer: Customer): Promise<void> {
  selected.value = customer
  rxForm.value = null
  prescriptions.value = await customersApi.prescriptions(customer.id)
}

function nullable(value: string | null): string | null {
  return value && value.trim() ? value.trim() : null
}

async function onSaved(customer: Customer): Promise<void> {
  customerForm.value = null
  await select(customer)
}

function startRx(): void {
  rxForm.value = {
    prescriber_name: '',
    prescriber_license: '',
    issued_on: new Date().toISOString().slice(0, 10),
    notes: '',
    items: [],
  }
  rxFile.value = null
}

async function searchProducts(): Promise<void> {
  productResults.value = await catalogApi.search({ q: productQuery.value, limit: 10 })
}

function addRxItem(product: Product): void {
  rxForm.value?.items.push({ product, max_quantity: 1 })
  productResults.value = []
  productQuery.value = ''
}

function onFile(event: Event): void {
  rxFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function saveRx(): Promise<void> {
  const form = rxForm.value
  if (!form || !selected.value || !rxFile.value) return
  const ok = await errors.run(() =>
    customersApi.createPrescription(
      {
        customer_id: selected.value!.id,
        prescriber_name: form.prescriber_name,
        prescriber_license: nullable(form.prescriber_license),
        issued_on: form.issued_on,
        notes: nullable(form.notes),
        items: form.items.map((i) => ({ product_id: i.product.id, max_quantity: i.max_quantity })),
      },
      rxFile.value!,
    ),
  )
  if (ok) await select(selected.value)
}

async function openFile(rx: Prescription): Promise<void> {
  await errors.run(async () => {
    const blob = await customersApi.prescriptionFile(rx.id)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  })
}
</script>

<template>
  <div class="customers">
    <section class="card stack">
      <div class="row">
        <h1 class="grow">{{ t('customers.title') }}</h1>
        <button
          class="primary"
          @click="
            () => {
              selected = null
              customerForm = 'new'
            }
          "
        >
          {{ t('customers.newCustomer') }}
        </button>
      </div>
      <form class="row" @submit.prevent="search">
        <input v-model="q" class="grow" :placeholder="t('pos.findCustomer')" />
        <button type="submit">{{ t('common.search') }}</button>
      </form>
      <ul class="list">
        <li v-for="c in results" :key="c.id">
          <button class="link" @click="select(c)">{{ c.full_name }}</button>
          <span class="muted">{{ c.document_id }}</span>
        </li>
      </ul>
    </section>

    <section class="stack">
      <CustomerForm
        v-if="customerForm"
        :key="customerForm === 'new' ? 'new' : customerForm.id"
        class="card"
        :customer="customerForm === 'new' ? null : customerForm"
        @saved="onSaved"
        @cancel="customerForm = null"
      />

      <div v-if="selected" class="card stack">
        <div class="row">
          <h2 class="grow">{{ selected.full_name }}</h2>
          <button class="link" @click="customerForm = selected">
            {{ t('common.edit') }}
          </button>
        </div>
        <p class="muted">
          {{ t('customers.documentId') }}: {{ selected.document_id }} ·
          {{ selected.phone ?? '—' }} ·
          {{ selected.email ?? '—' }}
        </p>
        <div class="row">
          <h2 class="grow">{{ t('customers.prescriptions') }}</h2>
          <button @click="startRx">{{ t('customers.newPrescription') }}</button>
        </div>

        <form v-if="rxForm" class="stack sub" @submit.prevent="saveRx">
          <div class="grid-2">
            <label
              >{{ t('customers.prescriber') }}<input v-model="rxForm.prescriber_name" required
            /></label>
            <label>{{ t('customers.license') }}<input v-model="rxForm.prescriber_license" /></label>
            <label
              >{{ t('customers.issuedOn') }}<input v-model="rxForm.issued_on" type="date" required
            /></label>
            <label>
              {{ t('customers.file') }}
              <input type="file" accept=".jpg,.jpeg,.png,.pdf" required @change="onFile" />
            </label>
          </div>
          <h3>{{ t('customers.items') }}</h3>
          <div v-for="(item, i) in rxForm.items" :key="item.product.id" class="row">
            <span class="grow">{{ item.product.name }}</span>
            <input
              v-model.number="item.max_quantity"
              type="number"
              min="1"
              class="qty"
              :aria-label="t('customers.maxQty')"
            />
            <button type="button" class="link danger" @click="rxForm.items.splice(i, 1)">✕</button>
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
              <button type="button" class="link" @click="addRxItem(p)">{{ p.name }}</button>
            </li>
          </ul>
          <label>{{ t('common.notes') }}<input v-model="rxForm.notes" /></label>
          <div class="row">
            <button class="primary" type="submit" :disabled="!rxForm.items.length || !rxFile">
              {{ t('common.save') }}
            </button>
            <button type="button" @click="rxForm = null">{{ t('common.cancel') }}</button>
          </div>
        </form>

        <div v-for="rx in prescriptions" :key="rx.id" class="sub stack">
          <div class="row">
            <strong class="grow"
              >#{{ rx.id }} · {{ rx.prescriber_name }} ({{ rx.prescriber_license ?? '—' }})</strong
            >
            <span class="muted">{{ rx.issued_on }}</span>
            <button v-if="auth.isStaff" class="link" @click="openFile(rx)">
              {{ t('customers.openFile') }}
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>{{ t('inventory.product') }}</th>
                <th class="num">{{ t('customers.maxQty') }}</th>
                <th class="num">{{ t('customers.dispensed') }}</th>
                <th class="num">{{ t('customers.remaining') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in rx.items" :key="item.id">
                <td>{{ item.product_name }}</td>
                <td class="num">{{ item.max_quantity }}</td>
                <td class="num">{{ item.dispensed_quantity }}</td>
                <td class="num">{{ item.remaining }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>
    </section>
  </div>
</template>

<style scoped>
.customers {
  display: grid;
  grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

@media (max-width: 860px) {
  .customers {
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
  gap: 0.5rem;
}

.sub {
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
}

.qty {
  width: 5rem;
}
</style>
