<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { usePipelineStore, useGraphStore } from '../store';
import { extractFieldErrors, inputFor, inputsOfStep, paramFieldErrors, shortVersion, unshownErrors, withoutEmptyValues } from '../utils';
import type { APINfPipelineNodeData, APINodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import YAML from 'yaml';
import NodeInputs from './NodeInputs.vue';
import ParamsForm from './ParamsForm.vue';
import PathPicker from './PathPicker.vue';
import { useStepSchema } from '../step_schema';

const props = defineProps<{
  initialValue: APINfPipelineNodeData,
  isNew: boolean,
}>()

const emit = defineEmits<{
  saved: [newNodeData?: APINodeData],
  deleted: [],
}>()

const pipelineStore = usePipelineStore()
const graphStore = useGraphStore()

const form = ref<APINfPipelineNodeData>({ ...props.initialValue })
const isEditing = ref(props.isNew)
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})

// Fields of the "More options" section; it starts open if any of them is set
// (an nf-core pipeline's description comes from the catalog)
const MORE_FIELDS = ['description', 'params_file', 'nf_config', 'nf_profile', 'main_script'] as const
const hasMore = () => MORE_FIELDS.some(f => !!form.value[f] && !(f === 'description' && form.value.is_nfcore))
const showMore = ref(hasMore())

// The graph changed (save, undo, another edit): show it, unless being edited
watch(() => props.initialValue, (value) => {
  if (!isEditing.value) form.value = { ...value }
})

const nfCorePipelines = computed(() => {
  return pipelineStore.nfCorePipelines?.map(p => p.name)
})

const selectedPipeline = computed(() => {
  return pipelineStore.nfCorePipelines?.find(p => p.name === form.value.name)
})

const selectedPipelineVersions = computed(() => {
  if (!selectedPipeline.value) return []
  return selectedPipeline.value.releases.map(r => r.tag_name)
})

