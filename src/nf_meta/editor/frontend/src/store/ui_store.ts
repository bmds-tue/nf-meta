import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { APINodeData, APIEvent, SideBarDetail, NewNodeData } from '../types'

export const useMessageStore = defineStore('message', () => {
    interface Message {
        text: string
        color: string
        timeout?: number
    }

    const queue = ref<Message[]>([])

    function add(text: string, color = 'success') {
        if (!['success', 'error', 'warning'].includes(color)) {
            console.warn('Message store: Invalid color received:', color, text)
        }
        queue.value.push({ text, color, timeout: 2000 })
    }

    return { queue, add }
})

export const useEditorStore = defineStore('editor', () => {
    const _sideBarOpen = ref(localStorage.getItem('showSideBar') == 'true')
    const sideBarOpen = computed(() => _sideBarOpen.value)

    const sideBarTab = ref('nodes')
    const hoveredNodeId = ref<string>()
    // Input hovered in the inputs panel; the steps it fills are highlighted
    const hoveredInputName = ref<string>()
    const flashingNodeId = ref<string>()
    const sideBarActiveDetailId = ref(0)
    const _nextSideBarId = ref(1)
    const _sideBarNodes = ref<SideBarDetail<APINodeData | NewNodeData>[]>([])
    const sideBarNodes = computed(() => _sideBarNodes.value)

    const _saveDialogOpen = ref<boolean>(false)
    const saveDialogOpen = computed(() => _saveDialogOpen.value)

    const _loadDialogOpen = ref<boolean>(false)
    const loadDialogOpen = computed(() => _loadDialogOpen.value)

    // 'refused': the backend refused the page's session token (none, or one of an earlier run);
    // 'unreachable': no answer (the editor was stopped, or the connection is gone)
    const _backendState = ref<'ok' | 'refused' | 'unreachable'>('ok')
    const backendState = computed(() => _backendState.value)

    function setBackendState(state: 'ok' | 'refused' | 'unreachable') {
        _backendState.value = state
    }

    // Shown when the editor starts without a config; closing it starts a new one
    const _startScreenOpen = ref(false)
    const startScreenOpen = computed(() => _startScreenOpen.value)

    function openStartScreen() {
        _startScreenOpen.value = true
    }

    function closeStartScreen() {
        _startScreenOpen.value = false
    }

    function openLoadDialog() {
        closeSaveDialog()
        closeStartScreen()
        _loadDialogOpen.value = true
    }

    function closeLoadDialog() {
        _loadDialogOpen.value = false
    }

    function openSaveDialog() {
        closeLoadDialog()
        _saveDialogOpen.value = true
    }

    function closeSaveDialog() {
        _saveDialogOpen.value = false
    }

    function toggleSidebar() {
        _sideBarOpen.value = !_sideBarOpen.value
        localStorage.setItem('showSideBar', String(_sideBarOpen.value))
    }

    function setActiveSidebarDetailId(id: number) {
        sideBarActiveDetailId.value = id
    }

    function setHoveredNodeId(id: string | undefined) {
        hoveredNodeId.value = id
    }

    function setHoveredInputName(name: string | undefined) {
        hoveredInputName.value = name
    }

    // Open a step in the Workflows tab (expanded, scrolled to and flashed)
    function showNode(node: APINodeData) {
        if (!_sideBarOpen.value) toggleSidebar()
        sideBarTab.value = 'nodes'
        addNodeToSideBar(node)
        if (node.id) flashNode(node.id)
    }

    // Inputs to point out in the inputs panel (scrolled to and flashed)
    const flashingInputNames = ref<string[]>([])

    function showInputs(names: string[]) {
        if (!_sideBarOpen.value) toggleSidebar()
        sideBarTab.value = 'inputs'
        flashingInputNames.value = names
        setTimeout(() => { flashingInputNames.value = [] }, 1200)
    }

    function flashNode(nodeId: string) {
        flashingNodeId.value = nodeId
        setTimeout(() => { flashingNodeId.value = undefined }, 800)
    }

    function createSideBarDetailWithId<T>(detailData: T): SideBarDetail<T> {
        _nextSideBarId.value++
        return { id: _nextSideBarId.value, detailData }
    }

    function addNodeToSideBar(node: APINodeData | NewNodeData, prepend = false) {
        const nodeId = 'id' in node ? node.id : undefined
        const existingDetail = sideBarNodes.value.find((sideBarDetail) => {
            const detailId = 'id' in sideBarDetail.detailData ? sideBarDetail.detailData.id : undefined
            return detailId == nodeId
        })
        if (existingDetail) {
            setActiveSidebarDetailId(existingDetail.id)
            return
        }

        const newDetail = createSideBarDetailWithId(node)
        if (prepend || !('id' in newDetail.detailData)) {
            _sideBarNodes.value = [newDetail, ..._sideBarNodes.value]
        } else {
            _sideBarNodes.value = [..._sideBarNodes.value, newDetail]
        }
        setActiveSidebarDetailId(newDetail.id)
    }

    // Show every step of the graph (in graph order, after unsaved new ones),
    // keeping each step's detail (and so whether it is expanded)
    function syncSidebarNodes(nodes: APINodeData[]) {
        const existing = new Map<string, SideBarDetail<APINodeData | NewNodeData>>()
        const drafts: SideBarDetail<APINodeData | NewNodeData>[] = []
        for (const detail of _sideBarNodes.value) {
            const id = 'id' in detail.detailData ? detail.detailData.id : undefined
            if (id) existing.set(id, detail)
            else drafts.push(detail)
        }
        const synced = nodes.map((node) => {
            const detail = node.id ? existing.get(node.id) : undefined
            return detail ? { ...detail, detailData: node } : createSideBarDetailWithId<APINodeData | NewNodeData>(node)
        })
        _sideBarNodes.value = [...drafts, ...synced]
    }

    function removeSidebarDetail(id: number) {
        _sideBarNodes.value = _sideBarNodes.value.filter((d) => d.id != id)
    }

    function removeSidebarDetailsForNodeIds(nodeIds: string[]) {
        const idSet = new Set(nodeIds)
        _sideBarNodes.value = _sideBarNodes.value.filter(d => {
            const detailNodeId = 'id' in d.detailData ? d.detailData.id : undefined
            return !detailNodeId || !idSet.has(detailNodeId)
        })
    }

    function collapseSidebarDetail(id: number) {
        if (id == sideBarActiveDetailId.value) {
            sideBarActiveDetailId.value = 0
        }
    }

    return {
        showSidebar: sideBarOpen, sideBarOpen, toggleSidebar,
        sideBarActiveDetailId, setActiveSidebarDetailId,
        sideBarTab, sideBarNodes, addNodeToSideBar, syncSidebarNodes,
        removeSidebarDetail, removeSidebarDetailsForNodeIds, collapseSidebarDetail,
        hoveredNodeId, setHoveredNodeId,
        hoveredInputName, setHoveredInputName,
        flashingInputNames, showInputs, showNode,
        flashingNodeId, flashNode,
        saveDialogOpen, openSaveDialog, closeSaveDialog,
        loadDialogOpen, openLoadDialog, closeLoadDialog,
        startScreenOpen, openStartScreen, closeStartScreen,
        backendState, setBackendState,
    }
})

export const useActivityStore = defineStore('activity', () => {
    interface LogEntry {
        // stable key for the list, while new entries are prepended
        id: number
        event: APIEvent
        timestamp: Date
    }

    const log = ref<LogEntry[]>([])
    const drawerOpen = ref(false)
    let nextId = 0

    function pushEvents(events: APIEvent[]) {
        const entries = events.map(event => ({ id: nextId++, event, timestamp: new Date() }))
        log.value = [...entries, ...log.value]
    }

    function clear() {
        log.value = []
    }

    function toggleDrawer() {
        drawerOpen.value = !drawerOpen.value
    }

    return { log, pushEvents, clear, drawerOpen, toggleDrawer }
})