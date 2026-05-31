from typing import Iterator, Tuple, Optional

from builderer import Condition


class Target:
    # The target types permitted as DIRECT deps of this target. The workspace
    # validates every dep edge against this when it builds the graph. Default is
    # empty (fail-closed): a target accepts no deps until it explicitly opts in.
    # Each concrete target assigns its own tuple after its class body (so the
    # tuple may reference the class itself and peer target classes). Use base
    # classes (e.g. RepositoryTarget) rather than enumerating every concrete
    # type. Only DIRECT deps are checked; the transitive closure is unrestricted.
    allowed_deps_types: tuple = ()

    def __init__(
        self,
        *,
        name: str,
        condition: Condition = Condition(),
        workspace_root: str,
        deps: list = [],
        sandbox: bool = False,
    ):
        self.name = name
        self.condition = condition
        self.workspace_root = workspace_root
        self.deps = deps
        self.sandbox = sandbox
        self.sandbox_root: Optional[str] = None

    @property
    def root(self):
        if self.sandbox:
            return self.sandbox_root
        else:
            return self.workspace_root

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield

    def get_all_path_fields(self) -> Iterator[Tuple[str, list]]:
        yield from self.get_file_path_fields()
        yield from self.get_dir_path_fields()

    def do_pre_build(self):
        raise RuntimeError(
            f"Sandboxed target class {self.__class__.__name__} requires implementation of do_pre_build()"
        )


# Targets that are responsible for fetching code from remote sources
# NOTE: repository targets do not support globbing
class RepositoryTarget(Target):
    def __init__(self, **kwargs):
        super().__init__(sandbox=True, **kwargs)


# Targets that produce their output from within builderer itself
class PreBuildTarget(Target):
    def __init__(self, **kwargs):
        super().__init__(sandbox=True, **kwargs)


# Targets that produce their output in the target build system
class BuildTarget(Target):
    def __init__(self, *, output_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.output_path = output_path
