"""Удаление SSL-зависимых переопределяемых объектов для сборки CFE как CF."""
import re
import shutil
from pathlib import Path


def patch_file(path: Path, func):
    text = path.read_text(encoding='utf-8')
    path.write_text(func(text), encoding='utf-8')


# 1. Удаляем каталог SSL-пользователей
shutil.rmtree('src/Catalogs/Пользователи', ignore_errors=True)

# 2. UUID вместо CatalogRef.Пользователи
patch_file(
    Path('src/DefinedTypes/кфкПользователь/кфкПользователь.mdo'),
    lambda t: t.replace('CatalogRef.Пользователи', 'UUID'),
)

# 3. Патч Configuration.mdo
def patch_mdo(text):
    text = re.sub(r'\s*<catalogs>Catalog\.Пользователи</catalogs>', '', text)
    return text
patch_file(Path('src/Configuration/Configuration.mdo'), patch_mdo)
