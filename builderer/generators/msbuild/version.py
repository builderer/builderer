from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class VisualStudioVersion:
    solution_format_version: str
    visual_studio_version: str
    minimum_visual_studio_version: str
    project_tools_version: str
    filters_tools_version: str
    vc_project_version: str
    platform_toolset: str
    windows_target_platform_version: str


VS_VERSIONS: Dict[int, VisualStudioVersion] = {
    2022: VisualStudioVersion(
        solution_format_version="12.0",
        visual_studio_version="17.0",
        minimum_visual_studio_version="17.0",
        project_tools_version="17.0",
        filters_tools_version="4.0",
        vc_project_version="16.0",
        platform_toolset="v143",
        windows_target_platform_version="10.0",
    ),
}
