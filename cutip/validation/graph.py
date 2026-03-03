from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipRefError
from cutip.workspace.registry import CutipRegistry


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False


class GraphValidator:
    """Validates the full artifact graph: Group → Unit → Card chain."""

    def __init__(self, registry: CutipRegistry, project_root: Path | None = None) -> None:
        self.registry = registry
        self.project_root = project_root
        self._resolver = RefResolver(registry)

    def validate(self) -> ValidationResult:
        result = ValidationResult(ok=True)
        n_cards = len(self.registry.cards)
        n_units = len(self.registry.units)
        n_groups = len(self.registry.groups)
        logger.info(
            f"Discovered {n_cards} card(s), {n_units} unit(s), {n_groups} group(s)"
        )
        logger.info(f"Validating {n_cards} card(s) ...")
        self._validate_units(result)
        logger.info(f"Validating {n_groups} group(s) ...")
        self._validate_groups(result)
        return result

    def _validate_units(self, result: ValidationResult) -> None:
        for unit_name, unit in self.registry.units.items():
            container_ref = unit.spec.containerRef.ref

            # Resolve containerRef → ContainerCard
            try:
                container_card = self._resolver.resolve_card(container_ref, ContainerCard)
            except CutipRefError as exc:
                result.add(f"[UnitResolve] {unit_name}: {exc.reason} (ref: '{container_ref}')")
                logger.warning(f"  ✗ {container_ref} — {exc.reason}")
                continue

            logger.info(f"  ✓ {container_ref}")

            # Resolve imageRef from ContainerCard
            image_ref = container_card.spec.imageRef.ref
            try:
                self._resolver.resolve_card(image_ref, ImageCard)
                logger.info(f"  ✓ {image_ref}")
            except CutipRefError as exc:
                result.add(
                    f"[CardResolve] {unit_name} → {container_card.name}: "
                    f"{exc.reason} (imageRef: '{image_ref}')"
                )
                logger.warning(f"  ✗ {image_ref} — {exc.reason}")

            # Resolve networkRef from ContainerCard (skipped when network_mode is used)
            if container_card.spec.networkRef is not None:
                network_ref = container_card.spec.networkRef.ref
                try:
                    self._resolver.resolve_card(network_ref, NetworkCard)
                    logger.info(f"  ✓ {network_ref}")
                except CutipRefError as exc:
                    result.add(
                        f"[CardResolve] {unit_name} → {container_card.name}: "
                        f"{exc.reason} (networkRef: '{network_ref}')"
                    )
                    logger.warning(f"  ✗ {network_ref} — {exc.reason}")

    def _validate_groups(self, result: ValidationResult) -> None:
        for group_name, group in self.registry.groups.items():
            # Resolve each unit ref
            for unit_ref in group.spec.units:
                ref = unit_ref.ref
                try:
                    self._resolver.resolve_unit(ref)
                    logger.info(f"  ✓ {group_name} → {ref}")
                except CutipRefError as exc:
                    result.add(f"[GroupResolve] {group_name}: {exc.reason} (ref: '{ref}')")
                    logger.warning(f"  ✗ {group_name} → {ref} — {exc.reason}")

            # Verify workflow path exists
            group_source = self.registry.source_of(f"groups/{group_name}")
            if group_source is not None:
                group_dir = group_source.parent
            elif self.project_root is not None:
                group_dir = self.project_root / "cutip" / "groups" / group_name
            else:
                group_dir = None

            if group_dir is not None:
                workflow_path = group_dir / group.spec.workflow
                if not workflow_path.is_file():
                    result.add(
                        f"[WorkflowPath] {group_name}: workflow file not found: "
                        f"'{workflow_path}'"
                    )
                    logger.warning(f"  ✗ {group_name}: workflow not found: '{workflow_path}'")
                else:
                    logger.info(f"  ✓ {group_name}: {group.spec.workflow}")
