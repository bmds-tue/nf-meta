import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEditorStore, useGraphStore } from '../store'

const EMPTY_GRAPH = { undoable: false, redoable: false, nodes: [], transitions: [], globals: {}, inputs: [] }

// A backend whose config is `filename`; records the requests it gets
function backend(filename: string) {
    const calls: string[] = []
    const fetch = vi.fn(async (url: string) => {
        calls.push(url)
        const body = url.startsWith('/api/graph/') && !url.includes('save') ? { ...EMPTY_GRAPH, filename } : { events: [] }
        return new Response(JSON.stringify(body), { status: 200 })
    })
    vi.stubGlobal('fetch', fetch)
    return calls
}

async function graphWith(filename: string) {
    const calls = backend(filename)
    const graphStore = useGraphStore()
    await graphStore.getAndUpdateGraph()
    return { graphStore, calls }
}

beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined })
    // the store keeps the page title up to date
    vi.stubGlobal('document', { title: '' })
    setActivePinia(createPinia())
})

describe('a config file before the first change', () => {
    it('is not asked for when the config is a local file', async () => {
        const { graphStore } = await graphWith('/data/mp.yaml')
        expect(await graphStore.ensureConfigFile()).toBe(true)
        expect(useEditorStore().saveDialogOpen).toBe(false)
    })

    it('is asked for a new config, and the change waits for it', async () => {
        const { graphStore, calls } = await graphWith('')
        const change = graphStore.updateGlobalOptions({ nf_profile: 'docker' })
        await Promise.resolve()
        expect(useEditorStore().saveDialogOpen).toBe(true)
        expect(useEditorStore().saveDialogReason).toBe('new')
        expect(calls.some(c => c.includes('/globals/update/'))).toBe(false)

        useEditorStore().closeSaveDialog(true)
        expect((await change).ok).toBe(true)
        expect(calls.some(c => c.includes('/globals/update/'))).toBe(true)
    })

    it('is asked for a config loaded from a URL', async () => {
        const { graphStore } = await graphWith('https://example.org/mp.yaml')
        void graphStore.ensureConfigFile()
        expect(useEditorStore().saveDialogReason).toBe('url')
    })

    it('when cancelled, the change is not sent', async () => {
        const { graphStore, calls } = await graphWith('')
        const change = graphStore.updateGlobalOptions({ nf_profile: 'docker' })
        await Promise.resolve()
        useEditorStore().closeSaveDialog()
        const result = await change
        expect(result.ok).toBe(false)
        expect(calls.some(c => c.includes('/globals/update/'))).toBe(false)
    })
})
