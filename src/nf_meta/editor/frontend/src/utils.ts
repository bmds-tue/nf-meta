import YAML, { isMap, isScalar } from 'yaml'
import type { APIInput, APIInputDefinition, APINodeData, APIWarning, FieldError, ParamSpec, StepSchema } from './types'
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

export type ReferenceParam = {
    key: string,
    // The value as written, or the input's name for a param filled by an input
    value: string,
    // Set when an input fills the param (with bind: or as ${inputs:<name>})
    input?: string,
}

export type ReferenceTarget = {
    stepId: string,
    stepName: string,
    // Already a direct predecessor; otherwise saving adds the edge
    connected: boolean,
    params: ReferenceParam[],
}

/**
 * The steps whose params step `stepId` can reference, `${<step>:params:<key>}`,
 * each with the params that have a value: set in its params, or filled by an
 * input (`bind:` or `${inputs:<name>}`). Every step is offered except `stepId`
 * itself and the steps after it (a reference to those would make a cycle).
 * Direct predecessors come first and are marked `connected`; for the others
 * saving adds the edge. Pass no `stepId` for a step that isn't saved yet.
 */
export function referenceTargets(
    nodes: APINodeData[], edges: { source: string, target: string }[], stepId?: string, inputs: APIInput[] = [],
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
            params: referencableParams(node, inputs),
        }))
        .sort((a, b) => Number(b.connected) - Number(a.connected))
}

/** The params of `node` that have a value: set in its params or filled by an input. */
export function referencableParams(node: APINodeData, inputs: APIInput[]): ReferenceParam[] {
    const params = new Map<string, ReferenceParam>()
    for (const [key, value] of Object.entries(node.params ?? {})) {
        if (value === null || value === undefined || value === '') continue
        const text = typeof value === 'string' ? value : JSON.stringify(value)
        const whole = text.match(new RegExp(`^${INPUT_REF.source}$`))
        params.set(key, whole ? { key, value: whole[1]!, input: whole[1]! } : { key, value: text })
    }
    for (const { param, input } of inputsOfStep(inputs, node.id ?? '')) {
        if (input.bound_by === 'bind' && !params.has(param)) params.set(param, { key: param, value: input.name, input: input.name })
    }
    return [...params.values()].sort((a, b) => a.key.localeCompare(b.key))
}

/**
 * Why input `name` can't be deleted, from the errors the API returned: the
 * steps that would be left without a value for a required param (by step
 * name), or the errors as they are.
 */
export function inputDeleteProblem(name: string, fieldErrors: FieldError[], nodes: APINodeData[]): string {
    const required: string[] = []
    const other: string[] = []
    for (const err of fieldErrors) {
        const param = err.field.replace(/^params\./, '')
        const step = nodes.find(n => n.id === err.workflow_id)
        const where = step ? `${step.name ?? step.id} (${step.id})` : (err.workflow_id ?? err.field)
        if (err.workflow_id && /^Required parameter/.test(err.message)) required.push(`'${param}' of ${where}`)
        else other.push(err.workflow_id ? `${where} · ${param}: ${err.message}` : err.message)
    }
    if (required.length && !other.length) {
        return `Can't delete '${name}': it fills ${required.join(', ')}, which ${required.length === 1 ? 'is' : 'are'} required. ` +
            'Give the param a value in the step first.'
    }
    return `Can't delete '${name}': ${[...required.map(r => `${r} would be unset`), ...other].join('; ')}`
}

export type ParamRow = {
    name: string,
    spec?: ParamSpec,
    required: boolean,
    // The value in the step's params (undefined: not set)
    value: unknown,
    // Filled by this input with bind: (not in the step's params)
    boundBy?: string,
}

/**
 * The rows of a step's params form, in order: the schema's required params
 * (set or not), then params filled by a `bind:` input, then the other params
 * the step sets (optional ones of the schema, then unknown ones, each sorted).
 */
export function paramRows(
    schema: StepSchema | null | undefined, params: Record<string, unknown> | undefined, bound: Record<string, string>,
): ParamRow[] {
    const values = params ?? {}
    const specs = schema ?? {}
    const rows: ParamRow[] = []
    const seen = new Set<string>()
    const push = (name: string) => {
        if (seen.has(name)) return
        seen.add(name)
        rows.push({ name, spec: specs[name], required: !!specs[name]?.required, value: values[name], boundBy: bound[name] })
    }
    Object.keys(specs).filter(name => specs[name]!.required).sort().forEach(push)
    Object.keys(bound).sort().forEach(push)
    Object.keys(values).filter(name => name in specs).sort().forEach(push)
    Object.keys(values).filter(name => !(name in specs)).sort().forEach(push)
    return rows
}

