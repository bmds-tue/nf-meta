<script setup lang="ts">
import { ref, watch } from 'vue'
import { useApiStore, useEditorStore, useGraphStore } from '../store'
import type { RecentConfig } from '../types'
import { baseName, folderOf, shortPath } from '../utils'
// Inlined so the logo takes the text color (it is drawn in currentColor)
import logoSvg from '../assets/nf-meta-octo.svg?raw'

const apiStore = useApiStore()
const editorStore = useEditorStore()
const graphStore = useGraphStore()

const recent = ref<RecentConfig[]>([])
const opening = ref<string>()
const problem = ref<string>()

watch(() => editorStore.startScreenOpen, async (open) => {
  if (!open) return
  problem.value = undefined
  const result = await apiStore.getRecentConfigs()
  recent.value = result.ok ? result.data : []
}, { immediate: true })

// Closing the start screen (✕, Escape, a click outside) leaves the new, empty config
function close() {
  editorStore.closeStartScreen()
}

async function openRecent(config: RecentConfig) {
  opening.value = config.path
  try {
    problem.value = await graphStore.loadConfig(config.path)
    if (!problem.value) close()
  } finally {
    opening.value = undefined
  }
}

async function forget(config: RecentConfig) {
  const result = await apiStore.forgetRecentConfig(config.path)
  if (result.ok) recent.value = recent.value.filter(r => r.path !== config.path)
}
</script>

<template>
  <v-dialog
    :model-value="editorStore.startScreenOpen" width="560"
    @update:model-value="(open: boolean) => !open && close()">
    <v-card class="start-screen pa-2">
      <v-btn icon="mdi-close" variant="text" size="small" class="close-btn" title="Close (start a new config)" @click="close" />
      <v-card-text>
        <div class="d-flex align-center ga-3 mb-1">
          <span class="logo" v-html="logoSvg"></span>
          <span class="text-headline-small">nf-meta</span>
        </div>
        <p class="muted mb-5">Open a metapipeline config or start a new one.</p>

        <div class="d-flex ga-3 mb-6">
          <v-btn color="primary" variant="flat" prepend-icon="mdi-folder-open-outline" @click="editorStore.openLoadDialog()">
            Open config…
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-plus" @click="close">Start new</v-btn>
        </div>

        <template v-if="recent.length">
          <div class="text-label-large muted mb-1">Recent</div>
          <v-list density="compact" class="recent-list" bg-color="transparent">
            <v-list-item
              v-for="config in recent" :key="config.path"
              :disabled="!config.exists || !!opening"
              :title="baseName(config.path)"
              prepend-icon="mdi-file-document-outline"
              rounded
              @click="openRecent(config)">
              <template #subtitle>
                <span :title="config.path">{{ shortPath(folderOf(config.path)) }}</span>
                <span v-if="!config.exists"> · not found</span>
              </template>
              <template #append>
                <v-progress-circular v-if="opening === config.path" indeterminate size="16" width="2" />
                <!-- a disabled item still needs its remove button -->
                <v-btn
                  v-else icon="mdi-close" variant="text" size="x-small" class="forget-btn"
                  title="Remove from this list" @click.stop="forget(config)" />
              </template>
            </v-list-item>
          </v-list>
          <p v-if="problem" class="field-error mt-2">{{ problem }}</p>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.start-screen {
  position: relative;
}
.close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
}
.logo {
  display: inline-flex;
  width: 40px;
  height: 40px;
}
.logo :deep(svg) {
  width: 100%;
  height: 100%;
}
.recent-list {
  padding: 0;
}
.recent-list :deep(.v-list-item-subtitle) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.forget-btn {
  pointer-events: auto;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
</style>
