<script setup lang="ts">
import { computed, ref } from 'vue'
import { INPUT_COLOR, REF_COLOR } from '../store'
import type { StepSchema } from '../types'
import { paramSuggestions, type ReferenceTarget } from '../utils'

const props = defineProps<{
  schema?: StepSchema | null
  loading?: boolean
  error?: string
  // Params that already have a value or a bind: input
  setParams: string[]
  // The input a param would get (shared if it exists already)
  inputFor: (param: string) => { name: string, shared: boolean }
  // Params of the direct predecessors, which a param can reference
  references: ReferenceTarget[]
}>()

const emit = defineEmits<{
  // value: '' (to be filled in), ${inputs:<name>} or ${<step>:params:<key>}
  add: [param: string, value: string],
}>()

const suggestions = computed(() => paramSuggestions(props.schema, props.setParams))
const optionalItems = computed(() => suggestions.value.optional.map(param => ({
  title: param,
  value: param,
  subtitle: props.schema?.[param]?.description,
})))
const picked = ref<string | null>(null)
const menuOpen = ref(false)
const canReference = computed(() => props.references.length > 0)

function add(param: string | null, value = '') {
  if (param) emit('add', param, value)
  picked.value = null
  menuOpen.value = false
}

function addInput(param: string) {
  add(param, `\${inputs:${props.inputFor(param).name}}`)
}

function addReference(param: string, stepId: string, key: string) {
  add(param, `\${${stepId}:params:${key}}`)
}

function inputTitle(param: string) {
  const { name, shared } = props.inputFor(param)
  return shared
    ? `Fill '${param}' per run with the existing input '${name}'`
    : `Fill '${param}' per run: new input '${name}'`
}

function referenceTitle(param: string) {
  return canReference.value
    ? `Fill '${param}' with a param of a previous step`
    : `Fill '${param}' with a param of a previous step: connect a step to this one first`
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
          @click="add(param)">
          <v-icon icon="mdi-asterisk" size="12" start />
          {{ param }}
          <template #append>
            <v-menu location="bottom start">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  icon="mdi-transit-connection-variant" size="22" variant="flat" class="pill-btn ml-2"
                  :color="REF_COLOR" :disabled="!canReference" :title="referenceTitle(param)"
                  @click.stop />
              </template>
              <v-list density="compact" class="reference-list">
                <template v-for="target in references" :key="target.stepId">
                  <v-list-subheader>{{ target.stepName }} ({{ target.stepId }})</v-list-subheader>
                  <v-list-item
                    v-for="p in target.params" :key="p.key"
                    :title="p.key" :subtitle="p.value"
                    @click="addReference(param, target.stepId, p.key)" />
                </template>
              </v-list>
            </v-menu>
            <v-btn
              icon="mdi-import" size="22" variant="flat" class="pill-btn ml-1 mr-n1"
              :color="INPUT_COLOR"
              :title="inputTitle(param)"
              @click.stop="addInput(param)" />
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
        @update:model-value="add">
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps" :subtitle="item.subtitle" lines="one">
            <template #append>
              <v-menu location="end">
                <template #activator="{ props: menuProps }">
                  <v-btn
                    v-bind="menuProps"
                    icon="mdi-transit-connection-variant" size="26" variant="flat" class="pill-btn mr-1"
                    :color="REF_COLOR" :disabled="!canReference" :title="referenceTitle(item.value)"
                    @click.stop />
                </template>
                <v-list density="compact" class="reference-list">
                  <template v-for="target in references" :key="target.stepId">
                    <v-list-subheader>{{ target.stepName }} ({{ target.stepId }})</v-list-subheader>
                    <v-list-item
                      v-for="p in target.params" :key="p.key"
                      :title="p.key" :subtitle="p.value"
                      @click="addReference(item.value, target.stepId, p.key)" />
                  </template>
                </v-list>
              </v-menu>
              <v-btn
                icon="mdi-import" size="26" variant="flat" class="pill-btn"
                :color="INPUT_COLOR"
                :title="inputTitle(item.value)"
                @click.stop="addInput(item.value)" />
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
.pill-btn :deep(.v-icon) {
  color: white;
  font-size: 15px;
}
.reference-list {
  max-height: 320px;
  min-width: 240px;
}
</style>
