<script setup lang="ts">
import { ref } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml as langyaml } from "@codemirror/lang-yaml"
import YAML, { YAMLParseError } from "yaml"
import { EditorView } from "@codemirror/view"
import { oneDark } from "@codemirror/theme-one-dark"

const props = defineProps<{
    modelValue?: object
    hint?: string
}>()

const emit = defineEmits<{
    (e: "update:modelValue", value: object | undefined): void
    (e: "save"): void
}>()

const paramsString = props.modelValue ? YAML.stringify(props.modelValue) : ""
const code = ref(paramsString)
const error = ref<string>("")

const fullHeightTheme = EditorView.theme({
  "&": { height: "99%" },
  ".cm-scroller": { overflow: "auto" }
})

function save() {
    try {
        error.value = ""
        const params = YAML.parse(code.value)
        emit("update:modelValue", params)
        emit("save")
    } catch (err: unknown) {
        if (err instanceof YAMLParseError) {
            error.value = err.message
        } else {
            console.log(err)
        }
    }
}
</script>

<template>
    <p v-show="error" style="color: rgb(var(--v-theme-error))">
        {{ error }}
    </p>    
    <Codemirror
        v-model="code"
        :extensions="[langyaml(), fullHeightTheme, oneDark]"
    />
    <small> {{ hint }} </small>
    <v-btn 
        @click="save"
    >
        Save changes
    </v-btn>
</template>

<style scoped>
</style>