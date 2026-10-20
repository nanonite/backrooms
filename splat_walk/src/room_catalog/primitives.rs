use anyhow::{Result, bail};

pub fn validate_stable_id(value: &str, label: &str) -> Result<()> {
    if value.is_empty()
        || value.starts_with('-')
        || value.ends_with('-')
        || value.contains("--")
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    {
        bail!("{label} ID must be a lowercase stable slug: {value}");
    }
    Ok(())
}

pub fn validate_nonempty(value: &str, label: &str) -> Result<()> {
    if value.trim().is_empty() {
        bail!("{label} must not be empty");
    }
    Ok(())
}

pub fn validate_finite(values: &[f64], label: &str) -> Result<()> {
    if values.iter().any(|value| !value.is_finite()) {
        bail!("{label} must contain only finite values");
    }
    Ok(())
}
