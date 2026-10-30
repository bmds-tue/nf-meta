import YAML, { isMap, isScalar } from 'yaml'
import type { APIInput, APIInputDefinition, APINodeData, FieldError, ParamSpec, StepSchema } from './types'
import { WorkflowType } from './types'

/**
 * Converts the flat FieldError list returned by the API into a per-field
 * error map for a single workflow form.
 *
 * Filtering: only errors whose workflow_id matches the given workflowId, or
 * whose workflow_id is null (errors that apply globally / have no specific owner),
 * are included. Pass workflowId = null to include all errors, e.g. for a node
 * that hasn't been saved yet and so has no id to match against.
 *
 * Prefix stripping: the API encodes the discriminated-union type tag into field
 * paths (e.g. "nf-pipeline.url", "nf-module.params"). When the first path
 * segment is a known WorkflowType value, it is stripped so that form fields
 * can bind directly to bare names ("url", "params") without knowing the type.
 *
 * Per-param bucketing: dynamic param-schema errors are keyed per-param (e.g.
 * "params.outdir") to support future fine-grained UI, but there is currently
 * only a single params form field. Any field of the form "params.<name>" is
 * bucketed back under "params" so its message still surfaces there.
 *
 * Returns a Record mapping each field name to the list of error messages for
 * that field, ready to pass as :error-messages to Vuetify inputs.
 */
export function extractFieldErrors(fieldErrors: FieldError[], workflowId: string | null): Record<string, string[]> {
    const result: Record<string, string[]> = {}
    const discriminators = new Set<string>(Object.values(WorkflowType))
    for (const err of fieldErrors.filter(e => workflowId === null || e.workflow_id === workflowId || e.workflow_id === null)) {
        const parts = err.field.split('.')
        const stripped = parts.length > 1 && discriminators.has(parts[0]!)
            ? parts.slice(1).join('.')
            : err.field
        const field = stripped !== 'params' && stripped.startsWith('params.') ? 'params' : stripped
        if (!result[field]) result[field] = []
        result[field]!.push(err.message)
    }
    return result
}

const INPUT_REF = /(?<!\\)\$\{inputs:([^}:]+)\}/
const INPUT_REF_GLOBAL = new RegExp(INPUT_REF.source, 'g')

/**
 * Splits the API's field errors for a save of input `name`: errors on the
 * input itself (field `inputs.<name>.<key>`), keyed by `<key>` ("" for the
 * input as a whole), and all other messages (e.g. a step param that conflicts
 * with the input), each prefixed with where it is.
 */
export function extractInputFieldErrors(
    fieldErrors: FieldError[], name: string,
): { fields: Record<string, string[]>, other: string[] } {
    const prefix = `inputs.${name}`
    const fields: Record<string, string[]> = {}
    const other: string[] = []
    for (const err of fieldErrors) {
        if (err.field === prefix || err.field.startsWith(prefix + '.')) {
            const key = err.field.slice(prefix.length + 1).split('.')[0] ?? ''
            ;(fields[key] ??= []).push(err.message)
        } else {
            const where = err.workflow_id ? `${err.workflow_id}.${err.field.replace(/^params\./, '')}` : err.field
            other.push(where ? `${where}: ${err.message}` : err.message)
        }
    }
    return { fields, other }
}

/** The inputs filling a param of step `stepId`, as param -> input. */
export function inputsOfStep(inputs: APIInput[], stepId: string): { param: string, input: APIInput }[] {
    const result: { param: string, input: APIInput }[] = []
    for (const input of inputs) {
        for (const binding of input.bindings) {
            const dot = binding.indexOf('.')
            if (binding.slice(0, dot) === stepId) result.push({ param: binding.slice(dot + 1), input })
        }
    }
    return result.sort((a, b) => a.param.localeCompare(b.param))
}

/** Whether `input` fills a param of step `stepId`. */
export function inputFillsStep(input: APIInput | undefined, stepId: string): boolean {
    return !!input?.bindings.some(b => b.startsWith(stepId + '.'))
}

export type TextProblem = { from: number, to: number, message: string }

/**
 * Problems with `${inputs:<name>}` in a step's params YAML, as the backend
 * reports them on save: a reference that is not the param's whole value, and
 * a reference to an input that is already bound with `bind:`. Positions are
 * offsets into `text`. Returns nothing if `text` is not valid YAML.
 */
export function lintInputReferences(text: string, inputs: APIInput[]): TextProblem[] {
    const doc = YAML.parseDocument(text)
    if (doc.errors.length || !isMap(doc.contents)) return []
    const problems: TextProblem[] = []
    for (const pair of doc.contents.items) {
        const value = pair.value
        if (!isScalar(value) || typeof value.value !== 'string' || !value.range) continue
        const param = isScalar(pair.key) ? String(pair.key.value) : ''
        const tokens = [...value.value.matchAll(INPUT_REF_GLOBAL)]
        if (!tokens.length) continue
        const [from, to] = value.range
        const whole = value.value.match(new RegExp(`^${INPUT_REF.source}$`))
        if (!whole) {
            problems.push({
                from, to,
                message: `'${tokens[0]![0]}' must be the whole value of '${param}'; declare an input for the full value instead`,
            })
            continue
        }
        const name = whole[1]!
        if (inputs.find(i => i.name === name)?.definition?.bind?.length) {
            problems.push({
                from, to,
                message: `input '${name}' is bound with 'bind:' in inputs.${name}; bind it in one place (remove this reference or the 'bind:' entry)`,
            })
        }
    }
    return problems
}

