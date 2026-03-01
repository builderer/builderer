import hashlib
import os
import pickle
import shutil

from graphlib import TopologicalSorter
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from typing import Dict, Iterable, Union, Type, Iterator, Optional, Callable

from builderer import Config
from builderer.details.context import ConfigContext, RulesContext, BuildContext
from builderer.details.glob_filter import glob_with_exclusions
from builderer.details.package import Package
from builderer.details.targets.target import Target, BuildTarget
from builderer.details.variable_expansion import resolve_conditionals, resolve_variables


def target_full_name(pkg: Package, target: Target) -> str:
    return ":".join([pkg.name, target.name])


def generate_roots(workspace_root: Path, filename: str) -> Iterator[Path]:
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
        if filename in files:
            yield Path(root).relative_to(workspace_root)


def load_user_module(ctx: Union[ConfigContext, RulesContext, BuildContext]):
    module_name = ".".join(["builderer", "workspace", *ctx.root.parts, ctx.MODULENAME])
    module_path = ctx.root.joinpath(ctx.FILENAME)
    spec = spec_from_loader(
        module_name, SourceFileLoader(module_name, str(module_path))
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"failed to load module spec {module_path}")
    build_module = module_from_spec(spec)
    setattr(build_module, "CTX", ctx)
    spec.loader.exec_module(build_module)


def load_recursive_contexts(
    workspace_root: Path,
    ctx_type: Union[Type[ConfigContext], Type[RulesContext], Type[BuildContext]],
):
    assert workspace_root.is_dir()
    contexts = [
        ctx_type(root) for root in generate_roots(workspace_root, ctx_type.FILENAME)
    ]
    for ctx in contexts:
        load_user_module(ctx)
    return contexts


class PackageFormatHelper:
    def __init__(self, root, pkg):
        self.root = root
        self.pkg = pkg

    def __format__(self, spec: str):
        return os.path.relpath(self.pkg.targets[spec].root, self.root)


