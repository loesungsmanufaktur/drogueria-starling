<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useErrors } from '@/composables/useErrors'
import { catalogApi } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { Named, Product, ProductInput } from '@/types/api'
import { formatMoney } from '@/utils/money'

const { t } = useI18n()
const auth = useAuthStore()
const errors = useErrors()

const products = ref<Product[]>([])
const categories = ref<Named[]>([])
const ingredients = ref<Named[]>([])
const q = ref('')
const showInactive = ref(false)

const editingId = ref<number | null>(null)
const form = ref<ProductInput | null>(null)
const newCategory = ref('')
const newIngredient = ref('')

function blank(): ProductInput {
  return {
    name: '',
    description: null,
    presentation: null,
    category_id: null,
    barcode: null,
    sanitary_registration: null,
    requires_prescription: false,
    controlled: false,
    tax_rate: '12.00',
    price: '',
    cost: '0.00',
    min_stock: 0,
    ingredients: [],
  }
}

async function load(): Promise<void> {
  await errors.run(async () => {
    products.value = await catalogApi.search({
      q: q.value || undefined,
      active: showInactive.value ? null : true,
      limit: 200,
    })
  })
}

async function loadLookups(): Promise<void> {
  ;[categories.value, ingredients.value] = await Promise.all([
    catalogApi.categories(),
    catalogApi.ingredients(),
  ])
}

function edit(product: Product | null): void {
  errors.clear()
  editingId.value = product?.id ?? null
  form.value = product
    ? {
        ...product,
        ingredients: product.ingredients.map((i) => ({
          ingredient_id: i.ingredient_id,
          strength: i.strength,
        })),
      }
    : blank()
}

function emptyToNull(value: string | null): string | null {
  return value && value.trim() ? value.trim() : null
}

async function save(): Promise<void> {
  if (!form.value) return
  const body: ProductInput = {
    ...form.value,
    barcode: emptyToNull(form.value.barcode),
    presentation: emptyToNull(form.value.presentation),
    sanitary_registration: emptyToNull(form.value.sanitary_registration),
    description: emptyToNull(form.value.description),
  }
  const ok = await errors.run(async () => {
    if (editingId.value) await catalogApi.update(editingId.value, body)
    else await catalogApi.create(body)
  })
  if (ok) {
    form.value = null
    await load()
  }
}

async function toggleActive(product: Product): Promise<void> {
  await errors.run(() => catalogApi.update(product.id, { is_active: !product.is_active }))
  await load()
}

async function addCategory(): Promise<void> {
  if (!newCategory.value) return
  await errors.run(async () => {
    const created = await catalogApi.createCategory(newCategory.value)
    await loadLookups()
    if (form.value) form.value.category_id = created.id
    newCategory.value = ''
  })
}

async function addIngredient(): Promise<void> {
  if (!newIngredient.value) return
  await errors.run(async () => {
    const created = await catalogApi.createIngredient(newIngredient.value)
    await loadLookups()
    form.value?.ingredients.push({ ingredient_id: created.id, strength: null })
    newIngredient.value = ''
  })
}

onMounted(() => Promise.all([load(), loadLookups()]))
</script>

