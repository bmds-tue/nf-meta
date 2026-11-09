<template>
  <div class="d-flex flex-column flex-shrink-0">
    <v-expand-transition>
      <div
        v-if="activityStore.drawerOpen"
        class="activity-panel d-flex flex-column bg-surface"
        :style="{ height: height + 'px' }">
        <div
          class="resize-handle"
          :class="{ dragging: isDragging }"
          title="Drag to resize"
          @pointerdown="startDrag"></div>
        <div class="activity-panel-header d-flex align-center justify-space-between pr-1 flex-shrink-0">
          <v-tabs v-model="activityStore.panelTab" density="compact" height="36">
            <v-tab value="history" class="text-caption">History</v-tab>
            <v-tab value="warnings" class="text-caption">
              Warnings
              <span v-if="graphStore.warnings.length" class="ml-1 text-warning">{{ graphStore.warnings.length }}</span>
            </v-tab>
          </v-tabs>
          <div class="d-flex align-center ga-1">
            <v-btn
              v-if="activityStore.panelTab === 'history'"
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
        <div class="panel-body d-flex">
          <ActivityLog v-if="activityStore.panelTab === 'history'" />
          <WarningsList v-else />
        </div>
      </div>
    </v-expand-transition>

    <v-footer class="app-footer pt-0 pb-0 d-flex align-center justify-space-between text-caption flex-shrink-0">
      <span class="d-flex align-center ga-1">
        <span>nf-meta v{{ version }}</span>
        <v-btn :href="github" target="_blank" title="nf-meta on GitHub" size="x-small" variant="text" icon="mdi-github"></v-btn>
        <v-btn :href="docs" target="_blank" title="Documentation" size="x-small" variant="text" icon="mdi-book-open-variant"></v-btn>
      </span>

      <span>{{ graphStore.filename }}</span>

      <span class="d-flex align-center ga-1">
        <v-btn
          v-if="graphStore.warnings.length"
          :title="warningsShown ? 'Hide warnings' : 'Show the warnings about this config'"
          size="x-small"
          variant="text"
          color="warning"
          prepend-icon="mdi-alert-outline"
          class="warnings-btn"
          @click="activityStore.togglePanel('warnings')"
        >{{ graphStore.warnings.length }}</v-btn>
        <v-btn
          :title="historyShown ? 'Hide history' : 'Show history'"
          size="x-small"
          variant="text"
          icon="mdi-history"
          @click="activityStore.togglePanel('history')"
        ></v-btn>
      </span>
    </v-footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { APP_VERSION } from '../version'
import { DOCS_URL, GITHUB_URL } from '../links'
import ActivityLog from './ActivityLog.vue'
import WarningsList from './WarningsList.vue'
import { useActivityStore, useEditorStore, useGraphStore } from '../store'

const version = APP_VERSION
const github = GITHUB_URL
const docs = DOCS_URL

const activityStore = useActivityStore()
const editorStore = useEditorStore()
const graphStore = useGraphStore()

const historyShown = computed(() => activityStore.drawerOpen && activityStore.panelTab === 'history')
const warningsShown = computed(() => activityStore.drawerOpen && activityStore.panelTab === 'warnings')

// a step's warnings stay marked while the warnings tab shows
watch(warningsShown, shown => {
  if (!shown) editorStore.warningsStepId = null
})

// The panel's height in pixels, kept per browser
const DEFAULT_HEIGHT = 280
const MIN_HEIGHT = 120
const MAX_SHARE = 0.7
const STORAGE_KEY = 'panel-height'

function clampHeight(h: number): number {
  return Math.max(MIN_HEIGHT, Math.min(window.innerHeight * MAX_SHARE, h))
}

function storedHeight(): number {
  try {
    const h = Number(localStorage.getItem(STORAGE_KEY))
    return h > 0 ? clampHeight(h) : DEFAULT_HEIGHT
  } catch {
    return DEFAULT_HEIGHT
  }
}

const height = ref(storedHeight())
const isDragging = ref(false)
let startY = 0
let startHeight = 0

watch(height, h => {
  try { localStorage.setItem(STORAGE_KEY, String(Math.round(h))) } catch { /* kept for this page only */ }
})

function onMove(e: PointerEvent) {
  height.value = clampHeight(startHeight + startY - e.clientY)
}

function stopDrag() {
  isDragging.value = false
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', stopDrag)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
}

function startDrag(e: PointerEvent) {
  isDragging.value = true
  startY = e.clientY
  startHeight = height.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'row-resize'
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', stopDrag)
}

onBeforeUnmount(stopDrag)
</script>

<style scoped>
.activity-panel {
  position: relative;
  border-top: 1px solid rgb(var(--v-theme-surfaceVariant));
}

.panel-body {
  flex: 1;
  min-height: 0;
  background: rgb(var(--v-theme-drawer));
}

/* the lists keep their own background off, so the drawer color shows */
.panel-body :deep(.v-list) {
  background: transparent;
}

/* the top edge: drag to resize */
.resize-handle {
  position: absolute;
  top: -3px;
  left: 0;
  right: 0;
  height: 6px;
  cursor: row-resize;
  z-index: 2;
  transition: background 0.15s;
}

.resize-handle:hover,
.resize-handle.dragging {
  background: rgba(var(--v-theme-primary), 0.5);
}

.activity-panel-header {
  border-bottom: 1px solid rgb(var(--v-theme-surfaceVariant));
}

.warnings-btn {
  min-width: 0;
  padding: 0 6px;
  font-size: 0.75rem;
}

/* the same size as the history button's icon */
.warnings-btn :deep(.v-icon) {
  font-size: 1rem;
}

.app-footer {
  color: rgb(var(--v-theme-onSurface));
  backdrop-filter: blur(6px);
}

</style>
