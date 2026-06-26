import type { FieldError } from './types'
import { WorkflowType } from './types'

/**
 * Converts the flat FieldError list returned by the API into a per-field
 * error map for a single workflow form.
 *
 * Filtering: only errors whose workflow_id matches the given workflowId, or
 * whose workflow_id is null (errors that apply globally / have no specific owner),
 * are included.
 *
 * Prefix stripping: the API encodes the discriminated-union type tag into field
 * paths (e.g. "nf-pipeline.url", "nf-module.params"). When the first path
 * segment is a known WorkflowType value, it is stripped so that form fields
 * can bind directly to bare names ("url", "params") without knowing the type.
 *
 * Returns a Record mapping each field name to the list of error messages for
 * that field, ready to pass as :error-messages to Vuetify inputs.
 */
export function extractFieldErrors(fieldErrors: FieldError[], workflowId: string): Record<string, string[]> {
    const result: Record<string, string[]> = {}
    const discriminators = new Set<string>(Object.values(WorkflowType))
    for (const err of fieldErrors.filter(e => e.workflow_id === workflowId || e.workflow_id === null)) {
        const parts = err.field.split('.')
        const field = parts.length > 1 && discriminators.has(parts[0]!)
            ? parts.slice(1).join('.')
            : err.field
        if (!result[field]) result[field] = []
        result[field]!.push(err.message)
    }
    return result
}
