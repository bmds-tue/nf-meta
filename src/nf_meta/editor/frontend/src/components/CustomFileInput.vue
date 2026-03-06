<script setup lang="ts">
import { ref, watch } from "vue"

const props = defineProps<{
  modelValue?: string
  label?: string
  errorMessages?: string | string[]
}>()

const emit = defineEmits<{
  (e: "update:modelValue", value: string | undefined): void
  (e: "file-selected", file: File | undefined): void
}>()

const file = ref<File | undefined>()

function removeFile() {
  emit("update:modelValue", undefined)
  file.value = undefined
  emit("file-selected", undefined)
}

watch(file, (newFile) => {
    // TODO: This is going to lead to issues 
    // -> we only get the filename here
    // -> the browser does not allow access to 
    // absolute paths by design
    emit("update:modelValue", newFile?.name)
    emit("file-selected", newFile)
})
</script>

<template>
  <div v-if="modelValue && !file" class="mb-2">
    Current {{ label }}: {{ modelValue }}

    <v-btn
      size="small"
      variant="text"
      color="error"
      class="ml-2"
      @click="removeFile"
    >
      Remove / Replace
    </v-btn>
  </div>

  <v-file-input
    v-if="!modelValue || file"
    v-model="file"
    :label="label"
    variant="outlined"
    density="compact"
    clearable
    :error-messages="errorMessages"
  />
</template>