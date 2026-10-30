<script setup lang="ts">
import { nextTick, ref, watch } from "vue"
import { Codemirror } from "vue-codemirror"
import { yaml as langyaml } from "@codemirror/lang-yaml"
import YAML, { YAMLParseError } from "yaml"
import { linter, type Diagnostic } from "@codemirror/lint"
import { EditorView, keymap, ViewPlugin, Decoration, type DecorationSet, type ViewUpdate, placeholder } from "@codemirror/view"
import { Prec, RangeSetBuilder } from "@codemirror/state"
import { oneDark } from "@codemirror/theme-one-dark"
import {
  autocompletion,
  startCompletion,
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete"
import { useGraphStore, useEditorStore } from "../store"
import { lintInputReferences, lintReferenceCount } from "../utils"

const props = defineProps<{
  modelValue?: object
  hint?: string
  nodeId?: string
  serverError?: string
}>()

const emit = defineEmits<{
  (e: "update:modelValue", value: object | undefined): void
  (e: "save"): void
    }>()

const graphStore = useGraphStore()
const editorStore = useEditorStore()

const paramsString = props.modelValue ? YAML.stringify(props.modelValue) : ""
const code = ref(paramsString)
const error = ref<string>("")

// Emit parsed params on every valid YAML change so v-model stays live.
// Explicit save() is still needed only for the @save event (Cmd+S / API call).
watch(code, (newCode) => {
  try {
    emit("update:modelValue", YAML.parse(newCode))
    error.value = ""
  } catch {
    // don't emit on parse error — keep last valid modelValue
  }
})


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
  input:     Decoration.mark({ class: "cm-ref-input" }),      // ids in ${inputs:ids}
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

          // ${inputs:<name>}: the namespace styled like ":params:", the name as an input
          if (nodeId === "inputs" && text[match.index + 2 + nodeId.length] === ":") {
            const rest = text.slice(match.index + 2 + nodeId.length + 1)
            const name = rest.match(/^[^}:\s]*/)?.[0] ?? ""
            const closed = rest[name.length] === "}"
            builder.add(cursor, cursor + 2, refMark.delimiter)
            cursor += 2
            builder.add(cursor, cursor + nodeId.length + 1, refMark.params)
            cursor += nodeId.length + 1
            if (name) builder.add(cursor, cursor + name.length, refMark.input)
            cursor += name.length
            if (closed) builder.add(cursor, cursor + 1, refMark.delimiter)
            REF_PATTERN.lastIndex = Math.max(REF_PATTERN.lastIndex, cursor - from + (closed ? 1 : 0))
            continue
          }

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
  ".cm-ref-input":     { color: "#c678dd" },
})

