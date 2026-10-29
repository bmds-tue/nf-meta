<script setup lang="ts">
import { computed, ref } from 'vue'
import { INPUT_COLOR } from '../store'
import type { StepSchema } from '../types'
import { paramSuggestions } from '../utils'

const props = defineProps<{
  schema?: StepSchema | null
  loading?: boolean
  error?: string
  // Params that already have a value or a bind: input
  setParams: string[]
}>()

const emit = defineEmits<{
  // asInput: fill the param with a new run input instead of a value
  add: [param: string, asInput: boolean],
}>()

const suggestions = computed(() => paramSuggestions(props.schema, props.setParams))
const optionalItems = computed(() => suggestions.value.optional.map(param => ({
  title: param,
  value: param,
  subtitle: props.schema?.[param]?.description,
})))
const picked = ref<string | null>(null)
const menuOpen = ref(false)

function pick(param: string | null, asInput = false) {
  if (param) emit('add', param, asInput)
  picked.value = null
  menuOpen.value = false
}
</script>

<template>
  <div class="param-assist mb-2">
    <div v-if="loading" class="text-body-2 text-medium-emphasis">
      <v-progress-circular indeterminate size="14" width="2" class="mr-1" /> Loading params…
    </div>
    <div v-else-if="error" class="text-body-2 text-medium-emphasis">{{ error }}</div>
    <template v-else-if="schema">
      <div v-if="suggestions.required.length" class="d-flex flex-wrap align-center ga-1 mb-2">
        <span class="text-caption mr-1">Required</span>
        <v-chip
          v-for="param in suggestions.required" :key="param"
          size="small" color="warning" variant="tonal"
          :title="schema[param]?.description ?? `Add '${param}'`"
          @click="pick(param)">
          {{ param }}
          <template #append>
            <v-btn
              icon="mdi-import" size="x-small" variant="text" density="comfortable" class="ml-1 mr-n2"
              :color="INPUT_COLOR"
              :title="`Set '${param}' per run: add it as an input`"
              @click.stop="pick(param, true)" />
          </template>
        </v-chip>
      </div>
      <div v-else class="text-caption text-success mb-2">
        <v-icon icon="mdi-check" size="14" /> All required params are set
      </div>

      <v-autocomplete
        v-if="optionalItems.length"
        v-model="picked"
        v-model:menu="menuOpen"
        :items="optionalItems"
        label="Add an optional param"
        color="info" base-color="info"
        prepend-inner-icon="mdi-plus"
        variant="outlined" density="compact" hide-details
        @update:model-value="pick">
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps" :subtitle="item.subtitle" lines="one">
            <template #append>
              <v-btn
                icon="mdi-import" size="x-small" variant="text"
                :color="INPUT_COLOR"
                :title="`Set '${item.value}' per run: add it as an input`"
                @click.stop="pick(item.value, true)" />
            </template>
          </v-list-item>
        </template>
      </v-autocomplete>
    </template>
  </div>
</template>
