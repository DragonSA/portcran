from typing import Dict, Iterable, List, Tuple
from .core import MakeDict, Uses

__all__ = ['Gnome', 'MySQL', 'PgSQL', 'PkgConfig', 'ShebangFix']


def create_uses(name: str) -> type:
    @Uses.register(name)
    class UsesClass(Uses):
        def __init__(self) -> None:
            super(UsesClass, self).__init__(name)
    return UsesClass


MySQL = create_uses('mysql')
PgSQL = create_uses('pgsql')
PkgConfig = create_uses('pkgconfig')


@Uses.register('gnome')
class Gnome(Uses):
    def __init__(self) -> None:
        super(Gnome, self).__init__('gnome')
        self.components: List[str] = []

    def generate(self) -> Iterable[Tuple[str, Iterable[str]]]:
        if self.components:
            yield ('USE_GNOME', self.components)

    def load(self, variables: MakeDict) -> None:
        self.components = variables.pop('USE_GNOME', default=[])


@Uses.register('perl5')
class Perl5(Uses):
    def __init__(self) -> None:
        super(Perl5, self).__init__('perl5')
        self.components: List[str] = []

    def generate(self) -> Iterable[Tuple[str, Iterable[str]]]:
        if self.components:
            yield ('USE_PERL5', self.components)

    def load(self, variables: MakeDict) -> None:
        self.components = variables.pop('USE_PERL5', default=[])


@Uses.register('shebangfix')
class ShebangFix(Uses):
    def __init__(self) -> None:
        super(ShebangFix, self).__init__('shebangfix')
        self.files: List[str] = []
        self.languages: Dict[str, Tuple[str, str]] = {}

    def generate(self) -> Iterable[Tuple[str, Iterable[str]]]:
        if self.files:
            yield ('SHEBANG_FILES', self.files)
        if self.languages:
            yield ('SHEBANG_LANG', sorted(self.languages))
            for lang in sorted(self.languages):
                old_cmd, new_cmd = self.languages[lang]
                yield ('%s_OLD_CMD' % lang, (old_cmd,))
                yield ('%s_CMD' % lang, (new_cmd,))

    def load(self, variables: MakeDict) -> None:
        self.files = variables.pop('SHEBANG_FILES', default=[])
        for lang in variables.pop('SHEBANG_LANG', default=[]):
            old_cmd = variables.pop_value('%s_OLD_CMD' % lang)
            new_cmd = variables.pop_value('%s_CMD' % lang)
            assert old_cmd is not None and new_cmd is not None
            self.languages[lang] = (old_cmd, new_cmd)
