<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { INPUT_COLOR, useApiStore, useEditorStore, useGraphStore } from '../store'
import type { APIInput, APIInputDefinition, StepSchema, Scalar } from '../types'
import { cleanInputDefinition, extractInputFieldErrors } from '../utils'

const props = defineProps<{
  // The input shown; none for an input being added
  input?: APIInput
}>()

const emit = defineEmits<{
  closed: [],
}>()

const graphStore = useGraphStore()
const editorStore = useEditorStore()
const apiStore = useApiStore()

const TYPES = ['string', 'integer', 'number', 'boolean']
const FORMATS = ['file-path', 'directory-path', 'path', 'file-path-pattern']
const PATH_FORMATS = new Set(FORMATS)
const BOOLEANS: Scalar[] = [true, false]
const STYLES = [
  { value: true, title: 'written in the step params', icon: 'mdi-code-braces' },
  { value: false, title: 'bound in the inputs: section', icon: 'mdi-link-variant' },
]

type Form = {
  name: string,
  inParams: boolean,
  bindings: string[],
  description?: string,
  default?: Scalar | null,
  type?: APIInputDefinition['type'],
  format?: string,
  enum: Scalar[],
  pattern?: string,
  minimum?: number | string,
  maximum?: number | string,
  exists?: boolean | null,
}

const isNew = computed(() => !props.input)
const isEditing = ref(isNew.value)
const saving = ref(false)
const fieldErrors = ref<Record<string, string[]>>({})
const otherErrors = ref<string[]>([])
const form = ref<Form>(initialForm())
const showKeywords = ref(false)
const card = ref<{ $el: HTMLElement }>()

function initialForm(): Form {
  const d = props.input?.definition ?? {}
  return {
    name: props.input?.name ?? '',
    inParams: props.input ? props.input.bound_by !== 'bind' : true,
    bindings: [...(props.input?.bindings ?? [])],
    description: d.description,
    default: d.default,
    type: d.type,
    format: d.format,
    enum: [...(d.enum ?? [])],
    pattern: d.pattern,
    minimum: d.minimum,
    maximum: d.maximum,
    exists: d.exists,
  }
}

// The two ways to write the bindings, with the YAML each would produce
const styleChoices = computed(() => {
  const name = form.value.name.trim() || '<name>'
  const bindings = form.value.bindings.length ? form.value.bindings : ['<step>.<param>']
  const first = bindingLabel(bindings[0]!)
  const more = bindings.length > 1 ? ` (and ${bindings.length - 1} more)` : ''
  return [
    { value: true, title: 'In the step params', preview: `${first.stepId}: params: ${first.param}: \${inputs:${name}}${more}` },
    { value: false, title: 'In the inputs: section', preview: `inputs: ${name}: bind: [${bindings.join(', ')}]` },
  ]
})

const style = computed(() => STYLES.find(s => s.value === (props.input?.bound_by !== 'bind')) ?? STYLES[0]!)
const warnings = computed(() => props.input?.diagnostics.filter(d => d.severity === 'warning') ?? [])
const errors = computed(() => props.input?.diagnostics.filter(d => d.severity === 'error') ?? [])

// The schema the default is checked against: own keywords over inherited ones
const effectiveType = computed(() => form.value.type ?? props.input?.schema.type)
const effectiveFormat = computed(() => form.value.format ?? props.input?.schema.format)
const effectiveEnum = computed(() => form.value.enum.length ? form.value.enum : props.input?.schema.enum)
const isPath = computed(() => PATH_FORMATS.has(effectiveFormat.value ?? ''))

const nodeNames = computed(() => Object.fromEntries(graphStore.nodeData.map(n => [n.id, n.name])))

function bindingLabel(binding: string) {
  const dot = binding.indexOf('.')
  const stepId = binding.slice(0, dot)
  return { stepId, step: nodeNames.value[stepId] ?? stepId, param: binding.slice(dot + 1) }
}

