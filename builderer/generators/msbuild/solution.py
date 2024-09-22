import os

from io import TextIOWrapper
from pathlib import Path
from typing import Dict

from builderer import Config
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace, target_full_name
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.utils import as_msft_path, make_guid

CXX_GUID = "{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}"
FOLDER_GUID = "{2150E333-8FDC-42A3-9474-1A3956D46DE8}"


class MsBuildSolution:
    SOLUTION_FORMAT_VERSION = "12.0"
    VISUAL_STUDIO_VERSION = "17.0"
    MINIMUM_VISUAL_STUDIO_VERSION = "17.0"

    def __init__(
        self, config: Config, workspace: Workspace, projects: Dict[str, MsBuildProject]
    ):
        self.config = config
        self.workspace = workspace
        self.projects = projects
        self.solution_root = Path(self.config.build_root)
        self.solution_path = self.solution_root.joinpath("Solution.sln")

    def __call__(self):
        self.solution_root.mkdir(parents=True, exist_ok=True)
        with open(self.solution_path, "w") as sln:
            self._write_solution(sln)

    def _write_solution(self, file: TextIOWrapper):
        # header
        file.writelines(
            [
                f"# Generated by Builderer\n",
                f"Microsoft Visual Studio Solution File, Format Version {self.SOLUTION_FORMAT_VERSION}\n",
                f"VisualStudioVersion = {self.VISUAL_STUDIO_VERSION}\n",
                f"MinimumVisualStudioVersion = {self.MINIMUM_VISUAL_STUDIO_VERSION}\n",
            ]
        )

        # projects
        for project in self.projects.values():
            project_path = os.path.relpath(project.vcxproj_path, self.solution_root)
            file.write(
                f'Project("{CXX_GUID}") = "{project.target.name}", "{as_msft_path(project_path)}", "{project.project_guid}"\n'
            )
            deps = [
                self.projects[target_full_name(dep_package, dep_target)]
                for dep_package, dep_target in self.workspace.direct_dependencies(
                    project.package, project.target
                )
                if isinstance(dep_target, BuildTarget)
            ]
            if deps:
                file.write("\tProjectSection(ProjectDependencies) = postProject\n")
                for dep in deps:
                    dep_name = target_full_name(dep.package, dep.target)
                    dep_project = self.projects[dep_name]
                    file.write(
                        f"\t\t{dep_project.project_guid} = {dep_project.project_guid}\n"
                    )
                file.write("\tEndProjectSection\n")
            file.write(f"EndProject\n")

        # folders
        target_roots = {
            Path(project.target.workspace_root) for project in self.projects.values()
        }
        target_parents = {
            parent
            for folder in target_roots
            for parent in folder.parents
            if parent != Path()
        }
        folders = sorted(target_roots | target_parents)
        for folder in folders:
            folder_name = folder.name
            folder_guid = make_guid(as_msft_path(folder))
            file.writelines(
                [
                    f'Project("{FOLDER_GUID}") = "{folder_name}", "{folder_name}", "{folder_guid}"\n'
                    f"EndProject\n",
                ]
            )

        # globals
        file.write("Global\n")

        # Solution Configurations
        file.write("\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n")
        for arch in self.config.architecture:
            for config in self.config.build_config:
                file.write(f"\t\t{config}|{arch} = {config}|{arch}\n")
        file.write("\tEndGlobalSection\n")

        # Project Configurations
        file.write("\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n")
        for project in self.projects.values():
            for arch in self.config.architecture:
                for config in self.config.build_config:
                    file.writelines(
                        [
                            f"\t\t{project.project_guid}.{config}|{arch}.ActiveCfg = {config}|{arch}\n",
                            f"\t\t{project.project_guid}.{config}|{arch}.Build.0 = {config}|{arch}\n",
                        ]
                    )
        file.write("\tEndGlobalSection\n")

        # Package nesting
        file.write("\tGlobalSection(NestedProjects) = preSolution\n")
        for project in self.projects.values():
            file.write(
                f"\t\t{project.project_guid} = {make_guid(as_msft_path(project.target.workspace_root))}\n"
            )
        for folder in folders:
            folder_parent = folder.parent
            if folder_parent != Path():
                file.write(
                    f"\t\t{make_guid(as_msft_path(folder))} = {make_guid(as_msft_path(folder_parent))}\n"
                )
        file.write("\tEndGlobalSection\n")

        # Solution GUID
        file.writelines(
            [
                f"\tGlobalSection(ExtensibilityGlobals) = postSolution\n",
                f"\t\tSolutionGuid = {make_guid(as_msft_path(self.solution_path))}\n",
                f"\tEndGlobalSection\n",
            ]
        )

        file.write("EndGlobal\n")
