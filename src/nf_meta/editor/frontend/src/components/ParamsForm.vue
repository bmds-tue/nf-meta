<script setup lang="ts">
import { computed, ref } from 'vue'
import { INPUT_COLOR, REF_COLOR } from '../store'
import type { ParamSpec, StepSchema } from '../types'
import { addableParams, paramRows, pathPick, splitLeadingReference, toParamValue, withoutEmptyValues, type ParamRow, type ReferenceTarget } from '../utils'
import ParamRowActions from './ParamRowActions.vue'
import PathPicker from './PathPicker.vue'
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

const BOOLEANS: unknown[] = [true, false]
const WHOLE_INPUT = /^\$\{inputs:([^}:]+)\}$/

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

// "Add param": every param of the schema without a value yet, filtered by what is typed
const addOpen = ref(false)
const addFilter = ref('')
const addable = computed(() => {
  const set = [
    ...Object.entries(params.value).filter(([, v]) => v !== '' && v !== null && v !== undefined).map(([k]) => k),
    ...Object.keys(props.bound),
  ]
  const text = addFilter.value.trim().toLowerCase()
  return addableParams(props.schema, set).filter(p => !text || p.name.toLowerCase().includes(text))
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

// A whole input value (or a bind: input) is shown as a chip; a reference at the start of a
// value as a chip inside the text field, with the rest of the value editable after it
function inputChip(row: ParamRow): { text: string, bound: boolean } | undefined {
  if (row.boundBy) return { text: `← input ${row.boundBy}`, bound: true }
  if (typeof row.value !== 'string') return undefined
  const input = row.value.match(WHOLE_INPUT)
  return input ? { text: `← input ${input[1]}`, bound: false } : undefined
}

function leadingReference(row: ParamRow) {
  return splitLeadingReference(row.value)
}

// The text of a field: after a leading reference, only the rest
function fieldText(row: ParamRow): string {
  const reference = leadingReference(row)
  if (reference) return reference.rest
  return row.value === undefined || row.value === null ? '' : String(row.value)
}

function setText(row: ParamRow, text: string) {
  const reference = leadingReference(row)
  if (reference) setValue(row.name, referenceValue(reference.stepId, reference.key) + text)
  else setValue(row.name, toParamValue(text, row.spec))
}

function dropReference(row: ParamRow) {
  setValue(row.name, leadingReference(row)?.rest ?? '')
}

function fieldKind(spec?: ParamSpec): 'enum' | 'boolean' | 'number' | 'text' {
  if (spec?.enum?.length) return 'enum'
  if (spec?.type === 'boolean') return 'boolean'
  if (spec?.type === 'integer' || spec?.type === 'number') return 'number'
  return 'text'
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
            v-model="addFilter" placeholder="Search params" prepend-inner-icon="mdi-magnify"
            variant="solo-filled" density="compact" hide-details flat autofocus />
          <v-list density="compact" class="add-list">
            <v-list-item v-if="!addable.length" disabled title="Every param has a value" />
            <v-list-item
              v-for="p in addable" :key="p.name"
              :subtitle="p.description" lines="one"
              @click="add(p.name)">
              <template #title>
                <span :class="{ 'text-warning': p.required }">{{ p.name }}{{ p.required ? ' *' : '' }}</span>
                <span v-if="p.hidden" class="text-caption muted ml-1">hidden</span>
              </template>
              <template #append>
                <ReferenceMenu :param="p.name" :references="references" :size="24" location="end" class="mr-1"
                  @pick="(stepId, key) => add(p.name, referenceValue(stepId, key))" />
                <v-btn
                  icon="mdi-import" size="24" variant="flat" class="pill-btn"
                  :color="INPUT_COLOR" :title="inputTitle(p.name)"
                  @click.stop="add(p.name, inputValue(p.name))" />
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
      <div v-for="row in rows" :key="row.name" class="param-row" :class="{ missing: missing(row), 'chip-row': !!inputChip(row) }" :title="row.spec?.description">
        <div class="param-main">
        <!-- a whole input: a chip, closed to give the param a value again -->
        <div v-if="inputChip(row)" class="chip-field">
          <span class="chip-label">{{ label(row) }}</span>
          <div class="d-flex align-center w-100">
            <v-chip
              size="small" variant="tonal" :color="INPUT_COLOR"
              :prepend-icon="inputChip(row)!.bound ? 'mdi-link-variant' : 'mdi-import'"
              :closable="!inputChip(row)!.bound"
              :title="inputChip(row)!.bound ? 'Bound with bind: in the inputs section; change it in the Inputs tab' : undefined"
              @click:close="setValue(row.name, '')">
              {{ inputChip(row)!.text }}
            </v-chip>
            <v-spacer />
            <ParamRowActions
              v-if="!inputChip(row)!.bound"
              :param="row.name" :references="references" :input-title="inputTitle(row.name)"
              @reference="(stepId, key) => setValue(row.name, referenceValue(stepId, key))"
              @input="setValue(row.name, inputValue(row.name))" />
          </div>
          <div v-for="message in errors[row.name] ?? []" :key="message" class="field-error">{{ message }}</div>
        </div>
        <v-select
          v-else-if="fieldKind(row.spec) === 'enum' || fieldKind(row.spec) === 'boolean'"
          :model-value="row.value" :items="fieldKind(row.spec) === 'enum' ? row.spec?.enum ?? [] : BOOLEANS" :label="label(row)"
          :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
          clearable variant="outlined" density="compact" hide-details="auto"
          :error-messages="errors[row.name]"
          @update:model-value="(v: unknown) => setValue(row.name, v ?? '')">
          <template #append-inner>
            <ParamRowActions
              :param="row.name" :references="references" :input-title="inputTitle(row.name)"
              @reference="(stepId, key) => setValue(row.name, referenceValue(stepId, key))"
              @input="setValue(row.name, inputValue(row.name))" />
          </template>
        </v-select>
        <v-text-field
          v-else
          :model-value="fieldText(row)"
          :type="fieldKind(row.spec) === 'number' && !leadingReference(row) ? 'number' : 'text'"
          :label="label(row)"
          :placeholder="leadingReference(row) ? 'more text, e.g. /samplesheet.csv' : undefined"
          :prepend-inner-icon="pathPick(row.spec?.format, row.spec?.type) && !leadingReference(row) ? 'mdi-file-outline' : undefined"
          :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
          variant="outlined" density="compact" hide-details="auto" class="value-text"
          :error-messages="errors[row.name]"
          @update:model-value="(v: string) => setText(row, v)">
          <template v-if="leadingReference(row)" #prepend-inner>
            <v-chip
              size="small" variant="tonal" :color="REF_COLOR" prepend-icon="mdi-transit-connection-variant"
              closable class="ref-chip" @click:close.stop="dropReference(row)" @mousedown.stop>
              {{ stepNames[leadingReference(row)!.stepId] ?? leadingReference(row)!.stepId }} · {{ leadingReference(row)!.key }}
            </v-chip>
          </template>
          <template #append-inner>
            <PathPicker
              v-if="pathPick(row.spec?.format, row.spec?.type) && !leadingReference(row)"
              :pick="pathPick(row.spec?.format, row.spec?.type)!" :value="fieldText(row)"
              @pick="(p) => setText(row, p)" />
            <ParamRowActions
              :param="row.name" :references="references" :input-title="inputTitle(row.name)"
              @reference="(stepId, key) => setValue(row.name, referenceValue(stepId, key) + (leadingReference(row)?.rest ?? ''))"
              @input="setValue(row.name, inputValue(row.name))" />
          </template>
        </v-text-field>
        </div>
        <v-btn
          v-if="!row.required && !row.boundBy"
          icon="mdi-close" size="small" variant="text" density="comfortable" class="remove-btn" title="Remove this param"
          @click="remove(row.name)" />
      </div>
    </template>

    <!-- YAML -->
    <template v-else>
      <p v-if="!schema" class="text-body-2 muted mb-0">
        No param schema{{ error ? `: ${error.replace(/\.\s*$/, '')}` : ' for this step yet' }}. Edit the params as YAML.
      </p>
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
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 2px;
}
.param-main {
  flex: 1;
  min-width: 0;
}
.remove-btn {
  margin-top: 4px;
}
/* on a chip row: level with the chip, below its label */
.chip-row .remove-btn {
  align-self: flex-end;
  margin: 0 0 -2px;
}
/* a required param without a value: an amber bar in the margin, like the required pills */
.param-row.missing::before {
  content: '';
  position: absolute;
  left: -9px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 2px;
  background: rgb(var(--v-theme-warning));
}
.ref-chip {
  flex-shrink: 0;
  margin-right: 4px;
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
