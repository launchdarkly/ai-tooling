#!/usr/bin/env python3
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

SKILL_GLOB = "**/SKILL.md"
EXCLUDED_DIRS = {"template", "node_modules"}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESC_LENGTH = 1024
MAX_COMPAT_LENGTH = 500


def is_excluded(path: pathlib.Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def parse_frontmatter(lines):
    if not lines or lines[0].strip() != "---":
        return None, "Missing opening frontmatter delimiter '---' on first line"

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break

    if end_idx is None:
        return None, "Missing closing frontmatter delimiter '---'"

    frontmatter_lines = lines[1:end_idx]
    body_lines = lines[end_idx + 1 :]
    return (frontmatter_lines, body_lines), None


def normalize_value(value: str) -> str | None:
    if value in {"", "|", ">", "|-", ">-"}:
        return None
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]
    return value


def parse_frontmatter_fields(frontmatter_lines: list[str]) -> tuple[dict, set]:
    fields: dict[str, str | None] = {}
    present: set[str] = set()
    for line in frontmatter_lines:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            continue
        key = match.group(1)
        raw_value = match.group(2).strip()
        present.add(key)
        fields[key] = normalize_value(raw_value)
    return fields, present


def validate_skill(path: pathlib.Path) -> list[str]:
    errors = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"Failed to read file: {exc}"]

    lines = text.splitlines()
    parsed, err = parse_frontmatter(lines)
    if err:
        return [err]

    frontmatter_lines, body_lines = parsed
    fields, present = parse_frontmatter_fields(frontmatter_lines)

    name_value = fields.get("name")
    if "name" not in present:
        errors.append("Frontmatter missing required field: name")
    elif not name_value:
        errors.append("Frontmatter field 'name' must be a non-empty string")
    else:
        if len(name_value) > MAX_NAME_LENGTH:
            errors.append(f"Frontmatter field 'name' exceeds {MAX_NAME_LENGTH} chars")
        if not NAME_PATTERN.match(name_value):
            errors.append(
                "Frontmatter field 'name' must be lowercase letters, numbers, "
                "and single hyphens only"
            )
        if path.parent.name != name_value:
            errors.append(
                "Frontmatter field 'name' must match the parent directory name"
            )

    description_value = fields.get("description")
    if "description" not in present:
        errors.append("Frontmatter missing required field: description")
    elif not description_value:
        errors.append("Frontmatter field 'description' must be a non-empty string")
    elif len(description_value) > MAX_DESC_LENGTH:
        errors.append(
            f"Frontmatter field 'description' exceeds {MAX_DESC_LENGTH} chars"
        )

    compatibility_value = fields.get("compatibility")
    if "compatibility" in present:
        if not compatibility_value:
            errors.append(
                "Frontmatter field 'compatibility' must be a non-empty string"
            )
        elif len(compatibility_value) > MAX_COMPAT_LENGTH:
            errors.append(
                f"Frontmatter field 'compatibility' exceeds {MAX_COMPAT_LENGTH} chars"
            )

    body_text = "\n".join(body_lines).strip()
    if not body_text:
        errors.append("Missing markdown content after frontmatter")

    return errors


def main():
    skill_files = [
        p for p in ROOT.rglob(SKILL_GLOB) if p.is_file() and not is_excluded(p)
    ]

    if not skill_files:
        print("No SKILL.md files found.")
        return 1

    all_errors = []
    for path in skill_files:
        errors = validate_skill(path)
        if errors:
            for err in errors:
                all_errors.append(f"{path.relative_to(ROOT)}: {err}")

    if all_errors:
        print("Skill validation failed:")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print(f"Validated {len(skill_files)} SKILL.md files successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
