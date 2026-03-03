<script setup lang="ts">
import { computed, ref } from 'vue';
import { useEditorStore, useGraphStore, usePipelineStore } from '../store';
import type { APINodeData, SideBarDetail } from '../types';
import type { SubmitEventPromise } from 'vuetify';

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
    form.value.url = selectedPipeline.value.url
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
              errors.value = result.fieldErrors
            }
          } else {
            removeDetail()
          }
        })
    }
  })
}

function handleReset() {
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
<v-card class="workflow-node sidebar-detail" :class="{'workflow-node-nfcore': form.is_nfcore}">
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
        :icon="isActive ? 'collapse' : 'expand'"
        height="30"
        width="30"
        class="ml-1"
      >
      </v-btn>
      <v-btn 
        @click.stop="removeDetail"
        icon="close"
        height="30"
        width="30"
        class="ml-1"
        >
      </v-btn>
    </div>
  </v-card-title>

  <v-card-text v-show="isActive && !isEditing" class="content">
    <strong v-show="!!form.description">
      Description: {{ form.description }}
    </strong>
    <p>Pipeline Location: <a :href="form.url" target="_blank"> {{ form.url }} </a></p>
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
      <v-container>
        <input
          id="is-nfcore-cb" 
          type="checkbox"
          v-model="form.is_nfcore" />
        <label for="is-nfcore-cb">nf-core pipeline</label>
      </v-container>

      <v-text-field
        v-if="!form.is_nfcore"
        v-model="form.name"
        label="Pipeline name"
        variant="outlined"
        :error-messages="errors.name">
      </v-text-field>
      <v-text-field
        v-if="!form.is_nfcore"
        v-model="form.url"
        label="Pipeline URL"
        variant="outlined"
        :error-messages="errors.url">
      </v-text-field>
      <v-text-field
        v-if="!form.is_nfcore"
        label="Version"
        v-model="form.version"
        variant="outlined"
        :error-messages="errors.version">
      </v-text-field>

      <v-autocomplete
        v-if="form.is_nfcore"
        label="Pipeline name"
        v-model="form.name"
        :items="nfCorePipelines"
        variant="outlined"
        @update:modelValue="handleUpdatePipeline"
        :error-messages="errors.name">
      </v-autocomplete>
      <v-autocomplete
        v-if="form.is_nfcore"
        label="Version"
        v-model="form.version"
        :items="selectedPipelineVersions"
        variant="outlined"
        :error-messages="errors.version">
      </v-autocomplete>

      <v-textarea
        :label="form.is_nfcore ? 'Pipeline Description (autofilled from nf-core)' : 'Pipeline Description'"
        v-model="form.description"
        variant="outlined"
        :readonly="form.is_nfcore">
      </v-textarea>

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
.sidebar-detail {
  margin: 20px 5px 20px 5px;
}
</style>