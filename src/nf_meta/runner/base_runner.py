from abc import ABC, abstractmethod
from typing import ClassVar

from nf_meta.core.graph import MetaworkflowGraph
from .utils import RunOptions


_REGISTRY: dict[str, type["BaseRunner"]] = {}


class BaseRunner(ABC):
    """Abstract base class for all metapipeline runner backends.

    Subclasses register themselves by defining a ``RUNNER_NAME`` class
    attribute. The value is the string name used to select the runner::

        class MyRunner(BaseRunner):
            RUNNER_NAME = "my-runner"

            def run(self, g): ...
            def resume(self, g): ...

    Registration happens automatically at class-definition time via
    ``__init_subclass__``. ``run_metapipeline`` looks up the concrete class
    from ``_REGISTRY``, so a new runner becomes available as soon as its
    module is imported, with no changes to ``run_metapipeline`` needed.

    Subclasses should not override ``__init__``. The ``RunOptions`` passed in
    is stored as ``self.run_options``, available to every runner without
    repeating the constructor.
    """

    RUNNER_NAME: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        runner_name = cls.__dict__.get("RUNNER_NAME")
        if runner_name is not None:
            _REGISTRY[runner_name] = cls

    def __init__(self, run_options: RunOptions) -> None:
        if "RUNNER_NAME" not in type(self).__dict__:
            raise TypeError(
                f"{type(self).__name__} must define RUNNER_NAME = '...' as a class attribute"
            )
        self.run_options = run_options

    @abstractmethod
    def run(self, g: MetaworkflowGraph) -> None:
        """Execute every workflow in `g` from scratch, in dependency order.
        Called by `run_metapipeline` when `run_options.resume` is falsy.
        Exceptions are not caught by the caller -- let a failure raise rather
        than returning normally with partial results."""

    @abstractmethod
    def resume(self, g: MetaworkflowGraph) -> None:
        """Continue a previously interrupted run of `g`, skipping whatever
        the implementation can determine already completed successfully.
        Called by `run_metapipeline` when `run_options.resume` is truthy.
        Same exception policy as `run`."""
