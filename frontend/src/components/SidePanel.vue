<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NSpace, NTag, NEmpty } from 'naive-ui'
import CompanionPanel from './CompanionPanel.vue'
import MemoryManager from './MemoryManager.vue'
import { useChatStore } from '../stores/chat'
import { formatTaskTime } from '../lib/time'

const chat = useChatStore()

const maskNames: Record<string, string> = {
  daily_companion: '同行者',
  old_bestie: '老闺蜜',
  love_guide: '感情向导',
  work_advisor: '工作参谋',
}

const replyModeNames: Record<string, string> = {
  catch_up: '日常接话',
  vent_with_user: '一起吐槽',
  comfort: '低落陪伴',
  advise: '给出建议',
  work_think: '工作参谋',
  play: '轻松玩梗',
  clarify: '自然澄清',
  close_loop: '温和收束',
}

interface Profile {
  intimacy: number
  interests: Record<string, number>
  updated_at: string | null
}

const profile = ref<Profile>({ intimacy: 0, interests: {}, updated_at: null })

interface RhythmProfile {
  total_turns: number
  active_hours: Array<{ hour: number; count: number }>
  topic_heat: Array<{ mask: string; count: number }>
  continuation_by_mode: Array<{ reply_mode: string; total: number; continued: number; rate: number }>
}

const rhythm = ref<RhythmProfile | null>(null)

const bestMode = computed(() => {
  const modes = rhythm.value?.continuation_by_mode || []
  const candidates = modes.filter((mode) => mode.total >= 2 && mode.rate >= 0.6)
  if (!candidates.length) return null
  return candidates.reduce((best, mode) => (mode.rate > best.rate ? mode : best))
})

async function loadRhythm() {
  try {
    const res = await fetch('/api/observations/rhythm?days=30')
    if (res.ok) rhythm.value = await res.json()
  } catch {
    // 节奏加载失败不影响主界面
  }
}

async function load() {
  const res = await fetch('/api/profile')
  if (res.ok) profile.value = await res.json()

  await chat.loadTasks()
}

async function bump() {
  await fetch('/api/profile/intimacy', { method: 'POST' })
  await load()
}

onMounted(() => {
  load()
  loadRhythm()
})
watch(
  () => chat.messages.length,
  () => {
    load()
    loadRhythm()
  },
)
</script>

<template>
  <div style="padding: 24px; display: flex; flex-direction: column; gap: 20px">
    <h3 style="margin: 0; font-size: 15px">当前面具</h3>
    <n-tag type="warning" size="small" :bordered="false">
      {{ maskNames[chat.currentMask] || '同行者' }}
    </n-tag>

    <h3 style="margin: 0; font-size: 15px">本轮动作</h3>
    <n-tag type="success" size="small" :bordered="false">
      {{ replyModeNames[chat.currentReplyMode] || '日常接话' }}
    </n-tag>

    <h3 style="margin: 0; font-size: 15px">今日心情</h3>
    <n-space vertical size="small">
      <n-tag type="info" size="small" :bordered="false">
        {{ chat.currentEmotion.emotion_label }} · {{ chat.currentEmotion.strategy_label }}
      </n-tag>
      <div style="font-size: 12px; color: #777">
        需要：{{ chat.currentEmotion.user_need_label }} · 强度 {{ chat.currentEmotion.intensity }}/3
      </div>
    </n-space>

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

    <h3 style="margin: 0; font-size: 15px">节奏观察</h3>
    <div style="font-size: 12px; color: #666; line-height: 1.7">
      <div v-if="rhythm && rhythm.total_turns >= 5">
        <div v-if="rhythm.active_hours.length">
          常活跃：{{ rhythm.active_hours.slice(0, 2).map(h => `${String(h.hour).padStart(2, '0')}:00`).join('、') }}
        </div>
        <div v-if="rhythm.topic_heat.length">
          聊得最多：{{ maskNames[rhythm.topic_heat[0].mask] || rhythm.topic_heat[0].mask }}
        </div>
        <div v-if="bestMode">
          我按「{{ replyModeNames[bestMode.reply_mode] || bestMode.reply_mode }}」接你时你更愿意继续聊
        </div>
      </div>
      <div v-else>还在了解你的节奏，多聊聊就会更准</div>
    </div>

    <CompanionPanel :interaction-key="chat.userInteractionSequence" />

    <MemoryManager :refresh-key="chat.userInteractionSequence" />

    <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px">
      <h3 style="margin: 0; font-size: 15px">记忆时间线</h3>
      <n-button size="small" secondary type="primary" @click="chat.newTask">新开任务</n-button>
    </div>
    <n-space vertical size="small">
      <div v-if="!chat.tasks.length">
        <n-empty description="还没有任务" size="small" />
      </div>
      <div
        v-for="task in chat.tasks"
        :key="task.id"
        :style="{
          padding: '8px 10px',
          borderRadius: '8px',
          cursor: 'pointer',
          background: task.id === chat.currentSessionId ? '#fff7e6' : 'transparent',
        }"
        @click="chat.switchTask(task.id)"
      >
        <div style="font-size: 12px; color: #999">
          #{{ task.id }} · {{ formatTaskTime(task.last_message_at) }}
        </div>
        <div style="font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
          {{ task.preview }}
        </div>
      </div>
    </n-space>
  </div>
</template>
