use std::process::Command;

use anyhow::{Context, Result, bail};
use serde::Serialize;

pub const MINIMUM_AVAILABLE_RAM_KIB: u64 = 10 * 1024 * 1024;
pub const MINIMUM_FREE_VRAM_MIB: u64 = 4096;

#[derive(Serialize, Clone)]
pub struct ResourcePreflight {
    pub available_ram_kib: u64,
    pub minimum_available_ram_kib: u64,
    pub free_vram_mib: u64,
    pub minimum_free_vram_mib: u64,
}

pub fn check_resources() -> Result<ResourcePreflight> {
    let available_ram_kib = read_available_ram_kib()?;
    let free_vram_mib = read_free_vram_mib()?;
    if available_ram_kib < MINIMUM_AVAILABLE_RAM_KIB {
        bail!(
            "play mode requires at least 10 GiB available RAM; found {:.2} GiB",
            available_ram_kib as f64 / (1024.0 * 1024.0)
        );
    }
    if free_vram_mib < MINIMUM_FREE_VRAM_MIB {
        bail!("play mode requires at least 4096 MiB free VRAM; found {free_vram_mib} MiB");
    }
    Ok(ResourcePreflight {
        available_ram_kib,
        minimum_available_ram_kib: MINIMUM_AVAILABLE_RAM_KIB,
        free_vram_mib,
        minimum_free_vram_mib: MINIMUM_FREE_VRAM_MIB,
    })
}

fn read_available_ram_kib() -> Result<u64> {
    let meminfo = std::fs::read_to_string("/proc/meminfo")
        .context("cannot read /proc/meminfo for play-mode RAM preflight")?;
    let host_available_kib = meminfo
        .lines()
        .find_map(|line| {
            line.strip_prefix("MemAvailable:")
                .and_then(|value| value.split_whitespace().next())
                .and_then(|value| value.parse().ok())
        })
        .context("/proc/meminfo has no valid MemAvailable value")?;
    Ok(
        cgroup_available_ram_kib()
            .map_or(host_available_kib, |limit| host_available_kib.min(limit)),
    )
}

fn cgroup_available_ram_kib() -> Option<u64> {
    let maximum = std::fs::read_to_string("/sys/fs/cgroup/memory.max")
        .ok()?
        .trim()
        .parse::<u64>()
        .ok()?;
    let current = std::fs::read_to_string("/sys/fs/cgroup/memory.current")
        .ok()?
        .trim()
        .parse::<u64>()
        .ok()?;
    Some(maximum.saturating_sub(current) / 1024)
}

fn read_free_vram_mib() -> Result<u64> {
    let output = Command::new("nvidia-smi")
        .args(["--query-gpu=memory.free", "--format=csv,noheader,nounits"])
        .output()
        .context("cannot run nvidia-smi for play-mode VRAM preflight")?;
    if !output.status.success() {
        bail!("nvidia-smi could not read GPU memory before play mode");
    }
    String::from_utf8(output.stdout)
        .context("nvidia-smi returned non-UTF8 GPU memory data")?
        .lines()
        .next()
        .context("nvidia-smi reported no available GPU")?
        .trim()
        .parse()
        .context("nvidia-smi returned an invalid free-VRAM value")
}

#[cfg(test)]
mod tests {
    use super::{MINIMUM_AVAILABLE_RAM_KIB, MINIMUM_FREE_VRAM_MIB};

    #[test]
    fn play_guard_requires_margin_over_the_recorded_capture_peak() {
        assert_eq!(MINIMUM_AVAILABLE_RAM_KIB, 10 * 1024 * 1024);
        assert_eq!(MINIMUM_FREE_VRAM_MIB, 4096);
    }
}
