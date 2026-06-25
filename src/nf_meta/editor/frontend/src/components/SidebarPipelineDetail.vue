<script setup lang="ts">
import { ref, computed } from 'vue';
import { usePipelineStore, useGraphStore } from '../store';
import { extractFieldErrors } from '../utils';
import type { APINfPipelineNodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import CustomFileInput from './CustomFileInput.vue';
import YamlEditor from './YamlEditor.vue';
import YAML from 'yaml';

const props = defineProps<{
  initialValue: APINfPipelineNodeData,
  isNew: boolean,
}>()

const emit = defineEmits<{
  saved: [],
  deleted: [],
}>()

const pipelineStore = usePipelineStore()
const graphStore = useGraphStore()

const form = ref<APINfPipelineNodeData>({ ...props.initialValue })
const isEditing = ref(props.isNew)
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})

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
    form.value.url = selectedPipeline.value.repository_url
  }
}

async function submitForm(e: SubmitEventPromise) {
  const { valid } = await e
  if (!valid) return
  errors.value = {}
  saving.value = true
  try {
    const result = await graphStore.saveNode({ ...form.value })
    if (result.ok) {
      isEditing.value = false
      emit('saved')
    } else if (result.fieldErrors) {
      errors.value = extractFieldErrors(result.fieldErrors, form.value.id ?? '')
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
}

function editDetail() {
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

const hasParams = computed(() => !!form.value.params && Object.keys(form.value.params).length > 0)
const paramsYaml = computed(() => form.value.params ? YAML.stringify(form.value.params).trim() : '')
</script>

<template>
  <v-card-text v-if="!isEditing" class="ma-0 pa-3">
    <p v-if="form.description" class="text-body-2 mb-3">{{ form.description }}</p>

    <div class="d-flex flex-column ga-2">
      <div v-if="form.version" class="detail-row d-flex align-center ga-2 text-body-2">
        <v-icon icon="mdi-tag-outline" size="16" class="flex-shrink-0" />
        <span>{{ form.version }}</span>
      </div>
      <div v-if="form.is_nfcore" class="detail-row d-flex align-center ga-2 text-body-2">
        <v-icon icon="$nfcore" size="16" class="flex-shrink-0" />
        <span>nf-core community pipeline</span>
      </div>
      <a v-if="form.url" class="detail-row detail-row-link text-primary d-flex align-center ga-2 text-body-2" :href="form.url" target="_blank">
        <v-icon icon="mdi-link-variant" size="16" class="flex-shrink-0" />
        <span class="text-truncate">{{ form.url }}</span>
        <v-icon icon="mdi-open-in-new" size="12" class="flex-shrink-0" />
      </a>
      <div v-if="form.params_file" class="detail-row d-flex align-start ga-2 text-body-2">
        <v-icon icon="mdi-file-document-outline" size="16" class="flex-shrink-0 mt-1" />
        <code class="path-text flex-grow-1">{{ form.params_file }}</code>
        <v-btn
          :icon="copiedField === 'params_file' ? 'mdi-check' : 'mdi-content-copy'"
          size="x-small" variant="text" :ripple="false" flat class="flex-shrink-0"
          @click.stop="copyPath(form.params_file!, 'params_file')" />
      </div>
      <div v-if="form.config_file" class="detail-row d-flex align-start ga-2 text-body-2">
        <v-icon icon="mdi-cog-outline" size="16" class="flex-shrink-0 mt-1" />
        <code class="path-text flex-grow-1">{{ form.config_file }}</code>
        <v-btn
          :icon="copiedField === 'config_file' ? 'mdi-check' : 'mdi-content-copy'"
          size="x-small" variant="text" :ripple="false" flat class="flex-shrink-0"
          @click.stop="copyPath(form.config_file!, 'config_file')" />
      </div>
    </div>

    <template v-if="hasParams">
      <div class="text-caption mt-3 mb-1">Params</div>
      <pre class="yaml-preview">{{ paramsYaml }}</pre>
    </template>

    <v-card-actions class="justify-end pa-0 pt-3">
      <v-btn size="small" @click.stop="editDetail">Edit</v-btn>
      <v-btn size="small" color="error" @click.stop="handleDelete">Delete</v-btn>
    </v-card-actions>
  </v-card-text>

  <v-card-text v-else class="content ma-0 pa-0">
    <v-form @submit.prevent="submitForm">
      <div class="d-flex align-center ga-2">
        <v-autocomplete
          v-if="form.is_nfcore"
          label="Pipeline name"
          v-model="form.name"
          :items="nfCorePipelines"
          variant="outlined"
          density="compact"
          @update:modelValue="handleUpdatePipeline"
          :error-messages="errors.name ?? (pipelineStore.initError ? [pipelineStore.initError] : [])"
          class="flex-grow-1">
        </v-autocomplete>
        <v-text-field
          v-if="!form.is_nfcore"
          v-model="form.name"
          label="Pipeline name"
          variant="outlined"
          density="compact"
          :error-messages="errors.name"
          class="flex-grow-1">
        </v-text-field>
        <v-switch
          true-icon="$nfcore"
          false-icon="mdi-close"
          density="compact"
          color="primary"
          v-model="form.is_nfcore"
          class="flex-shrink-0 mx-0">
          <template #label>
            <span style="color: rgb(var(--v-theme-nodeNfCoreBorder))"> nf-core </span>
          </template>
        </v-switch>
      </div>

      <v-text-field
        v-if="!form.is_nfcore"
        v-model="form.url"
        label="Pipeline URL"
        variant="outlined"
        density="compact"
        :error-messages="errors.url">
      </v-text-field>
      <v-text-field
        v-if="!form.is_nfcore"
        label="Version"
        v-model="form.version"
        variant="outlined"
        density="compact"
        :error-messages="errors.version">
      </v-text-field>

      <v-autocomplete
        v-if="form.is_nfcore"
        label="Version"
        v-model="form.version"
        :items="selectedPipelineVersions"
        variant="outlined"
        density="compact"
        :error-messages="errors.version">
      </v-autocomplete>

      <v-textarea
        v-if="!form.is_nfcore"
        label="Pipeline Description"
        v-model="form.description"
        variant="outlined"
        density="compact"
        rows="2"
        :readonly="form.is_nfcore">
      </v-textarea>

      <CustomFileInput
        v-model="form.params_file"
        label="Params File"
        :error-messages="errors.params_file">
      </CustomFileInput>

      <CustomFileInput
        v-model="form.config_file"
        label="Nextflow Config File"
        :error-messages="errors.config_file">
      </CustomFileInput>

      <v-label class="mt-2 mb-1">Params</v-label>
      <p v-if="errors['params']?.length" style="color: rgb(var(--v-theme-error)); font-size: 0.85em;" class="mb-1">
        {{ errors['params']!.join(' ') }}
      </p>
      <div style="height: 220px;">
        <YamlEditor
          v-model="form.params"
          :node-id="form.id">
        </YamlEditor>
      </div>

      <v-card-actions class="justify-end">
        <v-btn class="me-4" type="submit" :loading="saving">save changes</v-btn>
        <v-btn @click="handleReset" color="error">cancel edit</v-btn>
      </v-card-actions>
    </v-form>
  </v-card-text>
</template>

<style scoped>
.detail-row {
  min-width: 0;
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
  align-self: flex-start;
}
.yaml-preview {
  font-family: monospace;
  font-size: 0.78rem;
  line-height: 1.5;
  background: rgba(var(--v-theme-onSurface), 0.05);
  border-radius: 4px;
  padding: 8px;
  margin: 0;
  max-height: 110px;
  overflow-y: auto;
  white-space: pre;
}
</style>