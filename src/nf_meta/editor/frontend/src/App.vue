<script setup lang="ts">
import { ref } from 'vue'
import { VueFlow, type Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

const nodes = ref<Node[]>([
  {
    id: '1',
    position: { x: 250, y: 150 },
    data: { label: 'Hello Vue Flow' },
    type: 'default',
  },
])
</script>

<template>
  <div style="width: 100vw; height: 100vh;">
    <VueFlow :nodes="nodes" fit-view>
      <Background />
      <Controls />
    </VueFlow>
  </div>
</template>