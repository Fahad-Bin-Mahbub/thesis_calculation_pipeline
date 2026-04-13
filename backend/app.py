from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT_DIR / "app"
PACKAGE_ALIAS = "backend_app_pkg"


def _load_module(module_name: str, file_path: Path, package_paths: list[str] | None = None):
    spec = importlib.util.spec_from_file_location(module_name, file_path, submodule_search_locations=package_paths)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to build module spec for {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Avoid "app.py" shadowing the "app/" package when platforms import this file as module "app".
if PACKAGE_ALIAS not in sys.modules:
    _load_module(PACKAGE_ALIAS, PACKAGE_DIR / "__init__.py", [str(PACKAGE_DIR)])

main_module = _load_module(f"{PACKAGE_ALIAS}.main", PACKAGE_DIR / "main.py")
app = main_module.app
