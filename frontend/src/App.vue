<script setup lang="ts">
import { NConfigProvider, NMessageProvider, zhCN, dateZhCN } from 'naive-ui'
import ChatView from './views/ChatView.vue'
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <ChatView />
    </n-message-provider>
  </n-config-provider>
</template>
