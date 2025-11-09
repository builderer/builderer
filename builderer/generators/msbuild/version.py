from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class VisualStudioVersion:
    solution_format_version: Tuple[int, int]
    visual_studio_version: Tuple[int, int]
    minimum_visual_studio_version: Tuple[int, int]
    project_tools_version: Tuple[int, int]
    filters_tools_version: Tuple[int, int]
    vc_project_version: Tuple[int, int]
    platform_toolset: str
    windows_target_platform_version: Tuple[int, int]

    @property
    def solution_format_version_str(self) -> str:
        return f"{self.solution_format_version[0]}.{self.solution_format_version[1]}"

    @property
    def visual_studio_version_str(self) -> str:
        return f"{self.visual_studio_version[0]}.{self.visual_studio_version[1]}"

    @property
    def minimum_visual_studio_version_str(self) -> str:
        return f"{self.minimum_visual_studio_version[0]}.{self.minimum_visual_studio_version[1]}"

    @property
    def project_tools_version_str(self) -> str:
        return f"{self.project_tools_version[0]}.{self.project_tools_version[1]}"

    @property
    def filters_tools_version_str(self) -> str:
        return f"{self.filters_tools_version[0]}.{self.filters_tools_version[1]}"

    @property
    def vc_project_version_str(self) -> str:
        return f"{self.vc_project_version[0]}.{self.vc_project_version[1]}"

    @property
    def windows_target_platform_version_str(self) -> str:
        return f"{self.windows_target_platform_version[0]}.{self.windows_target_platform_version[1]}"


VS_VERSIONS: Dict[int, VisualStudioVersion] = {
    2022: VisualStudioVersion(
        solution_format_version=(12, 0),
        visual_studio_version=(17, 0),
        minimum_visual_studio_version=(17, 0),
        project_tools_version=(17, 0),
        filters_tools_version=(4, 0),
        vc_project_version=(16, 0),
        platform_toolset="v143",
        windows_target_platform_version=(10, 0),
    ),
    2026: VisualStudioVersion(
        solution_format_version=(12, 0),
        visual_studio_version=(18, 0),
        minimum_visual_studio_version=(18, 0),
        project_tools_version=(18, 0),
        filters_tools_version=(4, 0),
        vc_project_version=(17, 0),
        platform_toolset="v145",
        windows_target_platform_version=(10, 0),
    ),
}
