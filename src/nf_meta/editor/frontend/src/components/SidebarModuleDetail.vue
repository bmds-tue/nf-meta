<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useModuleStore, useGraphStore } from '../store';
import { extractFieldErrors, inputFor, inputsOfStep, paramFieldErrors, shortVersion, unshownErrors, withoutEmptyValues } from '../utils';
import type { APINfModuleNodeData, APINodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import YAML from 'yaml';
import NodeInputs from './NodeInputs.vue';
import ParamsForm from './ParamsForm.vue';
import { useStepSchema } from '../step_schema';

const props = defineProps<{
  initialValue: APINfModuleNodeData,
  isNew: boolean,
}>()

const emit = defineEmits<{
  saved: [newNodeData?: APINodeData],
  deleted: [],
}>()

const moduleStore = useModuleStore()
const graphStore = useGraphStore()

const CONTAINER_ENGINES = ['docker', 'singularity', 'conda', 'podman']

const form = ref<APINfModuleNodeData>({ ...props.initialValue })
const isEditing = ref(props.isNew)
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})
const moduleVersions = ref<string[]>([])
const versionsLoading = ref(false)
const versionsError = ref<string>()

// Fields of the "More options" section; it starts open if any of them is set
const MORE_FIELDS = ['nf_config', 'container_engine'] as const
const hasMore = () => MORE_FIELDS.some(f => !!form.value[f])
const showMore = ref(hasMore())

// The graph changed (save, undo, another edit): show it, unless being edited
watch(() => props.initialValue, (value) => {
  if (!isEditing.value) form.value = { ...value }
})

// nf-core/ prefix stripped for the API, shown with prefix in the autocomplete
const moduleNames = computed(() => {
  return moduleStore.nfCoreModules?.map(m => `nf-core/${m.name}`) ?? []
})

