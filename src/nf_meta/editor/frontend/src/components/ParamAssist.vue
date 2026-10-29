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
  // The input a param would get (shared if it exists already)
  inputFor: (param: string) => { name: string, shared: boolean }
}>()

const emit = defineEmits<{
  // asInput: fill the param with a run input instead of a value
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

function inputTitle(param: string) {
  const { name, shared } = props.inputFor(param)
  return shared
    ? `Fill '${param}' per run with the existing input '${name}'`
    : `Fill '${param}' per run: new input '${name}'`
}
</script>

<template>
  <div class="param-assist">
    <div v-if="loading" class="text-body-2 muted">
      <v-progress-circular indeterminate size="14" width="2" class="mr-1" /> Loading params…
    </div>
    <div v-else-if="error" class="text-body-2 muted">{{ error }}</div>
    <template v-else-if="schema">
      <div v-if="suggestions.required.length" class="d-flex flex-wrap align-center ga-2 mb-2">
        <v-chip
          v-for="param in suggestions.required" :key="param"
          color="warning" variant="tonal" class="param-pill"
          :title="schema[param]?.description ?? `Add '${param}'`"
          @click="pick(param)">
          <v-icon icon="mdi-asterisk" size="12" start />
          {{ param }}
          <template #append>
            <v-btn
              icon="mdi-import" size="22" variant="flat" class="input-btn ml-2 mr-n1"
              :color="INPUT_COLOR"
              :title="inputTitle(param)"
              @click.stop="pick(param, true)" />
          </template>
        </v-chip>
      </div>
      <div v-else class="text-body-2 text-success mb-2">
        <v-icon icon="mdi-check" size="16" /> All required params are set
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
                icon="mdi-import" size="26" variant="flat" class="input-btn"
                :color="INPUT_COLOR"
                :title="inputTitle(item.value)"
                @click.stop="pick(item.value, true)" />
            </template>
          </v-list-item>
        </template>
      </v-autocomplete>
    </template>
  </div>
</template>

<style scoped>
.param-pill {
  font-weight: 500;
}
.input-btn :deep(.v-icon) {
  color: white;
  font-size: 15px;
}
</style>
