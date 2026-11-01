import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { checkBackend, useApiStore, useEditorStore } from '../store'

function answer(status: number, body: unknown) {
    return vi.fn(async () => new Response(JSON.stringify(body), { status }))
}

beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined })
    setActivePinia(createPinia())
})

describe('backend state', () => {
    it('is refused when the API answers 401', async () => {
        vi.stubGlobal('fetch', answer(401, { detail: 'Missing or invalid editor token' }))
        await useApiStore().getGraph()
        expect(useEditorStore().backendState).toBe('refused')
    })

    it('is unreachable when a request gets no answer', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
        await useApiStore().getGraph()
        expect(useEditorStore().backendState).toBe('unreachable')
    })

    it('is unreachable when the check gets an answer not from the editor', async () => {
        vi.stubGlobal('fetch', answer(502, { error: 'proxy' }))
        await checkBackend()
        expect(useEditorStore().backendState).toBe('unreachable')
    })

    it('is unreachable when the check gets no answer in time', async () => {
        vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
            options.signal?.addEventListener('abort', () => reject(options.signal?.reason))
        })))
        await checkBackend(1)
        expect(useEditorStore().backendState).toBe('unreachable')
    })

    it('is ok again once the check gets the editor\'s answer', async () => {
        useEditorStore().setBackendState('unreachable')
        vi.stubGlobal('fetch', answer(200, { ok: true }))
        await checkBackend()
        expect(useEditorStore().backendState).toBe('ok')
    })

    it('stays refused when the check is refused', async () => {
        vi.stubGlobal('fetch', answer(401, { detail: 'no' }))
        await checkBackend()
        expect(useEditorStore().backendState).toBe('refused')
    })
})
