from abc import ABC, abstractmethod
from typing import ClassVar

from .utils import EditorOptions


_REGISTRY: dict[str, type["BaseEditor"]] = {}


class BaseEditor(ABC):
    """Abstract base class for all metapipeline editor backends.

    Subclasses register themselves by defining an ``EDITOR_NAME`` class
    attribute. Registration happens automatically at class-definition time
    via ``__init_subclass__``, so a new editor becomes available as soon as
    its module is imported — no changes to the dispatch logic are needed.

    Example::

        class MyEditor(BaseEditor):
            EDITOR_NAME = "my-editor"

            def start(self): ...

    Subclasses should not override ``__init__``. All ``EditorOptions`` fields
    are available via ``self.options``.
    """

    EDITOR_NAME: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        editor_name = cls.__dict__.get("EDITOR_NAME")
        if editor_name is not None:
            _REGISTRY[editor_name] = cls

    def __init__(self, options: EditorOptions) -> None:
        if "EDITOR_NAME" not in type(self).__dict__:
            raise TypeError(
                f"{type(self).__name__} must define EDITOR_NAME = '...' as a class attribute"
            )
        self.options = options

    @abstractmethod
    def start(self) -> None:
        """Start the editor. Should block until the user closes it."""
