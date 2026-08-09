<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NDatePicker,
  NEmpty,
  NInput,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
  useNotification,
} from 'naive-ui'
import { useChatStore } from '../stores/chat'

const props = defineProps<{ interactionKey?: number }>()
const chat = useChatStore()

type Frequency = 'quiet' | 'normal' | 'active'
type AlertKind = 'default' | 'info' | 'success' | 'warning' | 'error'

interface FollowUp {
  id: number
  title: string
  category: string
  due_at: string | null
  importance: number
  status: 'open' | 'done' | 'archived'
}

interface CarePoint {
  id: number
  kind: string
  content: string
  importance: number
  created_at: string
}

const enabled = ref(true)
const frequency = ref<Frequency>('normal')
const followUps = ref<FollowUp[]>([])
const carePoints = ref<CarePoint[]>([])
const visibleAlerts = ref<CarePoint[]>([])
const newFollowUpTitle = ref('')
const newFollowUpDueAt = ref<number | null>(null)
const newFollowUpImportance = ref(2)
const editingFollowUpId = ref<number | null>(null)
const editTitle = ref('')
const editDueAt = ref<number | null>(null)
const editImportance = ref(2)
const loading = ref(false)
const actionError = ref('')
const notificationPermission = ref<'default' | 'granted' | 'denied' | 'unsupported'>('unsupported')
const notification = useNotification()

const frequencyOptions = [
  { label: '安静：只提醒重要事项', value: 'quiet' },
  { label: '正常：早晚关心 + 重要提醒', value: 'normal' },
  { label: '积极：更主动地跟进', value: 'active' },
]

const importanceNames: Record<number, string> = {
  1: '普通',
  2: '重要',
  3: '优先',
}
const importanceOptions = [
  { label: '普通', value: 1 },
  { label: '重要', value: 2 },
  { label: '优先', value: 3 },
]