/** `definition` without empty values (blank strings, empty lists), as sent to the API. */
export function cleanInputDefinition(definition: APIInputDefinition): APIInputDefinition {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(definition)) {
        if (value === undefined || value === null || value === '') continue
        if (Array.isArray(value) && value.length === 0) continue
        result[key] = value
    }
    return result as APIInputDefinition
}

/**
 * `version` with every commit hash in it (12 or more hex digits) cut to its
 * first 8 characters, for display: `0.0.0-6c4ed3a9b1f2e3d4` -> `0.0.0-6c4ed3a9`.
 */
export function shortVersion(version: string | undefined): string | undefined {
    return version?.replace(/\b[0-9a-f]{12,}\b/gi, hash => hash.slice(0, 8))
}

// nf-core module meta.yml types, as JSON-Schema type + format (as the backend translates them)
const MODULE_TYPES: Record<string, { type: string, format: string }> = {
    file: { type: 'string', format: 'file-path' },
    directory: { type: 'string', format: 'directory-path' },
    path: { type: 'string', format: 'path' },
}

/**
 * Whether a param with `spec` can be filled by the existing input `input`
 * through a `${inputs:...}` reference: the input isn't bound with `bind:`, and
 * its type and format (where both are known) match the param's.
 */
export function canShareInput(input: APIInput, spec?: ParamSpec): boolean {
    if (input.definition?.bind?.length) return false
    const param = MODULE_TYPES[spec?.type ?? ''] ?? { type: spec?.type, format: spec?.format }
    for (const key of ['type', 'format'] as const) {
        const ours = param[key]
        const theirs = input.schema[key]
        if (ours && theirs && ours !== theirs) return false
    }
    return true
}

/**
 * The input to fill `param` (with `spec`) of a step named `stepName`: the
 * input named after the param, shared if it exists and can be
 * (`canShareInput`); otherwise one prefixed with the step's name
 * (`rnaseq_input`), numbered if needed. `shared` tells whether it exists.
 */
export function inputFor(
    param: string, stepName: string | undefined, inputs: APIInput[], spec?: ParamSpec,
): { name: string, shared: boolean } {
    const byName = new Map(inputs.map(i => [i.name, i]))
    const clean = (text: string) => text.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '')
    const step = clean(stepName?.split('/').pop() ?? '')
    const candidates = [clean(param), step ? `${step}_${clean(param)}` : ''].filter(Boolean)
    for (const name of candidates) {
        const existing = byName.get(name)
        if (!existing) return { name, shared: false }
        if (canShareInput(existing, spec)) return { name, shared: true }
    }
    const base = candidates[candidates.length - 1] ?? 'input'
    let n = 2
    while (byName.has(`${base}_${n}`)) n++
    return { name: `${base}_${n}`, shared: false }
}

export type ParamSuggestions = { required: string[], optional: string[] }

/**
 * The params of `schema` a step doesn't set yet, as required and optional
 * (hidden ones left out), sorted. `set` are the params with a value or a
 * `bind:` input.
 */
export function paramSuggestions(schema: StepSchema | null | undefined, set: Iterable<string>): ParamSuggestions {
    const done = new Set(set)
    const required: string[] = []
    const optional: string[] = []
    for (const [param, spec] of Object.entries(schema ?? {})) {
        if (done.has(param)) continue
        if (spec.required) required.push(param)
        else if (!spec.hidden) optional.push(param)
    }
    return { required: required.sort(), optional: optional.sort() }
}

export type ReferenceTarget = {
    stepId: string,
    stepName: string,
    // Already a direct predecessor; otherwise saving adds the edge
    connected: boolean,
    params: { key: string, value: string }[],
}

/**
 * The steps whose params step `stepId` can reference, `${<step>:params:<key>}`,
 * with their params that have a value: every step except `stepId` itself and
 * the steps after it (a reference to those would make a cycle). Direct
 * predecessors come first and are marked `connected`; for the others saving
 * adds the edge. Pass no `stepId` for a step that isn't saved yet.
 */
export function referenceTargets(
    nodes: APINodeData[], edges: { source: string, target: string }[], stepId?: string,
): ReferenceTarget[] {
    const after = new Set<string>()
    const queue = stepId ? [stepId] : []
    while (queue.length) {
        const current = queue.shift()!
        for (const e of edges) {
            if (e.source === current && !after.has(e.target)) {
                after.add(e.target)
                queue.push(e.target)
            }
        }
    }
    const predecessors = new Set(edges.filter(e => e.target === stepId).map(e => e.source))
    return nodes
        .filter((node): node is APINodeData & { id: string } => !!node.id && node.id !== stepId && !after.has(node.id))
        .map(node => ({
            stepId: node.id,
            stepName: node.name ?? node.id,
            connected: predecessors.has(node.id),
            params: Object.entries(node.params ?? {})
                .filter(([, value]) => value !== null && value !== undefined && value !== '')
                .map(([key, value]) => ({ key, value: typeof value === 'string' ? value : JSON.stringify(value) }))
                .sort((a, b) => a.key.localeCompare(b.key)),
        }))
        .sort((a, b) => Number(b.connected) - Number(a.connected))
}
