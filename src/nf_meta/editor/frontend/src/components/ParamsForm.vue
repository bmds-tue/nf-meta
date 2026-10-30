<script setup lang="ts">
import { computed, ref } from 'vue'
import { INPUT_COLOR, REF_COLOR } from '../store'
import type { ParamSpec, StepSchema } from '../types'
import { paramRows, paramSuggestions, toParamValue, withoutEmptyValues, type ParamRow, type ReferenceTarget } from '../utils'
import ReferenceMenu from './ReferenceMenu.vue'
import YamlEditor from './YamlEditor.vue'

const props = defineProps<{
  modelValue?: object
  schema?: StepSchema | null
  loading?: boolean
  error?: string
  // The input a param would get (shared if it exists already)
  inputFor: (param: string) => { name: string, shared: boolean }
  // The other steps' params a param can reference
  references: ReferenceTarget[]
  // Params filled by an input with bind:, as param -> input name
  bound: Record<string, string>
  // Errors from the last save, by param, and about the params as a whole
  errors: Record<string, string[]>
  generalErrors: string[]
  nodeId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: object | undefined],
}>()

const PATH_FORMATS = new Set(['file-path', 'directory-path', 'path', 'file-path-pattern'])
const MODULE_PATH_TYPES = new Set(['file', 'directory', 'path'])
const BOOLEANS: unknown[] = [true, false]
const WHOLE_INPUT = /^\$\{inputs:([^}:]+)\}$/
const WHOLE_STEP_REF = /^\$\{([^}:]+):params:([^}]+)\}$/

const params = computed(() => (props.modelValue ?? {}) as Record<string, unknown>)

// Form unless asked for YAML; YAML when there is no schema to build the form from
const asked = ref<'form' | 'yaml'>('form')
const mode = computed(() => !props.schema && !props.loading ? 'yaml' : asked.value)

const rows = computed(() => paramRows(props.schema, params.value, props.bound))
const stepNames = computed(() => Object.fromEntries(props.references.map(t => [t.stepId, t.stepName.split('/').pop()])))

// Every error of the last save, for the YAML view (the form shows them under their row)
const allErrors = computed(() => [
  ...props.generalErrors,
  ...Object.entries(props.errors).flatMap(([param, messages]) => messages.map(m => `${param}: ${m}`)),
])

// "Add param": the schema's optional params not set yet, filtered by what is typed
const addOpen = ref(false)
const addFilter = ref('')
const addable = computed(() => {
  const set = [...Object.keys(params.value), ...Object.keys(props.bound)]
  const text = addFilter.value.trim().toLowerCase()
  return paramSuggestions(props.schema, set).optional.filter(name => !text || name.toLowerCase().includes(text))
})

function setParams(next: Record<string, unknown>) {
  emit('update:modelValue', Object.keys(next).length ? next : undefined)
}

function setValue(name: string, value: unknown) {
  // '' keeps an added, still empty row; empty values are dropped when the step is saved
  setParams({ ...params.value, [name]: value === undefined ? '' : value })
}

function remove(name: string) {
  const next = { ...params.value }
  delete next[name]
  setParams(next)
}

function inputValue(name: string) {
  return `\${inputs:${props.inputFor(name).name}}`
}

function referenceValue(stepId: string, key: string) {
  return `\${${stepId}:params:${key}}`
}

const yamlEditor = ref<InstanceType<typeof YamlEditor>>()

// Add a param from the "Add param" menu: to the form, or as a line of the YAML
function add(name: string, value = '') {
  if (mode.value === 'yaml') yamlEditor.value?.addParam(name, value)
  else setValue(name, value)
  addOpen.value = false
  addFilter.value = ''
}