<template>
  <div class="stack">
    <div class="row">
      <h1 class="grow">{{ t('catalog.title') }}</h1>
      <button v-if="auth.isStaff" class="primary" @click="edit(null)">
        {{ t('catalog.newProduct') }}
      </button>
    </div>

    <form v-if="form" class="card stack" @submit.prevent="save">
      <h2>{{ editingId ? t('catalog.editProduct') : t('catalog.newProduct') }}</h2>
      <div class="grid-2">
        <label>{{ t('common.name') }}<input v-model="form.name" required /></label>
        <label>{{ t('catalog.presentation') }}<input v-model="form.presentation" /></label>
        <label>{{ t('catalog.barcode') }}<input v-model="form.barcode" /></label>
        <label
          >{{ t('catalog.sanitaryRegistration') }}<input v-model="form.sanitary_registration"
        /></label>
        <label>
          {{ t('catalog.category') }}
          <select v-model="form.category_id">
            <option :value="null">—</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </label>
        <label>
          {{ t('catalog.newCategory') }}
          <span class="row">
            <input v-model="newCategory" class="grow" />
            <button type="button" @click="addCategory">{{ t('common.add') }}</button>
          </span>
        </label>
        <label
          >{{ t('common.price') }}<input v-model="form.price" inputmode="decimal" required
        /></label>
        <label
          >{{ t('common.cost') }}<input v-model="form.cost" inputmode="decimal" required
        /></label>
        <label
          >{{ t('catalog.taxRate') }}<input v-model="form.tax_rate" inputmode="decimal" required
        /></label>
        <label
          >{{ t('catalog.minStock') }}<input v-model.number="form.min_stock" type="number" min="0"
        /></label>
      </div>
      <div class="row">
        <label class="check"
          ><input v-model="form.requires_prescription" type="checkbox" />{{
            t('catalog.requiresPrescription')
          }}</label
        >
        <label class="check"
          ><input v-model="form.controlled" type="checkbox" />{{ t('catalog.controlled') }}</label
        >
      </div>
      <fieldset class="stack">
        <legend>{{ t('catalog.ingredients') }}</legend>
        <div v-for="(item, i) in form.ingredients" :key="i" class="row">
          <select v-model="item.ingredient_id" class="grow" :aria-label="t('catalog.ingredients')">
            <option v-for="ing in ingredients" :key="ing.id" :value="ing.id">{{ ing.name }}</option>
          </select>
          <input v-model="item.strength" :placeholder="t('catalog.strength')" />
          <button type="button" class="link danger" @click="form.ingredients.splice(i, 1)">
            ✕
          </button>
        </div>
        <div class="row">
          <button
            type="button"
            :disabled="!ingredients.length"
            @click="form.ingredients.push({ ingredient_id: ingredients[0]!.id, strength: null })"
          >
            {{ t('common.add') }}
          </button>
          <input v-model="newIngredient" :placeholder="t('catalog.newIngredient')" />
          <button type="button" @click="addIngredient">{{ t('catalog.newIngredient') }}</button>
        </div>
      </fieldset>
      <label>{{ t('catalog.description') }}<textarea v-model="form.description" rows="2" /></label>
      <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>
      <div class="row">
        <button class="primary" type="submit">{{ t('common.save') }}</button>
        <button type="button" @click="form = null">{{ t('common.cancel') }}</button>
      </div>
    </form>

    <div class="card stack">
      <form class="row" @submit.prevent="load">
        <input v-model="q" class="grow" :placeholder="t('pos.scan')" />
        <label class="check"
          ><input v-model="showInactive" type="checkbox" @change="load" />{{
            t('catalog.showInactive')
          }}</label
        >
        <button type="submit">{{ t('common.search') }}</button>
      </form>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('common.name') }}</th>
              <th>{{ t('catalog.ingredients') }}</th>
              <th>{{ t('catalog.barcode') }}</th>
              <th class="num">{{ t('common.price') }}</th>
              <th class="num">{{ t('pos.stock') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in products" :key="p.id" :class="{ muted: !p.is_active }">
              <td>
                {{ p.name }} <span class="muted">{{ p.presentation }}</span>
                <span v-if="p.controlled" class="badge danger">{{ t('pos.controlled') }}</span>
                <span v-else-if="p.requires_prescription" class="badge warn">{{
                  t('pos.rx')
                }}</span>
              </td>
              <td>{{ p.ingredients.map((i) => `${i.name} ${i.strength ?? ''}`).join(', ') }}</td>
              <td>{{ p.barcode }}</td>
              <td class="num">{{ formatMoney(p.price) }}</td>
              <td class="num">
                <span :class="{ 'badge warn': p.stock < p.min_stock }">{{ p.stock }}</span>
              </td>
              <td>
                <template v-if="auth.isStaff">
                  <button class="link" @click="edit(p)">{{ t('common.edit') }}</button>
                  <button class="link" @click="toggleActive(p)">
                    {{ p.is_active ? t('catalog.deactivate') : t('catalog.activate') }}
                  </button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!products.length" class="muted">{{ t('common.empty') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
fieldset {
  border: 1px solid var(--border);
  border-radius: 6px;
}
</style>