/**
 * The API's field errors for one step's params, by param (`params.<name>`),
 * and the ones about the params as a whole. Same filtering as
 * `extractFieldErrors`.
 */
export function paramFieldErrors(
    fieldErrors: FieldError[], workflowId: string | null,
): { byParam: Record<string, string[]>, general: string[] } {
    const byParam: Record<string, string[]> = {}
    const general: string[] = []
    const discriminators = new Set<string>(Object.values(WorkflowType))
    for (const err of fieldErrors.filter(e => workflowId === null || e.workflow_id === workflowId || e.workflow_id === null)) {
        const parts = err.field.split('.')
        const field = parts.length > 1 && discriminators.has(parts[0]!) ? parts.slice(1).join('.') : err.field
        if (field.startsWith('params.')) (byParam[field.slice('params.'.length)] ??= []).push(err.message)
        else if (field === 'params') general.push(err.message)
    }
    return { byParam, general }
}

/** A form field's text as the param's value: numbers for numeric params, '' as unset. */
export function toParamValue(text: unknown, spec?: ParamSpec): unknown {
    if (text === null || text === undefined || text === '') return undefined
    if ((spec?.type === 'integer' || spec?.type === 'number') && typeof text === 'string' && text.trim() !== '') {
        const n = Number(text)
        if (!Number.isNaN(n)) return n
    }
    return text
}

/** `params` without empty values ('' or null), as saved; undefined if none are left. */
export function withoutEmptyValues(params: object | undefined): object | undefined {
    // not a mapping (e.g. a list typed in the YAML editor): left for the backend to refuse
    if (!params || typeof params !== 'object' || Array.isArray(params)) return params
    const kept = Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined)
    return kept.length ? Object.fromEntries(kept) : undefined
}

/**
 * A value that starts with a step reference, split into the reference and
 * the text after it: `${n01:params:outdir}/x.csv` -> n01, outdir, `/x.csv`.
 * Undefined for other values.
 */
export function splitLeadingReference(value: unknown): { stepId: string, key: string, rest: string } | undefined {
    if (typeof value !== 'string') return undefined
    const match = value.match(/^\$\{([^}:]+):params:([^}]+)\}([\s\S]*)$/)
    return match ? { stepId: match[1]!, key: match[2]!, rest: match[3]! } : undefined
}

export type AddableParam = { name: string, required: boolean, hidden: boolean, description?: string }

/**
 * The params of `schema` that can be added: all those not set yet (`set`),
 * required ones first, hidden ones last, each group sorted.
 */
export function addableParams(schema: StepSchema | null | undefined, set: Iterable<string>): AddableParam[] {
    const done = new Set(set)
    const rank = (p: AddableParam) => (p.required ? 0 : p.hidden ? 2 : 1)
    return Object.entries(schema ?? {})
        .filter(([name]) => !done.has(name))
        .map(([name, spec]) => ({ name, required: !!spec.required, hidden: !!spec.hidden, description: spec.description }))
        .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
}

/**
 * The messages of `errors` (as from `extractFieldErrors`) that no field of a
 * form shows, labelled with their field, e.g. a global setting a step's
 * change conflicts with: `nextflow_version: …`.
 */
export function unshownErrors(errors: Record<string, string[]>, shown: Iterable<string>): string[] {
    const fields = new Set(shown)
    return Object.entries(errors)
        .filter(([field]) => !fields.has(field) && field !== 'params')
        .flatMap(([field, messages]) => messages.map(m => (field ? `${field}: ${m}` : m)))
}

const STEP_REF_GLOBAL = /(?<!\\)\$\{[^}:]+:(?:params|outputs):[^}]+\}/g

/**
 * Params in a step's params YAML whose value contains more than one step
 * reference (a value can contain one, with text around it), as the backend
 * reports them. Positions are offsets into `text`; nothing if `text` isn't
 * valid YAML.
 */
export function lintReferenceCount(text: string): TextProblem[] {
    const doc = YAML.parseDocument(text)
    if (doc.errors.length || !isMap(doc.contents)) return []
    const problems: TextProblem[] = []
    for (const pair of doc.contents.items) {
        const value = pair.value
        if (!isScalar(value) || typeof value.value !== 'string' || !value.range) continue
        const count = [...value.value.matchAll(STEP_REF_GLOBAL)].length
        if (count > 1) {
            const param = isScalar(pair.key) ? String(pair.key.value) : ''
            problems.push({
                from: value.range[0], to: value.range[1],
                message: `'${param}' contains ${count} references; a param value can contain one reference to another step's param, with text around it`,
            })
        }
    }
    return problems
}

