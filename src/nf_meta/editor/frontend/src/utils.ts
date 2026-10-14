import type { FieldError } from './types'
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
