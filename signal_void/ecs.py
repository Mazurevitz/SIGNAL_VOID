"""
Entity-Component-System Core
=============================
Data-driven ECS using integer entity IDs and component dictionaries.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Type, TypeVar, Optional, Iterator, Tuple, Any
import itertools


# Type variable for component types
C = TypeVar('C')


class World:
    """
    The ECS World manages all entities and their components.

    Entities are integer IDs. Components are stored in dictionaries
    keyed by entity ID, with one dict per component type.
    """

    def __init__(self):
        self._next_entity_id: int = 0
        self._entities: Set[int] = set()
        self._components: Dict[Type, Dict[int, Any]] = {}
        self._dead_entities: Set[int] = set()  # Marked for removal

    def create_entity(self) -> int:
        """Create a new entity and return its ID."""
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        self._entities.add(entity_id)
        return entity_id

    def destroy_entity(self, entity_id: int) -> None:
        """Mark an entity for destruction (processed at end of frame)."""
        self._dead_entities.add(entity_id)

    def process_dead_entities(self) -> None:
        """Remove all entities marked for destruction."""
        for entity_id in self._dead_entities:
            if entity_id in self._entities:
                self._entities.remove(entity_id)
                # Remove all components for this entity
                for component_store in self._components.values():
                    if entity_id in component_store:
                        del component_store[entity_id]
        self._dead_entities.clear()

    def add_component(self, entity_id: int, component: Any) -> None:
        """Add a component to an entity."""
        component_type = type(component)
        if component_type not in self._components:
            self._components[component_type] = {}
        self._components[component_type][entity_id] = component

    def remove_component(self, entity_id: int, component_type: Type[C]) -> None:
        """Remove a component from an entity."""
        if component_type in self._components:
            if entity_id in self._components[component_type]:
                del self._components[component_type][entity_id]

    def get_component(self, entity_id: int, component_type: Type[C]) -> Optional[C]:
        """Get a component for an entity, or None if not found."""
        if component_type in self._components:
            return self._components[component_type].get(entity_id)
        return None

    def has_component(self, entity_id: int, component_type: Type) -> bool:
        """Check if an entity has a specific component."""
        if component_type in self._components:
            return entity_id in self._components[component_type]
        return False

    def has_components(self, entity_id: int, *component_types: Type) -> bool:
        """Check if an entity has all specified components."""
        return all(self.has_component(entity_id, ct) for ct in component_types)

    def query(self, *component_types: Type) -> Iterator[Tuple[int, ...]]:
        """
        Query for all entities that have ALL specified component types.

        Yields tuples of (entity_id, component1, component2, ...)
        """
        if not component_types:
            return

        # Find entities that have all required components
        first_type = component_types[0]
        if first_type not in self._components:
            return

        candidate_entities = set(self._components[first_type].keys())

        for component_type in component_types[1:]:
            if component_type not in self._components:
                return
            candidate_entities &= set(self._components[component_type].keys())

        # Yield entity and all its matching components
        for entity_id in candidate_entities:
            if entity_id in self._dead_entities:
                continue
            components = tuple(
                self._components[ct][entity_id] for ct in component_types
            )
            yield (entity_id,) + components

    def get_entities_with(self, *component_types: Type) -> Iterator[int]:
        """Get all entity IDs that have all specified components."""
        for result in self.query(*component_types):
            yield result[0]

    def entity_count(self) -> int:
        """Return the number of active entities."""
        return len(self._entities) - len(self._dead_entities)

    def is_alive(self, entity_id: int) -> bool:
        """Check if an entity is alive (exists and not marked for death)."""
        return entity_id in self._entities and entity_id not in self._dead_entities
