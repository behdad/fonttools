from collections import UserDict, UserList
import operator

__all__ = ["LazyDict", "LazyList"]


class LazyDict(UserDict):
    def __init__(self, data):
        super().__init__()
        self.data = data

    def __getitem__(self, k):
        v = self.data[k]
        if callable(v):
            v = v(k)
            self.data[k] = v
        return v


class LazyList(UserList):
    def __getitem__(self, k):
        if isinstance(k, slice):
            indices = range(*k.indices(len(self)))
            return [self[i] for i in indices]
        k = operator.index(k)
        v = self.data[k]
        if callable(v):
            if k < 0:
                k += len(self)
            v = v(k)
            self.data[k] = v
        return v

    def __add__(self, other):
        if isinstance(other, LazyList):
            other = list(other)
        elif isinstance(other, list):
            pass
        else:
            return NotImplemented
        return list(self) + other

    def __radd__(self, other):
        if not isinstance(other, list):
            return NotImplemented
        return other + list(self)
