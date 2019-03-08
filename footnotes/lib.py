def cached_property(func):
    def getter(self):
        if not hasattr(self, '_cache'):
            self._cache = {}
        if func not in self._cache:
            self._cache[func] = func(self)
        return self._cache[func]

    return property(fget=getter)
