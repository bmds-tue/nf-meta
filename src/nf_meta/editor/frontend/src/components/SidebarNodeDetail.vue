<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useEditorStore, useGraphStore } from '../store';
import type { APINodeData, SideBarDetail } from '../types';
import Icon from './Icon.vue'
import WorkflowNode from './WorkflowNode.vue';

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const props = defineProps<SideBarDetail<APINodeData>>()
const active = computed(() => editorStore.sideBarActiveDetailId == props.id)

const form = ref<APINodeData>({ ...props.detailData })

function save(nodeData: APINodeData) {
    graphStore.saveNode(nodeData)
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

function editDetail() {

}

</script>

<template>
<div class="workflow-node sidebar-detail" :class="{'workflow-node-nfcore': form.is_nfcore}">
  <div class="header">
    <b>DETAIL: {{ props.detailData.name }} </b>
    <div class="header-actions">
      <button @click.stop="editDetail">
        <Icon name="edit" />
      </button>
      <button v-show="!active" @click.stop=expandDetails>
        <Icon name="collapse" />
      </button>
      <button v-show="active" @click.stop=collapseDetails>
        <Icon name="expand" />
      </button>
      <button @click.stop=removeDetail>
        <Icon name="close" />
      </button>
    </div>
  </div>

  <div v-show="active" class="content">
      <p v-show="!!props.detailData.pipeline_description">
        Description: {{ props.detailData.pipeline_description }}
      </p>
      <p> 
        Location: {{ props.detailData.pipeline_location }}
      </p>
      <p>
        Version: {{ props.detailData.pipeline_version }}
      </p>
      <p>Pipeline Location: {{ props.detailData.pipeline_location }}</p>
  </div>
</div>
</template>

<style scoped>
.sidebar-detail {
  margin: 20px 5px 20px 5px;
}
.header {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
}
.header-actions {
  flex-wrap: nowrap;
}
.header button {
  width: 24px; 
  height: 24px;
  padding: 2px;
  border-radius: 8px;
  box-shadow: 0 0 5px rgba(0, 0, 0, 0.5);
}
</style>