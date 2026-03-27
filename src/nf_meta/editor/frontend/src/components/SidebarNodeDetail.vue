<script setup lang="ts">
import { computed, ref } from 'vue';
import { useEditorStore, useGraphStore, usePipelineStore } from '../store';
import type { APINodeData, SideBarDetail } from '../types';
import type { SubmitEventPromise } from 'vuetify';
import CustomFileInput from './CustomFileInput.vue';

const editorStore = useEditorStore()
const graphStore = useGraphStore()
const pipelineStore = usePipelineStore()

const props = defineProps<SideBarDetail<APINodeData>>()
const form = ref<APINodeData>({ ...props.detailData })
const errors = ref<Record<string, string[]>>({})

const isActive = computed(() => editorStore.sideBarActiveDetailId == props.id)
const isNew = computed(() => Boolean(!props.detailData?.id) )
const isEditing = ref(isNew.value)

const nfCorePipelines = computed(() => {
  return pipelineStore.nfCorePipelines?.map(pipeline => pipeline.name)
})

const selectedPipeline = computed(() => {
  return pipelineStore.nfCorePipelines?.find(
    pipeline => pipeline.name == form.value.name
  )
})

const selectedPipelineVersions = computed(() => {
  if (!selectedPipeline.value) {
    return []
  }
  return selectedPipeline.value.releases.map(release => release.tag_name)
})

function handleUpdatePipeline() {
  if(form.value.name && selectedPipeline.value?.description) {
    form.value.description = selectedPipeline.value.description
    form.value.url = selectedPipeline.value.repository_url
  }
}

function submitForm(e: SubmitEventPromise) {
  e.then(value => {
    if (value.valid) {
      errors.value = {}

      graphStore.saveNode(form.value)
        .then(result => {
          if (!result.ok) {
            if (result?.fieldErrors) {
              errors.value = graphStore.extractFieldErrors(result.fieldErrors, form.value.id ?? "")
            }
          } else {
            removeDetail()
          }
        })
      }
  })
}

function handleReset() {
  errors.value = {}
  form.value = props.detailData
  isEditing.value = false
}

function expandDetails() {
  editorStore.setActiveSidebarDetailId(props.id)
}

function collapseDetails() {
  editorStore.collapseSidebarDetail(props.id)
}

function removeDetail() {
  editorStore.removeSidebarDetail(props.id)
}

function deleteNode() {
  if (props.detailData?.id) {
    graphStore.removeNodeById(props.detailData?.id)
  }
  editorStore.removeSidebarDetail(props.id)
}

function editDetail() {
  isEditing.value = true
  expandDetails()
}

</script>

<template>
<v-card class="workflow-node mb-2 mt-2" :class="{'workflow-node-nfcore': form.is_nfcore}">
  <v-card-title class="d-flex justify-space-between w-100">
    <div class="d-flex flex-grow flex-shrink" style="min-width: 0;">
      <strong class="text-truncate mr-2"> 
        {{ form.name ?? "Add New Workflow" }}
      </strong>
      <v-chip v-if="form.version" size="small">{{ form.version }}</v-chip>
    </div>
    <div class="">
      <v-btn 
        @click.stop="!isActive ? expandDetails() : collapseDetails()"
        :icon="isActive ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        height="30"
        width="30"
        class="ml-1"
      >
      </v-btn>
      <v-btn 
        @click.stop="removeDetail"
        icon="mdi-close"
        height="30"
        width="30"
        class="ml-1"
        >
      </v-btn>
    </div>
  </v-card-title>

  <v-card-text v-show="isActive && !isEditing" class="content">
    <p v-show="!!form.description">
      <strong >
        Description: {{ form.description }}
      </strong>
    </p>
    <div class="d-flex flex-row align-center">
      Pipeline Location:
      <v-btn
        :href="form.url"
        target="_blank"
        variant="text"
        append-icon="mdi-open-in-new"
        class="text-none text-truncate">
        {{ form.url }} 
      </v-btn>
    </div>
    <p v-show="form.params_file">
      Params File: 
      <code>
        {{ form.params_file }} 
      </code>
    </p>
    <v-card-actions>
      <v-btn 
        @click.stop="editDetail"> 
        Edit 
      </v-btn>
      <v-btn
        @click.stop="deleteNode"
        color="error"> 
        Delete
      </v-btn>
    </v-card-actions>
  </v-card-text>

  <v-card-text v-show="isActive && isEditing" class="content">
    <v-form @submit.prevent="submitForm">
      <v-checkbox
        density="compact"
        label="nf-core pipeline" 
        v-model="form.is_nfcore">
      </v-checkbox>
      <v-text-field
        v-if="!form.is_nfcore"
        v-model="form.name"
        label="Pipeline name"
        variant="outlined"
        density="compact"
        :error-messages="errors.name">
      </v-text-field>
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
        label="Pipeline name"
        v-model="form.name"
        :items="nfCorePipelines"
        variant="outlined"
        density="compact"
        @update:modelValue="handleUpdatePipeline"
        :error-messages="errors.name">
      </v-autocomplete>
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
        :label="form.is_nfcore ? 'Pipeline Description (autofilled from nf-core)' : 'Pipeline Description'"
        v-model="form.description"
        variant="outlined"
        density="compact"
        :readonly="form.is_nfcore">
      </v-textarea>

      <CustomFileInput
        v-model="form.params_file"
        label="Params File"
        :error-messages="errors.params_file"
        >
      </CustomFileInput>

      <CustomFileInput
        v-model="form.config_file"
        label="Nextflow Config File"
        :error-messages="errors.config_file"
        >
      </CustomFileInput>

      <v-card-actions>
        <v-btn
          class="me-4"
          type="submit">
          save changes
        </v-btn>
  
        <v-btn 
          @click="handleReset"
          color="error">
          cancel edit
        </v-btn>
      </v-card-actions>
    </v-form>
  </v-card-text> 

</v-card>
</template>

<style scoped>
</style>