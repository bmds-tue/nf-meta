<script setup lang="ts">
import { ref, computed } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml as langyaml } from "@codemirror/lang-yaml"
import YAML, { YAMLParseError } from "yaml"
import { EditorView } from "@codemirror/view"
import { oneDark } from "@codemirror/theme-one-dark"
import { useGraphStore } from "../store"
import type { APINodeData } from "../types"

const graphStore = useGraphStore()
const props = defineProps<{nodeData: APINodeData}>()

const paramsString = YAML.stringify(props.nodeData.params)
const code = ref(paramsString || "")
const error = ref<string>("")

const fullHeightTheme = EditorView.theme({
  "&": { height: "99%" },
  ".cm-scroller": { overflow: "auto" }
})

function save() {
    try {
        error.value = ""
        const params = YAML.parse(code.value)
        const nodeUpdate = props.nodeData
        nodeUpdate.params = params
        graphStore.saveNode(nodeUpdate)
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
    <p v-if="error" style="color: rgb(var(--v-theme-error))">
        {{ error }}
    </p>    
    <Codemirror
        v-model="code"
        :extensions="[langyaml(), fullHeightTheme, oneDark]"
    />
    <small> Params defined here do not change your params_file </small>
    <v-btn 
        @click="save"
    >
        Save changes
    </v-btn>
</template>

<style scoped>
</style>