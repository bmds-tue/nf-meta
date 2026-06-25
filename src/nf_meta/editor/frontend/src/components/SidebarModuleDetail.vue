<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useModuleStore, useGraphStore } from '../store';
import { extractFieldErrors } from '../utils';
import type { APINfModuleNodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import YamlEditor from './YamlEditor.vue';

const props = defineProps<{
  initialValue: APINfModuleNodeData,
  isNew: boolean,
}>()

const emit = defineEmits<{
  saved: [],
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
</script>

<template>
  <div class="m-0 p-0">

    <div v-if="!isEditing" class="content">
      <div class="d-flex align-center">
        <strong>{{ form.name }}</strong>
        <v-chip v-if="form.version" size="small" class="ml-2">{{ form.version }}</v-chip>
      </div>
      <v-card-actions class="justify-end">
        <v-btn @click.stop="editDetail">Edit</v-btn>
        <v-btn @click.stop="handleDelete" color="error">Delete</v-btn>
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