/** The separator a path of the editor's machine uses: `\\` for Windows paths, else `/`. */
export function pathSeparator(path: string): string {
    return /^[A-Za-z]:\\/.test(path) || (path.includes('\\') && !path.includes('/')) ? '\\' : '/'
}

/** The last part of a path: a file or folder name. */
export function baseName(path: string): string {
    return path.split(/[\\/]/).filter(Boolean).pop() ?? ''
}

/** The folder a path is in: everything before its last part. */
export function folderOf(path: string): string {
    const sep = pathSeparator(path)
    const trimmed = path.endsWith(sep) && path.length > 1 ? path.slice(0, -1) : path
    const cut = trimmed.lastIndexOf(sep)
    if (cut < 0) return ''
    return cut === 0 ? sep : trimmed.slice(0, cut)
}

/** `path` cut from the front to at most `max` characters, keeping its last folders whole: `…/a/b`. */
export function shortPath(path: string, max = 40): string {
    if (path.length <= max) return path
    const sep = pathSeparator(path)
    const parts = path.split(sep).filter(Boolean)
    let kept = parts.pop() ?? ''
    while (parts.length && kept.length + parts[parts.length - 1].length + 3 <= max) {
        kept = parts.pop() + sep + kept
    }
    return `…${sep}${kept}`
}

/** `name` in the folder `folder`. */
export function joinPath(folder: string, name: string): string {
    const sep = pathSeparator(folder)
    return folder.endsWith(sep) ? folder + name : folder + sep + name
}

/** The folders from the root down to `path`, each as a label and its full path. */
export function pathCrumbs(path: string): { label: string, path: string }[] {
    const sep = pathSeparator(path)
    const parts = path.split(sep).filter(Boolean)
    const rootIsSlash = sep === '/' && path.startsWith('/')
    const crumbs = rootIsSlash ? [{ label: '/', path: '/' }] : []
    let current = rootIsSlash ? '' : undefined
    for (const part of parts) {
        current = current === undefined ? (sep === '\\' ? part + sep : part) : (current.endsWith(sep) ? current + part : current + sep + part)
        crumbs.push({ label: part, path: current })
    }
    return crumbs
}

/** What a path picker chooses: `config` (a .yaml/.yml file), any `file`, a `folder`, or either (`path`). */
export type PathPick = 'config' | 'file' | 'folder' | 'path'

/**
 * The picker for a value of JSON-Schema `format` (or nf-core module `type`), or none when the
 * value isn't a path.
 */
export function pathPick(format?: string, type?: string): PathPick | undefined {
    switch (format ?? '') {
        case 'file-path':
        case 'file-path-pattern':
            return 'file'
        case 'directory-path':
            return 'folder'
        case 'path':
            return 'path'
    }
    if (type && type in MODULE_TYPES) return pathPick(MODULE_TYPES[type]!.format)
    return undefined
}

/** Whether `value` is an `http(s)://` (or other `scheme://`) location rather than a local path. */
export function isUrl(value?: string | null): boolean {
    return /^[a-z][a-z0-9+.-]*:\/\//i.test(value ?? '')
}

export type WarningGroup = {
    key: string,
    entries: { message: string, steps: string[] }[],
}

// Warnings grouped by the config key they are about (a step's key without the
// `steps.<id>.` prefix), each message once with the steps it was reported for
export function groupWarnings(warnings: APIWarning[]): WarningGroup[] {
    const groups = new Map<string, Map<string, string[]>>()
    for (const w of warnings) {
        const prefix = w.workflow_id ? `steps.${w.workflow_id}.` : ''
        const key = prefix && w.yaml_path.startsWith(prefix) ? w.yaml_path.slice(prefix.length) : w.yaml_path
        const messages = groups.get(key) ?? new Map<string, string[]>()
        groups.set(key, messages)
        const steps = messages.get(w.message) ?? []
        messages.set(w.message, steps)
        if (w.workflow_id && !steps.includes(w.workflow_id)) steps.push(w.workflow_id)
    }
    return [...groups].map(([key, messages]) => ({
        key,
        entries: [...messages].map(([message, steps]) => ({ message, steps })),
    }))
}
