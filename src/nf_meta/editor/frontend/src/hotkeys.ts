import { useHotkey } from 'vuetify'
import { useGraphStore } from './store.ts'
import { useVueFlow } from '@vue-flow/core'

export function useEditorHotkeys() {
  const graphStore = useGraphStore()
  const { getSelectedNodes, getSelectedEdges } = useVueFlow()

  function deleteSelection() {
    const nodeIds = getSelectedNodes.value.map(n => n.id)
    const edgeIds = getSelectedEdges.value.map(e => e.id)

    graphStore.removeSelectionById({nodes: nodeIds, edges: edgeIds})
  }

  useHotkey('delete', deleteSelection)
  useHotkey('backspace', deleteSelection)

  useHotkey('meta+z', () => {
    console.log("UNDO pressed!")
    graphStore.undo()
  })

  useHotkey('meta+shift+z', () => {
    console.log("REDO pressed!")
    graphStore.redo()
  })

  useHotkey('meta+s', (e) => {
    console.log("SAVE pressed!")
    graphStore.save()
  })

  useHotkey('meta+shift+s', (e) => {
    console.log("SAVE-AS pressed!")
    graphStore.save()
  })
}
