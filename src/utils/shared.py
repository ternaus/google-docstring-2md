"""Shared utilities for docstring converters.

This module contains functions that are shared between markdown and TSX converters.
"""

import importlib
import inspect
import logging
import pkgutil
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

logger = logging.getLogger(__name__)


def normalize_anchor_id(module_name: str, name: str) -> str:
    """Normalize a name for use as an HTML anchor ID.

    Args:
        module_name: Module name
        name: Name to normalize

    Returns:
        Normalized name suitable for use as an HTML anchor ID
    """
    return f"{module_name.replace('.', '-')}-{name}".lower()


@dataclass
class ModuleFileConfig:
    """Configuration for processing a module file."""

    file_path: str
    modules: list[tuple[object, str]]
    output_dir: Path
    exclude_private: bool
    converter_func: Callable[[Any, str | None, str], str]
    output_extension: str


@dataclass
class PackageConfig:
    """Configuration for processing a package."""

    package_name: str
    output_dir: Path
    exclude_private: bool
    converter_func: Callable[[Any, str | None, str], str]
    output_extension: str
    progress_desc: str


def collect_package_modules(
    package: object,
    package_name: str,
    *,
    exclude_private: bool,
) -> list[tuple[object, str]]:
    """Collect all modules in a package.

    Args:
        package (object): The package object
        package_name (str): Name of the package
        exclude_private (bool): Whether to exclude private modules

    Returns:
        list: List of (module, module_name) tuples
    """
    modules_to_process = []

    # Process the root module
    if hasattr(package, "__file__") and package.__file__:
        modules_to_process.append((package, package.__name__))

    # Find all submodules recursively using a queue
    modules_to_explore = [(package, package_name)]
    explored_modules = set()

    while modules_to_explore:
        current_package, current_name = modules_to_explore.pop(0)
        if current_name in explored_modules:
            continue

        explored_modules.add(current_name)

        if not hasattr(current_package, "__path__"):
            continue

        for _module_finder, module_name, is_pkg in pkgutil.iter_modules(current_package.__path__, f"{current_name}."):
            if exclude_private and any(part.startswith("_") for part in module_name.split(".")):
                continue

            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "__file__") and module.__file__:
                    modules_to_process.append((module, module_name))

                    # If this is a package, add it to the exploration queue
                    if is_pkg:
                        modules_to_explore.append((module, module_name))
            except (ImportError, AttributeError):
                pass

    return modules_to_process


def group_modules_by_file(
    modules: list[tuple[object, str]],
) -> dict[str, list[tuple[object, str]]]:
    """Group modules by their file path.

    Args:
        modules (list): List of (module, module_name) tuples

    Returns:
        dict: Dictionary mapping file paths to lists of (module, module_name) tuples
    """
    file_to_modules = defaultdict(list)

    for module, module_name in modules:
        if hasattr(module, "__file__") and module.__file__:
            file_to_modules[module.__file__].append((module, module_name))

    return file_to_modules


def has_documentable_members(
    module: object,
    *,
    exclude_private: bool,
) -> bool:
    """Check if a module has documentable members.

    Args:
        module (object): Module to check
        exclude_private (bool): Whether to exclude private members

    Returns:
        bool: True if the module has documentable members
    """
    # Skip __init__.py files
    if hasattr(module, "__file__") and module.__file__ and module.__file__.endswith("__init__.py"):
        return False

    for name, obj in inspect.getmembers(module):
        if exclude_private and name.startswith("_"):
            continue

        if (
            (inspect.isclass(obj) or inspect.isfunction(obj))
            and hasattr(obj, "__module__")
            and obj.__module__ == module.__name__
        ):
            return True

    return False


def collect_module_members(module: object) -> tuple[list[tuple[str, object]], list[tuple[str, object]]]:
    """Collect classes and functions from a module.

    Args:
        module: Python module

    Returns:
        Tuple of (classes, functions) where each is a list of (name, object) pairs
    """
    classes = []
    functions = []

    for name, obj in inspect.getmembers(module):
        # Skip private members
        if name.startswith("_"):
            continue

        # Only consider items defined in this module
        if hasattr(obj, "__module__") and obj.__module__ == module.__name__:
            if inspect.isclass(obj):
                classes.append((name, obj))
            elif inspect.isfunction(obj):
                functions.append((name, obj))

    return classes, functions


def build_output_dir(config: ModuleFileConfig, module_name: str, file_name: str) -> Path:
    """Build the output directory path for a module file.

    Args:
        config: Configuration for module file processing
        module_name: Full module name (e.g., 'package.module.submodule')
        file_name: Name of the file without extension

    Returns:
        Path to the output directory
    """
    parts = module_name.split(".")
    if len(parts) > 1:
        simplified_path = parts[1:]
        if simplified_path and simplified_path[-1] == file_name:
            simplified_path = simplified_path[:-1]
        simplified_path = [part for part in simplified_path if part != "__init__"]
        return config.output_dir / "/".join(simplified_path) / file_name
    return config.output_dir / file_name


def process_module_file(
    file_path: str,
    modules: list[tuple[object, str]],
    converter_func: Callable[[object, str], str],  # (module, module_name)
    output_dir: Path,
    exclude_private: bool = False,
) -> bool:
    """Process a module file and generate documentation.

    Args:
        file_path: Path to the module file
        modules: List of (module, module_name) tuples
        converter_func: Function to convert module to documentation
        output_dir: Directory to write output files
        exclude_private: Whether to exclude private members

    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        path_obj = Path(file_path)
        file_name = path_obj.stem
        if file_name == "__init__":
            return False

        module, module_name = min(modules, key=lambda x: len(x[1]))
        output_dir = build_output_dir(
            ModuleFileConfig(
                file_path=file_path,
                modules=modules,
                output_dir=output_dir,
                output_extension=".tsx",
                converter_func=converter_func,
                exclude_private=exclude_private,
            ),
            module_name,
            file_name,
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        content = converter_func(module, module_name)
        output_file = output_dir / "page.tsx"
        output_file.write_text(content)

        return True
    except (ImportError, AttributeError, OSError, ValueError):
        logger.exception(f"Failed to process module file {file_path}")
        return False


def package_to_structure(config: PackageConfig) -> None:
    """Process a package and generate documentation structure.

    Args:
        config: Configuration for package processing
    """
    try:
        # Import the package
        package = importlib.import_module(config.package_name)
        if not hasattr(package, "__file__"):
            logger.error("Package %s has no __file__ attribute", config.package_name)
            return

        # Collect all modules in the package
        modules = collect_package_modules(
            package,
            config.package_name,
            exclude_private=config.exclude_private,
        )

        # Group modules by file
        module_groups = group_modules_by_file(modules)

        # Process each file with progress bar
        with tqdm(total=len(module_groups), desc=config.progress_desc) as pbar:
            for file_path, file_modules in module_groups.items():
                if process_module_file(
                    file_path,
                    file_modules,
                    config.converter_func,
                    output_dir=config.output_dir,
                    exclude_private=config.exclude_private,
                ):
                    pbar.update(1)
                else:
                    pbar.update(1)

    except Exception:
        logger.exception("Error processing package %s", config.package_name)
