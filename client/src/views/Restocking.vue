<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetTitle') }}</h3>
        </div>
        <div class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        <input
          type="range"
          class="budget-slider"
          v-model.number="budget"
          :min="0"
          :max="budgetMax"
          :step="BUDGET_STEP"
          :style="{ '--fill': fillPercent + '%' }"
        >
        <div class="budget-scale">
          <span>{{ formatCurrency(0, currentCurrency) }}</span>
          <span>{{ formatCurrency(budgetMax, currentCurrency) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budgetLabel') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.allocated') }}</div>
          <div class="stat-value">{{ formatCurrency(allocated, currentCurrency) }}</div>
        </div>
        <div class="stat-card" :class="overBudget ? 'danger' : 'warning'">
          <div class="stat-label">{{ overBudget ? t('restocking.overBudget') : t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(remaining, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ selectedItems.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            {{ t('restocking.recommendations') }}
            ({{ selectedItems.length }}/{{ recommendations.length }})
          </h3>
          <button class="reset-btn" @click="resetSelection">{{ t('restocking.resetSelection') }}</button>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th class="col-select"><span class="sr-only">{{ t('restocking.table.select') }}</span></th>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th class="col-item">{{ t('restocking.table.itemName') }}</th>
                <th class="col-warehouse">{{ t('restocking.table.warehouse') }}</th>
                <th class="col-trend">{{ t('restocking.table.trend') }}</th>
                <th class="col-forecast">{{ t('restocking.table.forecast') }}</th>
                <th class="col-stock">{{ t('restocking.table.inStock') }}</th>
                <th class="col-qty">{{ t('restocking.table.restockQty') }}</th>
                <th class="col-unit-cost">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-line-cost">{{ t('restocking.table.lineCost') }}</th>
                <th class="col-lead">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in recommendations" :key="r.item_sku" :class="{ 'row-selected': isSelected(r.item_sku) }">
                <td class="col-select">
                  <input
                    type="checkbox"
                    :checked="isSelected(r.item_sku)"
                    @change="toggleItem(r.item_sku)"
                    :aria-label="translateProductName(r.item_name)"
                  >
                </td>
                <td class="col-sku"><strong>{{ r.item_sku }}</strong></td>
                <td class="col-item">{{ translateProductName(r.item_name) }}</td>
                <td class="col-warehouse">{{ translateWarehouse(r.warehouse) }}</td>
                <td class="col-trend">
                  <span :class="['badge', r.trend]">{{ t('trends.' + r.trend) }}</span>
                </td>
                <td class="col-forecast">{{ r.forecasted_demand }}</td>
                <td class="col-stock">{{ r.current_stock }}</td>
                <td class="col-qty">{{ r.recommended_quantity }}</td>
                <td class="col-unit-cost">{{ formatCurrencyWithDecimals(r.unit_cost, currentCurrency, 2) }}</td>
                <td class="col-line-cost"><strong>{{ formatCurrencyWithDecimals(r.line_cost, currentCurrency, 2) }}</strong></td>
                <td class="col-lead">{{ t('restocking.leadTimeDays', { days: r.lead_time_days }) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="9" class="total-label">{{ t('restocking.totalLabel') }}</td>
                <td class="col-line-cost"><strong>{{ formatCurrencyWithDecimals(allocated, currentCurrency, 2) }}</strong></td>
                <td class="col-lead"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div class="submit-bar">
        <button class="place-order-btn" :disabled="!canSubmit" @click="placeOrder">
          {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
        </button>
        <span v-if="submitHint" class="submit-hint">{{ submitHint }}</span>
      </div>

      <div v-if="lastSubmittedOrder" class="success-panel">
        <h3>{{ t('restocking.orderPlaced', { orderNumber: lastSubmittedOrder.order_number }) }}</h3>
        <p>
          {{ t('restocking.orderPlacedDetail', {
            count: lastSubmittedOrder.items.length,
            total: formatCurrency(lastSubmittedOrder.total_value, currentCurrency),
            date: formatDate(lastSubmittedOrder.expected_delivery)
          }) }}
        </p>
        <router-link to="/orders" class="view-link">{{ t('restocking.viewInOrders') }}</router-link>
      </div>

      <div v-if="submitError" class="error">{{ submitError }}</div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName, translateWarehouse } = useI18n()
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const loading = ref(true)
    const error = ref(null)

    const recommendations = ref([])
    const budget = ref(0)
    const budgetReady = ref(false)
    const manualSkus = ref(null) // null = follow auto-selection; a Set = user override
    const BUDGET_STEP = 500

    const submitting = ref(false)
    const submitError = ref(null)
    const lastSubmittedOrder = ref(null)

    const totalRecommendedCost = computed(() =>
      Math.round(recommendations.value.reduce((s, r) => s + r.line_cost, 0) * 100) / 100)

    const budgetMax = computed(() =>
      Math.max(10000, Math.ceil(totalRecommendedCost.value / 5000) * 5000))

    const fillPercent = computed(() =>
      budgetMax.value ? (budget.value / budgetMax.value) * 100 : 0)

    // Greedy fill: skip-and-continue (do NOT break) so cheaper lower-priority
    // items can still absorb the leftover budget
    const autoSelectedSkus = computed(() => {
      const picked = new Set()
      let spent = 0
      for (const r of recommendations.value) {
        if (spent + r.line_cost <= budget.value + 0.005) {
          picked.add(r.item_sku)
          spent += r.line_cost
        }
      }
      return picked
    })

    const selectedSkus = computed(() => manualSkus.value ?? autoSelectedSkus.value)
    const isSelected = (sku) => selectedSkus.value.has(sku)

    const toggleItem = (sku) => {
      const next = new Set(selectedSkus.value)
      next.has(sku) ? next.delete(sku) : next.add(sku)
      manualSkus.value = next // always reassign a fresh Set, never mutate in place
    }
    const resetSelection = () => { manualSkus.value = null }

    // Moving the slider re-drives the automatic selection and discards manual edits
    watch(budget, () => { manualSkus.value = null })

    const selectedItems = computed(() =>
      recommendations.value.filter(r => selectedSkus.value.has(r.item_sku)))

    const allocated = computed(() =>
      Math.round(selectedItems.value.reduce((s, r) => s + r.line_cost, 0) * 100) / 100)

    const remaining = computed(() => Math.round((budget.value - allocated.value) * 100) / 100)
    const overBudget = computed(() => remaining.value < 0)
    const canSubmit = computed(() => selectedItems.value.length > 0 && !overBudget.value && !submitting.value)

    const submitHint = computed(() => {
      if (selectedItems.value.length === 0) return t('restocking.selectAtLeastOne')
      if (overBudget.value) return t('restocking.reduceSelection')
      return ''
    })

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()
        recommendations.value = await api.getRestockRecommendations({
          warehouse: filters.warehouse,
          category: filters.category
        })
        manualSkus.value = null
        if (!budgetReady.value) {
          // First load: start at 40% of max, snapped to the step
          budget.value = Math.round(budgetMax.value * 0.4 / BUDGET_STEP) * BUDGET_STEP
          budgetReady.value = true
        } else {
          budget.value = Math.min(budget.value, budgetMax.value) // clamp, preserve
        }
      } catch (err) {
        error.value = t('restocking.loadFailed') + ': ' + err.message
      } finally {
        loading.value = false
      }
    }

    watch([selectedLocation, selectedCategory], loadRecommendations)

    const placeOrder = async () => {
      if (!canSubmit.value) return
      try {
        submitting.value = true
        submitError.value = null
        const response = await api.createRestockOrder({
          budget: budget.value,
          items: selectedItems.value.map(r => ({ item_sku: r.item_sku, quantity: r.recommended_quantity }))
        })
        lastSubmittedOrder.value = response
        // Clear the selection so clicking again cannot silently duplicate the
        // order. The request finishes in milliseconds, so the submitting flag
        // alone re-enables the button long before the user stops clicking.
        // Moving the slider resets this and restores the recommended set.
        manualSkus.value = new Set()
      } catch (err) {
        submitError.value = t('restocking.submitFailed') + ': ' + (err.response?.data?.detail || err.message)
      } finally {
        submitting.value = false
      }
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return ''
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    onMounted(loadRecommendations)

    return {
      t,
      currentCurrency,
      translateProductName,
      translateWarehouse,
      formatCurrency,
      formatCurrencyWithDecimals,
      formatDate,
      loading,
      error,
      recommendations,
      budget,
      budgetMax,
      fillPercent,
      BUDGET_STEP,
      isSelected,
      toggleItem,
      resetSelection,
      selectedItems,
      allocated,
      remaining,
      overBudget,
      canSubmit,
      submitHint,
      submitting,
      submitError,
      lastSubmittedOrder,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
  margin-bottom: 1rem;
}

.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  border-radius: 999px;
  cursor: pointer;
  outline: none;
  background: linear-gradient(to right,
    #2563eb 0%, #2563eb var(--fill), #e2e8f0 var(--fill), #e2e8f0 100%);
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #ffffff;
  border: 3px solid #2563eb;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.2);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.budget-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.budget-slider:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.18);
}

/* Firefox ignores the element background for the track, so paint both parts */
.budget-slider::-moz-range-track {
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
}

.budget-slider::-moz-range-progress {
  height: 8px;
  border-radius: 999px;
  background: #2563eb;
}

.budget-slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 3px solid #2563eb;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.2);
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  color: #94a3b8;
  font-size: 0.813rem;
}

.reset-btn {
  padding: 0.5rem 1rem;
  background: #ffffff;
  color: #334155;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.reset-btn:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
}

.empty-state {
  text-align: center;
  padding: 2.5rem 1rem;
  color: #64748b;
  font-size: 0.938rem;
}

/* The Select header is for screen readers only: the column is too narrow to
   render the label without it spilling into the SKU column */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Fixed table layout to prevent column shifting. Widths total roughly 1130px so
   all 11 columns fit inside the card at a 1280px viewport without clipping. */
.restock-table {
  table-layout: fixed;
  width: 100%;
}

.col-select {
  width: 44px;
  text-align: center;
}

.col-sku {
  width: 95px;
}

.col-item {
  width: 210px;
}

.col-warehouse {
  width: 120px;
}

.col-trend {
  width: 100px;
}

.col-forecast {
  width: 80px;
  text-align: right;
}

.col-stock {
  width: 80px;
  text-align: right;
}

.col-qty {
  width: 95px;
  text-align: right;
}

.col-unit-cost {
  width: 95px;
  text-align: right;
}

.col-line-cost {
  width: 115px;
  text-align: right;
}

.col-lead {
  width: 95px;
  text-align: right;
}

tbody tr.row-selected {
  background: #eff6ff;
}

tbody tr.row-selected:hover {
  background: #eff6ff;
}

tfoot td {
  border-top: 2px solid #e2e8f0;
  font-weight: 600;
  color: #0f172a;
}

.total-label {
  text-align: right;
}

.submit-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.place-order-btn {
  padding: 0.75rem 1.75rem;
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Explains why Place Order is disabled, so amber rather than error red */
.submit-hint {
  color: #b45309;
  font-size: 0.875rem;
}

.success-panel {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}

.success-panel h3 {
  color: #065f46;
  font-size: 1.125rem;
  margin-bottom: 0.5rem;
}

.success-panel p {
  color: #047857;
  font-size: 0.938rem;
  margin-bottom: 0.75rem;
}

.view-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: none;
}

.view-link:hover {
  text-decoration: underline;
}
</style>
