"""Edits: commands that work out the primitive changes they need from the
current graph (which steps reference an input, what is declared) and apply
them as one `Transaction`: validated once at the end, rolled back on error,
undone in one step.

Each `*_commands` function returns that transaction; each edit command
computes it when applied, so it always starts from the current graph.
"""

from dataclasses import dataclass

from .events import AddInput, Command, EditWorkflow, GraphEventHandler, RemoveInput, Transaction, UpdateInput
from .inputs import Binding, InputDefinition
from .refs import INPUT_NAME_PATTERN, INPUT_REF_PATTERN


class _Draft:
    """A working copy of every step's params and of the declared inputs.
    Edits change the draft; `commands` turns the difference to the graph into
    primitive commands (one `EditWorkflow` per changed step)."""

    def __init__(self, graph: GraphEventHandler):
        self._workflows = {wf.id: wf for wf in graph.get_workflows()}
        self._declared = dict(graph.inputs)
        self.params = {wf_id: dict(wf.params or {}) for wf_id, wf in self._workflows.items()}
        self.inputs = dict(graph.inputs)

    def references(self, name: str) -> set[Binding]:
        """The params whose whole value is `${inputs:<name>}`."""
        return {
            Binding(wf_id, param)
            for wf_id, params in self.params.items()
            for param, value in params.items()
            if isinstance(value, str) and (m := INPUT_REF_PATTERN.fullmatch(value)) and m.group(1) == name
        }

    def names(self) -> set[str]:
        """Every input, declared or only referenced."""
        referenced = {
            m.group(1)
            for params in self.params.values()
            for value in params.values()
            if isinstance(value, str) and (m := INPUT_REF_PATTERN.fullmatch(value))
        }
        return set(self.inputs) | referenced

    def bindings(self, name: str) -> tuple[Binding, ...]:
        declared = set(self.inputs[name].bindings) if name in self.inputs else set()
        return tuple(sorted(declared | self.references(name)))

    def set_references(self, name: str, value: str, keep: set[Binding]) -> None:
        """Remove every whole-value `${inputs:<name>}` from params, then set
        each param in `keep` to `value`."""
        for b in self.references(name) - keep:
            del self.params[b.step_id][b.param]
        for b in keep:
            self.params[b.step_id][b.param] = value

    def commands(self) -> Transaction:
        commands: list[Command] = []
        for wf_id, params in self.params.items():
            wf = self._workflows[wf_id]
            if params != (wf.params or {}):
                commands.append(EditWorkflow(wf.model_copy(update={"params": params or None})))
        for name in self._declared.keys() - self.inputs.keys():
            commands.append(RemoveInput(name))
        for name, definition in self.inputs.items():
            if name not in self._declared:
                commands.append(AddInput(name, definition))
            elif definition != self._declared[name]:
                commands.append(UpdateInput(name, definition))
        return Transaction(tuple(commands))


def _edit_input(
    draft: _Draft,
    name: str,
    definition: InputDefinition,
    bindings: tuple[Binding, ...],
    *,
    in_params: bool,
    new_name: str | None,
    create: bool,
) -> None:
    target = new_name or name
    names = draft.names()
    if create and name in names:
        raise ValueError(f"Input '{name}' already exists")
    if not create and name not in names:
        raise ValueError(f"Input '{name}' does not exist")
    if target != name and target in names:
        raise ValueError(f"Input '{target}' already exists")
    if not INPUT_NAME_PATTERN.fullmatch(target):
        raise ValueError(f"Invalid input name '{target}': it can't be empty or contain '}}', ':' or whitespace")
    for b in bindings:
        if b.step_id not in draft.params:
            raise ValueError(f"Can't bind input '{target}' to '{b}': there is no step '{b.step_id}'")

    declaration = definition.model_copy(update={"bind": () if in_params else tuple(str(b) for b in sorted(bindings))})
    keep_declaration = not in_params or not bindings or declaration != InputDefinition()
    draft.set_references(name, f"${{inputs:{target}}}", set(bindings) if in_params else set())
    if name in draft.inputs and (target != name or not keep_declaration):
        del draft.inputs[name]
    if keep_declaration:
        draft.inputs[target] = declaration


