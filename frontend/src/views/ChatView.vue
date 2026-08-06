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
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider bordered width="300" :native-scrollbar="false">
      <SidePanel />
    </n-layout-sider>
    <n-layout-content>
      <ChatWindow />
    </n-layout-content>
  </n-layout>
</template>