// The keywords in the effective schema, marked as set on this input or inherited
const keywords = computed(() => {
  const own = props.input?.definition ?? {}
  return Object.entries(props.input?.schema ?? {})
    .filter(([key]) => key !== 'schema' && key !== 'mimetype')
    .map(([key, value]) => ({
      key,
      value: Array.isArray(value) ? value.join(', ') : String(value),
      own: key in own,
    }))
})

// Bind targets: every param of every step, from the steps' schemas
const bindTargets = ref<{ title: string, value: string }[]>([])
const targetsLoading = ref(false)

async function loadBindTargets() {
  targetsLoading.value = true
  try {
    const targets: { title: string, value: string }[] = []
    for (const node of graphStore.nodeData) {
      if (!node.id) continue
      const result = await apiStore.getNodeSchema(node.id)
      const schema: StepSchema = result.ok ? result.data : {}
      const params = new Set([...Object.keys(schema), ...Object.keys(node.params ?? {})])
      for (const param of [...params].sort()) {
        if (schema[param]?.hidden) continue
        targets.push({ title: `${node.name ?? node.id} (${node.id}) · ${param}`, value: `${node.id}.${param}` })
      }
    }
    bindTargets.value = targets
  } finally {
    targetsLoading.value = false
  }
}

function startEditing() {
  form.value = initialForm()
  fieldErrors.value = {}
  otherErrors.value = []
  showKeywords.value = Object.keys(props.input?.definition ?? {}).some(k => !['bind', 'description', 'default'].includes(k))
  isEditing.value = true
  loadBindTargets()
}

if (isNew.value) loadBindTargets()

function cancel() {
  isEditing.value = false
  if (isNew.value) emit('closed')
}

function toNumber(value: number | string | undefined): number | undefined {
  if (value === undefined || value === '') return undefined
  const n = Number(value)
  return Number.isNaN(n) ? undefined : n
}

function defaultValue(): Scalar | undefined {
  const value = form.value.default
  if (value === null || value === undefined || value === '') return undefined
  if ((effectiveType.value === 'integer' || effectiveType.value === 'number') && typeof value === 'string') {
    return toNumber(value) ?? value
  }
  return value
}

