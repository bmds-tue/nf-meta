<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGraphStore } from '../store'
import InputDetail from './InputDetail.vue'

const graphStore = useGraphStore()
const adding = ref(false)

const inputs = computed(() => [...graphStore.inputs].sort((a, b) => a.name.localeCompare(b.name)))
</script>

<template>
  <div class="d-flex flex-column">
    <div class="d-flex justify-end px-1">
      <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" :disabled="adding" @click="adding = true">Add input</v-btn>
    </div>

    <InputDetail v-if="adding" @closed="adding = false" />

    <InputDetail v-for="input in inputs" :key="input.name" :input="input" />

    <v-card v-if="!inputs.length && !adding" class="mt-2">
      <v-card-text>
        No inputs yet. Add one here and bind it to step params, or write
        <code>${inputs:&lt;name&gt;}</code> as a param's value in a step.
      </v-card-text>
    </v-card>
  </div>
</template>
