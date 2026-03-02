import { useHotkey } from 'vuetify'
import { useEditorStore, useGraphStore } from './store.ts'
import { useVueFlow } from '@vue-flow/core'

export function useEditorHotkeys() {
  const graphStore = useGraphStore()
  const editorStore = useEditorStore()
  const { getSelectedNodes, getSelectedEdges } = useVueFlow()

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

  useHotkey('meta+s', (e) => {
    if (!graphStore.filename) {
      editorStore.openSaveDialog()
    } else {
      graphStore.save()
    }
  })

  useHotkey('meta+shift+s', (e) => {
    editorStore.openSaveDialog()
  })

  useHotkey('meta+o', (e) => {
    console.log("OPEN pressed")
    editorStore.openLoadDialog()
  })
}
