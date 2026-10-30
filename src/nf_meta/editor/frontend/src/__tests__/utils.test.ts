import { describe, expect, it } from 'vitest'
import type { APIInput } from '../types'
import {
    cleanInputDefinition, extractFieldErrors, extractInputFieldErrors,
    addableParams, baseName, canShareInput, joinPath, lintReferenceCount, pathCrumbs, unshownErrors, inputDeleteProblem, splitLeadingReference, paramFieldErrors, paramRows, toParamValue, inputFillsStep, inputFor, inputsOfStep, referenceTargets, lintInputReferences, paramSuggestions, shortVersion,
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

describe('shortVersion', () => {
    it('cuts commit hashes to 8 characters', () => {
        expect(shortVersion('0.0.0-6c4ed3a9b1f2e3d4c5b6')).toBe('0.0.0-6c4ed3a9')
        expect(shortVersion('3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a')).toBe('3f2a1b0c')
    })

    it('leaves release tags and short hashes alone', () => {
        expect(shortVersion('3.14.0')).toBe('3.14.0')
        expect(shortVersion('0.0.0-6c4ed3a')).toBe('0.0.0-6c4ed3a')
        expect(shortVersion(undefined)).toBeUndefined()
    })
})

describe('inputFor / canShareInput', () => {
    const fileInput = input('input', { bound_by: 'reference', schema: { type: 'string', format: 'file-path' } })

    it('uses the param name for a new input', () => {
        expect(inputFor('input', 'nf-core/rnaseq', [])).toEqual({ name: 'input', shared: false })
    })

    it('shares an existing input of the same type and format', () => {
        expect(inputFor('input', 'nf-core/rnaseq', [fileInput], { type: 'string', format: 'file-path' }))
            .toEqual({ name: 'input', shared: true })
        expect(inputFor('input', 'nf-core/rnaseq', [fileInput])).toEqual({ name: 'input', shared: true })
    })

    it('uses the step name as prefix when the input can not be shared', () => {
        expect(inputFor('input', 'nf-core/rnaseq', [fileInput], { type: 'string', format: 'directory-path' }))
            .toEqual({ name: 'rnaseq_input', shared: false })
        const bound = input('input', { definition: { bind: ['n01.input'] } })
        expect(inputFor('input', 'nf-core/rnaseq', [bound])).toEqual({ name: 'rnaseq_input', shared: false })
        const both = [bound, input('rnaseq_input', { definition: { bind: ['n02.input'] } })]
        expect(inputFor('input', 'nf-core/rnaseq', both)).toEqual({ name: 'rnaseq_input_2', shared: false })
    })

    it('translates module types', () => {
        expect(canShareInput(fileInput, { type: 'file' })).toBe(true)
        expect(canShareInput(fileInput, { type: 'directory' })).toBe(false)
    })
})

describe('paramSuggestions', () => {
    it('splits unset params into required and optional, without hidden ones', () => {
        const schema = {
            input: { required: true }, outdir: { required: true }, genome: {},
            aligner: {}, monochrome_logs: { hidden: true },
        }
        expect(paramSuggestions(schema, ['outdir', 'aligner'])).toEqual({ required: ['input'], optional: ['genome'] })
        expect(paramSuggestions(null, [])).toEqual({ required: [], optional: [] })
    })
})

describe('referenceTargets', () => {
    const node = (id: string, params: object) => ({ type: 'nf-pipeline' as const, id, name: `step ${id}`, params })
    const nodes = [
        node('n01', { outdir: 'out', input: '${inputs:ids}', empty: '' }),
        node('n02', { outdir: 'out2' }),
        node('n03', { outdir: 'out3' }),
        node('n04', {}),
        node('n05', { outdir: 'out5' }),
    ]
    // n01 -> n03 -> n05, n02 and n04 unconnected
    const edges = [{ source: 'n01', target: 'n03' }, { source: 'n03', target: 'n05' }]
    const genome = input('genome', { bound_by: 'bind', bindings: ['n02.genome'], definition: { bind: ['n02.genome'] } })

    it('lists predecessors first, then unconnected steps; not itself or later steps', () => {
        const targets = referenceTargets(nodes, edges, 'n03')
        expect(targets.map(t => [t.stepId, t.connected])).toEqual([['n01', true], ['n02', false], ['n04', false]])
        expect(targets[0]!.params).toEqual([{ key: 'input', value: 'ids', input: 'ids' }, { key: 'outdir', value: 'out' }])
    })

    it('includes params filled by a bind: input', () => {
        const n02 = referenceTargets(nodes, edges, 'n03', [genome]).find(t => t.stepId === 'n02')!
        expect(n02.params).toEqual([{ key: 'genome', value: 'genome', input: 'genome' }, { key: 'outdir', value: 'out2' }])
    })

    it('offers every step to a step that is not saved yet', () => {
        expect(referenceTargets(nodes, edges).map(t => t.stepId)).toEqual(['n01', 'n02', 'n03', 'n04', 'n05'])
    })
})



describe('inputDeleteProblem', () => {
    const nodes = [{ type: 'nf-pipeline' as const, id: 'n01', name: 'nf-core/fetchngs' }]

    it('names the required params the input fills', () => {
        const message = inputDeleteProblem('ids', [
            { workflow_id: 'n01', field: 'params.input', message: "Required parameter 'input' is not set. Provide it…" },
        ], nodes)
        expect(message).toBe("Can't delete 'ids': it fills 'input' of nf-core/fetchngs (n01), which is required. Give the param a value in the step first.")
    })

    it('passes other errors on', () => {
        expect(inputDeleteProblem('ids', [{ workflow_id: null, field: 'inputs.ids', message: 'boom' }], nodes))
            .toBe("Can't delete 'ids': boom")
    })
})

describe('paramRows', () => {
    const schema = { input: { required: true }, outdir: { required: true }, genome: {}, aligner: {} }

    it('orders required, bound, set optional, then unknown params', () => {
        const rows = paramRows(schema, { aligner: 'star', input: 'a.csv', custom: 1 }, { genome: 'genome' })
        expect(rows.map(r => [r.name, r.required, r.value, r.boundBy])).toEqual([
            ['input', true, 'a.csv', undefined],
            ['outdir', true, undefined, undefined],
            ['genome', false, undefined, 'genome'],
            ['aligner', false, 'star', undefined],
            ['custom', false, 1, undefined],
        ])
    })
})

describe('paramFieldErrors', () => {
    it('groups errors by param and keeps general ones apart', () => {
        expect(paramFieldErrors([
            { workflow_id: 'n01', field: 'nf-pipeline.params.input', message: 'not set' },
            { workflow_id: 'n01', field: 'params', message: 'bad yaml' },
            { workflow_id: 'n02', field: 'params.input', message: 'other step' },
            { workflow_id: 'n01', field: 'url', message: 'not a param' },
        ], 'n01')).toEqual({ byParam: { input: ['not set'] }, general: ['bad yaml'] })
    })
})

describe('toParamValue', () => {
    it('converts numbers for numeric params and empty text to unset', () => {
        expect(toParamValue('4', { type: 'integer' })).toBe(4)
        expect(toParamValue('4', { type: 'string' })).toBe('4')
        expect(toParamValue('', { type: 'integer' })).toBeUndefined()
        expect(toParamValue(true, { type: 'boolean' })).toBe(true)
    })
})

describe('splitLeadingReference', () => {
    it('splits a leading reference from the text after it', () => {
        expect(splitLeadingReference('${n01:params:outdir}/x.csv')).toEqual({ stepId: 'n01', key: 'outdir', rest: '/x.csv' })
        expect(splitLeadingReference('${n01:params:outdir}')).toEqual({ stepId: 'n01', key: 'outdir', rest: '' })
    })

    it('leaves other values alone', () => {
        expect(splitLeadingReference('a/${n01:params:outdir}')).toBeUndefined()
        expect(splitLeadingReference('${inputs:ids}')).toBeUndefined()
        expect(splitLeadingReference(4)).toBeUndefined()
    })
})

describe('addableParams', () => {
    it('lists unset params, required first and hidden last', () => {
        const schema = { outdir: { required: true }, input: { required: true }, aligner: {}, genome: {}, debug: { hidden: true } }
        expect(addableParams(schema, ['input', 'genome']).map(p => [p.name, p.required, p.hidden])).toEqual([
            ['outdir', true, false], ['aligner', false, false], ['debug', false, true],
        ])
    })
})

describe('unshownErrors', () => {
    it('lists errors of fields the form does not show, labelled', () => {
        expect(unshownErrors({ name: ['bad'], params: ['p'], nextflow_version: ['too old'], '': ['general'] }, ['name']))
            .toEqual(['nextflow_version: too old', 'general'])
    })
})

describe('lintReferenceCount', () => {
    it('marks a value with two step references', () => {
        const text = 'outdir: ${n01:params:outdir}/x\ninput: ${n01:params:outdir}/${n02:params:outdir}\n'
        const problems = lintReferenceCount(text)
        expect(problems.map(p => text.slice(p.from, p.to))).toEqual(['${n01:params:outdir}/${n02:params:outdir}'])
        expect(problems[0]!.message).toContain("'input' contains 2 references")
    })

    it('accepts one reference and ignores invalid YAML', () => {
        expect(lintReferenceCount('outdir: a/${n01:params:outdir}/b\n')).toEqual([])
        expect(lintReferenceCount('outdir: [unclosed')).toEqual([])
    })
})

describe('paths of the editor machine', () => {
    it('joins and splits POSIX paths', () => {
        expect(joinPath('/home/me', 'mp.yaml')).toBe('/home/me/mp.yaml')
        expect(joinPath('/', 'mp.yaml')).toBe('/mp.yaml')
        expect(baseName('/home/me/mp.yaml')).toBe('mp.yaml')
        expect(pathCrumbs('/home/me')).toEqual([
            { label: '/', path: '/' }, { label: 'home', path: '/home' }, { label: 'me', path: '/home/me' },
        ])
        expect(pathCrumbs('/')).toEqual([{ label: '/', path: '/' }])
    })

    it('handles Windows paths', () => {
        expect(joinPath('C:\\Users\\me', 'mp.yaml')).toBe('C:\\Users\\me\\mp.yaml')
        expect(baseName('C:\\Users\\me\\mp.yaml')).toBe('mp.yaml')
        expect(pathCrumbs('C:\\Users\\me').map(c => c.path)).toEqual(['C:\\', 'C:\\Users', 'C:\\Users\\me'])
    })
})
