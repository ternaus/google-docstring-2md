"""Utilities for converting Google-style docstrings to TSX.

This module provides functions to convert Python classes and functions with Google-style
docstrings into TSX documentation components that use imported React components.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

from google_docstring_parser import parse_google_docstring

from docstring_2tsx.processor import (
    build_params_data,
    format_section_data,
    process_description,
)
from utils.shared import (
    collect_module_members,
    collect_package_modules,
    group_modules_by_file,
    has_documentable_members,
    process_module_file,
)
from utils.signature_formatter import (
    format_signature,
    get_signature_params,
)

logger = logging.getLogger(__name__)

# Path to import components from, could be made configurable
COMPONENTS_IMPORT_PATH = "@/components/DocComponents"


def get_source_line(obj: type | Callable) -> int:
    """Get the source line number for a class or function.

    Args:
        obj: Class or function to get source line for

    Returns:
        Line number in the source file
    """
    try:
        return obj.__code__.co_firstlineno
    except AttributeError:
        return 1


def get_source_code(obj: type | Callable) -> str | None:
    """Get source code for a class or function.

    Args:
        obj: Class or function to get source code for

    Returns:
        Source code as string or None if not available
    """
    try:
        import inspect

        return inspect.getsource(obj)
    except (TypeError, OSError):
        return None


def class_to_data(obj: type | Callable) -> dict:
    """Convert class or function to structured data format.

    This function extracts documentation data for a class or function from
    its docstring and signature, returning a structured dictionary.

    Args:
        obj: Class or function to document

    Returns:
        Dictionary containing structured documentation data
    """
    # Get object name and parameters
    obj_name = obj.__name__
    params = get_signature_params(obj)

    # Get signature data
    signature_data = format_signature(obj, params)

    # Get source code and line number
    source_code = get_source_code(obj)
    source_line = get_source_line(obj)

    # Parse docstring
    docstring = obj.__doc__ or ""
    try:
        parsed = parse_google_docstring(docstring)
    except Exception:
        logger.exception("Error parsing docstring for %s", docstring)
        parsed = {}

    # Get description
    description = process_description(parsed)

    # Get parameters data
    params_data = build_params_data(params, parsed)

    # Process other sections (returns, raises, etc.)
    sections = []
    for section, content in parsed.items():
        if section not in ["Description", "Args"] and (section_data := format_section_data(section, content)):
            sections.append(section_data)

    # Create the data structure
    member_data = {
        "name": obj_name,
        "type": "class" if isinstance(obj, type) else "function",
        "signature": {
            "name": signature_data.name,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default": p.default,
                    "description": p.description,
                }
                for p in signature_data.params
            ],
            "return_type": signature_data.return_type,
        },
        "source_line": source_line,
    }

    # Add optional fields
    if description:
        member_data["description"] = description
    if params_data:
        member_data["params"] = params_data
    if sections:
        member_data["sections"] = sections
    if source_code:
        member_data["source_code"] = source_code

    return member_data


def file_to_tsx(module: object, module_name: str) -> str:
    """Convert a module to a TSX document that uses imported components.

    Args:
        module: The module object to document
        module_name: Name of the module for the heading

    Returns:
        str: The TSX content
    """
    # Collect module members
    classes, functions = collect_module_members(module)

    # Process classes and functions to get their data
    members_data = []
    for _name, obj in sorted(classes + functions):
        # Convert to data structure
        member_data = class_to_data(obj)
        members_data.append(member_data)

    # Parse module-level docstring
    module_docstring = module.__doc__ or ""
    try:
        parsed_module_doc = parse_google_docstring(module_docstring)
        module_description = process_description(parsed_module_doc)
    except Exception:
        logger.exception("Error parsing module docstring for %s", module_name)
        module_description = None

    # Create module data
    module_data = {
        "moduleName": module_name,
        "description": module_description,
        "members": members_data,
    }

    # JSON representation of the data (with indentation for readability)
    module_data_str = json.dumps(module_data, indent=2)

    # Create the page.tsx file content
    components = "ModuleDoc"
    return (
        f"import {{ {components} }} from '{COMPONENTS_IMPORT_PATH}';\n\n"
        "// Data structure extracted from Python docstrings\n"
        f"const moduleData = {module_data_str};\n\n"
        "export default function Page() {\n"
        "  return <ModuleDoc {...moduleData} />;\n"
        "}\n"
    )


def package_to_tsx_files(
    package: object,
    output_dir: Path,
) -> None:
    """Convert a package to TSX files.

    Args:
        package: Python package
        output_dir: Directory to write TSX files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all modules in the package
    modules = collect_package_modules(package)

    # Group modules by file
    module_groups = group_modules_by_file(modules)

    # Process each file
    for file_path, file_modules in module_groups.items():
        if not has_documentable_members(file_modules[0][1]):
            continue

        try:
            # Get the module name from the first module in the file
            module_name = file_modules[0][1].__name__

            # Process the file
            content = process_module_file(
                file_path,
                file_modules,
                converter_func=file_to_tsx,
            )

            # Create the Next.js page structure
            # Convert module name to path (e.g., "package.module.submodule" -> "package/module/submodule")
            page_path = output_dir / module_name.replace(".", "/")
            page_path.mkdir(parents=True, exist_ok=True)

            # Write the content to page.tsx
            output_file = page_path / "page.tsx"
            output_file.write_text(content)
        except Exception:
            logger.exception("Error processing file %s", file_path)
