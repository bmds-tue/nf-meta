from .models import Reference
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError


class GraphValidationError(BaseException):
    pass


@dataclass
class WorkflowReferenceError(GraphValidationError):
    reference: Reference
    message: str


@dataclass
class WorkflowReferenceErrors(GraphValidationError):
    errors: list[WorkflowReferenceError]


@dataclass
class FieldError:
    workflow_id: str
    field: str
    message: str


@dataclass
class SessionCommandError(Exception):
    field_errors: list[FieldError]
    graph_errors: list[str]

    @classmethod
    def from_exception(cls, e: WorkflowReferenceError | WorkflowReferenceErrors | GraphValidationError):
        if isinstance(e, WorkflowReferenceError):
            e = WorkflowReferenceErrors([e])
        if isinstance(e, WorkflowReferenceErrors):
            return cls(
                field_errors=[
                    FieldError(
                        workflow_id=ref_error.reference.source_wf_id,
                        field="params",  # TODO: For now ok. Think about more finegrained errors for Workflow output/input references
                        message=ref_error.message
                    )
                    for ref_error in e.errors
                ],
                graph_errors=[]
            )
        return cls(field_errors=[], graph_errors=[str(e)])
    
    def to_dict(self):
        return {
            "field_errors": [{"workflow_id": e.workflow_id, "field": e.field, "message": e.message} 
                             for e in self.field_errors],
            "graph_errors": self.graph_errors
        }
    
