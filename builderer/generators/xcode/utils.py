from pathlib import Path

from builderer.config import Config


def validate_xcode_project_path(config: Config) -> Path:
    """
    Validate that the build_root ends with .xcodeproj and return the path.

    Args:
        config: The configuration with the build_root setting.

    Returns:
        The validated project path.

    Raises:
        ValueError: If the build_root does not end with .xcodeproj.
    """
    build_root = Path(config.build_root)
    if not str(build_root).endswith(".xcodeproj"):
        raise ValueError(
            f"Xcode generator requires build_root to end with '.xcodeproj'. "
            f"Got '{build_root}' instead. Please specify a path ending with '.xcodeproj'."
        )
    return build_root