// How a row's value is shown: a chip for a whole input or reference, else a field
function chip(row: ParamRow): { kind: 'input' | 'ref', text: string, bound?: boolean } | undefined {
  if (row.boundBy) return { kind: 'input', text: `← input ${row.boundBy}`, bound: true }
  if (typeof row.value !== 'string') return undefined
  const input = row.value.match(WHOLE_INPUT)
  if (input) return { kind: 'input', text: `← input ${input[1]}` }
  const reference = row.value.match(WHOLE_STEP_REF)
  if (reference) return { kind: 'ref', text: `${stepNames.value[reference[1]!] ?? reference[1]} (${reference[1]}) · ${reference[2]}` }
  return undefined
}

function fieldKind(spec?: ParamSpec): 'enum' | 'boolean' | 'number' | 'text' {
  if (spec?.enum?.length) return 'enum'
  if (spec?.type === 'boolean') return 'boolean'
  if (spec?.type === 'integer' || spec?.type === 'number') return 'number'
  return 'text'
}

function isPath(spec?: ParamSpec) {
  return PATH_FORMATS.has(spec?.format ?? '') || MODULE_PATH_TYPES.has(spec?.type ?? '')
}

function missing(row: ParamRow) {
  return row.required && !row.boundBy && (row.value === undefined || row.value === null || row.value === '')
}

function label(row: ParamRow) {
  return row.required ? `${row.name} *` : row.name
}

function inputTitle(name: string) {
  const { name: input, shared } = props.inputFor(name)
  return shared ? `Fill '${name}' per run with the existing input '${input}'` : `Fill '${name}' per run: new input '${input}'`
}
</script>

