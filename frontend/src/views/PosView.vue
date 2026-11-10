<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import CustomerDialog from '@/components/CustomerDialog.vue'
import ReceiptView from '@/components/ReceiptView.vue'
import { useApproval } from '@/composables/useApproval'
import { useErrors } from '@/composables/useErrors'
import { catalogApi, customersApi, inventoryApi, posApi } from '@/services/api'
import { errorCode } from '@/services/http'
import { missingPaymentDetails, newPayment, useCartStore } from '@/stores/cart'
import type {
  CardType,
  Customer,
  Lot,
  PaymentMethod,
  Product,
  Register,
  Sale,
  Shift,
} from '@/types/api'
import { formatMoney, fromCents } from '@/utils/money'

const { t } = useI18n()
const cart = useCartStore()
const errors = useErrors()
const { withApproval } = useApproval()

const shift = ref<Shift | null>(null)
const registers = ref<Register[]>([])
const openForm = ref({ register_id: 0, opening_cash: '0.00' })
const closeForm = ref({ counted_cash: '', notes: '' })
const showClose = ref(false)
const loading = ref(true)

const scanInput = ref<HTMLInputElement | null>(null)
const scan = ref('')
const results = ref<Product[]>([])
const lots = ref<Record<number, Lot[]>>({})

// Popup asking for the customer's NIT/CUI when the first item is added.
const askCustomer = ref(false)

const completed = ref<Sale | null>(null)
const busy = ref(false)
const methods: PaymentMethod[] = ['cash', 'card', 'transfer']
const cardTypes: CardType[] = ['visa', 'mastercard', 'amex']

const canCharge = computed(
  () =>
    cart.lines.length > 0 &&
    cart.balance === 0 &&
    cart.paymentsComplete &&
    !cart.needsPrescription &&
    !busy.value,
)

async function loadShift(): Promise<void> {
  loading.value = true
  await errors.run(async () => {
    shift.value = await posApi.currentShift()
    if (!shift.value) {
      registers.value = (await posApi.registers()).filter((r) => r.is_active)
      openForm.value.register_id = registers.value[0]?.id ?? 0
    }
  })
  loading.value = false
  focusScan()
}

async function openShift(): Promise<void> {
  await errors.run(async () => {
    shift.value = await posApi.openShift(openForm.value.register_id, openForm.value.opening_cash)
  })
  focusScan()
}

async function closeShift(): Promise<void> {
  if (!shift.value) return
  const ok = await errors.run(async () => {
    const closed = await posApi.closeShift(
      shift.value!.id,
      closeForm.value.counted_cash,
      closeForm.value.notes || null,
    )
    alert(
      `${t('pos.expectedCash')}: ${formatMoney(closed.expected_cash)}\n` +
        `${t('pos.countedCash')}: ${formatMoney(closed.counted_cash)}\n` +
        `${t('pos.difference')}: ${formatMoney(closed.difference)}`,
    )
  })
  if (ok) {
    showClose.value = false
    cart.clear()
    await loadShift()
  }
}

function focusScan(): void {
  nextTick(() => scanInput.value?.focus())
}

async function addProduct(product: Product): Promise<void> {
  cart.add(product)
  results.value = []
  scan.value = ''
  if (!cart.customerAsked && !cart.customer) {
    cart.customerAsked = true
    askCustomer.value = true
  }
  if (!lots.value[product.id]) {
    lots.value[product.id] = await inventoryApi.lots({ product_id: product.id })
  }
  if (cart.lines.length && cart.payments.length === 0) cart.payAllCash()
  else syncCashPayment()
  if (!askCustomer.value) focusScan()
}

/** A barcode scanner types the code and presses Enter. */
async function onScan(): Promise<void> {
  const code = scan.value.trim()
  if (!code) return
  errors.clear()
  try {
    await addProduct(await catalogApi.byBarcode(code))
  } catch (error) {
    if (errorCode(error) !== 'PRODUCT_NOT_FOUND') return errors.show(error)
    results.value = await catalogApi.search({ q: code, limit: 15 })
    if (results.value.length === 1) await addProduct(results.value[0]!)
  }
}