function handleUpdatePipeline() {
  if (form.value.name && selectedPipeline.value?.description) {
    form.value.description = selectedPipeline.value.description
    form.value.url = selectedPipeline.value.url
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
}

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

// The params form: the step's schema, the params inputs fill with bind:, and what can be referenced
const { schema, loading: schemaLoading, error: schemaError } = useStepSchema(() => ({
  kind: 'pipeline',
  url: form.value.url || (form.value.is_nfcore && form.value.name ? `https://github.com/${form.value.name}` : undefined),
  version: form.value.version,
}))
const boundParams = computed(() => Object.fromEntries(
  form.value.id
    ? inputsOfStep(graphStore.inputs, form.value.id).filter(e => e.input.bound_by === 'bind').map(e => [e.param, e.input.name])
    : [],
))
const references = computed(() => graphStore.getReferenceTargets(form.value.id))
// Errors no field of this form shows (e.g. a global setting the step conflicts with)
const FORM_FIELDS = ['name', 'url', 'version', 'description', 'params_file', 'nf_config', 'nf_profile', 'main_script', 'is_nfcore']
const otherErrors = computed(() => unshownErrors(errors.value, FORM_FIELDS))
const paramErrors = ref<{ byParam: Record<string, string[]>, general: string[] }>({ byParam: {}, general: [] })

function inputForParam(param: string) {
  return inputFor(param, form.value.name, graphStore.inputs, schema.value?.[param])
}

const hasParams = computed(() => !!form.value.params && Object.keys(form.value.params).length > 0)
const paramsYaml = computed(() => form.value.params ? YAML.stringify(form.value.params).trim() : '')

// File rows of the read-only view
const pathRows = computed(() => [
  { field: 'params_file', icon: 'mdi-file-document-outline', label: 'Params file', value: form.value.params_file },
  { field: 'nf_config', icon: 'mdi-cog-outline', label: 'Nextflow config', value: form.value.nf_config },
  { field: 'main_script', icon: 'mdi-script-text-outline', label: 'Main script', value: form.value.main_script },
].filter(r => r.value))
</script>

<template>
  <!-- View -->
  <div v-if="!isEditing" class="pt-1 pb-2">
    <p v-if="form.description" class="text-body-2 muted mb-2">{{ form.description }}</p>

    <div class="d-flex flex-wrap align-center ga-1 mb-1">
      <v-chip v-if="form.version" size="small" prepend-icon="mdi-tag-outline" :title="form.version">
        {{ shortVersion(form.version) }}
      </v-chip>
      <v-chip v-if="form.is_nfcore" size="small" prepend-icon="$nfcore">nf-core</v-chip>
      <v-chip v-if="form.nf_profile" size="small" prepend-icon="mdi-account-cog-outline" title="Nextflow profile">
        {{ form.nf_profile }}
      </v-chip>
    </div>
    <a v-if="form.url" class="detail-row detail-row-link text-primary d-flex align-center ga-1 text-body-2" :href="form.url" target="_blank">
      <v-icon icon="mdi-link-variant" size="14" class="flex-shrink-0" />
      <span class="text-truncate">{{ form.url }}</span>
      <v-icon icon="mdi-open-in-new" size="12" class="flex-shrink-0" />
    </a>
    <div v-for="row in pathRows" :key="row.field" class="detail-row d-flex align-center ga-1 text-body-2" :title="row.label">
      <v-icon :icon="row.icon" size="14" class="flex-shrink-0" />
      <code class="path-text flex-grow-1">{{ row.value }}</code>
      <v-btn
        :icon="copiedField === row.field ? 'mdi-check' : 'mdi-content-copy'"
        size="x-small" variant="text" density="compact" :ripple="false" flat class="flex-shrink-0"
        @click.stop="copyPath(row.value!, row.field)" />
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
    <div class="d-flex align-center ga-2">
      <v-autocomplete
        v-if="form.is_nfcore"
        label="Pipeline"
        v-model="form.name"
        :items="nfCorePipelines"
        variant="outlined" density="compact" hide-details="auto"
        @update:modelValue="handleUpdatePipeline"
        :error-messages="errors.name ?? (pipelineStore.initError ? [pipelineStore.initError] : [])"
        class="flex-grow-1" />
      <v-text-field
        v-else
        v-model="form.name"
        label="Pipeline name"
        variant="outlined" density="compact" hide-details="auto"
        :error-messages="errors.name"
        class="flex-grow-1" />
      <v-switch
        v-model="form.is_nfcore"
        true-icon="$nfcore" false-icon="mdi-close"
        density="compact" color="primary" hide-details inset
        class="flex-grow-0"
        title="nf-core pipeline" />
    </div>

    <v-text-field
      v-if="!form.is_nfcore"
      v-model="form.url"
      label="Repository URL"
      prepend-inner-icon="mdi-link-variant"
      variant="outlined" density="compact" hide-details="auto"
      :error-messages="errors.url" />

    <v-autocomplete
      v-if="form.is_nfcore"
      label="Version"
      v-model="form.version"
      :items="selectedPipelineVersions"
      prepend-inner-icon="mdi-tag-outline"
      variant="outlined" density="compact" hide-details="auto"
      :error-messages="errors.version" />
    <v-text-field
      v-else
      label="Version (tag, branch or commit)"
      v-model="form.version"
      prepend-inner-icon="mdi-tag-outline"
      variant="outlined" density="compact" hide-details="auto"
      :error-messages="errors.version" />

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
      <v-textarea
        v-if="!form.is_nfcore"
        v-model="form.description"
        label="Description"
        variant="outlined" density="compact" rows="1" auto-grow hide-details="auto" />
      <v-text-field
        v-model="form.params_file"
        label="Params file"
        placeholder="YAML file, relative to the config file" persistent-placeholder
        prepend-inner-icon="mdi-file-document-outline"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.params_file">
        <template #append-inner>
          <PathPicker pick="config" :value="form.params_file" @pick="(p) => form.params_file = p" />
        </template>
      </v-text-field>
      <v-text-field
        v-model="form.nf_config"
        label="Nextflow config"
        placeholder="Path, relative to the config file" persistent-placeholder
        prepend-inner-icon="mdi-cog-outline"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.nf_config">
        <template #append-inner>
          <PathPicker pick="file" :value="form.nf_config" @pick="(p) => form.nf_config = p" />
        </template>
      </v-text-field>
      <v-text-field
        v-model="form.nf_profile"
        label="Nextflow profile(s)"
        placeholder="e.g. docker,test" persistent-placeholder
        prepend-inner-icon="mdi-account-cog-outline"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.nf_profile" />
      <v-text-field
        v-model="form.main_script"
        label="Main script"
        placeholder="Entry script, if not main.nf" persistent-placeholder
        prepend-inner-icon="mdi-script-text-outline"
        variant="outlined" density="compact" hide-details="auto" clearable
        :error-messages="errors.main_script" />
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
  text-decoration: none;
}
.detail-row-link {
  text-decoration: none;
  transition: opacity 0.15s;
}
.detail-row-link:hover {
  opacity: 0.8;
}
.detail-row-link:hover span {
  text-decoration: underline;
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
