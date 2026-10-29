import { describe, expect, it } from 'vitest'
import type { APIInput } from '../types'
import {
    cleanInputDefinition, extractFieldErrors, extractInputFieldErrors,
    inputFillsStep, inputsOfStep, lintInputReferences,
} from '../utils'

function input(name: string, overrides: Partial<APIInput> = {}): APIInput {
    return {
        name, declared: true, definition: {}, bound_by: null, bindings: [], schema: {},
        default: null, description: '', diagnostics: [], ...overrides,
    }
}

describe('extractFieldErrors', () => {
    it('keeps errors of the workflow and unowned ones, strips the type tag', () => {
        const errors = extractFieldErrors([
            { workflow_id: 'n01', field: 'nf-pipeline.url', message: 'bad url' },
            { workflow_id: 'n02', field: 'url', message: 'other node' },
            { workflow_id: null, field: 'params.outdir', message: 'missing' },
        ], 'n01')
        expect(errors).toEqual({ url: ['bad url'], params: ['missing'] })
    })
})

describe('extractInputFieldErrors', () => {
    it('keys errors on the input by keyword and keeps the rest apart', () => {
        const { fields, other } = extractInputFieldErrors([
            { workflow_id: null, field: 'inputs.ids.bind', message: 'no such param' },
            { workflow_id: null, field: 'inputs.ids', message: 'not used' },
            { workflow_id: null, field: 'inputs.idsx.bind', message: 'another input' },
            { workflow_id: 'n01', field: 'params.input', message: 'bound twice' },
        ], 'ids')
        expect(fields).toEqual({ bind: ['no such param'], '': ['not used'] })
        expect(other).toEqual(['inputs.idsx.bind: another input', 'n01.input: bound twice'])
    })
})

describe('inputsOfStep / inputFillsStep', () => {
    const ids = input('ids', { bindings: ['n01.input', 'n02.input'] })
    const genome = input('genome', { bindings: ['n01.genome'] })

    it('lists the inputs filling a step, by param', () => {
        expect(inputsOfStep([ids, genome], 'n01').map(e => [e.param, e.input.name]))
            .toEqual([['genome', 'genome'], ['input', 'ids']])
        expect(inputsOfStep([ids, genome], 'n0')).toEqual([])
    })

    it('matches whole step ids only', () => {
        expect(inputFillsStep(ids, 'n02')).toBe(true)
        expect(inputFillsStep(ids, 'n0')).toBe(false)
        expect(inputFillsStep(undefined, 'n01')).toBe(false)
    })
})

describe('lintInputReferences', () => {
    it('accepts whole-value references', () => {
        expect(lintInputReferences('input: ${inputs:ids}\nother: "${inputs:x}"\n', [])).toEqual([])
    })

    it('rejects a reference that is part of a value', () => {
        const text = 'outdir: results\ninput: ${inputs:dir}/ids.csv\n'
        const [problem, ...rest] = lintInputReferences(text, [])
        expect(rest).toEqual([])
        expect(text.slice(problem!.from, problem!.to)).toBe('${inputs:dir}/ids.csv')
        expect(problem!.message).toContain("must be the whole value of 'input'")
    })

    it('rejects a reference to an input bound with bind:', () => {
        const bound = input('ids', { definition: { bind: ['n01.input'] } })
        const metadataOnly = input('genome', { definition: { description: 'Genome' } })
        const problems = lintInputReferences('input: ${inputs:ids}\ngenome: ${inputs:genome}\n', [bound, metadataOnly])
        expect(problems.map(p => p.message)).toEqual([
            "input 'ids' is bound with 'bind:' in inputs.ids; bind it in one place (remove this reference or the 'bind:' entry)",
        ])
    })

    it('ignores step references, escaped references and invalid YAML', () => {
        expect(lintInputReferences('input: ${n01:params:outdir}/x.csv\nother: \\${inputs:x}/y\n', [])).toEqual([])
        expect(lintInputReferences('input: [unclosed', [])).toEqual([])
    })
})

describe('cleanInputDefinition', () => {
    it('drops empty values but keeps false and 0', () => {
        expect(cleanInputDefinition({ description: '', bind: [], exists: false, minimum: 0, pattern: undefined }))
            .toEqual({ exists: false, minimum: 0 })
    })
})