def edit_input_commands(
    graph: GraphEventHandler,
    name: str,
    definition: InputDefinition,
    bindings: tuple[Binding, ...],
    *,
    in_params: bool,
    new_name: str | None = None,
    create: bool = False,
) -> Transaction:
    """Make input `name` (renamed to `new_name`, if given) fill exactly
    `bindings`, with `definition`'s description, default and keywords (its
    `bind` is ignored).

    With `in_params`, each bound param's value becomes `${inputs:<name>}`
    and the input is declared in `inputs:` only if `definition` adds
    something; otherwise it is declared with `bind:`. References to the input
    from params not in `bindings` are removed. An input with no bindings is
    always declared.

    With `create`, the input must not exist yet; otherwise it must. Raises
    `ValueError` for an unknown, existing or invalid name or a binding to a
    missing step.
    """
    draft = _Draft(graph)
    _edit_input(draft, name, definition, bindings, in_params=in_params, new_name=new_name, create=create)
    return draft.commands()


def delete_input_commands(graph: GraphEventHandler, name: str) -> Transaction:
    """Remove input `name`: its declaration and the params referencing it with
    `${inputs:<name>}`. Raises `ValueError` if there is no such input."""
    draft = _Draft(graph)
    if name not in draft.names():
        raise ValueError(f"Input '{name}' does not exist")
    draft.set_references(name, "", set())
    draft.inputs.pop(name, None)
    return draft.commands()


def declare_step_inputs_commands(graph: GraphEventHandler, wf_id: str) -> Transaction:
    """Declare every input that step `wf_id` references with
    `${inputs:<name>}` in `inputs:`, bound with `bind:` to all params it
    fills (in this and other steps). Raises `ValueError` for an unknown step
    or one that references no inputs."""
    draft = _Draft(graph)
    if wf_id not in draft.params:
        raise ValueError(f"Workflow with id '{wf_id}' does not exist")
    names = sorted({b_name for b_name in draft.names() if any(b.step_id == wf_id for b in draft.references(b_name))})
    if not names:
        raise ValueError(f"Step '{wf_id}' uses no inputs from its params")
    for name in names:
        definition = draft.inputs.get(name, InputDefinition())
        _edit_input(draft, name, definition, draft.bindings(name), in_params=False, new_name=None, create=False)
    return draft.commands()


def set_inputs_style_commands(graph: GraphEventHandler, *, in_params: bool) -> Transaction:
    """Write every input that fills params the same way: with
    `${inputs:<name>}` in those params (`in_params`) or with `bind:` in
    `inputs:` (see `edit_input_commands`). Unused inputs stay as they are."""
    draft = _Draft(graph)
    for name in sorted(draft.names()):
        bindings = draft.bindings(name)
        definition = draft.inputs.get(name, InputDefinition())
        if not bindings or bool(definition.bind) != in_params:
            continue  # unused, or already written that way
        _edit_input(draft, name, definition, bindings, in_params=in_params, new_name=None, create=False)
    return draft.commands()


@dataclass(frozen=True)
class EditInput:
    """Set an input's bindings, binding style and details; see `edit_input_commands`."""

    name: str
    definition: InputDefinition
    bindings: tuple[Binding, ...]
    in_params: bool
    new_name: str | None = None
    create: bool = False

    def apply(self, g: GraphEventHandler):
        edit_input_commands(
            g,
            self.name,
            self.definition,
            self.bindings,
            in_params=self.in_params,
            new_name=self.new_name,
            create=self.create,
        ).apply(g)


@dataclass(frozen=True)
class DeleteInput:
    """Remove an input with its references; see `delete_input_commands`."""

    name: str

    def apply(self, g: GraphEventHandler):
        delete_input_commands(g, self.name).apply(g)


@dataclass(frozen=True)
class DeclareStepInputs:
    """Move a step's `${inputs:...}` inputs to `inputs:`; see `declare_step_inputs_commands`."""

    wf_id: str

    def apply(self, g: GraphEventHandler):
        declare_step_inputs_commands(g, self.wf_id).apply(g)


@dataclass(frozen=True)
class SetInputsStyle:
    """Write all inputs in params or all in `inputs:`; see `set_inputs_style_commands`."""

    in_params: bool

    def apply(self, g: GraphEventHandler):
        set_inputs_style_commands(g, in_params=self.in_params).apply(g)
