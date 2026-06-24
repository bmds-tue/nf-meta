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
    const sideBarActiveDetailId = ref(0)
    const _nextSideBarId = ref(1)
    const _sideBarNodes = ref<SideBarDetail<APINodeData | NewNodeData>[]>([])
    const sideBarNodes = computed(() => _sideBarNodes.value)

    const _saveDialogOpen = ref<boolean>(false)
    const saveDialogOpen = computed(() => _saveDialogOpen.value)

    const _loadDialogOpen = ref<boolean>(false)
    const loadDialogOpen = computed(() => _loadDialogOpen.value)

    function openLoadDialog() {
        closeSaveDialog()
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

    function createSideBarDetailWithId<T>(detailData: T): SideBarDetail<T> {
        _nextSideBarId.value++
        return { id: _nextSideBarId.value, detailData }
    }

    function addNodeToSideBar(node: APINodeData | NewNodeData) {
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
        if (!('id' in newDetail.detailData)) {
            _sideBarNodes.value = [newDetail, ..._sideBarNodes.value]
        } else {
            _sideBarNodes.value = [..._sideBarNodes.value, newDetail]
        }
        setActiveSidebarDetailId(newDetail.id)
    }

    function removeSidebarDetail(id: number) {
        _sideBarNodes.value = _sideBarNodes.value.filter((d) => d.id != id)
    }

    function collapseSidebarDetail(id: number) {
        if (id == sideBarActiveDetailId.value) {
            sideBarActiveDetailId.value = 0
        }
    }

    return {
        showSidebar: sideBarOpen, sideBarOpen, toggleSidebar,
        sideBarActiveDetailId, setActiveSidebarDetailId,
        sideBarTab, sideBarNodes, addNodeToSideBar,
        removeSidebarDetail, collapseSidebarDetail,
        saveDialogOpen, openSaveDialog, closeSaveDialog,
        loadDialogOpen, openLoadDialog, closeLoadDialog,
    }
})

export const useActivityStore = defineStore('activity', () => {
    interface LogEntry {
        event: APIEvent
        timestamp: Date
    }

    const log = ref<LogEntry[]>([])
    const drawerOpen = ref(false)

    function pushEvents(events: APIEvent[]) {
        const entries = events.map(event => ({ event, timestamp: new Date() }))
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