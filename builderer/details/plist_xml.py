from xml.sax.saxutils import escape


def plist_value_to_xml_lines(value, indent: str = "  ") -> list[str]:
    if isinstance(value, str):
        return [f"{indent}<string>{escape(value)}</string>"]
    elif isinstance(value, bool):
        return [f"{indent}<{str(value).lower()}/>"]
    elif isinstance(value, int):
        return [f"{indent}<integer>{value}</integer>"]
    elif isinstance(value, float):
        return [f"{indent}<real>{value}</real>"]
    elif isinstance(value, list):
        lines = [f"{indent}<array>"]
        for item in value:
            lines.extend(plist_value_to_xml_lines(item, indent + "  "))
        lines.append(f"{indent}</array>")
        return lines
    elif isinstance(value, dict):
        lines = [f"{indent}<dict>"]
        for key in sorted(value.keys()):
            lines.append(f"{indent}  <key>{escape(str(key))}</key>")
            lines.extend(plist_value_to_xml_lines(value[key], indent + "  "))
        lines.append(f"{indent}</dict>")
        return lines
    else:
        raise ValueError(f"unsupported plist value type: {type(value).__name__}")


def plist_dict_to_xml_text(plist: dict) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
    ]
    for key in sorted(plist.keys()):
        lines.append(f"  <key>{escape(str(key))}</key>")
        lines.extend(plist_value_to_xml_lines(plist[key], "  "))
    lines.extend(["</dict>", "</plist>"])
    return "\n".join(lines)
