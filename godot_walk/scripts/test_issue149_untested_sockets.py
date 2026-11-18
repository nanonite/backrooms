"""Non-layout modules may declare untested sockets; layout never uses them."""

from __future__ import annotations

import copy
import unittest

from issue149_layout_core import (
    MIN_PLACEMENTS,
    _validate_module,
    generate_layout,
    load_catalog_snapshot,
)

SOCKET = {
    "id": "north",
    "local_floor_center": [0.0, 0.0, -10.0],
    "outward_normal": [0.0, 0.0, -1.0],
    "clear_size_m": [2.0, 2.1],
    "floor_elevation_m": 0.0,
    "compatibility_type": "level_doorway_2m_v1",
}


class UntestedSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot, cls.catalog_hash, _ = load_catalog_snapshot()
        cls.template = next(
            module
            for module in cls.snapshot["modules"]
            if module.get("layout_eligible", True) and module.get("sockets")
        )

    def _module(self, **changes: object) -> dict:
        module = copy.deepcopy(self.template)
        module["layout_eligible"] = False
        module["sockets"] = [copy.deepcopy(SOCKET)]
        module.update(changes)
        return module

    def test_non_layout_module_may_declare_valid_sockets(self) -> None:
        _validate_module(self._module())

    def test_declared_socket_type_and_size_are_still_checked(self) -> None:
        bad_type = copy.deepcopy(SOCKET) | {"compatibility_type": "other"}
        bad_size = copy.deepcopy(SOCKET) | {"clear_size_m": [1.0, 2.0]}
        for socket in (bad_type, bad_size):
            with self.subTest(socket=socket), self.assertRaises(ValueError):
                _validate_module(self._module(sockets=[socket]))

    def test_duplicate_socket_ids_are_still_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_module(self._module(sockets=[SOCKET, copy.deepcopy(SOCKET)]))

    def test_layout_eligible_module_still_needs_sockets(self) -> None:
        with self.assertRaises(ValueError):
            _validate_module(self._module(layout_eligible=True, sockets=[]))

    def test_layout_never_places_a_non_layout_module(self) -> None:
        ineligible = {
            module["id"]
            for module in self.snapshot["modules"]
            if not module.get("layout_eligible", True)
        }
        self.assertTrue(ineligible)
        for seed in range(40):
            layout = generate_layout(
                seed, MIN_PLACEMENTS, self.snapshot, self.catalog_hash
            )
            used = {placement["module_id"] for placement in layout["placements"]}
            self.assertFalse(used & ineligible, f"seed {seed}")


if __name__ == "__main__":
    unittest.main()
