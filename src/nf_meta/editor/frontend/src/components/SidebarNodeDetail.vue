<script setup lang="ts">
import { computed, ref } from 'vue';
import { useEditorStore, useGraphStore } from '../store';
import type { APINodeData, APINfPipelineNodeData, APINfModuleNodeData, SideBarDetail, NewNodeData, WorkflowTypeValue } from '../types';
import { WorkflowType } from '../types';
import SidebarPipelineDetail from './SidebarPipelineDetail.vue';
import SidebarModuleDetail from './SidebarModuleDetail.vue';

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const props = defineProps<SideBarDetail<APINodeData | NewNodeData>>()

const errors = ref<Record<string, string[]>>({})
const isActive = computed(() => editorStore.sideBarActiveDetailId == props.id)
const isNew = computed(() => !('id' in props.detailData && props.detailData.id))

// For existing nodes: type is fixed from server data.
// For new nodes: default to NF_PIPELINE so the form is shown immediately.
const confirmedType = ref<WorkflowTypeValue>(
  ('type' in props.detailData && props.detailData.type)
    ? props.detailData.type
    : WorkflowType.NF_PIPELINE
)

const pipelineData = computed<APINfPipelineNodeData>(() => {
  if ('type' in props.detailData && props.detailData.type === WorkflowType.NF_PIPELINE) {
    return props.detailData as APINfPipelineNodeData
  }
  return { type: WorkflowType.NF_PIPELINE }
})

const moduleData = computed<APINfModuleNodeData>(() => {
  if ('type' in props.detailData && props.detailData.type === WorkflowType.NF_MODULE) {
    return props.detailData as APINfModuleNodeData
  }
  return { type: WorkflowType.NF_MODULE }
})

async function onSave(data: APINodeData) {
  errors.value = {}
  const result = await graphStore.saveNode(data)
  if (!result.ok) {
    if (result.fieldErrors) {
      errors.value = graphStore.extractFieldErrors(result.fieldErrors, data.id ?? '')
    }
  } else {
    removeDetail()
  }
}

function onDelete() {
  if ('id' in props.detailData && props.detailData.id) {
    graphStore.removeNodeById(props.detailData.id)
  }
  editorStore.removeSidebarDetail(props.id)
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

const displayName = computed(() => {
  if ('name' in props.detailData && props.detailData.name) return props.detailData.name
  if (confirmedType.value === WorkflowType.NF_PIPELINE) return 'New Pipeline'
  if (confirmedType.value === WorkflowType.NF_MODULE) return 'New Module'
  return 'Add New Node'
})

const displayVersion = computed(() => {
  return 'version' in props.detailData ? props.detailData.version : undefined
})
</script>

<template>
<v-card class="mb-2 mt-2"
  :class="{
    'workflow-node-nfcore': confirmedType === WorkflowType.NF_PIPELINE && 'is_nfcore' in detailData && detailData.is_nfcore,
    'workflow-node-module': confirmedType === WorkflowType.NF_MODULE
  }">
  <v-card-title class="d-flex justify-space-between w-100">
    <div class="d-flex flex-grow flex-shrink" style="min-width: 0;">
      <strong class="text-truncate mr-2" :class="isNew ? 'font-italic' : ''">{{ displayName }}</strong>
      <v-chip v-if="displayVersion" size="small">{{ displayVersion }}</v-chip>
      <v-chip v-if="confirmedType === WorkflowType.NF_MODULE" size="small" color="success" class="ml-1">module</v-chip>
    </div>
    <div>
      <v-btn
        @click.stop="!isActive ? expandDetails() : collapseDetails()"
        :icon="isActive ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        height="30" width="30" class="ml-1">
      </v-btn>
      <v-btn
        @click.stop="removeDetail"
        icon="mdi-close"
        height="30" width="30" class="ml-1">
      </v-btn>
    </div>
  </v-card-title>

  <v-card-text class="pb-0 h-100">
    <v-select v-if="isActive && isNew" 
      v-model="confirmedType"
      :items="Object.values(WorkflowType)"
      variant="outlined"
      density="compact"
    >
    </v-select>

    <SidebarPipelineDetail
      v-if="isActive && confirmedType === WorkflowType.NF_PIPELINE"
      :initial-value="pipelineData"
      :errors="errors"
      :is-new="isNew"
      @save="onSave"
      @delete="onDelete"
    />

    <SidebarModuleDetail
      v-if="isActive && confirmedType === WorkflowType.NF_MODULE"
      :initial-value="moduleData"
      :errors="errors"
      :is-new="isNew"
      @save="onSave"
      @delete="onDelete"
    />
  </v-card-text>
</v-card>
</template>

<style scoped>
</style>
