<script setup>
import { ref, watch } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml } from "@codemirror/lang-yaml"
import { EditorView } from "@codemirror/view"
import { oneDark } from "@codemirror/theme-one-dark"


const props = defineProps({
    modelValue: String
})

const emit = defineEmits(["update:modelValue"])

const code = ref(props.modelValue || "")

const fullHeightTheme = EditorView.theme({
  "&": { height: "99%" },
  ".cm-scroller": { overflow: "auto" }
})

watch(code, v => emit("update:modelValue", v))
watch(() => props.modelValue, v => code.value = v)
</script>

<template>
    <v-container class="ma-0 mt-2 pa-0">
        <v-text-field 
            label="Params File"
            variant="outlined">
        </v-text-field>
    </v-container>
    <Codemirror
        v-model="code"
        :extensions="[yaml(), fullHeightTheme, oneDark]"
    />
</template>

<style scoped>
</style>