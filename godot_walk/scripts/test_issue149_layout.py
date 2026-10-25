"""Contract tests for seeded #149 room layouts."""

from __future__ import annotations

import copy
import unittest

from issue149_layout_core import (
    MAX_PLACEMENTS,
    MIN_PLACEMENTS,
    _seed_choice,
    canonical_json,
    generate_layout,
    load_catalog_snapshot,
    validate_layout,
)


class Issue149LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot, cls.catalog_hash, cls.snapshot_bytes = load_catalog_snapshot()

    def test_layout_serialization_is_seed_reproducible(self) -> None:
        first = generate_layout(149, 10, self.snapshot, self.catalog_hash, bounded_streaming=True)
        second = generate_layout(149, 10, self.snapshot, self.catalog_hash, bounded_streaming=True)
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(first["layout_sha256"], second["layout_sha256"])

    def test_supported_sizes_have_a_branch_and_round_trip_route(self) -> None:
        north_seed = self._seed_with_branch_yaw(0)
        south_seed = self._seed_with_branch_yaw(180)
        for seed, count in ((north_seed, MIN_PLACEMENTS), (south_seed, MAX_PLACEMENTS)):
            with self.subTest(seed=seed, count=count):
                layout = generate_layout(seed, count, self.snapshot, self.catalog_hash)
                self.assertEqual(len(layout["placements"]), count)
                self.assertEqual(len(layout["connections"]), count - 1)
                self.assertEqual(layout["topology"]["cycle_rank"], 0)
                self.assertEqual(layout["topology"]["branch_yaw_degrees"], 180 if seed == south_seed else 0)
                self.assertEqual(layout["walk_route_xz"][0], layout["walk_route_xz"][-1])
                self.assertEqual(validate_layout(layout, self.snapshot), [])

    def test_every_open_socket_is_connected_once(self) -> None:
        layout = generate_layout(149, 10, self.snapshot, self.catalog_hash, bounded_streaming=True)
        for placement in layout["placements"]:
            self.assertEqual(set(placement["open_sockets"]), set(placement["connected_sockets"]))
        self.assertEqual(layout["topology"]["dead_end_count"], 3)
        self.assertGreater(layout["repeated_instances"], 0)

    def test_socket_reuse_and_footprint_overlap_are_rejected(self) -> None:
        layout = generate_layout(149, 10, self.snapshot, self.catalog_hash)
        changed = copy.deepcopy(layout)
        changed["connections"].append(copy.deepcopy(changed["connections"][0]))
        self.assertIn("a socket is connected more than once", validate_layout(changed, self.snapshot))
        changed = copy.deepcopy(layout)
        changed["placements"][1]["transform"]["position"][0] = 0.0
        self.assertTrue(any("footprints overlap" in error for error in validate_layout(changed, self.snapshot)))

    def test_unsupported_loops_and_sizes_are_rejected(self) -> None:
        layout = generate_layout(149, 10, self.snapshot, self.catalog_hash)
        changed = copy.deepcopy(layout)
        changed["settings"]["loops"] = True
        self.assertIn("loops are unsupported by this kit", validate_layout(changed, self.snapshot))
        with self.assertRaisesRegex(ValueError, "between 10 and 20"):
            generate_layout(149, MIN_PLACEMENTS - 1, self.snapshot, self.catalog_hash)
        with self.assertRaisesRegex(ValueError, "between 10 and 20"):
            generate_layout(149, MAX_PLACEMENTS + 1, self.snapshot, self.catalog_hash)

    def test_configured_layout_envelope_is_enforced(self) -> None:
        layout = generate_layout(149, 10, self.snapshot, self.catalog_hash)
        changed = copy.deepcopy(layout)
        changed["settings"]["layout_bounds_m"] = [-1.0, -1.0, 1.0, 1.0]
        self.assertIn("placement footprints exceed layout_bounds_m", validate_layout(changed, self.snapshot))
        changed["settings"]["layout_bounds_m"] = [-160.0, -30.0, 180.0]
        self.assertIn("layout_bounds_m must contain min_x, min_z, max_x, max_z", validate_layout(changed, self.snapshot))

    def test_streaming_settings_are_bounded_and_reproducible(self) -> None:
        layout = generate_layout(149, 10, self.snapshot, self.catalog_hash, bounded_streaming=True)
        settings = layout["settings"]["streaming"]
        self.assertEqual(settings["mode"], "bounded_graph_window")
        self.assertEqual(settings["graph_radius"], 1)
        self.assertEqual(settings["max_resident_modules"], 4)
        changed = copy.deepcopy(layout)
        changed["settings"]["streaming"]["mode"] = "unbounded"
        self.assertIn("streaming must use the supported radius-one, four-module window",
                      validate_layout(changed, self.snapshot))

    def test_catalog_snapshot_hashes_generation_and_scene_dependencies(self) -> None:
        hashes = {item["path"]: item["sha256"] for item in self.snapshot["file_hashes"]}
        for path in self.snapshot["generation_dependencies"]:
            self.assertIn(path, hashes)
        runtime = {item["path"] for item in self.snapshot["runtime_dependencies"]}
        self.assertIn("godot_walk/scripts/issue149_generated_walkthrough.gd", runtime)
        self.assertIn("godot_walk/scenes/issue149_generated_walkthrough.tscn", runtime)
        self.assertNotIn("godot_walk/scripts/issue149_layout_core.py", runtime)
        self.assertEqual(self.snapshot["registration_accepted"], False)
        self.assertEqual(self.snapshot["scale_calibrated"], False)

    @staticmethod
    def _seed_with_branch_yaw(yaw: int) -> int:
        desired_parity = 0 if yaw == 0 else 1
        return next(seed for seed in range(1000) if _seed_choice(seed + 1) % 2 == desired_parity)


if __name__ == "__main__":
    unittest.main()
