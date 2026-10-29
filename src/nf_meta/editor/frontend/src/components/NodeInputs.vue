<script setup lang="ts">
import { computed } from 'vue'
import { useEditorStore, useGraphStore } from '../store'
import type { APIInput } from '../types'
import { inputsOfStep } from '../utils'

const props = defineProps<{
  nodeId?: string
}>()

const graphStore = useGraphStore()
const editorStore = useEditorStore()

function bindingTitle(input: APIInput) {
  return input.bound_by === 'bind' ? `Bound with bind: in inputs.${input.name}` : `\${inputs:${input.name}}`
}

const filled = computed(() => props.nodeId ? inputsOfStep(graphStore.inputs, props.nodeId) : [])
</script>

<template>
  <template v-if="filled.length">
    <div class="text-caption mt-3 mb-1">Inputs</div>
    <div class="d-flex flex-column ga-1">
      <div
        v-for="{ param, input } in filled" :key="param"
        class="d-flex align-center ga-2 text-body-2 input-row"
        :title="bindingTitle(input)"
        @mouseenter="editorStore.setHoveredInputName(input.name)"
        @mouseleave="editorStore.setHoveredInputName(undefined)"
        @click.stop="editorStore.sideBarTab = 'inputs'">
        <v-icon icon="mdi-import" size="16" class="flex-shrink-0" />
        <code>{{ param }}</code>
        <v-icon icon="mdi-arrow-left" size="14" class="flex-shrink-0" />
        <span class="text-truncate">{{ input.name }}</span>
        <v-icon
          v-if="input.diagnostics.length"
          :icon="input.diagnostics.some(d => d.severity === 'error') ? 'mdi-alert-circle' : 'mdi-alert'"
          :color="input.diagnostics.some(d => d.severity === 'error') ? 'error' : 'warning'"
          size="14" />
      </div>
    </div>
  </template>
</template>

<style scoped>
.input-row {
  min-width: 0;
  cursor: pointer;
}
.input-row:hover span {
  text-decoration: underline;
}
</style>