function toApiDateTime(value: number | null): string | undefined {
  if (value === null) return undefined
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:00`
}

function fromApiDateTime(value: string | null): number | null {
  return value ? new Date(value.replace(' ', 'T')).getTime() : null
}

function syncNotificationPermission() {
  notificationPermission.value =
    typeof window !== 'undefined' && 'Notification' in window
      ? window.Notification.permission
      : 'unsupported'
}

async function enableSystemNotifications() {
  if (!('Notification' in window)) {
    notificationPermission.value = 'unsupported'
    return
  }
  try {
    notificationPermission.value = await window.Notification.requestPermission()
  } catch {
    notificationPermission.value = 'denied'
  }
}

function alertType(point: CarePoint): AlertKind {
  if (point.kind === 'overdue') return 'warning'
  if (point.kind === 'due_now' || point.importance >= 3) return 'error'
  return 'info'
}

function dismissAlert(id: number) {
  visibleAlerts.value = visibleAlerts.value.filter((point) => point.id !== id)
}

function clearVisibleAlerts() {
  visibleAlerts.value = []
  notification.destroyAll()
}

function announce(points: CarePoint[]) {
  chat.receiveProactiveMessages(points)
  for (const point of points) {
    if (visibleAlerts.value.some((existing) => existing.id === point.id)) continue
    visibleAlerts.value.unshift(point)
    notification.create({
      title: '时叙提醒你',
      content: point.content,
      type: alertType(point),
      duration: 8000,
    })
    if (notificationPermission.value === 'granted') {
      try {
        new window.Notification('时叙提醒你', {
          body: point.content,
          tag: `companion-${point.id}`,
        })
      } catch {
        // 浏览器可能在页面失焦或权限变化后拒绝创建系统通知，应用内通知仍保留。
      }
    }
  }
}

async function load(checkForReminders = false) {
  loading.value = true
  actionError.value = ''
  try {
    const response = await fetch(
      checkForReminders ? '/api/companion/check-in' : '/api/companion/overview',
      { method: checkForReminders ? 'POST' : 'GET' },
    )
    if (!response.ok) throw new Error('companion_load_failed')
    const data = await response.json()
    enabled.value = data.settings.enabled !== false
    frequency.value = data.settings.frequency
    followUps.value = data.follow_ups || []
    carePoints.value = data.care_points || []
    if (checkForReminders) announce(data.new_care_points || [])
    if (!enabled.value) clearVisibleAlerts()
  } catch {
    actionError.value = '主动陪伴暂时没有连上，稍后会再试。'
  } finally {
    loading.value = false
  }
}

async function updateFrequency(value: string | number | null) {
  if (value !== 'quiet' && value !== 'normal' && value !== 'active') return
  actionError.value = ''
  try {
    const response = await fetch('/api/companion/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frequency: value }),
    })
    if (!response.ok) throw new Error('frequency_update_failed')
    frequency.value = (await response.json()).frequency
  } catch {
    actionError.value = '陪伴频率暂时没能更新。'
  }
}

async function updateEnabled(value: boolean) {
  actionError.value = ''
  try {
    const response = await fetch('/api/companion/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: value }),
    })
    if (!response.ok) throw new Error('companion_enabled_update_failed')
    enabled.value = (await response.json()).enabled
    if (enabled.value) await load(true)
    else clearVisibleAlerts()
  } catch {
    actionError.value = '主动陪伴开关暂时没能更新。'
  }
}

async function addFollowUp() {
  const title = newFollowUpTitle.value.trim()
  if (!title) return
  actionError.value = ''
  try {
    const payload: Record<string, unknown> = {
      title,
      importance: newFollowUpImportance.value,
    }
    const dueAt = toApiDateTime(newFollowUpDueAt.value)
    if (dueAt) payload.due_at = dueAt
    const response = await fetch('/api/companion/follow-ups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new Error('follow_up_create_failed')
    newFollowUpTitle.value = ''
    newFollowUpDueAt.value = null
    newFollowUpImportance.value = 2
    await load()
  } catch {
    actionError.value = '这件待跟进事项暂时没能记下。'
  }
}

function startEditing(item: FollowUp) {
  editingFollowUpId.value = item.id
  editTitle.value = item.title
  editDueAt.value = fromApiDateTime(item.due_at)
  editImportance.value = item.importance
}

function cancelEditing() {
  editingFollowUpId.value = null
}

async function saveEditing(item: FollowUp) {
  const title = editTitle.value.trim()
  if (!title) return
  actionError.value = ''
  try {
    const payload: Record<string, unknown> = {
      title,
      importance: editImportance.value,
    }
    const dueAt = toApiDateTime(editDueAt.value)
    if (dueAt) payload.due_at = dueAt
    else payload.clear_due_at = true
    const response = await fetch(`/api/companion/follow-ups/${item.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new Error('follow_up_update_failed')
    editingFollowUpId.value = null
    await load()
  } catch {
    actionError.value = '这件事项暂时没能更新。'
  }
}

