mod files;
mod model;
mod primitives;
mod runtime_model;
mod structure;
mod validate;

pub use model::Catalog;
pub use validate::{validate_catalog, validate_structure};

pub const CATALOG_PATH: &str = "splat_walk/room_catalog/catalog.json";

#[cfg(test)]
mod tests;
