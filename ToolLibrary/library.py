"""Independent, in-memory rules for a numbered tool library."""

from dataclasses import dataclass, replace


def _validate_number(number):
    if type(number) is not int or number < 1:
        raise ValueError("Tool number must be a positive integer.")


@dataclass(frozen=True)
class ToolEntry:
    """A library number and an opaque reference to a reusable tool asset."""

    number: int
    tool_id: str
    name: str = ""
    shape: str = ""

    def __post_init__(self):
        _validate_number(self.number)
        if not isinstance(self.tool_id, str) or not self.tool_id.strip():
            raise ValueError("Tool identity must be a non-empty string.")
        if not isinstance(self.name, str) or not isinstance(self.shape, str):
            raise ValueError("Tool name and shape must be strings.")


class ToolLibrary:
    """Manage entries without file, GUI or machining dependencies."""

    def __init__(self, entries=()):
        self._entries = {}
        for entry in entries:
            self.add(entry)

    @property
    def entries(self):
        return tuple(self._entries[number] for number in sorted(self._entries))

    @property
    def next_number(self):
        return max(self._entries, default=0) + 1

    def get(self, number):
        _validate_number(number)
        return self._entries[number]

    def add(self, entry):
        if not isinstance(entry, ToolEntry):
            raise TypeError("Expected a ToolEntry.")
        if entry.number in self._entries:
            raise ValueError(f"Tool number {entry.number} is already in use.")
        if any(existing.tool_id == entry.tool_id for existing in self._entries.values()):
            raise ValueError(f"Tool {entry.tool_id} is already in this library.")
        self._entries[entry.number] = entry
        return entry

    def remove(self, number):
        self.get(number)
        return self._entries.pop(number)

    def renumber(self, number, new_number):
        entry = self.get(number)
        _validate_number(new_number)
        if new_number == number:
            return entry
        if new_number in self._entries:
            raise ValueError(f"Tool number {new_number} is already in use.")
        updated = replace(entry, number=new_number)
        del self._entries[number]
        self._entries[new_number] = updated
        return updated

    def edit(self, number, *, name=None, shape=None):
        entry = self.get(number)
        updated = replace(
            entry,
            name=entry.name if name is None else name,
            shape=entry.shape if shape is None else shape,
        )
        self._entries[number] = updated
        return updated