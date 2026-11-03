<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useApiStore, useGraphStore } from '../store'
import type { StepSchema } from '../types'

// The step params an input fills (`<step id>.<param>`), and a menu to add one: pick a step,
// then one of its params (with description, type and default)
const props = defineProps<{
  modelValue: string[]
  errorMessages?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [bindings: string[]],
}>()

const apiStore = useApiStore()
const graphStore = useGraphStore()

const open = ref(false)
const stepId = ref<string>()
const filter = ref('')
const schema = ref<StepSchema>({})
const loading = ref(false)

watch(open, (isOpen) => {
  if (isOpen) return
  stepId.value = undefined
  filter.value = ''
})

const steps = computed(() => graphStore.nodeData.filter(n => n.id))
const step = computed(() => steps.value.find(n => n.id === stepId.value))
const stepNames = computed(() => Object.fromEntries(steps.value.map(n => [n.id, n.name ?? n.id])))

function shortName(name?: string) {
  return name?.split('/').pop() ?? ''
}

async function chooseStep(id: string) {
  stepId.value = id
  loading.value = true
  try {
    const result = await apiStore.getNodeSchema(id)
    schema.value = result.ok ? result.data : {}
  } finally {
    loading.value = false
  }
}

// The step's params: from its schema (not hidden) and those it sets; required ones first
const params = computed(() => {
  const own = Object.keys(step.value?.params ?? {})
  const names = new Set([...Object.keys(schema.value).filter(p => !schema.value[p]?.hidden), ...own])
  const text = filter.value.trim().toLowerCase()
  return [...names]
    .filter(name => !text || name.toLowerCase().includes(text))
    .map(name => ({ name, spec: schema.value[name] ?? {}, bound: props.modelValue.includes(`${stepId.value}.${name}`) }))
    .sort((a, b) => Number(!!b.spec.required) - Number(!!a.spec.required) || a.name.localeCompare(b.name))
})

function details(spec: StepSchema[string]) {
  const type = spec.format ?? spec.type
  const fallback = spec.default !== undefined && spec.default !== null && spec.default !== '' ? `default ${spec.default}` : ''
  return [type, fallback].filter(Boolean).join(' · ')
}

function add(param: string) {
  emit('update:modelValue', [...props.modelValue, `${stepId.value}.${param}`])
  open.value = false
}

function remove(binding: string) {
  emit('update:modelValue', props.modelValue.filter(b => b !== binding))
}

function label(binding: string) {
  const dot = binding.indexOf('.')
  const id = binding.slice(0, dot)
  return { id, step: shortName(stepNames.value[id]) || id, param: binding.slice(dot + 1) }
}
</script>

<template>
  <div class="binding-picker">
    <div class="d-flex align-center flex-wrap ga-1">
      <span class="text-caption muted mr-1">Fills step params</span>
      <v-chip
        v-for="binding in modelValue" :key="binding"
        size="small" closable :title="`${stepNames[label(binding).id] ?? label(binding).id} (${label(binding).id}) · ${label(binding).param}`"
        @click:close="remove(binding)">
        {{ label(binding).step }}&nbsp;· {{ label(binding).param }}
      </v-chip>
      <v-menu v-model="open" location="bottom start" :close-on-content-click="false">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" size="x-small" variant="tonal" prepend-icon="mdi-plus">Add step param</v-btn>
        </template>
        <v-card class="bind-menu">
          <!-- stage 1: steps -->
          <v-list v-if="!step" density="compact" class="bind-list">
            <v-list-item v-if="!steps.length" disabled title="No steps yet" />
            <v-list-item
              v-for="s in steps" :key="s.id"
              :title="`${shortName(s.name)} (${s.id})`" :subtitle="s.name"
              append-icon="mdi-chevron-right"
              @click="chooseStep(s.id!)" />
          </v-list>

          <!-- stage 2: params of the chosen step -->
          <template v-else>
            <v-list density="compact" class="pb-0">
              <v-list-item prepend-icon="mdi-chevron-left" :title="`${shortName(step.name)} (${step.id})`" class="back-row" @click="stepId = undefined" />
            </v-list>
            <v-text-field
              v-model="filter" placeholder="Search params" prepend-inner-icon="mdi-magnify"
              variant="solo-filled" density="compact" hide-details flat autofocus />
            <v-progress-linear v-if="loading" indeterminate height="2" />
            <v-list density="compact" class="bind-list">
              <v-list-item v-if="!loading && !params.length" disabled title="No params" />
              <v-list-item
                v-for="p in params" :key="p.name"
                :subtitle="p.spec.description" lines="one" :disabled="p.bound"
                @click="add(p.name)">
                <template #title>
                  <span :class="{ 'text-warning': p.spec.required }">{{ p.name }}{{ p.spec.required ? ' *' : '' }}</span>
                  <span v-if="p.bound" class="text-caption muted ml-1">already filled</span>
                </template>
                <template #append>
                  <span class="text-caption muted">{{ details(p.spec) }}</span>
                </template>
              </v-list-item>
            </v-list>
          </template>
        </v-card>
      </v-menu>
    </div>
    <p v-if="errorMessages?.length" class="field-error mb-0 mt-1">{{ errorMessages.join(' ') }}</p>
  </div>
</template>

<style scoped>
.bind-menu {
  width: 360px;
}
.bind-list {
  max-height: 320px;
  overflow-y: auto;
}
.back-row {
  font-weight: 600;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
</style>
