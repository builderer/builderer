from typing import Union


class Config:
    def __init__(
        self,
        buildtool: str,
        toolchain: str,
        platform: str,
        sandbox_root: str,
        build_root: str,
        build_config: Union[str, list[str]],
        architecture: Union[str, list[str]],
        **kwargs
    ):
        self.buildtool = buildtool
        self.toolchain = toolchain
        self.platform = platform
        self.sandbox_root = sandbox_root
        self.build_root = build_root
        self.build_config = build_config
        self.architecture = architecture
        self.__dict__.update(kwargs)
