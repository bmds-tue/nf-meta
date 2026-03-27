from .models import Reference
from dataclasses import dataclass
from typing import Optional

import click
from pydantic import ValidationError


class GraphValidationError(Exception):
    pass


@dataclass
class WorkflowReferenceError(GraphValidationError):
    reference: Reference
    message: str


@dataclass
class WorkflowReferenceErrors(GraphValidationError):
    errors: list[WorkflowReferenceError]


@dataclass
class SessionCommandError(Exception):
    @dataclass
    class FieldError:
        workflow_id: str
        field: str
        message: str

    field_errors: list[FieldError]
    graph_errors: list[str]

    @classmethod
    def from_exception(cls, e: WorkflowReferenceError | WorkflowReferenceErrors | GraphValidationError):
        if isinstance(e, WorkflowReferenceError):
            e = WorkflowReferenceErrors([e])
        if isinstance(e, WorkflowReferenceErrors):
            return cls(
                field_errors=[
                    cls.FieldError(
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
    

def format_errors_for_cli(e: WorkflowReferenceError | WorkflowReferenceErrors | GraphValidationError | ValidationError) -> str:
    lines = []
    if isinstance(e, WorkflowReferenceError):
        e = WorkflowReferenceErrors([e])
    if isinstance(e, WorkflowReferenceErrors):
        lines.append(click.style("Reference errors:", fg="red", bold=True))
        for ref_err in e.errors:
            wf = click.style(f"Workflow {ref_err.reference.source_wf_id}", fg="yellow")
            lines.append(f" {wf}: {ref_err.message}")
    elif isinstance(e, GraphValidationError):
        lines.append(click.style("Graph validation error:", fg="red", bold=True))
        lines.append(f" {str(e)}")
    elif isinstance(e, ValidationError):
        lines.append(click.style("Validation failed:", fg="red", bold=True))
        for err in e.errors():
            field = ".".join(str(l) for l in err["loc"])
            lines.append(f" {click.style(field, fg="yellow")}: {err["msg"]}")
    return "\n".join(lines)
