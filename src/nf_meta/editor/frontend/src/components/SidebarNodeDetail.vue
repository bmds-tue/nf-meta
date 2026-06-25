<script setup lang="ts">
import { computed, ref } from 'vue';
import { useEditorStore } from '../store';
import type { APINodeData, APINfPipelineNodeData, APINfModuleNodeData, SideBarDetail, NewNodeData, WorkflowTypeValue } from '../types';
import { WorkflowType } from '../types';
import SidebarPipelineDetail from './SidebarPipelineDetail.vue';
import SidebarModuleDetail from './SidebarModuleDetail.vue';

const editorStore = useEditorStore()

const props = defineProps<SideBarDetail<APINodeData | NewNodeData>>()

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
  if (confirmedType.value === WorkflowType.NF_PIPELINE) return 'Add Pipeline'
  if (confirmedType.value === WorkflowType.NF_MODULE) return 'Add Module'
  return 'Add Workflow'
})

const displayVersion = computed(() => {
  return 'version' in props.detailData ? props.detailData.version : undefined
})

const nodeId = computed(() => 'id' in props.detailData ? props.detailData.id : undefined)
const isMouseOver = ref(false)
const isHovered = computed(() => !!nodeId.value && editorStore.hoveredNodeId === nodeId.value && !isMouseOver.value)
const isFlashing = computed(() => !!nodeId.value && editorStore.flashingNodeId === nodeId.value)

function onSaved(newNodeData?: APINodeData) {
  if (isNew.value) {
    removeDetail()
    if (newNodeData?.id) {
      editorStore.addNodeToSideBar(newNodeData, true)
      editorStore.flashNode(newNodeData.id)
    }
  } else if (nodeId.value) {
    editorStore.flashNode(nodeId.value)
  }
}
</script>

<template>
<v-card class="mb-2 mt-2"
  :class="{
    'workflow-node-nfcore': confirmedType === WorkflowType.NF_PIPELINE && 'is_nfcore' in detailData && detailData.is_nfcore,
    'workflow-node-module': confirmedType === WorkflowType.NF_MODULE,
    'detail-hovered': isHovered || isFlashing,
  }"
  @mouseenter="isMouseOver = true; editorStore.setHoveredNodeId(nodeId)"
  @mouseleave="isMouseOver = false; editorStore.setHoveredNodeId(undefined)">
  <v-card-title
    class="node-title d-flex justify-space-between align-center w-100"
    @click="!isActive ? expandDetails() : collapseDetails()"
  >
    <div class="d-flex align-center flex-grow-1 flex-shrink-1" style="min-width: 0;">
      <strong class="text-truncate mr-2" :class="isNew ? 'font-italic' : ''">{{ displayName }}</strong>
      <v-chip v-if="displayVersion" size="small">{{ displayVersion }}</v-chip>
      <v-chip v-if="confirmedType === WorkflowType.NF_MODULE" size="small" color="success" class="ml-1">module</v-chip>
    </div>
    <div class="d-flex align-center">
      <v-icon :icon="isActive ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="20" class="ml-1" />
      <v-btn
        @click.stop="removeDetail"
        icon="mdi-close"
        flat
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
      :is-new="isNew"
      @saved="onSaved"
      @deleted="removeDetail"
    />

    <SidebarModuleDetail
      v-if="isActive && confirmedType === WorkflowType.NF_MODULE"
      :initial-value="moduleData"
      :is-new="isNew"
      @saved="onSaved"
      @deleted="removeDetail"
    />
  </v-card-text>
</v-card>
</template>

<style scoped>
.node-title {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s;
}
.node-title:hover {
  background-color: rgba(var(--v-theme-onSurface), 0.06);
}
.v-card {
  transition: box-shadow 0.2s;
}
.detail-hovered {
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.4) !important;
}
</style>
