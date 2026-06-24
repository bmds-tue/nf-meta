<template>
  <div class="footer-wrapper">
    <v-expand-transition>
      <div v-if="activityStore.drawerOpen" class="activity-panel">
        <div class="activity-panel-header">
          <v-tabs v-model="activeTab" density="compact" height="36">
            <v-tab value="history" class="text-caption">History</v-tab>
          </v-tabs>
          <div class="drawer-actions">
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

    <v-footer class="app-footer pt-0 pb-0">
      <span class="left">{{ year }} ©</span>

      <span class="center">
        Code and Issues on
        <a :href="github">Github</a>
      </span>

      <span class="right">
        <v-btn
          :title="activityStore.drawerOpen ? 'Hide history' : 'Show history'"
          size="x-small"
          variant="text"
          icon="mdi-history"
          @click="activityStore.toggleDrawer()"
        ></v-btn>
        v{{ version }}
      </span>
    </v-footer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { APP_VERSION } from '../version'
import ActivityLog from './ActivityLog.vue'
import { useActivityStore } from '../store'

const year = new Date().getFullYear()
const version = APP_VERSION
const github = "https://github.com/bmds-tue/nf-meta"

const activeTab = ref('history')
const activityStore = useActivityStore()
</script>

<style scoped>
.footer-wrapper {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.activity-panel {
  max-height: 280px;
  overflow: hidden;
  border-top: 1px solid rgb(var(--v-theme-surfaceVariant));
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex-direction: column;
}

.activity-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 4px;
  border-bottom: 1px solid rgb(var(--v-theme-surfaceVariant));
  flex-shrink: 0;
}

.drawer-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.app-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: rgb(var(--v-theme-onSurface));
  flex-shrink: 0;
  backdrop-filter: blur(6px);
}

.app-footer a {
  color: inherit;
}

.right {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