/** Keep a single cash payment in sync with the total while the cart changes. */
function syncCashPayment(): void {
  const [first] = cart.payments
  if (cart.payments.length === 1 && first?.method === 'cash') {
    first.amount = fromCents(cart.totals.total)
  }
}

async function selectCustomer(customer: Customer | null): Promise<void> {
  await errors.run(async () => {
    const rx = customer ? await customersApi.prescriptions(customer.id) : []
    cart.setCustomer(customer, rx)
  })
  focusScan()
}

function addPayment(): void {
  cart.payments.push(newPayment('card', fromCents(Math.max(cart.balance, 0))))
}

async function charge(): Promise<void> {
  if (!shift.value || !canCharge.value) return
  busy.value = true
  const input = cart.toSaleInput(shift.value.register_id)
  const ok = await errors.run(async () => {
    completed.value = await withApproval((token) => posApi.checkout(input, token), errors.describe)
  })
  busy.value = false
  if (ok) {
    cart.clear()
    lots.value = {}
    shift.value = await posApi.currentShift()
  }
}

function printReceipt(): void {
  window.print()
}

function newSale(): void {
  completed.value = null
  cart.clear()
  errors.clear()
  focusScan()
}

function onKey(event: KeyboardEvent): void {
  if (askCustomer.value) return
  if (event.key === 'F2') {
    event.preventDefault()
    focusScan()
  } else if (event.key === 'F9') {
    event.preventDefault()
    charge()
  } else if (event.key === 'Escape' && completed.value) {
    newSale()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  loadShift()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function rxOptions(productId: number) {
  return cart.prescriptions.filter((rx) => rx.items.some((i) => i.product_id === productId))
}
</script>

<template>
  <p v-if="loading" class="muted">{{ t('common.loading') }}</p>

  <!-- No shift: open one first (SAL-9). -->
  <section v-else-if="!shift" class="card stack open-shift">
    <h1>{{ t('pos.noShift') }}</h1>
    <label>
      {{ t('pos.register') }}
      <select v-model.number="openForm.register_id">
        <option v-for="r in registers" :key="r.id" :value="r.id">
          {{ r.code }} — {{ r.name }}
        </option>
      </select>
    </label>
    <label>
      {{ t('pos.openingCash') }}
      <input v-model="openForm.opening_cash" inputmode="decimal" />
    </label>
    <p v-if="errors.message.value" class="error">{{ errors.message.value }}</p>
    <button class="primary" :disabled="!openForm.register_id" @click="openShift">
      {{ t('pos.openShift') }}
    </button>
  </section>

  <!-- Sale completed: show receipt. -->
  <section v-else-if="completed" class="stack done">
    <h1>{{ t('pos.saleDone') }}</h1>
    <ReceiptView :sale="completed" />
    <div class="row">
      <button class="primary" @click="newSale">{{ t('pos.newSale') }}</button>
      <button @click="printReceipt">{{ t('common.print') }}</button>
    </div>
  </section>

  <div v-else class="pos">
    <section class="stack">
      <div class="row shift-bar">
        <span class="badge ok">{{ t('pos.shiftOpen', { register: shift.register_name }) }}</span>
        <span v-if="shift.summary" class="muted">
          {{ t('pos.salesCount') }}: {{ shift.summary.sales_count }} ·
          {{ formatMoney(shift.summary.sales_total) }}
        </span>
        <span class="grow" />
        <button @click="showClose = !showClose">{{ t('pos.closeShift') }}</button>
      </div>

      <div v-if="showClose && shift.summary" class="card stack">
        <h2>{{ t('pos.summary') }}</h2>
        <div class="grid-2">
          <div>{{ t('pos.openingCash') }}: {{ formatMoney(shift.opening_cash) }}</div>
          <div>{{ t('pos.cashSales') }}: {{ formatMoney(shift.summary.cash_sales) }}</div>
          <div>{{ t('pos.voided') }}: {{ formatMoney(shift.summary.voided_cash) }}</div>
          <div>{{ t('pos.refunds') }}: {{ formatMoney(shift.summary.cash_refunds) }}</div>
          <div>
            <strong
              >{{ t('pos.expectedCash') }}: {{ formatMoney(shift.summary.expected_cash) }}</strong
            >
          </div>
        </div>
        <div class="row">
          <label class="grow">
            {{ t('pos.countedCash') }}
            <input v-model="closeForm.counted_cash" inputmode="decimal" required />
          </label>
          <label class="grow">
            {{ t('common.notes') }}
            <input v-model="closeForm.notes" />
          </label>
        </div>
        <button class="primary" :disabled="!closeForm.counted_cash" @click="closeShift">
          {{ t('pos.closeShift') }}
        </button>
      </div>

      <form class="scan" @submit.prevent="onScan">
        <input
          ref="scanInput"
          v-model="scan"
          :placeholder="t('pos.scan')"
          :aria-label="t('pos.scan')"
          autocomplete="off"
        />
      </form>
      <ul v-if="results.length" class="card results">
        <li v-for="p in results" :key="p.id">
          <button class="link" @click="addProduct(p)">
            {{ p.name }} <span class="muted">{{ p.presentation }}</span>
          </button>
          <span class="muted">{{ formatMoney(p.price) }} · {{ t('pos.stock') }} {{ p.stock }}</span>
        </li>
      </ul>

      <div class="card table-wrap">
        <h2>{{ t('pos.cart') }}</h2>
        <p v-if="!cart.lines.length" class="muted">{{ t('pos.emptyCart') }}</p>
        <table v-else>
          <thead>
            <tr>
              <th>{{ t('common.name') }}</th>
              <th class="num">{{ t('common.quantity') }}</th>
              <th class="num">{{ t('common.price') }}</th>
              <th class="num">{{ t('pos.discount') }}</th>
              <th>{{ t('pos.lot') }}</th>
              <th class="num">{{ t('common.total') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in cart.priced" :key="p.line.key">
              <td>
                {{ p.line.product.name }}
                <span v-if="p.line.product.controlled" class="badge danger">{{
                  t('pos.controlled')
                }}</span>
                <span v-else-if="p.line.product.requires_prescription" class="badge warn">{{
                  t('pos.rx')
                }}</span>
                <div v-if="p.line.product.requires_prescription">
                  <select
                    v-model="p.line.prescriptionId"
                    :aria-label="t('pos.prescription')"
                    @change="syncCashPayment"
                  >
                    <option :value="null">{{ t('pos.selectPrescription') }}</option>
                    <option v-for="rx in rxOptions(p.line.product.id)" :key="rx.id" :value="rx.id">
                      #{{ rx.id }} · {{ rx.prescriber_name }} · {{ rx.issued_on }}
                    </option>
                  </select>
                </div>
              </td>
              <td class="num">
                <input
                  v-model.number="p.line.quantity"
                  type="number"
                  min="1"
                  class="qty"
                  @input="syncCashPayment"
                />
              </td>
              <td class="num">{{ formatMoney(p.line.product.price) }}</td>
              <td class="num">
                <input
                  v-model="p.line.discountPercent"
                  inputmode="decimal"
                  class="qty"
                  @input="syncCashPayment"
                />
              </td>
              <td>
                <select v-model="p.line.lotId" :aria-label="t('pos.lot')">
                  <option :value="null">{{ t('pos.fefo') }}</option>
                  <option
                    v-for="lot in lots[p.line.product.id] ?? []"
                    :key="lot.id"
                    :value="lot.id"
                  >
                    {{ lot.lot_number }} · {{ lot.expiry_date }} ({{ lot.quantity }})
                  </option>
                </select>
              </td>
              <td class="num">{{ formatMoney(p.total) }}</td>
              <td>
                <button
                  class="link danger"
                  @click="
                    () => {
                      cart.remove(p.line.key)
                      syncCashPayment()
                    }
                  "
                >
                  ✕
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <aside class="stack">
      <div class="card stack">
        <h2>{{ t('pos.customer') }}</h2>
        <div class="row">
          <span class="grow">
            {{ cart.customer?.full_name ?? t('pos.noCustomer') }}
            <span class="muted">
              {{ t('customers.documentId') }}: {{ cart.customer?.document_id ?? 'CF' }}
            </span>
          </span>
          <button class="link" @click="askCustomer = true">{{ t('pos.changeCustomer') }}</button>
        </div>
      </div>

      <div class="card stack totals">
        <div class="split">
          <span>{{ t('pos.subtotal') }}</span
          ><span>{{ formatMoney(cart.totals.subtotal) }}</span>
        </div>
        <div class="split">
          <span>{{ t('pos.tax') }}</span
          ><span>{{ formatMoney(cart.totals.tax) }}</span>
        </div>
        <div class="split">
          <span>{{ t('pos.discountTotal') }}</span
          ><span>{{ formatMoney(cart.totals.discount) }}</span>
        </div>
        <div class="split grand">
          <span>{{ t('common.total') }}</span
          ><span>{{ formatMoney(cart.totals.total) }}</span>
        </div>
      </div>

      <div class="card stack">
        <h2>{{ t('pos.payments') }}</h2>
        <div v-for="(payment, i) in cart.payments" :key="i" class="stack payment">
          <div class="row">
            <select v-model="payment.method" :aria-label="t('pos.payments')">
              <option v-for="m in methods" :key="m" :value="m">{{ t(`pos.methods.${m}`) }}</option>
            </select>
            <input v-model="payment.amount" inputmode="decimal" class="grow" />
            <button class="link danger" @click="cart.payments.splice(i, 1)">✕</button>
          </div>
          <!-- SAL-11 / SAL-12: reference details for card and transfer payments. -->
          <div v-if="payment.method !== 'cash'" class="grid-2 details">
            <label>
              {{ t('pos.reference') }}
              <input v-model="payment.reference" maxlength="80" required />
            </label>
            <template v-if="payment.method === 'card'">
              <label>
                {{ t('pos.cardType') }}
                <select v-model="payment.cardType" required>
                  <option value="" disabled>—</option>
                  <option v-for="c in cardTypes" :key="c" :value="c">
                    {{ t(`pos.cards.${c}`) }}
                  </option>
                </select>
              </label>
              <label>
                {{ t('pos.cardLast4') }}
                <input
                  v-model="payment.cardLast4"
                  inputmode="numeric"
                  maxlength="4"
                  pattern="[0-9]{4}"
                  autocomplete="off"
                  required
                />
              </label>
            </template>
            <label v-else>
              {{ t('pos.bankName') }}
              <input v-model="payment.bankName" maxlength="80" required />
            </label>
            <span v-if="missingPaymentDetails(payment).length" class="error">
              {{ t('pos.paymentDetailsMissing') }}
            </span>
          </div>
        </div>
        <div class="row">
          <button @click="cart.payAllCash()">{{ t('pos.payAllCash') }}</button>
          <button @click="addPayment">{{ t('pos.addPayment') }}</button>
        </div>
        <label v-if="cart.cashDue > 0">
          {{ t('pos.tendered') }}
          <input v-model="cart.cashTendered" inputmode="decimal" />
        </label>
        <div class="split">
          <span>{{ t('pos.change') }}</span
          ><strong>{{ formatMoney(cart.change) }}</strong>
        </div>
        <div v-if="cart.balance !== 0" class="split error">
          <span>{{ t('pos.balance') }}</span
          ><span>{{ formatMoney(cart.balance) }}</span>
        </div>
        <p v-if="errors.message.value" class="error" role="alert">{{ errors.message.value }}</p>
        <button class="primary charge" :disabled="!canCharge" @click="charge">
          {{ t('pos.charge') }}
        </button>
      </div>
    </aside>
  </div>
  <CustomerDialog v-model="askCustomer" @select="selectCustomer" />
</template>

<style scoped>
.pos {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 1rem;
  align-items: start;
}

@media (max-width: 960px) {
  .pos {
    grid-template-columns: minmax(0, 1fr);
  }
}

.scan input {
  width: 100%;
  font-size: 1.15rem;
  padding: 0.7rem 0.8rem;
}

.results {
  list-style: none;
  margin: 0;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.results li {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.qty {
  width: 4.5rem;
  text-align: right;
}

.split {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.grand {
  font-size: 1.5rem;
  font-weight: 700;
}

.charge {
  font-size: 1.1rem;
  padding: 0.7rem;
}

.payment + .payment {
  border-top: 1px solid var(--border);
  padding-top: 0.5rem;
}

.details {
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}

.open-shift,
.done {
  max-width: 420px;
}
</style>
