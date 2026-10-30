<script setup lang="ts">
import { INPUT_COLOR } from '../store'
import type { ReferenceTarget } from '../utils'
import ReferenceMenu from './ReferenceMenu.vue'

// The buttons at the end of a param's field: reference and input
defineProps<{
  param: string
  references: ReferenceTarget[]
  inputTitle: string
}>()

const emit = defineEmits<{
  reference: [stepId: string, key: string],
  input: [],
}>()
</script>

<template>
  <!-- stop clicks here from focusing the field or opening its dropdown -->
  <span class="row-actions" @click.stop @mousedown.stop>
    <ReferenceMenu :param="param" :references="references" :size="22" @pick="(stepId, key) => emit('reference', stepId, key)" />
    <v-btn
      icon="mdi-import" size="22" variant="flat" class="pill-btn"
      :color="INPUT_COLOR" :title="inputTitle"
      @click="emit('input')" />
  </span>
</template>

<style scoped>
.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 4px;
}
.pill-btn :deep(.v-icon) {
  color: white;
  font-size: 14px;
}
</style>
