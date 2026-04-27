<script setup lang="ts">
import { ref } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml as langyaml } from "@codemirror/lang-yaml"
import YAML, { YAMLParseError } from "yaml"
import { linter, type Diagnostic } from "@codemirror/lint"
import { EditorView, keymap, ViewPlugin, Decoration, type DecorationSet, type ViewUpdate } from "@codemirror/view"
import { Prec, RangeSetBuilder } from "@codemirror/state"
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


// ==== THEMES ================================================
const fullHeightTheme = EditorView.theme({
  "&": { height: "99%" },
  ".cm-scroller": { overflow: "auto" },
})


// ==== REFERENCE SYNTAX HIGHLIGHTING =========================
// Colors are from the oneDark palette so they blend naturally.

const refMark = {
  delimiter: Decoration.mark({ class: "cm-ref-delimiter" }),  // ${ and }
  nodeId:    Decoration.mark({ class: "cm-ref-node" }),       // n01
  params:    Decoration.mark({ class: "cm-ref-params" }),     // :params:
  paramKey:  Decoration.mark({ class: "cm-ref-paramkey" }),   // outdir
}

// Matches: ${nodeId}  or  ${nodeId:params:key}  (not preceded by \)
const REF_PATTERN = /(?<!\\)\$\{([^:}]*)(?:(:params:)([^}]*))?(\})?/g

const referenceHighlighter = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet

    constructor(view: EditorView) {
      this.decorations = this.build(view)
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.viewportChanged)
        this.decorations = this.build(update.view)
    }

    build(view: EditorView): DecorationSet {
      const builder = new RangeSetBuilder<Decoration>()

      for (const { from, to } of view.visibleRanges) {
        const text = view.state.doc.sliceString(from, to)
        REF_PATTERN.lastIndex = 0

        let match: RegExpExecArray | null
        while ((match = REF_PATTERN.exec(text)) !== null) {
          const base      = from + match.index
          const nodeId    = match[1] ?? ""  // may be empty string
          const paramsSep = match[2]  // ":params:" or undefined
          const paramKey  = match[3]  // may be empty string or undefined
          const closing   = match[4]  // "}" or undefined

          let cursor = base

          // "${" — 2 chars
          builder.add(cursor, cursor + 2, refMark.delimiter)
          cursor += 2

          // node id
          if (nodeId.length > 0) {
            builder.add(cursor, cursor + nodeId.length, refMark.nodeId)
          }
          cursor += nodeId.length

          // ":params:"
          if (paramsSep) {
            builder.add(cursor, cursor + paramsSep.length, refMark.params)
            cursor += paramsSep.length

            // param key
            if (paramKey && paramKey.length > 0) {
              builder.add(cursor, cursor + paramKey.length, refMark.paramKey)
              cursor += paramKey.length
            }
          }

          // "}"
          if (closing) {
            builder.add(cursor, cursor + 1, refMark.delimiter)
          }
        }
      }

      return builder.finish()
    }
  },
  { decorations: (v) => v.decorations }
)

const referenceHighlightTheme = EditorView.baseTheme({
  ".cm-ref-delimiter": { color: "#abb2bf", },
  ".cm-ref-params":    { color: "#5a6478", fontStyle: "italic" },
  ".cm-ref-node":      { color: "#61afef" },
  ".cm-ref-paramkey":  { color: "#61afef" },
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


// ==== Linter: validate all ${nodeId:params:key} references =================

const referenceLinter = linter(async (): Promise<Diagnostic[]> => {
  const diagnostics: Diagnostic[] = []

  let predecessors: { id: string }[]
  try {
    predecessors = await graphStore.getPredecessors(props.nodeId) as { id: string }[]
  } catch {
    return []  // can't validate without predecessor list
  }
  const validNodeIds = new Set(predecessors.map((n) => n.id))

  // Matches complete references only: ${nodeId}  or  ${nodeId:params:key}
  const pattern = /(?<!\\)\$\{([^:}]*)(?::params:([^}]*))?\}/g
  const text    = code.value  // read from the ref, not the view, to stay reactive

  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const nodeId   = match[1] ?? ""
    const paramKey = match[2] ?? ""  // undefined if no :params: section
    const from     = match.index
    const to       = from + match[0].length

    if (nodeId) {
      if (!validNodeIds.has(nodeId)) {
        diagnostics.push({
          from,
          to,
          severity: "error",
          message:  `Referenced node is not a predecessor: "${nodeId}"`,
        })
      }
    } else {
      diagnostics.push({
        from,
        to,
        severity: "error",
        message: "Node reference missing"
      })
    }

    if (paramKey) {
      let params: Record<string, unknown>
      try {
        params = await graphStore.getParams(nodeId) as Record<string, unknown>
      } catch {
        continue
      }
      if (!Object.prototype.hasOwnProperty.call(params ?? {}, paramKey)) {
        diagnostics.push({
          from,
          to,
          severity: "error",
          message:  `Node "${nodeId}" has no param "${paramKey}"`,
        })
      }
    } else {
      diagnostics.push({
        from,
        to,
        severity: "error",
        message: "Param key missing"
      })
    }
  }

  return diagnostics
})

// ─── Combined extensions ──────────────────────────────────────────────────────


const extensions = [
  langyaml(),
  fullHeightTheme,
  oneDark,
  referenceHighlighter,
  referenceHighlightTheme,
  referenceLinter,
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