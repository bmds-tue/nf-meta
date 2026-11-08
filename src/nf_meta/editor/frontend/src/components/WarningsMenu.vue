<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'
import { groupWarnings } from '../utils'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const groups = computed(() => groupWarnings(graphStore.warnings))
const list = ref<{ $el: HTMLElement }>()

function isMarked(steps: string[]) {
    return editorStore.warningsStepId !== null && steps.includes(editorStore.warningsStepId)
}

function openStep(stepId: string) {
    const node = graphStore.nodeData.find(n => n.id === stepId)
    if (node) editorStore.showNode(node)
}

watch(() => editorStore.warningsOpen, async open => {
    if (!open) {
        editorStore.warningsStepId = null
        return
    }
    await nextTick()
    list.value?.$el.querySelector('.warning-marked')?.scrollIntoView({ block: 'nearest' })
})
</script>

<template>
  <v-menu
    v-if="graphStore.warnings.length"
    v-model="editorStore.warningsOpen"
    location="bottom start"
    max-width="560"
    max-height="70vh">
    <template #activator="{ props: menuProps }">
      <v-btn v-bind="menuProps" title="Warnings about this config" icon variant="text" color="warning">
        <v-badge :content="graphStore.warnings.length" color="warning" floating>
          <v-icon icon="mdi-alert-outline" />
        </v-badge>
      </v-btn>
    </template>
    <v-list ref="list" density="compact">
      <template v-for="group in groups" :key="group.key">
        <v-list-subheader>{{ group.key }}</v-list-subheader>
        <v-list-item
          v-for="entry in group.entries"
          :key="entry.message"
          :class="isMarked(entry.steps) && 'warning-marked'"
          :active="isMarked(entry.steps)"
          color="warning">
          <div class="warning-message">{{ entry.message }}</div>
          <div class="mt-1">
            <v-chip
              v-for="step in entry.steps"
              :key="step"
              size="x-small"
              class="mr-1"
              title="Open this step"
              @click.stop="openStep(step)">
              {{ step }}
            </v-chip>
            <span v-if="!entry.steps.length" class="text-caption text-medium-emphasis">whole config</span>
          </div>
        </v-list-item>
      </template>
    </v-list>
  </v-menu>
</template>

<style scoped>
.warning-message {
    white-space: normal;
    font-size: 0.875rem;
}
</style>