class Workspace:
    def __init__(self, workspace_root: Path = Path(".")):
        self.root = Path(workspace_root).resolve()
        # load workspace config
        config_context = ConfigContext(self.root)
        load_user_module(config_context)
        self.buildtools = config_context.buildtools
        self.configs = config_context.configs
        # install user rules
        for ctx in load_recursive_contexts(self.root, RulesContext):
            for name, rule in ctx.rules.items():
                # TODO: install on package instaces based on nearest RULES file
                # up in directory structure, currently this installs all rules
                # on all packages...
                setattr(Package, name, rule)
        # acquire user packages
        self.packages: Dict[str, Package] = {
            pkg.name: pkg
            for ctx in load_recursive_contexts(self.root, BuildContext)
            for pkg in ctx.packages.values()
        }
        # Initialize empty graph, won't be able to fill it in until conditionals are expanded
        self._graph: dict[tuple[Package, Target], list[tuple[Package, Target]]] = {}

    @property
    def targets(self):
        for pkg in self.packages.values():
            for target in pkg.targets.values():
                yield pkg, target

    def find_target(
        self, name: str, outer: Optional[Package]
    ) -> tuple[Package, Target]:
        pkg_name, target_name = name.split(":")
        if pkg_name:
            dep_pkg = self.packages[pkg_name]
        elif outer:
            dep_pkg = outer
        else:
            raise RuntimeError(f"unable to locate package for {name}")
        return dep_pkg, dep_pkg.targets[target_name]

    def direct_dependencies(
        self, package: Package, target: Target
    ) -> Iterator[tuple[Package, Target]]:
        for dep in target.deps:
            yield self.find_target(dep, package)

    def all_dependencies(
        self, package: Package, target: Target
    ) -> Iterable[tuple[Package, Target]]:
        # Collect all reachable dependencies via BFS
        direct = [(p, t) for p, t in self.direct_dependencies(package, target)]
        all_deps = set(self._breadth_first(direct))
        # Topologically sort (dependencies before dependents)
        sorter: TopologicalSorter = TopologicalSorter()
        for dep in sorted(all_deps, key=lambda pt: target_full_name(*pt)):
            sorter.add(dep, *[d for d in self._graph[dep] if d in all_deps])
        return sorter.static_order()

    # Configure the workspace to the given build profile, this includes
    # collapsing conditional fields, expanding variables, and filtering out
    # conditional targets...
    def configure(self, config: Config, filter_target_names: list[str] = []):
        # Empty out available configs once we set one
        self.configs = {}
        # Filter out conditional targets
        self._filter_targets(lambda _, t: t.condition(config))
        # First pass at expanding conditionals, passing permissive=True here
        # skips conditionals that test Config values that are lists, since those
        # will be expanded into build-time variants and expanded later.
        for _, target in self.targets:
            for key, value in target.__dict__.items():
                target.__dict__[key] = resolve_conditionals(
                    config=config,
                    value=value,
                    permissive=isinstance(target, BuildTarget),
                )
        # Filter out empty packages
        self._filter_empty_packages()
        # Initialize graph
        self._update_graph()
        # Optionally filter graph based on requested targets
        if filter_target_names:
            self._filter_by_requested_targets(
                [self.find_target(n, None) for n in filter_target_names]
            )
        # Configure targets...
        for package, target in self._topological_sort():
            # Expand format variables and configure sandbox paths
            self._expand_variables(config=config, package=package, target=target)
            # Glob path variables...
            target_root = Path(target.workspace_root)
            for _, attr in target.get_all_path_fields():
                attr[:] = glob_with_exclusions(target_root, attr)
            # Perform pre-build tasks (e.g. sandboxing, code generation, etc)...
            if target.sandbox:
                target.do_pre_build()

    def _expand_variables(self, config: Config, package: Package, target: Target):
        dep_packages = {
            dep_package.name
            for dep_package, _ in self.direct_dependencies(
                package=package, target=target
            )
        }
        variables: Dict[str, Union[str, PackageFormatHelper]] = {
            dep_name: PackageFormatHelper(
                target.workspace_root, self.packages[dep_name]
            )
            for dep_name in dep_packages
        }
        # Expand path fields first (they never reference __sandbox__)
        path_fields = list(target.get_all_path_fields())
        path_field_ids = {id(attr) for _, attr in path_fields}
        for _, attr in path_fields:
            attr[:] = [
                resolve_variables(config=config, variables=variables, value=v)
                for v in attr
            ]
        # Compute sandbox hash after path expansion so dependency changes propagate
        if target.sandbox:
            assert target.sandbox_root is None
            hasher = hashlib.blake2b()
            hasher.update(pickle.dumps(target))
            sandbox_hash = hasher.hexdigest()[:16]
            sandbox_parent = Path(config.sandbox_root).joinpath(
                target.workspace_root, target.name
            )
            target.sandbox_root = sandbox_parent.joinpath(sandbox_hash).as_posix()
            # Delete previous versions (if any exist)...
            if sandbox_parent.is_dir():
                for child in sandbox_parent.iterdir():
                    assert len(child.name) == 16 and all(
                        c in "0123456789abcdef" for c in child.name
                    ), f"unexpected entry in sandbox directory: {child}"
                    if child.name != sandbox_hash:
                        shutil.rmtree(child)
            variables["__sandbox__"] = os.path.relpath(
                target.sandbox_root, target.workspace_root
            )
        # Expand non-path fields (path fields already expanded above)
        for key, value in target.__dict__.items():
            if id(value) not in path_field_ids:
                target.__dict__[key] = resolve_variables(
                    config=config, variables=variables, value=value
                )

    def _filter_by_requested_targets(self, targets: list[tuple[Package, Target]]):
        allowed_targets = set(self._breadth_first(targets))
        self._filter_targets(lambda p, t: (p, t) in allowed_targets)
        self._update_graph()

    def _filter_targets(self, condition: Callable):
        for pkg in self.packages.values():
            pkg.targets = {
                name: target
                for name, target in pkg.targets.items()
                if condition(pkg, target)
            }

    def _filter_empty_packages(self):
        self.packages = {pkg.name: pkg for pkg in self.packages.values() if pkg.targets}

    def _update_graph(self):
        self._graph = {
            (package, target): [self.find_target(dep, package) for dep in target.deps]
            for package, target in self.targets
        }

    def _breadth_first(self, start: list[tuple[Package, Target]]):
        visited = {k: False for k in self._graph.keys()}
        queue = start
        while queue:
            m = queue.pop(0)
            yield m
            for dep in self._graph[m]:
                if not visited[dep]:
                    visited[dep] = True
                    queue.append(dep)

    def _topological_sort(self) -> Iterable[tuple[Package, Target]]:
        sorter: TopologicalSorter = TopologicalSorter()
        for (p, t), deps in self._graph.items():
            sorter.add((p, t), *deps)
        return sorter.static_order()
