<script setup lang="ts">
import { ref, computed } from 'vue';
import { usePipelineStore, useGraphStore } from '../store';
import { extractFieldErrors } from '../utils';
import type { APINfPipelineNodeData } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import CustomFileInput from './CustomFileInput.vue';
import YamlEditor from './YamlEditor.vue';

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
</script>

<template>
  <v-card-text v-if="!isEditing" class="content ma-0 pa-0">
    <p v-show="!!form.description">
      <strong>{{ form.description }}</strong>
    </p>
    <p v-show="form.params_file">
      Params File: <code>{{ form.params_file }}</code>
    </p>
    <v-card-actions class="justify-space-between">
      <v-btn
        :href="form.url"
        target="_blank"
        variant="text"
        append-icon="mdi-open-in-new"
        class=" text-none text-truncate">
        go to code
      </v-btn>
      <div>
        <v-btn @click.stop="editDetail">Edit</v-btn>
        <v-btn @click.stop="handleDelete" color="error">Delete</v-btn>
      </div>
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
          :error-messages="errors.name"
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