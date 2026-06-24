import type { XYPosition } from "@vue-flow/core"

export type Selection = {
  nodes: string[],
  edges: string[]
}

export type FieldError = {
    workflow_id: string | null
    field: string
    message: string
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; fieldErrors?: FieldError[]; graphErrors?: string[] }

export type SideBarDetail<T> = {
  id: number,
  detailData: T
}

export type APIEdgeData = {
  id?: string,
  source: string,
  target: string,
}

export const WorkflowType = {
  NF_PIPELINE: 'nf-pipeline',
  NF_MODULE: 'nf-module',
} as const

export type WorkflowTypeValue = typeof WorkflowType[keyof typeof WorkflowType]

// Shared base fields for all node types
export type APINodeBase = {
    id?: string,
    name?: string,
    version?: string,
    position?: XYPosition,
    config_file?: string,
    params?: object
}

export type APINfPipelineNodeData = APINodeBase & {
    type: typeof WorkflowType.NF_PIPELINE,
    description?: string,
    url?: string,
    is_nfcore?: boolean,
    params_file?: string,
    profile?: string,
    main_script?: string,
}

export type APINfModuleNodeData = APINodeBase & {
    type: typeof WorkflowType.NF_MODULE,
}

export type APINodeData = APINfPipelineNodeData | APINfModuleNodeData

// Placeholder for a node in the sidebar before selecting a type.
// All fields optional; satisfies {}, so App.vue can pass `node?.data ?? {}`.
export type NewNodeData = { type?: WorkflowTypeValue }

export type APIGlobalOptions = {
  profile?: string,
  config_file?: string,
  params?: object
}

export type APIGraph = {
  redoable: boolean,
  undoable: boolean,
  filename: string,
  nodes: APINodeData[],
  transitions: APIEdgeData[],
  globals: APIGlobalOptions
}

export type NfCorePipelineReleaseInfo = {
  tag_name: string,
  published_at: string,
  tag_sha: string
}

export type NfCorePipelineInfo = {
  name: string
  description: string,
  repository_url: string,
  releases: NfCorePipelineReleaseInfo[]
}

export type NfCoreModuleVersionInfo = {
  version: string,
  createdAt?: string,
  status?: string,
}

export type NfCoreModuleInfo = {
  name: string,
  description?: string,
  keywords?: string[],
}