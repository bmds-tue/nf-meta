<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useModuleStore, useGraphStore } from '../store';
import { extractFieldErrors } from '../utils';
import type { APINfModuleNodeData, APINodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import YamlEditor from './YamlEditor.vue';
import YAML from 'yaml';

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

const form = ref<APINfModuleNodeData>({ ...props.initialValue })
const isEditing = ref(props.isNew)
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})
const moduleVersions = ref<string[]>([])
const versionsLoading = ref(false)
const versionsError = ref<string>()

// nf-core/ prefix stripped for the API, shown with prefix in the autocomplete
const moduleNames = computed(() => {
  return moduleStore.nfCoreModules?.map(m => `nf-core/${m.name}`) ?? []
})

async function handleUpdateModule() {
  const name = form.value.name
  form.value.version = undefined
  versionsError.value = undefined
  if (!name) {
    moduleVersions.value = []
    return
  }
  const shortName = name.replace(/^nf-core\//, '')
  versionsLoading.value = true
  try {
    moduleVersions.value = (await moduleStore.fetchModuleVersions(shortName)).map(nfmv => nfmv.version)
    // auto-select the latest version if none set yet
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

// Load versions when editing an existing module (name already set)
watch(() => props.initialValue.name, async (name) => {
  if (name && !props.isNew) {
    form.value.name = name
    await handleUpdateModule()
  }
}, { immediate: true })

async function submitForm(e: SubmitEventPromise) {
  const { valid } = await e
  if (!valid) return
  errors.value = {}
  saving.value = true
  try {
    const previousIds = new Set(graphStore.nodes.map(n => n.id))
    const result = await graphStore.saveNode({ ...form.value })
    if (result.ok) {
      isEditing.value = false
      if (props.isNew) {
        const newNode = graphStore.nodes.find(n => !previousIds.has(n.id))
        emit('saved', newNode?.data)
      } else {
        emit('saved')
      }
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
  <div class="m-0 p-0">

    <div v-if="!isEditing" class="pa-3">
      <div class="d-flex flex-column ga-2 mb-2">
        <div v-if="form.version" class="detail-row d-flex align-center ga-2 text-body-2">
          <v-icon icon="mdi-tag-outline" size="16" class="flex-shrink-0" />
          <span>{{ form.version }}</span>
        </div>
        <div class="detail-row d-flex align-center ga-2 text-body-2">
          <v-icon icon="$nfcore" size="16" class="flex-shrink-0" />
          <span>nf-core community module</span>
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
        <div class="text-caption mb-1">Params</div>
        <pre class="yaml-preview">{{ paramsYaml }}</pre>
      </template>
      <p v-else class="text-body-2 mb-0">No params configured.</p>

      <v-card-actions class="justify-end pa-0 pt-3">
        <v-btn size="small" @click.stop="editDetail">Edit</v-btn>
        <v-btn size="small" color="error" @click.stop="handleDelete">Delete</v-btn>
      </v-card-actions>
    </div>

    <div v-else class="content">
      <v-form @submit.prevent="submitForm">
        <v-autocomplete
          label="Module name"
          v-model="form.name"
          :items="moduleNames"
          variant="outlined"
          density="compact"
          @update:modelValue="handleUpdateModule"
          :error-messages="errors.name ?? (moduleStore.initError ? [moduleStore.initError] : [])">
        </v-autocomplete>

        <v-autocomplete
          label="Version"
          v-model="form.version"
          :items="moduleVersions"
          key="version"
          :loading="versionsLoading"
          :disabled="!form.name"
          variant="outlined"
          density="compact"
          :error-messages="errors.version ?? (versionsError ? [versionsError] : [])">
        </v-autocomplete>

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
    </div>
  </div>
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