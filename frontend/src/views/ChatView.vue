<script setup lang="ts">
import { onMounted } from 'vue'
import { NLayout, NLayoutSider, NLayoutContent } from 'naive-ui'
import { useChatStore } from '../stores/chat'
import ChatWindow from '../components/ChatWindow.vue'
import SidePanel from '../components/SidePanel.vue'

const chat = useChatStore()
onMounted(() => chat.init())
</script>

<template>
  <n-layout has-sider class="chat-view">
    <n-layout-sider bordered width="300" :native-scrollbar="false">
      <SidePanel />
    </n-layout-sider>
    <n-layout-content class="chat-content">
      <ChatWindow />
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
}
</style>
