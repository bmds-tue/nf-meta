import type { Edge, Node, XYPosition } from "@vue-flow/core"

export type ApiResult<T> = 
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; fieldErrors?: Record<string, string[]> }

export type SideBarDetail<T> = {
  id: number,
  detailData: T
}

export type APIEdgeData = {
  id?: string,
  source: string,
  target: string,
}

export type APINodeData = {
    id?: string,
    name?: string,
    description?: string,
    url?: string,
    version?: string,
    position?: XYPosition,
    is_nfcore?: boolean,
}

export type APIGraph = {
  nodes: Node<APINodeData>[],
  transitions: Edge<APIEdgeData>[]
}

export type NfCorePipelineReleaseInfo = {
  tag_name: string,
  published_at: string,
  tag_sha: string
}

export type NfCorePipelineInfo = {
  name: string
  description: string,
  url: string,
  releases: NfCorePipelineReleaseInfo[]
}
