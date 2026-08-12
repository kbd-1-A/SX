<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NLayout, NLayoutSider, NLayoutContent } from 'naive-ui'
import { useChatStore } from '../stores/chat'
import ChatWindow from '../components/ChatWindow.vue'
import SidePanel from '../components/SidePanel.vue'
import CompanionView from './CompanionView.vue'

const chat = useChatStore()
onMounted(() => chat.init())

// 聊天模式 / 陪伴模式（粒子球）互切；陪伴模式是同一份 store 状态的另一种渲染
const mode = ref<'chat' | 'companion'>('chat')
</script>

<template>
  <CompanionView v-if="mode === 'companion'" @switch-to-chat="mode = 'chat'" />
  <n-layout v-else has-sider class="chat-view">
    <n-layout-sider bordered width="300" :native-scrollbar="false">
      <SidePanel />
    </n-layout-sider>
    <n-layout-content class="chat-content">
      <ChatWindow />
      <button class="mode-switch" type="button" title="切换到陪伴模式" @click="mode = 'companion'">
        ◉ 陪伴模式
      </button>
    </n-layout-content>
  </n-layout>
</template>

<style scoped>
.chat-view {
  height: 100dvh;
  overflow: hidden;
}

.chat-content {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.mode-switch {
  position: absolute;
  top: 12px;
  right: 14px;
  z-index: 5;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: rgba(255, 255, 255, 0.85);
  color: #333;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
}
.mode-switch:hover {
  background: #fff;
}
</style>