// ==== AUTOCOMPLETION ==============================
async function referenceCompletionSource(
  context: CompletionContext
): Promise<CompletionResult | null> {
  const line = context.state.doc.lineAt(context.pos)
  const textBefore = line.text.slice(0, context.pos - line.from)

  // ${inputs:<partial>  ->  suggest inputs that a reference may use
  const inputMatch = textBefore.match(/(?<!\\)\$\{inputs:([^:}]*)$/)
  if (inputMatch) {
    const partial = inputMatch[1] ?? ""
    const from = context.pos - partial.length
    const closed = context.state.doc.sliceString(context.pos, context.pos + 1) === "}"
    const options = graphStore.inputs
      .filter((input) => !input.definition?.bind?.length)
      .map((input) => ({
        label: input.name,
        detail: input.declared ? input.description || undefined : "implicit",
        apply: closed ? input.name : input.name + "}",
      }))
    return { from, options, validFor: /^[^:}]*$/ }
  }

  // Stage 2 - inside ${nodeId:params:<partial> ->  suggest param keys
  const paramMatch = textBefore.match(/(?<!\\)\$\{([^:}]+):params:([^}]*)$/)
  if (paramMatch) {
    const nodeId = paramMatch[1] ?? ""
    const partial = paramMatch[2] ?? ""
    const from = context.pos - partial.length
    try {
      const options = graphStore.getReferencableParams(nodeId).map((key) => ({
        label: key,
        apply: key,
      }))
      return { from, options, validFor: /^[^}]*$/ }
    } catch {
      return null
    }
  }

  // Stage 1 - ${<partial>  ->  suggest the steps that can be referenced (connected ones first)
  const nodeMatch = textBefore.match(/(?<!\\)\$\{([^:}]*)$/)
  if (nodeMatch) {
    const partial = nodeMatch[1] ?? ""
    const from = context.pos - partial.length
    try {
      const options: { label: string, apply: string, detail?: string }[] = graphStore.getReferenceTargets(props.nodeId)
        .filter((target) => target.params.length > 0)
        .map((target) => ({
        label: `${target.stepId} (${target.stepName})`,
        apply: target.stepId + ":params:",
        detail: target.connected ? "connected" : "saving adds an edge",
      }))
      options.push({ label: "inputs", apply: "inputs:" })
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

  // Steps this one can reference; a connected one needs no new edge
  const targets = graphStore.getReferenceTargets(props.nodeId)
  const referable = new Map(targets.map((t) => [t.stepId, t.connected]))
  const existing = new Set(graphStore.nodeData.map((n) => n.id))

  // Matches complete references only: ${nodeId}  or  ${nodeId:params:key}
  const pattern = /(?<!\\)\$\{([^:}]*)(?::params:([^}]*))?\}/g
  const text    = code.value  // read from the ref, not the view, to stay reactive

  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const nodeId   = match[1] ?? ""
    const paramKey = match[2] ?? ""  // undefined if no :params: section
    const from     = match.index
    const to       = from + match[0].length
    if (nodeId === "inputs") continue  // ${inputs} without a name; checked below

    if (nodeId) {
      if (!existing.has(nodeId)) {
        diagnostics.push({ from, to, severity: "error", message: `No step "${nodeId}"` })
      } else if (!referable.has(nodeId)) {
        diagnostics.push({
          from, to, severity: "error",
          message: nodeId === props.nodeId
            ? "A step can't reference its own params"
            : `"${nodeId}" runs after this step; referencing it would make a cycle`,
        })
      } else if (!referable.get(nodeId)) {
        diagnostics.push({ from, to, severity: "info", message: `Saving adds an edge from "${nodeId}" to this step` })
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
      // set in the step's params or filled by an input
      if (!graphStore.getReferencableParams(nodeId).includes(paramKey)) {
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

  for (const problem of lintInputReferences(text, graphStore.inputs)) {
    diagnostics.push({ ...problem, severity: "error" })
  }
  for (const problem of lintReferenceCount(text)) {
    diagnostics.push({ ...problem, severity: "error" })
  }

  return diagnostics
})

// ─── Global save (Cmd/Ctrl+S) ─────────────────────────────────────────────────
// useHotkey skips contenteditable targets, so we intercept Cmd+S inside
// CodeMirror directly. Returning true prevents the browser's Save Page default.

const globalSaveKeymap = Prec.high(keymap.of([{
  key: "Mod-s",
  run() {
    if (save() && !graphStore.filename) {
      editorStore.openSaveDialog()
    }
    return true
  }
}]))

// ─── Combined extensions ──────────────────────────────────────────────────────

const extensions = [
  langyaml(),
  fullHeightTheme,
  oneDark,
  globalSaveKeymap,
]

// Only add the node references features if YAML-Editor is used in node
// details: global params pass an empty nodeId, a step not saved yet none
if (props.nodeId !== "") {
  const nodeRefExtensions = [
    referenceHighlighter,
    referenceHighlightTheme,
    referenceLinter,
    completionTriggerKeymap,
    smartBackspaceKeymap,
    autocompletion({ override: [referenceCompletionSource] }),
    placeholder("Define Workflow Params here as yaml. \n\nThey overwrite global params \nand complement a params-file. \n\nUse '${}' to reference \npredecessor nodes' params, \ne.g. ${n01:params:outdir}, \nor a run input with ${inputs:<name>}")
  ]
  extensions.push(nodeRefExtensions)
} else {
  extensions.push(
    placeholder("Define global params here as yaml. \n\nThey are applied to all workflows.")
  )
}

// ─── Adding params from outside (param pills) ─────────────────────────────────

let view: EditorView | undefined

function onReady(payload: { view: EditorView }) {
  view = payload.view
}

// Set `key` to `value`: replace its value if the params have it, otherwise
// append `key: value` as a new line; put the cursor at the end of that line
function addParam(key: string, value: string) {
  const doc = YAML.parseDocument(code.value)
  if (!doc.errors.length && doc.has(key)) {
    doc.set(key, value)
    code.value = doc.toString()
    nextTick(() => {
      if (!view) return
      view.focus()
      const line = code.value.split("\n").findIndex(l => l.startsWith(`${key}:`))
      if (line >= 0) view.dispatch({ selection: { anchor: view.state.doc.line(line + 1).to } })
    })
    return
  }
  const line = `${key}: ${value}`
  const text = code.value.trim() ? `${code.value.replace(/\s*$/, "")}\n${line}\n` : `${line}\n`
  code.value = text
  nextTick(() => {
    if (!view) return
    view.focus()
    view.dispatch({ selection: { anchor: Math.min(text.length - 1, view.state.doc.length) } })
  })
}

defineExpose({ addParam })

// ─── Save ─────────────────────────────────────────────────────────────────────

function save(): boolean {
  try {
    error.value = ""
    const params = YAML.parse(code.value)
    emit("update:modelValue", params)
    emit("save")
    return true
  } catch (err: unknown) {
    if (err instanceof YAMLParseError) {
      error.value = err.message
    } else {
      console.log(err)
    }
    return false
  }
}
</script>

<template>
  <p v-show="error || serverError" style="color: rgb(var(--v-theme-error))">
    {{ error || serverError }}
  </p>
  <Codemirror v-model="code" :extensions="extensions" @ready="onReady" />
  <small>{{ hint }}</small>
</template>