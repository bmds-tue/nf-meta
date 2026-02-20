<script setup lang="ts">
import { computed, ref } from 'vue';
import { useEditorStore, useGraphStore } from '../store';
import type { APINodeData, SideBarDetail } from '../types';
import WorkflowNode from './WorkflowNode.vue';

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const props = defineProps<SideBarDetail<APINodeData>>()
const active = computed(() => editorStore.sideBarActiveDetailId == props.id)

const form = ref<APINodeData>({ ...props.detailData })

function save(nodeData: APINodeData) {
    graphStore.saveNode(nodeData)
}

</script>

<template>
<div class="workflow-node" :class="{'workflow-node-nfcore': form.is_nfcore}" @click="editorStore.setActiveSidebarDetailId(props.id)">
  <div class="header">
    <h3>DETAIL: {{ props.detailData.name }} </h3>
  </div>

  <!-- <WorkflowNode :data="props.detailData" :preview="true"></WorkflowNode> -->

  <div v-show="active" class="content">
    <!-- form -->
     FOOBARBAZ {{ props.detailData.pipeline_location }}
  </div>
</div>
</template>