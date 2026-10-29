<script setup lang="ts">
import { Handle } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { computed } from 'vue'
import { INPUT_COLOR, useEditorStore } from '../store'
import type { APIInput } from '../types'

const props = defineProps<NodeProps<{ inputs: APIInput[] }>>()

const editorStore = useEditorStore()

const MAX_SHOWN = 6
const names = computed(() => props.data.inputs.map(i => i.name).sort())
const hasProblems = computed(() => props.data.inputs.some(i => i.diagnostics.length))
</script>

<template>
  <div class="inputs-node" title="Run inputs: double click to open the Inputs tab">
    <div class="d-flex align-center ga-2 mb-1">
      <v-icon icon="mdi-import" :color="INPUT_COLOR" size="18" />
      <strong>Inputs</strong>
      <v-icon v-if="hasProblems" icon="mdi-alert" color="warning" size="16" />
    </div>
    <div class="d-flex flex-wrap ga-1">
      <v-chip
        v-for="name in names.slice(0, MAX_SHOWN)" :key="name"
        size="x-small" class="nodrag"
        @mouseenter="editorStore.setHoveredInputName(name)"
        @mouseleave="editorStore.setHoveredInputName(undefined)"
        @click.stop="editorStore.showInputs([name])"
        @dblclick.stop>
        {{ name }}
      </v-chip>
      <v-chip v-if="names.length > MAX_SHOWN" size="x-small" variant="text">+{{ names.length - MAX_SHOWN }}</v-chip>
    </div>
    <Handle class="inputs-node-handle" type="source" :position="sourcePosition" :connectable="false" />
  </div>
</template>

<style scoped>
.inputs-node {
  min-width: 140px;
  max-width: 260px;
  padding: 8px 10px;
  color: rgb(var(--v-theme-onPrimary));
  background: rgb(var(--v-theme-background));
  border: 3px solid #8a8f98;
  border-radius: 8px;
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.35);
}
.inputs-node-handle {
  background: #8a8f98;
  width: 10px;
  height: 10px;
  border-radius: 10px;
}
</style>
