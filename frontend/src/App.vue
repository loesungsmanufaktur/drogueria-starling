<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppLayout from '@/components/AppLayout.vue'
import ApprovalDialog from '@/components/ApprovalDialog.vue'

const route = useRoute()
const bare = computed(() => route.meta.public === true)
</script>

<template>
  <RouterView v-if="bare" />
  <AppLayout v-else>
    <RouterView />
  </AppLayout>
  <ApprovalDialog />
</template>
