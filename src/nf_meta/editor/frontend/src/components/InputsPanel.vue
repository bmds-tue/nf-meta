<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGraphStore } from '../store'
import InputDetail from './InputDetail.vue'

const graphStore = useGraphStore()
const adding = ref(false)

const inputs = computed(() => [...graphStore.inputs].sort((a, b) => a.name.localeCompare(b.name)))

// Inputs that fill params, by how they are written; a bulk move is offered if any is the other way
const bound = computed(() => graphStore.inputs.filter(i => i.bound_by))
const anyInParams = computed(() => bound.value.some(i => i.bound_by === 'reference'))
const anyInSection = computed(() => bound.value.some(i => i.bound_by === 'bind'))
</script>

<template>
  <div class="inputs-panel">
    <div class="pane-actions">
      <v-btn
        size="small" variant="text" prepend-icon="mdi-link-variant" :disabled="!anyInParams"
        title="Declare every input with bind: in the inputs: section"
        @click="graphStore.setInputsStyle(false)">
        All to inputs: section
      </v-btn>
      <v-btn
        size="small" variant="text" prepend-icon="mdi-code-braces" :disabled="!anyInSection"
        title="Write every input as ${inputs:…} in the step params it fills"
        @click="graphStore.setInputsStyle(true)">
        All to step params
      </v-btn>
      <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" :disabled="adding" @click="adding = true">Add input</v-btn>
    </div>

    <InputDetail v-if="adding" @closed="adding = false" />

    <InputDetail v-for="input in inputs" :key="input.name" :input="input" />

    <v-card v-if="!inputs.length && !adding">
      <v-card-text>
        No inputs yet. Add one here and bind it to step params, or write
        <code>${inputs:&lt;name&gt;}</code> as a param's value in a step.
      </v-card-text>
    </v-card>
  </div>
</template>

<style scoped>
.inputs-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pane-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
}
</style>
