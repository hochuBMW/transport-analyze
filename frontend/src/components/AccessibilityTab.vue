<script setup>
import { ref, inject, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { MapPin, Play, Trash2, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { API_BASE } from '../apiBase.js'

const props = defineProps(['isOpen'])
const emit = defineEmits(['toggle'])

const API_ISO = `${API_BASE}/isochrone/pedestrian`
const API_GRAPH = `${API_BASE}/graph/pedestrian/status`

const isLoading = inject('isLoading')
const isochroneOrigin = inject('isochroneOrigin')
const isochroneResult = inject('isochroneResult')
const isochronePickMode = inject('isochronePickMode')

const graphReady = ref(false)
const graphMeta = ref(null)
const notifications = ref([])

const intervalStep = ref(5)
const intervalCount = ref(3)
const maxSnapM = ref(80)

const intervalsPreview = computed(() => {
  const out = []
  for (let i = 0; i < intervalCount.value; i++) {
    out.push(intervalStep.value * (i + 1))
  }
  return out
})

const hasOrigin = computed(() => Array.isArray(isochroneOrigin?.value) && isochroneOrigin.value.length === 2)

const addNotification = (message, type = 'info') => {
  const id = Date.now()
  notifications.value.push({ id, message, type })
  setTimeout(() => {
    notifications.value = notifications.value.filter((n) => n.id !== id)
  }, 6000)
}

const loadGraphStatus = async () => {
  try {
    const { data } = await axios.get(API_GRAPH)
    graphReady.value = !!data.ready
    graphMeta.value = data.ready ? data : null
    if (!data.ready) {
      addNotification(data.hint || 'Сначала соберите пеший граф (этап 1)', 'error')
    }
  } catch (e) {
    graphReady.value = false
    addNotification(e.response?.data?.detail || e.message, 'error')
  }
}

onMounted(() => {
  loadGraphStatus()
  if (isochronePickMode) isochronePickMode.value = true
})

onUnmounted(() => {
  if (isochronePickMode) isochronePickMode.value = false
})

const togglePick = () => {
  if (isochronePickMode) isochronePickMode.value = !isochronePickMode.value
}

const clearAll = () => {
  if (isochroneOrigin) isochroneOrigin.value = null
  if (isochroneResult) isochroneResult.value = null
}

const runIsochrone = async () => {
  if (!graphReady.value) {
    addNotification('Граф не готов. Выполните build_pedestrian_graph.', 'error')
    return
  }
  if (!hasOrigin.value) {
    addNotification('Укажите точку на карте (клик при включённом выборе).', 'error')
    return
  }

  isLoading.value = true
  try {
    const { data } = await axios.post(API_ISO, {
      origin: isochroneOrigin.value,
      interval_step_min: intervalStep.value,
      interval_count: intervalCount.value,
      max_snap_m: maxSnapM.value,
    })
    isochroneResult.value = data
    addNotification(
      `Построено зон: ${data.zones?.length || 0}, привязка ${data.snap_distance_m} м`,
      'success',
    )
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    addNotification(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <aside
    :class="[
      'bg-white border-r border-gray-200 flex flex-col transition-all duration-300 z-20 shadow-sm h-full',
      isOpen ? 'w-80' : 'w-0 overflow-hidden',
    ]"
  >
    <div class="p-4 border-b border-gray-100 flex items-center justify-between">
      <h2 class="font-bold text-gray-800">Доступность</h2>
      <button @click="emit('toggle')" class="p-1 hover:bg-gray-100 rounded-lg text-gray-500">
        <ChevronLeft v-if="isOpen" class="w-5 h-5" />
        <ChevronRight v-else class="w-5 h-5" />
      </button>
    </div>

    <div class="p-4 space-y-4 overflow-y-auto flex-1 text-sm">
      <div
        :class="[
          'rounded-lg px-3 py-2 text-xs',
          graphReady ? 'bg-green-50 text-green-800 border border-green-100' : 'bg-amber-50 text-amber-900 border border-amber-100',
        ]"
      >
        <template v-if="graphReady">
          Граф: {{ graphMeta?.node_count?.toLocaleString() }} узлов,
          {{ graphMeta?.edge_count?.toLocaleString() }} рёбер
        </template>
        <template v-else>Граф не собран — см. этап 1</template>
      </div>

      <div class="space-y-2">
        <label class="text-xs font-semibold text-gray-500 uppercase">Точка объекта</label>
        <button
          type="button"
          @click="togglePick"
          :class="[
            'w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border font-medium transition-colors',
            isochronePickMode?.value
              ? 'border-primary-500 bg-primary-50 text-primary-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-50',
          ]"
        >
          <MapPin class="w-4 h-4" />
          {{ isochronePickMode?.value ? 'Кликните на карте…' : 'Выбрать на карте' }}
        </button>
        <p v-if="hasOrigin" class="text-xs text-gray-600 font-mono">
          {{ isochroneOrigin[0].toFixed(5) }}, {{ isochroneOrigin[1].toFixed(5) }}
        </p>
        <p v-else class="text-xs text-gray-400">Точка не выбрана</p>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="text-xs text-gray-500">Шаг, мин</label>
          <input
            v-model.number="intervalStep"
            type="number"
            min="1"
            max="60"
            class="w-full mt-1 border border-gray-200 rounded-lg px-2 py-1.5"
          />
        </div>
        <div>
          <label class="text-xs text-gray-500">Число зон</label>
          <input
            v-model.number="intervalCount"
            type="number"
            min="1"
            max="8"
            class="w-full mt-1 border border-gray-200 rounded-lg px-2 py-1.5"
          />
        </div>
      </div>
      <p class="text-xs text-gray-500">
        Интервалы: <span class="font-semibold">{{ intervalsPreview.join(', ') }}</span> мин
      </p>

      <div>
        <label class="text-xs text-gray-500">Привязка к графу, м</label>
        <input
          v-model.number="maxSnapM"
          type="number"
          min="20"
          max="300"
          class="w-full mt-1 border border-gray-200 rounded-lg px-2 py-1.5"
        />
      </div>

      <button
        type="button"
        @click="runIsochrone"
        :disabled="isLoading || !graphReady"
        class="w-full flex items-center justify-center gap-2 bg-primary-600 text-white py-2.5 rounded-lg font-semibold hover:bg-primary-700 disabled:opacity-50"
      >
        <Play class="w-4 h-4" />
        Построить зоны
      </button>

      <button
        type="button"
        @click="clearAll"
        class="w-full flex items-center justify-center gap-2 border border-gray-200 text-gray-600 py-2 rounded-lg hover:bg-gray-50"
      >
        <Trash2 class="w-4 h-4" />
        Очистить
      </button>

      <div v-if="isochroneResult?.zones?.length" class="border border-gray-100 rounded-lg p-3 space-y-2">
        <h3 class="text-xs font-bold text-gray-500 uppercase">Результат</h3>
        <div
          v-for="z in isochroneResult.zones"
          :key="z.interval_min"
          class="flex justify-between text-xs text-gray-700"
        >
          <span>≤ {{ z.interval_min }} мин</span>
          <span class="text-gray-500">{{ z.reachable_nodes }} узлов</span>
        </div>
        <p class="text-[10px] text-gray-400 pt-1 border-t">
          Привязка: {{ isochroneResult.snap_distance_m }} м
        </p>
      </div>
    </div>

    <div class="p-2 space-y-1">
      <div
        v-for="n in notifications"
        :key="n.id"
        :class="[
          'text-xs px-3 py-2 rounded-lg',
          n.type === 'error' ? 'bg-red-50 text-red-700' : n.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-700',
        ]"
      >
        {{ n.message }}
      </div>
    </div>
  </aside>
</template>
