<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'
import { groupWarnings } from '../utils'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const groups = computed(() => groupWarnings(graphStore.warnings))
const root = ref<HTMLElement>()

function isMarked(steps: string[]) {
    return editorStore.warningsStepId !== null && steps.includes(editorStore.warningsStepId)
}

function openStep(stepId: string) {
    const node = graphStore.nodeData.find(n => n.id === stepId)
    if (node) editorStore.showNode(node)
}

async function scrollToMarked() {
    await nextTick()
    root.value?.querySelector('.warning-marked')?.scrollIntoView({ block: 'nearest' })
}

onMounted(scrollToMarked)
watch(() => editorStore.warningsStepId, scrollToMarked)
</script>

<template>
  <div ref="root" class="w-100 overflow-y-auto">
    <v-list density="compact" class="pa-0">
      <v-list-item v-if="!groups.length">
        No warnings about this config
      </v-list-item>
      <template v-for="group in groups" :key="group.key">
        <v-list-item
          v-for="(entry, i) in group.entries"
          :key="entry.message"
          :class="['px-1 py-1', isMarked(entry.steps) && 'warning-marked']"
          :active="isMarked(entry.steps)"
          color="warning">
          <div class="d-flex align-center ga-3 w-100">
            <div class="key-cell text-caption dim">
              <code v-if="i === 0">{{ group.key }}</code>
            </div>
            <span class="text-caption warning-message">{{ entry.message }}</span>
            <span class="ml-auto d-flex ga-1 flex-shrink-0">
              <v-chip
                v-for="step in entry.steps"
                :key="step"
                size="x-small"
                title="Open this step"
                @click.stop="openStep(step)">
                {{ step }}
              </v-chip>
              <span v-if="!entry.steps.length" class="text-caption dim text-no-wrap">whole config</span>
            </span>
          </div>
        </v-list-item>
      </template>
    </v-list>
  </div>
</template>

<style scoped>
.key-cell {
    flex: 0 0 160px;
    overflow-wrap: anywhere;
}

.dim {
    opacity: 0.7;
}

.warning-message {
    white-space: normal;
}
</style>
