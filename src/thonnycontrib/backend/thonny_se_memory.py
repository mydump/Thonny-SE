# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Import explicit source snapshots in memory; never create Python files."""
import hashlib
import importlib.abc
import importlib.util
import linecache
from pathlib import Path
import sys


class MemoryModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.sources = {}
        self.loaded = {}

    def configure(self, sources):
        for source in sources:
            previous = self.sources.get(source['name'])
            if previous is not None and previous['text'] != source['text'] and source['name'] in self.loaded:
                raise ValueError('memory_source_changed')
        for source in sources:
            name = source['name']
            existing = sys.modules.get(name)
            if existing is not None and name not in self.loaded:
                if getattr(existing, '__file__', None) != source['filename']:
                    raise ValueError('module_name_conflict')
                sys.modules.pop(name)
            self.sources[name] = source
        if self not in sys.meta_path:
            sys.meta_path.insert(0, self)

    def find_spec(self, fullname, path=None, target=None):
        source = self.sources.get(fullname)
        if source is None:
            return None
        return importlib.util.spec_from_loader(fullname, self, origin=source['filename'],
                                               is_package=source.get('package', False))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = self.sources[module.__name__]
        filename, text = source['filename'], source['text']
        module.__file__ = filename
        if source.get('package'):
            module.__path__ = [str(Path(filename).parent)]
        linecache.cache[filename] = (len(text), None, text.splitlines(keepends=True), filename)
        exec(compile(text, filename, 'exec'), vars(module))
        self.loaded[module.__name__] = hashlib.sha256(text.encode('utf-8')).hexdigest()

    def load(self, name):
        source = self.sources[name]
        module = sys.modules.get(name)
        if module is not None and name not in self.loaded:
            origin = getattr(module, '__file__', None)
            if origin != source['filename']:
                raise ValueError('module_name_conflict')
            # An ordinary Run may have imported the saved version earlier.
            # Replace that module with the explicitly requested snapshot.
            sys.modules.pop(name)
        paths = [item['root'] for item in self.sources.values() if item.get('root')]
        for path in reversed(paths):
            if path not in sys.path:
                sys.path.insert(0, path)
        return importlib.import_module(name)

    def clear(self):
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        for name, source in self.sources.items():
            module = sys.modules.get(name)
            if module is not None and getattr(module, '__file__', None) == source['filename']:
                sys.modules.pop(name, None)
            linecache.cache.pop(source['filename'], None)
        self.sources.clear()
        self.loaded.clear()
