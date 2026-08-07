<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  NButton,
  NDatePicker,
  NEmpty,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NTag,
} from 'naive-ui'

const props = defineProps<{ refreshKey?: number }>()

type MemoryStatus = 'pending' | 'active' | 'stale' | 'archived'

interface AnchorItem {
  id: number
  kind: string
  content: string
  tags: string[]
  status: MemoryStatus
  expires_at: string | null
  confirmed_at: string | null
}

interface SelfMemory {
  nicknames: string[]
}

const kindNames: Record<string, string> = {
  user_fact: '用户事实',
  preference: '偏好',
  episode: '事件',
  open_loop: '待跟进',
  relationship_note: '关系',
}

const kindOptions = Object.entries(kindNames).map(([value, label]) => ({ value, label }))
const pending = ref<AnchorItem[]>([])
const active = ref<AnchorItem[]>([])
const stale = ref<AnchorItem[]>([])
const nicknames = ref<string[]>([])
const loading = ref(false)
const actionError = ref('')

const showEditor = ref(false)
const editing = ref<AnchorItem | null>(null)
const draftContent = ref('')
const draftKind = ref('user_fact')
const draftTags = ref('')
const draftExpiry = ref<number | null>(null)

async function fetchAnchors(status: MemoryStatus) {
  const response = await fetch(`/api/memory/anchors?status=${status}&limit=30`)
  if (!response.ok) throw new Error('memory_load_failed')
  return (await response.json()) as AnchorItem[]
}

async function fetchSelfMemory() {
  const response = await fetch('/api/memory/self')
  if (!response.ok) throw new Error('self_memory_load_failed')
  return (await response.json()) as SelfMemory
}

async function load() {
  loading.value = true
  actionError.value = ''
  try {
    const [nextPending, nextActive, nextStale, selfMemory] = await Promise.all([
      fetchAnchors('pending'),
      fetchAnchors('active'),
      fetchAnchors('stale'),
      fetchSelfMemory(),
    ])
    pending.value = nextPending
    active.value = nextActive
    stale.value = nextStale
    nicknames.value = selfMemory.nicknames || []
  } catch {
    actionError.value = '记忆列表暂时没加载出来。'
  } finally {
    loading.value = false
  }
}

