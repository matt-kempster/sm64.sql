from dataclasses import dataclass
from pathlib import Path
from typing import List

from parse_utils import strip_comments_and_whitespace


@dataclass
class SM64MacroPreset:
    macro_name: str
    behavior: str
    model_name: str
    # TODO: beh params


def get_macro_preset_names(path: Path) -> List[str]:
    lines = path.read_text().splitlines()
    macro_preset_names = []
    for line in lines:
        line = line.strip()
        if not line.startswith("macro_"):
            continue
        line = line.replace(",", "")
        macro_preset_names.append(line)
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
        line = line.strip()
        if not within_macro_presets and line.startswith(
            "struct MacroPreset MacroObjectPresets[] = {"
        ):
            within_macro_presets = True
            continue
        elif within_macro_presets and line == "};":
            break
        elif not within_macro_presets:
            continue
        line = line.replace("{", "").replace("},", "")
        line_parts = [strip_comments_and_whitespace(part) for part in line.split(",")]
        if len(line_parts) != 3:
            raise ValueError(
                f"Invalid number of parts ({len(line_parts)}) in line: {line}"
            )
        macro_presets.append(
            SM64MacroPreset(
                macro_name=macro_preset_names[enum_index],
                behavior=line_parts[0],
                model_name=line_parts[1],
                # TODO: beh params
            )
        )
        enum_index += 1
    return macro_presets
