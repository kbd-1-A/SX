<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NSpace, NTag, NEmpty } from 'naive-ui'
import { useChatStore } from '../stores/chat'

const chat = useChatStore()

const maskNames: Record<string, string> = {
  daily_companion: '同行者',
  old_bestie: '老闺蜜',
  love_guide: '感情向导',
  work_advisor: '工作参谋',
}

interface Profile {
  intimacy: number
  interests: Record<string, number>
  updated_at: string | null
}

interface DayItem {
  date: string
  first: string
}

const profile = ref<Profile>({ intimacy: 0, interests: {}, updated_at: null })
const daily = ref<DayItem[]>([])

async function load() {
  const res = await fetch('/api/profile')
  if (res.ok) profile.value = await res.json()

  // 记忆时间线：V1 用消息按天聚合，显示"日期 + 该天第一条"
  const mres = await fetch('/api/messages?limit=200')
  if (mres.ok) {
    const msgs: any[] = await mres.json()
    const byDay = new Map<string, string>()
    for (const m of msgs) {
      const d = m.created_at ? m.created_at.slice(0, 10) : ''
      if (d && !byDay.has(d)) byDay.set(d, m.content)
    }
    daily.value = [...byDay.entries()]
      .slice(0, 7)
      .map(([date, first]) => ({ date, first }))
  }
}

async function bump() {
  await fetch('/api/profile/intimacy', { method: 'POST' })
  await load()
}

onMounted(load)
</script>

<template>
  <div style="padding: 24px; display: flex; flex-direction: column; gap: 20px">
    <h3 style="margin: 0; font-size: 15px">当前面具</h3>
    <n-tag type="warning" size="small" :bordered="false">
      {{ maskNames[chat.currentMask] || '同行者' }}
    </n-tag>

    <h3 style="margin: 0; font-size: 15px">今日心情</h3>
    <n-tag type="info" size="small" :bordered="false">V1 先占位，情绪识别后置</n-tag>

    <h3 style="margin: 0; font-size: 15px">画像速览</h3>
    <n-space vertical size="small">
      <div>亲密度：<b>{{ profile.intimacy }}</b> / 100</div>
      <div>
        话题：
        <template v-if="Object.keys(profile.interests).length">
          <n-tag
            v-for="(w, k) in profile.interests"
            :key="k"
            size="small"
            style="margin-right: 6px"
          >
            {{ k }}
          </n-tag>
        </template>
        <span v-else style="color: #999">还没积累，多聊聊</span>
      </div>
      <n-button size="small" @click="bump">手动 +1 亲密度</n-button>
    </n-space>

    <h3 style="margin: 0; font-size: 15px">记忆时间线</h3>
    <n-space vertical size="small">
      <div v-if="!daily.length">
        <n-empty description="还没有对话记录" size="small" />
      </div>
      <div v-for="d in daily" :key="d.date">
        <div style="font-size: 12px; color: #999">{{ d.date }}</div>
        <div style="font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
          {{ d.first }}
        </div>
      </div>
    </n-space>
  </div>
</template>