async function completeFollowUp(item: FollowUp) {
  actionError.value = ''
  try {
    const response = await fetch(`/api/companion/follow-ups/${item.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'done' }),
    })
    if (!response.ok) throw new Error('follow_up_complete_failed')
    await load()
  } catch {
    actionError.value = '这件事项暂时没能标记完成。'
  }
}

function dueLabel(item: FollowUp) {
  return item.due_at ? `时间：${item.due_at.slice(0, 16)}` : '等你方便时再继续'
}

onMounted(() => {
  notification.destroyAll()
  syncNotificationPermission()
  load()
})
watch(
  () => props.interactionKey,
  (value, previous) => {
    if (value && value !== previous) load(true)
  },
)
</script>

<template>
  <section style="display: flex; flex-direction: column; gap: 10px">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px">
      <h3 style="margin: 0; font-size: 15px">时叙在惦记</h3>
      <n-button size="tiny" :loading="loading" @click="() => load()">刷新</n-button>
    </div>

    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px">
      <span style="font-size: 13px">主动陪伴</span>
      <n-switch :value="enabled" size="small" @update:value="updateEnabled" />
    </div>

    <n-select
      :value="frequency"
      size="small"
      :options="frequencyOptions"
      :disabled="!enabled"
      @update:value="updateFrequency"
    />

    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px">
      <span style="font-size: 11px; color: #999">
        {{ notificationPermission === 'granted' ? '系统提醒已开启' : '页面保持打开即可收到提醒' }}
      </span>
      <n-button
        v-if="notificationPermission === 'default'"
        size="tiny"
        secondary
        @click="enableSystemNotifications"
      >
        开启系统提醒
      </n-button>
    </div>

    <n-alert
      v-for="point in visibleAlerts"
      :key="point.id"
      :type="alertType(point)"
      :show-icon="false"
      closable
      style="font-size: 12px"
      @close="dismissAlert(point.id)"
    >
      {{ point.content }}
    </n-alert>

    <div v-if="actionError" style="font-size: 12px; color: #d03050">
      {{ actionError }}
    </div>

    <div style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">待跟进事项</div>
      <div style="display: flex; gap: 6px">
        <n-input
          v-model:value="newFollowUpTitle"
          size="small"
          placeholder="例如：周五前完成项目汇报"
          :maxlength="120"
          @keydown.enter.prevent="addFollowUp"
        />
        <n-button size="small" type="primary" @click="addFollowUp">记下</n-button>
      </div>
      <div style="display: grid; grid-template-columns: minmax(0, 1fr) 80px; gap: 6px">
        <n-date-picker
          v-model:value="newFollowUpDueAt"
          type="datetime"
          size="small"
          clearable
          placeholder="选择提醒时间"
        />
        <n-select
          v-model:value="newFollowUpImportance"
          size="small"
          :options="importanceOptions"
        />
      </div>
      <n-empty v-if="!followUps.length" description="暂时没有需要惦记的事" size="small" />
      <div
        v-for="item in followUps"
        :key="item.id"
        style="padding: 8px 0; border-bottom: 1px solid #eee"
      >
        <template v-if="editingFollowUpId === item.id">
          <div style="display: flex; flex-direction: column; gap: 6px">
            <n-input v-model:value="editTitle" size="small" :maxlength="120" />
            <n-date-picker
              v-model:value="editDueAt"
              type="datetime"
              size="small"
              clearable
              placeholder="选择提醒时间"
            />
            <n-select v-model:value="editImportance" size="small" :options="importanceOptions" />
            <div style="display: flex; justify-content: flex-end; gap: 6px">
              <n-button size="tiny" @click="cancelEditing">取消</n-button>
              <n-button size="tiny" type="primary" @click="saveEditing(item)">保存</n-button>
            </div>
          </div>
        </template>
        <template v-else>
          <div style="font-size: 13px; line-height: 1.5">{{ item.title }}</div>
          <div style="margin-top: 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px">
            <n-tag size="tiny" :type="item.importance >= 3 ? 'error' : item.importance === 2 ? 'warning' : 'default'">
              {{ importanceNames[item.importance] }}
            </n-tag>
            <span style="font-size: 11px; color: #999">{{ dueLabel(item) }}</span>
            <n-button size="tiny" @click="startEditing(item)">编辑</n-button>
            <n-button size="tiny" @click="completeFollowUp(item)">完成</n-button>
          </div>
        </template>
      </div>
    </div>

    <div style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">最近关心点</div>
      <n-empty v-if="!carePoints.length" description="时叙会在合适的时候来关心你" size="small" />
      <n-space v-else vertical size="small">
        <div v-for="point in carePoints.slice(0, 4)" :key="point.id" style="font-size: 12px; line-height: 1.5; color: #666">
          {{ point.content }}
        </div>
      </n-space>
    </div>
  </section>
</template>
