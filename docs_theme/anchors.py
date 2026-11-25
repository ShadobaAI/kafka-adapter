"""Use Latin URL fragments while keeping the headings in Russian."""

from markdown.extensions.toc import slugify

_RUSSIAN = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
_LATIN = (
    "a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m",
    "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch",
    "", "y", "", "e", "yu", "ya",
)
_TRANSLITERATION = str.maketrans(dict(zip(_RUSSIAN, _LATIN, strict=True)))


def latin_slug(value, separator):
    return slugify(value.lower().translate(_TRANSLITERATION), separator).strip(separator)


def on_config(config):
    for extension in ("toc", "pymdownx.tabbed"):
        config.mdx_configs.setdefault(extension, {})["slugify"] = latin_slug
    return config