async function removeNickname(name: string) {
  actionError.value = ''
  try {
    const response = await fetch(`/api/memory/self/nicknames/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
    if (!response.ok) throw new Error('nickname_delete_failed')
    await load()
  } catch {
    actionError.value = '这个称呼暂时没能删除。'
  }
}

async function confirm(anchor: AnchorItem) {
  actionError.value = ''
  try {
    const response = await fetch(`/api/memory/anchors/${anchor.id}/confirm`, { method: 'POST' })
    if (!response.ok) throw new Error('confirm_failed')
    await load()
  } catch {
    actionError.value = '这条记忆暂时没能更新。'
  }
}

async function remove(anchor: AnchorItem) {
  actionError.value = ''
  try {
    const response = await fetch(`/api/memory/anchors/${anchor.id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('delete_failed')
    await load()
  } catch {
    actionError.value = '删除失败，这条记忆暂时还在。'
  }
}

function toDateValue(expiresAt: string | null): number | null {
  if (!expiresAt) return null
  const value = new Date(`${expiresAt.replace(' ', 'T')}Z`).getTime()
  return Number.isFinite(value) ? value : null
}

function openEditor(anchor: AnchorItem) {
  editing.value = anchor
  draftContent.value = anchor.content
  draftKind.value = anchor.kind
  draftTags.value = anchor.tags.join('，')
  draftExpiry.value = toDateValue(anchor.expires_at)
  showEditor.value = true
}

function formatExpiry(value: number | null): string | null {
  if (!value) return null
  const date = new Date(value)
  date.setHours(23, 59, 59, 0)
  return date.toISOString()
}

async function saveEditor() {
  if (!editing.value || !draftContent.value.trim()) return
  actionError.value = ''
  try {
    const response = await fetch(`/api/memory/anchors/${editing.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: draftContent.value.trim(),
        kind: draftKind.value,
        tags: draftTags.value
          .split(/[，,]/)
          .map((tag) => tag.trim())
          .filter(Boolean),
        expires_at: formatExpiry(draftExpiry.value),
        clear_expiry: draftExpiry.value === null,
      }),
    })
    if (!response.ok) throw new Error('update_failed')
    showEditor.value = false
    await load()
  } catch {
    actionError.value = '这条记忆暂时没能保存。'
  }
}

function formatExpiryLabel(anchor: AnchorItem) {
  return anchor.expires_at ? `到期：${anchor.expires_at.slice(0, 10)}` : '长期保留'
}

onMounted(load)
watch(() => props.refreshKey, load)
</script>

<template>
  <section style="display: flex; flex-direction: column; gap: 10px">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px">
      <h3 style="margin: 0; font-size: 15px">记忆管理</h3>
      <n-button size="tiny" :loading="loading" @click="load">刷新</n-button>
    </div>

    <div v-if="actionError" style="font-size: 12px; color: #d03050">
      {{ actionError }}
    </div>

    <div v-if="nicknames.length" style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">称呼记忆</div>
      <div
        v-for="name in nicknames"
        :key="name"
        style="padding: 9px; border: 1px solid #d9e8fb; border-radius: 8px; background: #f7fbff"
      >
        <div style="font-size: 13px; line-height: 1.5">时叙会称呼你为「{{ name }}」</div>
        <div style="margin-top: 7px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px">
          <n-tag size="tiny" type="info">称呼</n-tag>
          <span style="font-size: 11px; color: #999">来自历史对话</span>
          <n-popconfirm @positive-click="removeNickname(name)">
            <template #trigger>
              <n-button size="tiny" type="error" secondary>删除</n-button>
            </template>
            删除后，时叙将不再使用这个称呼。
          </n-popconfirm>
        </div>
      </div>
    </div>

    <div style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">待确认</div>
      <n-empty v-if="!pending.length" description="没有待确认记忆" size="small" />
      <div
        v-for="anchor in pending"
        :key="anchor.id"
        style="padding: 9px; border: 1px solid #f0d9a7; border-radius: 8px; background: #fffaf0"
      >
        <div style="font-size: 13px; line-height: 1.5">{{ anchor.content }}</div>
        <div style="margin-top: 7px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px">
          <n-tag size="tiny" type="warning">{{ kindNames[anchor.kind] || anchor.kind }}</n-tag>
          <span style="font-size: 11px; color: #999">{{ formatExpiryLabel(anchor) }}</span>
          <n-button size="tiny" type="primary" @click="confirm(anchor)">记住</n-button>
          <n-button size="tiny" @click="openEditor(anchor)">编辑</n-button>
          <n-popconfirm @positive-click="remove(anchor)">
            <template #trigger>
              <n-button size="tiny" type="error" secondary>删除</n-button>
            </template>
            删除后，时叙不会再引用这条记忆。
          </n-popconfirm>
        </div>
      </div>
    </div>

    <div style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">已记住</div>
      <n-empty v-if="!active.length" description="还没有已确认记忆" size="small" />
      <div v-for="anchor in active" :key="anchor.id" style="padding: 8px 0; border-bottom: 1px solid #eee">
        <div style="font-size: 13px; line-height: 1.5">{{ anchor.content }}</div>
        <div style="margin-top: 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px">
          <n-tag size="tiny" type="success">{{ kindNames[anchor.kind] || anchor.kind }}</n-tag>
          <n-tag v-for="tag in anchor.tags" :key="tag" size="tiny" :bordered="false">{{ tag }}</n-tag>
          <span style="font-size: 11px; color: #999">{{ formatExpiryLabel(anchor) }}</span>
          <n-button size="tiny" @click="openEditor(anchor)">编辑</n-button>
          <n-popconfirm @positive-click="remove(anchor)">
            <template #trigger>
              <n-button size="tiny" type="error" secondary>删除</n-button>
            </template>
            删除后，时叙不会再引用这条记忆。
          </n-popconfirm>
        </div>
      </div>
    </div>

    <div v-if="stale.length" style="display: flex; flex-direction: column; gap: 8px">
      <div style="font-size: 13px; font-weight: 600">已过期</div>
      <div v-for="anchor in stale" :key="anchor.id" style="padding: 8px 0; border-bottom: 1px solid #eee">
        <div style="font-size: 13px; color: #777; line-height: 1.5">{{ anchor.content }}</div>
        <div style="margin-top: 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px">
          <n-tag size="tiny" type="default">{{ kindNames[anchor.kind] || anchor.kind }}</n-tag>
          <n-button size="tiny" type="primary" secondary @click="confirm(anchor)">重新启用</n-button>
          <n-button size="tiny" @click="openEditor(anchor)">编辑</n-button>
          <n-popconfirm @positive-click="remove(anchor)">
            <template #trigger>
              <n-button size="tiny" type="error" secondary>删除</n-button>
            </template>
            删除后，时叙不会再引用这条记忆。
          </n-popconfirm>
        </div>
      </div>
    </div>
  </section>

  <n-modal v-model:show="showEditor" preset="card" title="编辑记忆" style="width: min(480px, 92vw)">
    <n-space vertical size="large">
      <n-input v-model:value="draftContent" type="textarea" :maxlength="200" show-count />
      <n-select v-model:value="draftKind" :options="kindOptions" />
      <n-input v-model:value="draftTags" placeholder="标签，用逗号分隔" />
      <n-date-picker v-model:value="draftExpiry" type="date" clearable />
      <div style="display: flex; justify-content: flex-end; gap: 8px">
        <n-button @click="showEditor = false">取消</n-button>
        <n-button type="primary" @click="saveEditor">保存</n-button>
      </div>
    </n-space>
  </n-modal>
</template>
