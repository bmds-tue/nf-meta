import { useHotkey } from 'vuetify'
import { useEditorStore, useGraphStore } from './store.ts'
import { useVueFlow } from '@vue-flow/core'

export function useEditorHotkeys() {
  const graphStore = useGraphStore()
  const editorStore = useEditorStore()
  const { getSelectedNodes, getSelectedEdges } = useVueFlow({id: "main-flow"})

  function deleteSelection() {
    const nodeIds = getSelectedNodes.value.map(n => n.id)
    const edgeIds = getSelectedEdges.value.map(e => e.id)

    graphStore.removeSelectionById({nodes: nodeIds, edges: edgeIds})
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
}
