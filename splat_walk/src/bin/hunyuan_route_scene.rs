#[path = "walkability_harness/mod.rs"]
mod walkability_harness;

fn main() -> anyhow::Result<()> {
    if std::env::args().any(|argument| argument == "--full-harness") {
        walkability_harness::run()
    } else if std::env::args().any(|argument| argument == "--capture") {
        walkability_harness::run_route_scene_capture()
    } else {
        walkability_harness::run_route_scene()
    }
}