async function save() {
  const name = form.value.name.trim()
  const original = props.input?.name ?? name
  saving.value = true
  fieldErrors.value = {}
  otherErrors.value = []
  try {
    const result = await graphStore.saveInput({
      name: original,
      new_name: name !== original ? name : undefined,
      create: isNew.value,
      in_params: form.value.inParams,
      bindings: form.value.bindings,
      definition: cleanInputDefinition({
        description: form.value.description,
        default: defaultValue(),
        type: form.value.type,
        format: form.value.format,
        enum: form.value.enum,
        pattern: form.value.pattern,
        minimum: toNumber(form.value.minimum),
        maximum: toNumber(form.value.maximum),
        exists: form.value.exists ?? undefined,
      }),
    })
    if (result.ok) {
      isEditing.value = false
      if (isNew.value) emit('closed')
    } else if (result.fieldErrors?.length) {
      const split = extractInputFieldErrors(result.fieldErrors, name)
      fieldErrors.value = split.fields
      otherErrors.value = [...(split.fields[''] ?? []), ...split.other]
    } else if (result.graphErrors?.length) {
      otherErrors.value = result.graphErrors
    }
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (props.input) await graphStore.removeInput(props.input.name)
}

function openStep(stepId: string) {
  const node = graphStore.nodeData.find(n => n.id === stepId)
  if (node) editorStore.showNode(node)
}

function hover(name: string | undefined) {
  editorStore.setHoveredInputName(name)
}

const isFlashing = computed(() => !!props.input && editorStore.flashingInputNames.includes(props.input.name))
watch(isFlashing, async (flashing) => {
  if (!flashing) return
  await nextTick()
  card.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
})
</script>

<template>
  <v-card
    ref="card"
    class="mt-2 input-card"
    :class="{ 'input-card-hovered': !!input && (editorStore.hoveredInputName === input.name || isFlashing) }"
    @mouseenter="hover(input?.name)"
    @mouseleave="hover(undefined)">
    <v-card-title class="d-flex align-center ga-2 py-1 text-subtitle-1">
      <v-icon icon="mdi-import" :color="INPUT_COLOR" size="18" />
      <strong v-if="input" class="text-truncate">{{ input.name }}</strong>
      <span v-else class="font-italic">New input</span>
      <v-icon v-if="errors.length" icon="mdi-alert-circle" color="error" size="16" />
      <v-icon v-else-if="warnings.length" icon="mdi-alert" color="warning" size="16" />
      <v-spacer />
      <template v-if="input && !isEditing">
        <v-btn icon="mdi-pencil" size="small" variant="text" density="comfortable" title="Edit" @click.stop="startEditing" />
        <v-btn icon="mdi-delete-outline" size="small" variant="text" density="comfortable" color="error" title="Delete" @click.stop="remove" />
      </template>
    </v-card-title>

    <!-- View -->
    <v-card-text v-if="input && !isEditing" class="pt-0 pb-2">
      <p v-if="input.description" class="text-body-2 muted mt-0 mb-1">{{ input.description }}</p>

      <div class="d-flex flex-wrap align-center ga-1">
        <v-chip
          v-for="binding in input.bindings" :key="binding"
          size="small" :prepend-icon="style.icon"
          :title="`Fills ${bindingLabel(binding).param} of ${bindingLabel(binding).step} (${bindingLabel(binding).stepId}), ${style.title}. Click to open the step.`"
          @mouseenter="editorStore.setHoveredNodeId(bindingLabel(binding).stepId)"
          @mouseleave="editorStore.setHoveredNodeId(undefined)"
          @click.stop="openStep(bindingLabel(binding).stepId)">
          {{ bindingLabel(binding).step.split('/').pop() }} · {{ bindingLabel(binding).param }}
        </v-chip>
        <v-chip v-if="input.default !== null" size="small" variant="outlined" prepend-icon="mdi-format-text" title="default">
          {{ input.default }}
        </v-chip>
        <v-chip
          v-for="kw in keywords" :key="kw.key"
          size="x-small"
          :variant="kw.own ? 'flat' : 'outlined'"
          :title="kw.own ? 'set on this input' : 'from the bound param'">
          {{ kw.key }}: {{ kw.value }}
        </v-chip>
      </div>

      <div v-for="d in [...errors, ...warnings]" :key="d.yaml_path + d.message" class="d-flex align-center ga-1 text-caption mt-1">
        <v-icon
          :icon="d.severity === 'error' ? 'mdi-alert-circle' : 'mdi-alert'"
          :color="d.severity === 'error' ? 'error' : 'warning'"
          size="14" />
        <span>{{ d.message }}</span>
      </div>
    </v-card-text>

    <!-- Edit -->
    <v-card-text v-else class="pt-0 pb-2">
      <v-form class="compact-form" @submit.prevent="save">
        <v-text-field
          v-model="form.name"
          label="Name"
          hint="Referenced as ${inputs:<name>}"
          variant="outlined" density="compact" hide-details="auto" :autofocus="isNew"
          :error-messages="fieldErrors.name" />

        <v-combobox
          v-model="form.bindings"
          :items="bindTargets"
          :loading="targetsLoading"
          :return-object="false"
          label="Fills step params"
          multiple chips closable-chips
          variant="outlined" density="compact" hide-details="auto"
          :error-messages="fieldErrors.bind" />

        <v-radio-group v-model="form.inParams" density="compact" hide-details class="style-choice">
          <template #label><span class="text-body-2">Where the config says which params it fills</span></template>
          <v-radio v-for="choice in styleChoices" :key="String(choice.value)" :value="choice.value" color="primary">
            <template #label>
              <div class="d-flex flex-column">
                <span class="text-body-2">{{ choice.title }}</span>
                <code class="style-preview">{{ choice.preview }}</code>
              </div>
            </template>
          </v-radio>
        </v-radio-group>

        <v-textarea
          v-model="form.description"
          label="Description"
          variant="outlined" density="compact" hide-details="auto" rows="1" auto-grow
          :error-messages="fieldErrors.description" />

        <v-select
          v-if="effectiveEnum?.length"
          v-model="form.default"
          :items="effectiveEnum"
          label="Default"
          clearable
          variant="outlined" density="compact" hide-details="auto"
          :error-messages="fieldErrors.default" />
        <v-select
          v-else-if="effectiveType === 'boolean'"
          v-model="form.default"
          :items="BOOLEANS"
          label="Default"
          clearable
          variant="outlined" density="compact" hide-details="auto"
          :error-messages="fieldErrors.default" />
        <v-text-field
          v-else
          v-model="form.default"
          :type="effectiveType === 'integer' || effectiveType === 'number' ? 'number' : 'text'"
          :prepend-inner-icon="isPath ? 'mdi-file-outline' : undefined"
          :hint="isPath ? 'Relative paths are relative to the config file' : undefined"
          label="Default"
          clearable
          variant="outlined" density="compact" hide-details="auto"
          :error-messages="fieldErrors.default" />

        <v-btn
          size="small" variant="text" class="px-1 align-self-start"
          :prepend-icon="showKeywords ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          @click="showKeywords = !showKeywords">
          Type and constraints
        </v-btn>
        <template v-if="showKeywords">
          <p class="text-caption muted mb-0">
            Empty fields are inherited from the bound params' schema; set ones narrow it.
          </p>
          <div class="d-flex ga-2">
            <v-select
              v-model="form.type" :items="TYPES" label="Type" clearable
              :placeholder="input?.schema.type"
              persistent-placeholder
              variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.type" />
            <v-combobox
              v-model="form.format" :items="FORMATS" label="Format" clearable
              :placeholder="input?.schema.format"
              persistent-placeholder
              variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.format" />
          </div>
          <v-combobox
            v-model="form.enum" label="Allowed values" multiple chips closable-chips
            variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.enum" />
          <v-text-field
            v-model="form.pattern" label="Pattern (regex)" :placeholder="input?.schema.pattern"
            persistent-placeholder
            variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.pattern" />
          <div class="d-flex ga-2">
            <v-text-field
              v-model="form.minimum" type="number" label="Minimum"
              variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.minimum" />
            <v-text-field
              v-model="form.maximum" type="number" label="Maximum"
              variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.maximum" />
          </div>
          <v-select
            v-model="form.exists"
            :items="[{ title: 'Must exist', value: true }, { title: 'May be missing', value: false }]"
            label="Path existence" clearable
            variant="outlined" density="compact" hide-details="auto" :error-messages="fieldErrors.exists" />
        </template>

        <div v-for="message in otherErrors" :key="message" class="d-flex ga-2 text-body-2 mb-1">
          <v-icon icon="mdi-alert-circle" color="error" size="16" class="mt-1" />
          <span>{{ message }}</span>
        </div>

        <div class="d-flex justify-end ga-1">
          <v-btn size="small" variant="flat" color="primary" type="submit" :loading="saving" prepend-icon="mdi-check">Save</v-btn>
          <v-btn size="small" variant="text" color="error" @click="cancel">Cancel</v-btn>
        </div>
      </v-form>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.input-card {
  transition: box-shadow 0.2s;
}
.input-card-hovered {
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.4) !important;
}
.style-choice :deep(.v-label) {
  opacity: 1;
}
.style-preview {
  font-size: 0.75rem;
  opacity: 0.75;
  word-break: break-all;
}
.compact-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
