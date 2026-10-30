<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { INPUT_COLOR, REF_COLOR } from '../store'
import type { ParamSpec, StepSchema } from '../types'
import { paramRows, paramSuggestions, toParamValue, type ParamRow, type ReferenceTarget } from '../utils'
import ParamAssist from './ParamAssist.vue'
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
const optional = computed(() => paramSuggestions(props.schema, [...Object.keys(params.value), ...Object.keys(props.bound)]).optional)
const optionalItems = computed(() => optional.value.map(name => ({ title: name, value: name, subtitle: props.schema?.[name]?.description })))
const picked = ref<string | null>(null)
const menuOpen = ref(false)

const stepNames = computed(() => Object.fromEntries(props.references.map(t => [t.stepId, t.stepName.split('/').pop()])))

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

function setInput(name: string) {
  setValue(name, `\${inputs:${props.inputFor(name).name}}`)
}

function setReference(name: string, stepId: string, key: string) {
  setValue(name, `\${${stepId}:params:${key}}`)
}

function addOptional(name: string | null, value = '') {
  if (name) setValue(name, value)
  picked.value = null
  menuOpen.value = false
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

function enumItems(spec?: ParamSpec): unknown[] {
  return spec?.enum ?? []
}

function isPath(spec?: ParamSpec) {
  return PATH_FORMATS.has(spec?.format ?? '') || MODULE_PATH_TYPES.has(spec?.type ?? '')
}

function missing(row: ParamRow) {
  return row.required && !row.boundBy && (row.value === undefined || row.value === null || row.value === '')
}

function inputTitle(name: string) {
  const { name: input, shared } = props.inputFor(name)
  return shared ? `Fill '${name}' per run with the existing input '${input}'` : `Fill '${name}' per run: new input '${input}'`
}

// YAML mode: the existing editor with its param pills
const yamlEditor = ref<InstanceType<typeof YamlEditor>>()
const setInYaml = computed(() => [...Object.keys(params.value), ...Object.keys(props.bound)])
const valuedInYaml = computed(() => Object.keys(params.value))

function addInYaml(param: string, value: string) {
  yamlEditor.value?.addParam(param, value)
}

function switchMode(next: 'form' | 'yaml') {
  asked.value = next
  nextTick()
}
</script>

<template>
  <div class="params-form">
    <div class="d-flex align-center mb-1">
      <span class="text-caption">Params</span>
      <v-spacer />
      <v-btn-toggle
        :model-value="mode" mandatory density="compact" variant="text" class="mode-toggle"
        @update:model-value="switchMode">
        <v-btn value="form" size="x-small" :disabled="!schema" title="One field per param, from the schema">Form</v-btn>
        <v-btn value="yaml" size="x-small" title="Edit the params as YAML">YAML</v-btn>
      </v-btn-toggle>
    </div>

    <p v-for="message in generalErrors" :key="message" class="field-error mb-1">{{ message }}</p>

    <div v-if="loading" class="text-body-2 muted">
      <v-progress-circular indeterminate size="14" width="2" class="mr-1" /> Loading params…
    </div>

    <!-- Form -->
    <template v-else-if="mode === 'form'">
      <div v-for="row in rows" :key="row.name" class="param-row" :class="{ missing: missing(row) }">
        <div class="param-field">
          <!-- a whole input or reference: a chip, cleared to edit the value again -->
          <v-text-field
            v-if="chip(row)"
            :model-value="chip(row)!.text"
            :label="row.required ? `${row.name} *` : row.name"
            :hint="chip(row)!.bound ? 'Bound with bind: in the inputs section; change it in the Inputs tab' : row.spec?.description"
            readonly
            :clearable="!chip(row)!.bound"
            :prepend-inner-icon="chip(row)!.kind === 'input' ? 'mdi-import' : 'mdi-transit-connection-variant'"
            :class="['value-chip', chip(row)!.kind === 'input' ? 'is-input' : 'is-ref']"
            variant="outlined" density="compact" hide-details="auto"
            :error-messages="errors[row.name]"
            @click:clear="setValue(row.name, '')" />
          <v-select
            v-else-if="fieldKind(row.spec) === 'enum'"
            :model-value="row.value" :items="enumItems(row.spec)"
            :label="row.required ? `${row.name} *` : row.name" :hint="row.spec?.description"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            clearable variant="outlined" density="compact" hide-details="auto"
            :error-messages="errors[row.name]"
            @update:model-value="(v: unknown) => setValue(row.name, v ?? '')" />
          <v-select
            v-else-if="fieldKind(row.spec) === 'boolean'"
            :model-value="row.value" :items="BOOLEANS"
            :label="row.required ? `${row.name} *` : row.name" :hint="row.spec?.description"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            clearable variant="outlined" density="compact" hide-details="auto"
            :error-messages="errors[row.name]"
            @update:model-value="(v: unknown) => setValue(row.name, v ?? '')" />
          <v-text-field
            v-else
            :model-value="row.value === undefined || row.value === null ? '' : String(row.value)"
            :type="fieldKind(row.spec) === 'number' ? 'number' : 'text'"
            :label="row.required ? `${row.name} *` : row.name" :hint="row.spec?.description"
            :prepend-inner-icon="isPath(row.spec) ? 'mdi-file-outline' : undefined"
            :color="missing(row) ? 'warning' : undefined" :base-color="missing(row) ? 'warning' : undefined"
            variant="outlined" density="compact" hide-details="auto" class="value-text"
            :error-messages="errors[row.name]"
            @update:model-value="(v: string) => setValue(row.name, toParamValue(v, row.spec))" />
        </div>
        <div class="param-actions">
          <template v-if="!row.boundBy">
            <ReferenceMenu :param="row.name" :references="references" :size="24" @pick="(stepId, key) => setReference(row.name, stepId, key)" />
            <v-btn
              icon="mdi-import" size="24" variant="flat" class="pill-btn"
              :color="INPUT_COLOR" :title="inputTitle(row.name)"
              @click="setInput(row.name)" />
          </template>
          <v-btn
            v-if="!row.required && !row.boundBy"
            icon="mdi-close" size="24" variant="text" density="comfortable" title="Remove this param"
            @click="remove(row.name)" />
          <span v-else class="action-spacer" />
        </div>
      </div>

      <v-autocomplete
        v-if="optionalItems.length"
        v-model="picked"
        v-model:menu="menuOpen"
        :items="optionalItems"
        label="Add an optional param"
        color="info" base-color="info"
        prepend-inner-icon="mdi-plus"
        variant="outlined" density="compact" hide-details class="mt-1"
        @update:model-value="addOptional">
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps" :subtitle="item.subtitle" lines="one">
            <template #append>
              <ReferenceMenu :param="item.value" :references="references" :size="26" location="end" class="mr-1"
                @pick="(stepId, key) => addOptional(item.value, `\${${stepId}:params:${key}}`)" />
              <v-btn
                icon="mdi-import" size="26" variant="flat" class="pill-btn"
                :color="INPUT_COLOR" :title="inputTitle(item.value)"
                @click.stop="addOptional(item.value, `\${inputs:${inputFor(item.value).name}}`)" />
            </template>
          </v-list-item>
        </template>
      </v-autocomplete>
    </template>

    <!-- YAML -->
    <template v-else>
      <p v-if="!schema" class="text-body-2 muted mb-1">{{ error ?? 'No param schema for this step yet: edit the params as YAML.' }}</p>
      <ParamAssist
        :schema="schema" :error="undefined"
        :set-params="setInYaml" :input-for="inputFor" :references="references" :valued-params="valuedInYaml"
        @add="addInYaml" />
      <div class="params-editor">
        <YamlEditor ref="yamlEditor" :model-value="modelValue" :node-id="nodeId" @update:model-value="(v) => emit('update:modelValue', v)" />
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
.value-chip.is-input :deep(input),
.value-chip.is-input :deep(.v-field__prepend-inner .v-icon) {
  color: v-bind(INPUT_COLOR);
  opacity: 1;
}
.value-chip.is-ref :deep(input),
.value-chip.is-ref :deep(.v-field__prepend-inner .v-icon) {
  color: v-bind(REF_COLOR);
  opacity: 1;
}
.pill-btn :deep(.v-icon) {
  color: white;
  font-size: 15px;
}
.params-editor {
  height: 200px;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
</style>
