#[path = "walkability_harness/mod.rs"]
mod walkability_harness;

fn main() -> anyhow::Result<()> {
    walkability_harness::run()
}
