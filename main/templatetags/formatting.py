from django import template


register = template.Library()


@register.filter
def phone_format(value):
    if not value:
        return ""

    raw_value = str(value)
    digits = "".join(character for character in raw_value if character.isdigit())

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    return raw_value


@register.filter
def get_item(mapping, key):
    if not mapping:
        return ""

    return mapping.get(key, "")
