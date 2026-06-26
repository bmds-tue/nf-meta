import { useHotkey } from 'vuetify'
import { useEditorStore, useGraphStore, useActivityStore } from './store'
import { useVueFlow } from '@vue-flow/core'

export function useEditorHotkeys() {
  const graphStore = useGraphStore()
  const editorStore = useEditorStore()
  const activityStore = useActivityStore()
  const { getSelectedNodes, getSelectedEdges } = useVueFlow({id: "main-flow"})

  async function deleteSelection() {
    const nodeIds = getSelectedNodes.value.map(n => n.id)
    const edgeIds = getSelectedEdges.value.map(e => e.id)

    const result = await graphStore.removeSelectionById({nodes: nodeIds, edges: edgeIds})
    if (result.ok && nodeIds.length > 0) {
      editorStore.removeSidebarDetailsForNodeIds(nodeIds)
    }
  }

  useHotkey('delete', deleteSelection)
  useHotkey('backspace', deleteSelection)

  useHotkey('meta+z', () => {
    graphStore.undo()
  })

  useHotkey('meta+shift+z', () => {
    graphStore.redo()
  })

  useHotkey('meta+s', () => {
    if (!graphStore.filename) {
      editorStore.openSaveDialog()
    } else {
      graphStore.save()
    }
  })

  useHotkey('meta+shift+s', () => {
    editorStore.openSaveDialog()
  })

  useHotkey('meta+o', () => {
    editorStore.openLoadDialog()
  })

  useHotkey('meta+b', () => {
    editorStore.toggleSidebar()
  })

  useHotkey('meta+j', () => {
    activityStore.toggleDrawer()
  })
}