// Load the module's versions; a newly picked module gets its latest one
async function loadVersions(pickLatest: boolean) {
  const name = form.value.name
  versionsError.value = undefined
  if (pickLatest) form.value.version = undefined
  if (!name) {
    moduleVersions.value = []
    return
  }
  const shortName = name.replace(/^nf-core\//, '')
  versionsLoading.value = true
  try {
    moduleVersions.value = (await moduleStore.fetchModuleVersions(shortName)).map(nfmv => nfmv.version)
    if (!form.value.version && moduleVersions.value.length > 0) {
      form.value.version = moduleVersions.value[0]
    }
  } catch {
    versionsError.value = 'Failed to load versions'
    moduleVersions.value = []
  } finally {
    versionsLoading.value = false
  }
}

async function submitForm(e: SubmitEventPromise) {
  const { valid } = await e
  if (!valid) return
  errors.value = {}
  paramErrors.value = { byParam: {}, general: [] }
  saving.value = true
  try {
    const previousIds = new Set(graphStore.nodeData.map(n => n.id))
    const result = await graphStore.saveNode({ ...form.value, params: withoutEmptyValues(form.value.params) })
    if (result.ok) {
      isEditing.value = false
      if (props.isNew) {
        const newNode = graphStore.nodeData.find(n => !previousIds.has(n.id))
        emit('saved', newNode)
      } else {
        emit('saved')
      }
    } else if (result.fieldErrors) {
      // A new node's id is assigned by the backend, so its errors can't be matched by id
      errors.value = extractFieldErrors(result.fieldErrors, props.isNew ? null : form.value.id ?? '')
      paramErrors.value = paramFieldErrors(result.fieldErrors, props.isNew ? null : form.value.id ?? '')
      if (MORE_FIELDS.some(f => errors.value[f]?.length)) showMore.value = true
    }
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (form.value.id) {
    await graphStore.removeNodeById(form.value.id)
  }
  emit('deleted')
}

function handleReset() {
  form.value = { ...props.initialValue }
  errors.value = {}
  isEditing.value = false
  if (props.isNew) emit('deleted')
}

function editDetail() {
  showMore.value = hasMore()
  isEditing.value = true
  loadVersions(false)
}

// The params form: the step's schema, the params inputs fill with bind:, and what can be referenced
const { schema, loading: schemaLoading, error: schemaError } = useStepSchema(() => ({ kind: 'module', name: form.value.name, version: form.value.version }))
const boundParams = computed(() => Object.fromEntries(
  form.value.id
    ? inputsOfStep(graphStore.inputs, form.value.id).filter(e => e.input.bound_by === 'bind').map(e => [e.param, e.input.name])
    : [],
))
const references = computed(() => graphStore.getReferenceTargets(form.value.id))
// Errors no field of this form shows (e.g. a global setting the step conflicts with)
const FORM_FIELDS = ['name', 'version', 'nf_config', 'container_engine']
const otherErrors = computed(() => unshownErrors(errors.value, FORM_FIELDS))
const paramErrors = ref<{ byParam: Record<string, string[]>, general: string[] }>({ byParam: {}, general: [] })

function inputForParam(param: string) {
  return inputFor(param, form.value.name, graphStore.inputs, schema.value?.[param])
}

const hasParams = computed(() => !!form.value.params && Object.keys(form.value.params).length > 0)
const paramsYaml = computed(() => form.value.params ? YAML.stringify(form.value.params).trim() : '')

const copiedField = ref<string>()
async function copyPath(text: string, field: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedField.value = field
    setTimeout(() => copiedField.value = undefined, 2000)
  } catch (e) {
    console.error('Clipboard write failed:', e)
  }
}
</script>

<template>
  <!-- View -->
  <div v-if="!isEditing" class="pt-1 pb-2">
    <div class="d-flex flex-wrap align-center ga-1 mb-1">
      <v-chip v-if="form.version" size="small" prepend-icon="mdi-tag-outline" :title="form.version">
        {{ shortVersion(form.version) }}
      </v-chip>
      <v-chip size="small" prepend-icon="$nfcore">nf-core module</v-chip>
      <v-chip v-if="form.container_engine" size="small" prepend-icon="mdi-package-variant-closed" title="Container engine">
        {{ form.container_engine }}
      </v-chip>
    </div>
    <div v-if="form.nf_config" class="detail-row d-flex align-center ga-1 text-body-2" title="Nextflow config">
      <v-icon icon="mdi-cog-outline" size="14" class="flex-shrink-0" />
      <code class="path-text flex-grow-1">{{ form.nf_config }}</code>
      <v-btn
        :icon="copiedField === 'nf_config' ? 'mdi-check' : 'mdi-content-copy'"
        size="24" variant="text" :ripple="false" flat class="flex-shrink-0 copy-btn"
        @click.stop="copyPath(form.nf_config!, 'nf_config')" />
    </div>

    <NodeInputs :node-id="form.id" />

    <div class="text-caption mt-2">Params</div>
    <pre v-if="hasParams" class="yaml-preview">{{ paramsYaml }}</pre>
    <p v-else class="text-body-2 muted mb-0">None</p>

    <div class="d-flex justify-end ga-1 pt-2">
      <v-btn size="small" variant="tonal" prepend-icon="mdi-pencil" @click.stop="editDetail">Edit</v-btn>
      <v-btn size="small" variant="text" color="error" prepend-icon="mdi-delete-outline" @click.stop="handleDelete">Delete</v-btn>
    </div>
  </div>

  <!-- Edit -->
  <v-form v-else class="compact-form pt-1 pb-2" @submit.prevent="submitForm">
    <v-autocomplete
      label="Module"
      v-model="form.name"
      :items="moduleNames"
      variant="outlined" density="compact" hide-details="auto"
      @update:modelValue="loadVersions(true)"
      :error-messages="errors.name ?? (moduleStore.initError ? [moduleStore.initError] : [])" />

    <v-autocomplete
      label="Version"
      v-model="form.version"
      :items="moduleVersions"
      :loading="versionsLoading"
      :disabled="!form.name"
      prepend-inner-icon="mdi-tag-outline"
      variant="outlined" density="compact" hide-details="auto"
      :error-messages="errors.version ?? (versionsError ? [versionsError] : [])" />

    <ParamsForm
      v-model="form.params"
      :schema="schema" :loading="schemaLoading" :error="schemaError"
      :input-for="inputForParam" :references="references" :bound="boundParams"
      :errors="paramErrors.byParam" :general-errors="paramErrors.general"
      :node-id="form.id" />

    <v-btn
      size="small" variant="text" class="px-1 align-self-start"
      :prepend-icon="showMore ? 'mdi-chevron-up' : 'mdi-chevron-down'"
      @click="showMore = !showMore">
      More options
    </v-btn>
    <template v-if="showMore">
      <v-text-field
        v-model="form.nf_config"
        label="Nextflow config"
        placeholder="Path, relative to the config file" persistent-placeholder
        prepend-inner-icon="mdi-cog-outline"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.nf_config" />
      <v-select
        v-model="form.container_engine"
        :items="CONTAINER_ENGINES"
        label="Container engine"
        prepend-inner-icon="mdi-package-variant-closed"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.container_engine" />
    </template>

    <div v-for="message in otherErrors" :key="message" class="other-error d-flex align-center ga-2 text-body-2">
      <v-icon icon="mdi-alert-circle" color="error" size="16" />
      <span>{{ message }}</span>
    </div>

    <div class="d-flex justify-end ga-1 pt-1">
      <v-btn size="small" variant="flat" color="primary" type="submit" :loading="saving" prepend-icon="mdi-check">Save</v-btn>
      <v-btn size="small" variant="text" color="error" @click="handleReset">Cancel</v-btn>
    </div>
  </v-form>
</template>

<style scoped>
.compact-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.params-editor {
  height: 200px;
}
.other-error {
  color: rgb(var(--v-theme-error));
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
.detail-row {
  min-width: 0;
  line-height: 1.6;
}
.detail-row .v-icon {
  color: rgba(var(--v-theme-onSurface), 0.45) !important;
}
.copy-btn :deep(.v-icon) {
  font-size: 14px;
}
.path-text {
  word-break: break-all;
  font-size: 0.8rem;
}
.yaml-preview {
  font-family: monospace;
  font-size: 0.75rem;
  line-height: 1.45;
  background: rgba(var(--v-theme-onSurface), 0.05);
  border-radius: 4px;
  padding: 6px 8px;
  margin: 2px 0 0;
  max-height: 110px;
  overflow-y: auto;
  white-space: pre;
}
</style>
