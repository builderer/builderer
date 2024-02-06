from pathlib import Path
from subprocess import check_call

from builderer.details.targets.target import PreBuildTarget

class GenerateFiles(PreBuildTarget):
    def __init__(self,
                 args: list,
                 **kwargs):
        super().__init__(**kwargs)
        self.args = args
    
    def do_pre_build(self):
        assert self.sandbox_root
        sandbox_root = Path(self.sandbox_root)
        if not sandbox_root.is_dir():
            print(f"generating {self.name}")
            sandbox_root.mkdir(parents=True, exist_ok=True)
            check_call(self.args, cwd=self.workspace_root)