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
    nf_config?: string,
    params?: object
}

export type APINfPipelineNodeData = APINodeBase & {
    type: typeof WorkflowType.NF_PIPELINE,
    description?: string,
    url?: string,
    is_nfcore?: boolean,
    params_file?: string,
    nf_profile?: string,
    main_script?: string,
}

export type APINfModuleNodeData = APINodeBase & {
    type: typeof WorkflowType.NF_MODULE,
    container_engine?: 'docker' | 'singularity' | 'conda' | 'podman',
}

export type APINodeData = APINfPipelineNodeData | APINfModuleNodeData

// Placeholder for a node in the sidebar before selecting a type.
// All fields optional; satisfies {}, so App.vue can pass `node?.data ?? {}`.
export type NewNodeData = { type?: WorkflowTypeValue }

export type APIGlobalOptions = {
  nf_profile?: string,
  nf_config?: string,
  params?: object
}

export type Scalar = string | number | boolean

// One entry of the config's `inputs:` section, as written
export type APIInputDefinition = {
  bind?: string[],
  default?: Scalar,
  description?: string,
  type?: 'string' | 'integer' | 'number' | 'boolean',
  format?: string,
  enum?: Scalar[],
  pattern?: string,
  minimum?: number,
  maximum?: number,
  exists?: boolean,
  mimetype?: string,
  schema?: string,
}

export type APIInputDiagnostic = {
  severity: 'error' | 'warning',
  message: string,
  yaml_path: string,
}

// An input as the backend reports it: declared in `inputs:` or implicit
// (only referenced as `${inputs:<name>}`), with its effective schema
export type APIInput = {
  name: string,
  declared: boolean,
  definition: APIInputDefinition | null,
  bound_by: 'bind' | 'reference' | null,
  bindings: string[],
  schema: Omit<APIInputDefinition, 'bind' | 'default' | 'description'>,
  default: Scalar | null,
  description: string,
  diagnostics: APIInputDiagnostic[],
}

export type ParamSpec = {
  type?: string,
  format?: string,
  description?: string,
  required?: boolean,
  hidden?: boolean,
  default?: unknown,
}

export type StepSchema = Record<string, ParamSpec>

// An input as saved from the inputs panel (POST /api/inputs/save/)
export type APIInputSave = {
  name: string,
  new_name?: string,
  create: boolean,
  in_params: boolean,
  bindings: string[],
  definition: APIInputDefinition,
}

export type APIGraph = {
  redoable: boolean,
  undoable: boolean,
  filename: string,
  nodes: APINodeData[],
  transitions: APIEdgeData[],
  globals: APIGlobalOptions,
  inputs: APIInput[],
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

export type APIEvent = {
  type: string
  [key: string]: unknown
}

export type APICommandResponse = {
  events: APIEvent[]
}