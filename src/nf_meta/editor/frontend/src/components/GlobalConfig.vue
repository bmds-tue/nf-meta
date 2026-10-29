<script setup lang="ts">
import { computed, ref } from 'vue'
import YAML from 'yaml'
import YamlEditor from './YamlEditor.vue'
import { useGraphStore } from '../store'
import type { APIGlobalOptions } from '../types'
import { extractFieldErrors } from '../utils'

const graphStore = useGraphStore()

const isEditing = ref(false)
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})
const form = ref<APIGlobalOptions>({})

const globals = computed(() => graphStore.globalOptions ?? {})
const hasParams = computed(() => !!globals.value.params && Object.keys(globals.value.params).length > 0)
const paramsYaml = computed(() => hasParams.value ? YAML.stringify(globals.value.params).trim() : '')
const isEmpty = computed(() => !hasParams.value && !globals.value.nf_profile && !globals.value.nf_config && !globals.value.nextflow_version)

function startEditing() {
  form.value = { ...globals.value }
  errors.value = {}
  isEditing.value = true
}

function cancel() {
  isEditing.value = false
  errors.value = {}
}

async function save() {
  errors.value = {}
  saving.value = true
  try {
    const result = await graphStore.updateGlobalOptions({
      ...form.value,
      nf_profile: form.value.nf_profile || undefined,
      nf_config: form.value.nf_config || undefined,
      nextflow_version: form.value.nextflow_version || undefined,
    })
    if (result.ok) {
      isEditing.value = false
    } else if (result.fieldErrors) {
      errors.value = extractFieldErrors(result.fieldErrors, '')
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-card class="mt-2">
    <v-card-title class="d-flex align-center ga-2 py-1 text-subtitle-1">
      <v-icon icon="mdi-earth" size="18" />
      <strong>Global settings</strong>
      <v-spacer />
      <v-btn
        v-if="!isEditing"
        icon="mdi-pencil" size="small" variant="text" density="comfortable" title="Edit"
        @click="startEditing" />
    </v-card-title>

    <!-- View -->
    <v-card-text v-if="!isEditing" class="pt-0 pb-2">
      <p class="text-body-2 muted mt-0 mb-2">Applied to every step; a step's own values win.</p>
      <p v-if="isEmpty" class="text-body-2 muted mb-0">None set.</p>
      <template v-else>
        <div class="d-flex flex-wrap align-center ga-1 mb-1">
          <v-chip v-if="globals.nextflow_version" size="small" prepend-icon="mdi-tag-outline" title="Required Nextflow version">
            Nextflow {{ globals.nextflow_version }}
          </v-chip>
          <v-chip v-if="globals.nf_profile" size="small" prepend-icon="mdi-account-cog-outline" title="Nextflow profile(s)">
            {{ globals.nf_profile }}
          </v-chip>
        </div>
        <div v-if="globals.nf_config" class="detail-row d-flex align-center ga-1 text-body-2" title="Nextflow config">
          <v-icon icon="mdi-cog-outline" size="14" class="flex-shrink-0" />
          <code class="path-text">{{ globals.nf_config }}</code>
        </div>
        <template v-if="hasParams">
          <div class="text-caption mt-2">Params</div>
          <pre class="yaml-preview">{{ paramsYaml }}</pre>
        </template>
      </template>
    </v-card-text>

    <!-- Edit -->
    <v-card-text v-else class="pt-0 pb-2">
      <v-form class="compact-form" @submit.prevent="save">
        <v-text-field
          v-model="form.nextflow_version"
          label="Nextflow version"
          hint="e.g. 25.10 or 25.10.4-edge; checked against the installed Nextflow before a run"
          prepend-inner-icon="mdi-tag-outline"
          variant="outlined" density="compact" hide-details="auto" clearable
          :error-messages="errors.nextflow_version" />
        <v-text-field
          v-model="form.nf_profile"
          label="Nextflow profile(s)"
          hint="Comma-separated, e.g. docker,test"
          prepend-inner-icon="mdi-account-cog-outline"
          variant="outlined" density="compact" hide-details="auto" clearable
          :error-messages="errors.nf_profile" />
        <v-text-field
          v-model="form.nf_config"
          label="Nextflow config"
          hint="Relative to the config file"
          prepend-inner-icon="mdi-cog-outline"
          variant="outlined" density="compact" hide-details="auto" clearable
          :error-messages="errors.nf_config" />
        <div class="text-caption">Params</div>
        <p v-if="errors['params']?.length" class="field-error mb-0">{{ errors['params']!.join(' ') }}</p>
        <div class="params-editor">
          <YamlEditor v-model="form.params" node-id="" @save="save" />
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
.compact-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.params-editor {
  height: 200px;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
.detail-row .v-icon {
  opacity: 0.6;
}
.path-text {
  word-break: break-all;
  font-size: 0.8rem;
}
.yaml-preview {
  font-family: monospace;
  font-size: 0.75rem;
  line-height: 1.45;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border-radius: 4px;
  padding: 6px 8px;
  margin: 2px 0 0;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre;
}
</style>
