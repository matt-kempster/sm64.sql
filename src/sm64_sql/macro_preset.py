from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import split_top_level, strip_block_comments


@dataclass
class SM64MacroPreset:
    macro_name: str
    behavior: str
    model_name: str
    # TODO: param


def _strip_comments(line: str) -> str:
    """Remove both block and trailing line comments from a single line."""
    return strip_block_comments(line).split("//")[0].strip()


def get_macro_preset_names(path: Path) -> List[str]:
    """Read the ordered preset names from the ``enum MacroPresets`` declaration.

    The final ``macro_count`` entry is the enum-size sentinel, not a preset, so
    it is skipped. The remaining names line up by index with the rows of the
    ``sMacroObjectPresets`` array.
    """
    macro_preset_names = []
    within_enum = False
    for line in path.read_text().splitlines():
        line = _strip_comments(line)
        if not within_enum:
            if line.startswith("enum MacroPresets"):
                within_enum = True
            continue
        if line.startswith("}"):
            break
        name = line.rstrip(",").strip()
        if not name.startswith("macro_") or name == "macro_count":
            continue
        macro_preset_names.append(name)
    return macro_preset_names


def parse_macro_presets(
    macro_preset_path: Path, macro_preset_names_path: Path
) -> List[SM64MacroPreset]:
    macro_preset_names = get_macro_preset_names(macro_preset_names_path)
    lines = macro_preset_path.read_text().splitlines()
    within_macro_presets = False
    macro_presets = []
    enum_index = 0
    for line in lines:
        line = _strip_comments(line)
        if not within_macro_presets:
            # Matches both the historic `MacroObjectPresets[]` and the current
            # `sMacroObjectPresets[]` array declarations.
            if "MacroObjectPresets[]" in line and "{" in line:
                within_macro_presets = True
            continue
        if line.startswith("};"):
            break
        if "{" not in line or "}" not in line:
            continue
        inner = line[line.index("{") + 1 : line.rindex("}")]
        line_parts = [part.strip() for part in split_top_level(inner, ",")]
        if len(line_parts) != 3:
            raise ValueError(
                f"Invalid number of parts ({len(line_parts)}) in line: {line}"
            )
        if enum_index >= len(macro_preset_names):
            raise ValueError(
                "More preset rows than names in enum MacroPresets "
                f"(row {enum_index}): {line}"
            )
        macro_presets.append(
            SM64MacroPreset(
                macro_name=macro_preset_names[enum_index],
                behavior=line_parts[0],
                model_name=line_parts[1],
                # TODO: param (line_parts[2])
            )
        )
        enum_index += 1
    return macro_presets
