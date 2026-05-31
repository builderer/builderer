import hashlib
import os
import pickle
import sys

from graphlib import TopologicalSorter
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from typing import Dict, Iterable, Union, Type, Iterator, Optional, Callable

from builderer import Config
from builderer.conditional import ConditionalValue
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


# Parse an optional .builderer.env dotenv into a {NAME: value} dict.
def load_env_file(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    try:
        text = path.read_text()
    except FileNotFoundError:
        return env
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}: expected KEY=VALUE, got: {line}")
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


# Resolves {__env__:NAME} against the values loaded from .builderer.env.
class EnvFormatHelper:
    def __init__(self, env):
        self.env = env

    def __format__(self, spec: str):
        if spec not in self.env:
            raise ValueError(
                f"{{__env__:{spec}}} is not set; define {spec} in .builderer.env"
            )
        return self.env[spec]


class PackageFormatHelper:
    def __init__(self, root, pkg):
        self.root = root
        self.pkg = pkg

    def __format__(self, spec: str):
        dep_target = self.pkg.targets[spec]
        if not dep_target.sandbox:
            raise ValueError(
                f"{self.pkg.name}:{spec} is not sandboxed; only sandboxed "
                f"targets (git_repository, https_repository, generate_files, "
                f"cc_library(sandbox=True)) can be referenced via "
                f"{{Pkg:target}} path expansion."
            )
        return os.path.relpath(dep_target.root, self.root)


class Workspace:
    def __init__(self, workspace_root: Path = Path(".")):
        self.root = Path(workspace_root).resolve()
        # Local, uncommitted values referenced as {__env__:NAME} in build files,
        # loaded only from the optional .builderer.env (NOT the process
        # environment, which would leak ambient state into every build).
        self.env = load_env_file(self.root / ".builderer.env")
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
            self._expand_variables(config=config, package=package, target=target)
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
        variables: Dict[str, Union[str, PackageFormatHelper, EnvFormatHelper]] = {
            dep_name: PackageFormatHelper(
                target.workspace_root, self.packages[dep_name]
            )
            for dep_name in dep_packages
        }
        # Local/uncommitted values, referenced anywhere as {__env__:NAME}.
        variables["__env__"] = EnvFormatHelper(self.env)
        # Expand path fields first (they never reference __sandbox__)
        path_fields = list(target.get_all_path_fields())
        path_field_ids = {id(attr) for _, attr in path_fields}
        for _, attr in path_fields:
            attr[:] = [
                resolve_variables(config=config, variables=variables, value=v)
                for v in attr
            ]
        # Glob path fields before hashing so the hash sees the actual file list.
        target_root = Path(target.workspace_root)
        for field, attr in target.get_all_path_fields():
            if target.sandbox and any(isinstance(v, ConditionalValue) for v in attr):
                raise ValueError(
                    f"{package.name}:{target.name}.{field}: sandboxed targets "
                    f"cannot have build_config/architecture conditionals in path fields"
                )
        for _, attr in target.get_file_path_fields():
            attr[:] = glob_with_exclusions(target_root, attr, Path.is_file)
        for _, attr in target.get_dir_path_fields():
            attr[:] = glob_with_exclusions(target_root, attr, Path.is_dir)
        # Compute sandbox hash from the rule description plus mtime/size of every
        # declared input file. mtime semantics match make: touching invalidates.
        if target.sandbox:
            assert target.sandbox_root is None
            hasher = hashlib.blake2b()
            hasher.update(pickle.dumps(target))
            # Mix each direct sandboxed dep's hash so non-path-field references
            # to deps (e.g. GenerateFiles.args = ["--input={:Repo}"]) propagate
            # dep changes into our hash. Path-field references already propagate
            # via path expansion. Non-sandboxed deps are skipped (Change 7
            # forbids referencing them via {Pkg:target}, so they carry no
            # content to propagate).
            for _, dep_target in self.direct_dependencies(
                package=package, target=target
            ):
                if dep_target.sandbox_root:
                    hasher.update(Path(dep_target.sandbox_root).name.encode())
            for _, files in target.get_file_path_fields():
                for src in files:
                    st = os.stat(src)
                    hasher.update(f"{src}:{st.st_mtime_ns}:{st.st_size}".encode())
            sandbox_hash = hasher.hexdigest()[:16]
            sandbox_parent = Path(config.sandbox_root).joinpath(
                target.workspace_root, target.name
            )
            target.sandbox_root = sandbox_parent.joinpath(sandbox_hash).as_posix()
            variables["__sandbox__"] = os.path.relpath(
                target.sandbox_root, target.workspace_root
            )
        # Built-in variables that resolve at run time, not at hash time. Set
        # after hashing so the pickle never sees env-specific values like
        # sys.executable -- the template strings ("{__python__}", etc.) are
        # what gets hashed, while the resolved values are substituted into
        # non-path fields below.
        variables["__python__"] = sys.executable
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
