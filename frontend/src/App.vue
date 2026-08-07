<script setup lang="ts">
import { NConfigProvider, NMessageProvider, NNotificationProvider, zhCN, dateZhCN } from 'naive-ui'
import ChatView from './views/ChatView.vue'
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-notification-provider>
        <ChatView />
      </n-notification-provider>
    </n-message-provider>
  </n-config-provider>
</template>
