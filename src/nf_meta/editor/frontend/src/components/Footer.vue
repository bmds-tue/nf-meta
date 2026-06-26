<template>
  <div class="d-flex flex-column flex-shrink-0">
    <v-expand-transition>
      <div v-if="activityStore.drawerOpen" class="activity-panel d-flex flex-column bg-surface overflow-hidden">
        <div class="activity-panel-header d-flex align-center justify-space-between pr-1 flex-shrink-0">
          <v-tabs v-model="activeTab" density="compact" height="36">
            <v-tab value="history" class="text-caption">History</v-tab>
          </v-tabs>
          <div class="d-flex align-center ga-1">
            <v-btn
              v-if="activeTab === 'history'"
              size="x-small"
              variant="text"
              prepend-icon="mdi-delete-outline"
              @click="activityStore.clear()"
            >Clear history</v-btn>
            <v-btn
              title="Collapse"
              size="x-small"
              variant="text"
              icon="mdi-chevron-down"
              @click="activityStore.drawerOpen = false"
            ></v-btn>
          </div>
        </div>
        <ActivityLog />
      </div>
    </v-expand-transition>

    <v-footer class="app-footer pt-0 pb-0 d-flex align-center justify-space-between text-caption flex-shrink-0">
      <span class="d-flex align-center ga-1">
        <span>v{{ version }}</span>
        <v-btn :href="github" target="_blank" size="x-small" variant="text" icon="mdi-github"></v-btn>
      </span>

      <span>{{ graphStore.filename }}</span>

      <v-btn
        :title="activityStore.drawerOpen ? 'Hide history' : 'Show history'"
        size="x-small"
        variant="text"
        icon="mdi-history"
        @click="activityStore.toggleDrawer()"
      ></v-btn>
    </v-footer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { APP_VERSION } from '../version'
import ActivityLog from './ActivityLog.vue'
import { useActivityStore, useGraphStore } from '../store'

const version = APP_VERSION
const github = "https://github.com/bmds-tue/nf-meta"

const activeTab = ref('history')
const activityStore = useActivityStore()
const graphStore = useGraphStore()
</script>

<style scoped>
.activity-panel {
  max-height: 280px;
  border-top: 1px solid rgb(var(--v-theme-surfaceVariant));
}

.activity-panel-header {
  border-bottom: 1px solid rgb(var(--v-theme-surfaceVariant));
}

.app-footer {
  color: rgb(var(--v-theme-onSurface));
  backdrop-filter: blur(6px);
}

</style>
