from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cutip.models.base import CutipBaseModel
from cutip.models.group import Group
from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipError


@dataclass
class CutipRegistry:
    """In-memory registry of all discovered CUTIP artifacts.

    Cards are keyed by "<prefix>/<name>" (e.g. "containers/my-app").
    Units and groups are keyed by their metadata.name.
    """

    cards: dict[str, CutipBaseModel] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)

    # maps artifact name → source file path (for diagnostics)
    _sources: dict[str, Path] = field(default_factory=dict, repr=False)

    def register(self, artifact: CutipBaseModel, source: Path | None = None) -> None:
        """Add an artifact to the registry. Raises on duplicate name."""
        from cutip.utils.yaml_loader import kind_prefix

        kind = artifact.kind
        name = artifact.name
        key = f"{kind_prefix(kind)}/{name}"

        if isinstance(artifact, Group):
            if name in self.groups:
                raise CutipError(f"Duplicate Group name '{name}' (already registered)")
            self.groups[name] = artifact
        elif isinstance(artifact, Unit):
            if name in self.units:
                raise CutipError(f"Duplicate Unit name '{name}' (already registered)")
            self.units[name] = artifact
        else:
            if key in self.cards:
                raise CutipError(f"Duplicate card ref '{key}' (already registered)")
            self.cards[key] = artifact

        if source:
            self._sources[key] = source

    def get_card(self, ref: str) -> CutipBaseModel | None:
        """Look up a card by its ref string (e.g. 'containers/my-app')."""
        return self.cards.get(ref)

    def get_unit(self, name: str) -> Unit | None:
        """Look up a unit by name."""
        return self.units.get(name)

    def get_group(self, name: str) -> Group | None:
        """Look up a group by name."""
        return self.groups.get(name)

    def source_of(self, ref: str) -> Path | None:
        """Return the file path where an artifact was loaded from."""
        return self._sources.get(ref)