<template>
  <div class="params-form">
    <div class="d-flex align-center ga-1">
      <span class="text-caption">Params</span>
      <v-spacer />
      <v-menu v-if="schema" v-model="addOpen" location="bottom end" :close-on-content-click="false">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" size="x-small" variant="tonal" color="info" prepend-icon="mdi-plus">Add param</v-btn>
        </template>
        <v-card class="add-menu">
          <v-text-field
            v-model="addFilter" placeholder="Search optional params" prepend-inner-icon="mdi-magnify"
            variant="solo-filled" density="compact" hide-details flat autofocus />
          <v-list density="compact" class="add-list">
            <v-list-item v-if="!addable.length" disabled title="No more optional params" />
            <v-list-item
              v-for="name in addable" :key="name"
              :title="name" :subtitle="schema[name]?.description" lines="one"
              @click="add(name)">
              <template #append>
                <ReferenceMenu :param="name" :references="references" :size="24" location="end" class="mr-1"
                  @pick="(stepId, key) => add(name, referenceValue(stepId, key))" />
                <v-btn
                  icon="mdi-import" size="24" variant="flat" class="pill-btn"
                  :color="INPUT_COLOR" :title="inputTitle(name)"
                  @click.stop="add(name, inputValue(name))" />
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>
      <v-btn-toggle v-model="asked" mandatory density="compact" variant="text" class="mode-toggle">
        <v-btn value="form" size="x-small" :disabled="!schema" title="One field per param, from the schema">Form</v-btn>
        <v-btn value="yaml" size="x-small" title="Edit the params as YAML">YAML</v-btn>
      </v-btn-toggle>
    </div>

    <div v-if="loading" class="text-body-2 muted">
      <v-progress-circular indeterminate size="14" width="2" class="mr-1" /> Loading params…
    </div>

    <!-- Form -->
    <template v-else-if="mode === 'form'">
      <p v-for="message in generalErrors" :key="message" class="field-error mb-0">{{ message }}</p>
      <div v-for="row in rows" :key="row.name" class="param-row" :class="{ missing: missing(row) }" :title="row.spec?.description">
        <div class="param-field">
          <!-- a whole input or reference: a chip, closed to edit the value again -->
          <div v-if="chip(row)" class="chip-field">
            <span class="chip-label">{{ label(row) }}</span>
            <v-chip
              size="small" variant="tonal"
              :color="chip(row)!.kind === 'input' ? INPUT_COLOR : REF_COLOR"
              :prepend-icon="chip(row)!.kind === 'input' ? 'mdi-import' : 'mdi-transit-connection-variant'"
              :closable="!chip(row)!.bound"
              :title="chip(row)!.bound ? 'Bound with bind: in the inputs section; change it in the Inputs tab' : undefined"
              @click:close="setValue(row.name, '')">
              {{ chip(row)!.text }}
            </v-chip>
            <div v-for="message in errors[row.name] ?? []" :key="message" class="field-error">{{ message }}</div>
          </div>
          <v-select
            v-else-if="fieldKind(row.spec) === 'enum'"
            :model-value="row.value" :items="row.spec?.enum ?? []" :label="label(row)"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            clearable variant="outlined" density="compact" hide-details="auto"
            :error-messages="errors[row.name]"
            @update:model-value="(v: unknown) => setValue(row.name, v ?? '')" />
          <v-select
            v-else-if="fieldKind(row.spec) === 'boolean'"
            :model-value="row.value" :items="BOOLEANS" :label="label(row)"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            clearable variant="outlined" density="compact" hide-details="auto"
            :error-messages="errors[row.name]"
            @update:model-value="(v: unknown) => setValue(row.name, v ?? '')" />
          <v-text-field
            v-else
            :model-value="row.value === undefined || row.value === null ? '' : String(row.value)"
            :type="fieldKind(row.spec) === 'number' ? 'number' : 'text'"
            :label="label(row)"
            :prepend-inner-icon="isPath(row.spec) ? 'mdi-file-outline' : undefined"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            variant="outlined" density="compact" hide-details="auto" class="value-text"
            :error-messages="errors[row.name]"
            @update:model-value="(v: string) => setValue(row.name, toParamValue(v, row.spec))" />
        </div>
        <div class="param-actions">
          <template v-if="!row.boundBy">
            <ReferenceMenu :param="row.name" :references="references" :size="24" @pick="(stepId, key) => setValue(row.name, referenceValue(stepId, key))" />
            <v-btn
              icon="mdi-import" size="24" variant="flat" class="pill-btn"
              :color="INPUT_COLOR" :title="inputTitle(row.name)"
              @click="setValue(row.name, inputValue(row.name))" />
          </template>
          <v-btn
            v-if="!row.required && !row.boundBy"
            icon="mdi-close" size="24" variant="text" density="comfortable" title="Remove this param"
            @click="remove(row.name)" />
          <span v-else class="action-spacer" />
        </div>
      </div>
    </template>

    <!-- YAML -->
    <template v-else>
      <p v-if="!schema" class="text-body-2 muted mb-0">{{ error ?? 'No param schema for this step yet: edit the params as YAML.' }}</p>
      <p v-for="message in allErrors" :key="message" class="field-error mb-0">{{ message }}</p>
      <div class="params-editor">
        <!-- empty rows of the form are left out: they aren't saved either -->
        <YamlEditor ref="yamlEditor" :model-value="withoutEmptyValues(modelValue)" :node-id="nodeId" @update:model-value="(v) => emit('update:modelValue', v)" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.params-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mode-toggle {
  height: 24px;
}
.param-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding-left: 8px;
  border-left: 3px solid transparent;
  border-radius: 2px;
  transition: border-color 0.2s;
}
/* a required param without a value: an amber bar, like the required pills */
.param-row.missing {
  border-left-color: rgb(var(--v-theme-warning));
}
.param-field {
  flex: 1;
  min-width: 0;
}
.chip-field {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 0 2px 2px;
}
.chip-label {
  font-size: 0.75rem;
  opacity: 0.72;
}
.param-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-top: 6px;
}
.action-spacer {
  width: 24px;
}
.value-text :deep(input) {
  font-family: monospace;
  font-size: 0.85rem;
}
.pill-btn :deep(.v-icon) {
  color: white;
  font-size: 15px;
}
.add-menu {
  width: 340px;
}
.add-list {
  max-height: 320px;
}
.params-editor {
  height: 220px;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
</style>
