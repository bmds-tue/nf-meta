<script setup lang="ts">
import { ref } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml as langyaml } from "@codemirror/lang-yaml"
import YAML, { YAMLParseError } from "yaml"
import { EditorView, keymap } from "@codemirror/view"
import { Prec } from "@codemirror/state"
import { oneDark } from "@codemirror/theme-one-dark"
import {
  autocompletion,
  startCompletion,
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete"
import { useGraphStore } from "../store"

const props = defineProps<{
  modelValue?: object
  hint?: string
  nodeId: string
}>()

const emit = defineEmits<{
  (e: "update:modelValue", value: object | undefined): void
  (e: "save"): void
    }>()

const graphStore = useGraphStore()

const paramsString = props.modelValue ? YAML.stringify(props.modelValue) : ""
const code = ref(paramsString)
const error = ref<string>("")

const fullHeightTheme = EditorView.theme({
  "&": { height: "99%" },
  ".cm-scroller": { overflow: "auto" },
})

// ==== AUTOCOMPLETION ==============================
async function referenceCompletionSource(
  context: CompletionContext
): Promise<CompletionResult | null> {
  const line = context.state.doc.lineAt(context.pos)
  const textBefore = line.text.slice(0, context.pos - line.from)

  // Stage 2 - inside ${nodeId:params:<partial> ->  suggest param keys
  const paramMatch = textBefore.match(/(?<!\\)\$\{([^:}]+):params:([^}]*)$/)
  if (paramMatch) {
    const nodeId = paramMatch[1] ?? ""
    const partial = paramMatch[2] ?? ""
    const from = context.pos - partial.length
    try {
      const params = await graphStore.getParams(nodeId) as Record<string, unknown>
      const options = Object.keys(params ?? {}).map((key) => ({
        label: key,
        apply: key,
      }))
      return { from, options, validFor: /^[^}]*$/ }
    } catch {
      return null
    }
  }

  // Stage 1 - ${<partial>  ->  suggest predecessor node IDs
  const nodeMatch = textBefore.match(/(?<!\\)\$\{([^:}]*)$/)
  if (nodeMatch) {
    const partial = nodeMatch[1] ?? ""
    const from = context.pos - partial.length
    try {
      const predecessors = await graphStore.getPredecessors(props.nodeId) as { id: string }[]
      const options = predecessors.map((node) => ({
        label: node.id,
        apply: node.id + ":params:",
      }))
      return { from, options, validFor: /^[^:}]*$/ }
    } catch {
      return null
    }
  }

  return null
}

// ==== KEYMAP TRIGGERS =========================================
//  ($, {, : are not word chars by default so CM won't auto-fire)
const completionTriggerKeymap = keymap.of(
  (["$", "{", ":"] as const).map((char) => ({
    key: char,
    run(view: EditorView) {
      view.dispatch(view.state.replaceSelection(char))
      startCompletion(view)
      return true
    },
  }))
)

// ==== Smart backspace ===========================================
// Deletes whole reference segments rather than single characters:
//
//   ${n02:params:outdi  -> (1st ⌫)  ${n02:params:
//   ${n02:params:       -> (2nd ⌫)  ${
//   ${                  -> (3rd ⌫)  (empty)

const smartBackspaceKeymap = Prec.high(
  keymap.of([
    {
      key: "Backspace",
      run(view: EditorView) {
        const { state } = view
        const sel = state.selection.main
        if (sel.from !== sel.to) return false

        const pos        = sel.from
        const line       = state.doc.lineAt(pos)
        const textBefore = line.text.slice(0, pos - line.from)

        // Case: cursor is right after "${nodeId:params:" with optional partial key
        const fullMatch = textBefore.match(/(\$\{)([^:}]+)(:params:)([^}]*)$/)
        if (fullMatch) {
          const paramKey = fullMatch[4] ?? ""
          if (paramKey.length > 0) {
            // Mid-param-key — fall through to default character delete
            return false
          }
          // Right after ":params:" — delete it wholesale
          const segment = fullMatch[3]  ?? ""
          view.dispatch({ changes: { from: pos - segment.length, to: pos } })
          return true
        }

        // Case: cursor is right after "${" with optional partial node id
        const openMatch = textBefore.match(/(\$\{)([^:}]*)$/)
        if (openMatch) {
          const nodeId = openMatch[2] ?? ""
          if (nodeId.length > 0) {
            // Mid-node-id — fall through to default character delete
            return false
          }
          // Right after "${" with nothing typed — delete ${ and auto-closed } if present
          const open      = openMatch[1] ?? ""      // "${"
          const nextChar  = state.doc.sliceString(pos, pos + 1)
          const deleteEnd = nextChar === "}" ? pos + 1 : pos
          view.dispatch({ changes: { from: pos - open.length, to: deleteEnd } })
          return true
        }

        return false
      },
    },
  ])
)

// ─── Combined extensions ──────────────────────────────────────────────────────

const extensions = [
  langyaml(),
  fullHeightTheme,
  oneDark,
  autocompletion({ override: [referenceCompletionSource] }),
  completionTriggerKeymap,
  smartBackspaceKeymap,
]

// ─── Save ─────────────────────────────────────────────────────────────────────

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
  <Codemirror v-model="code" :extensions="extensions" />
  <small>{{ hint }}</small>
  <v-btn @click="save">Save changes</v-btn>
</template>