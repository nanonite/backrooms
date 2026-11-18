# Issue 274: local audio analysis through MCP

Research status: upstream project pages were consulted through a read-only web research tool; the execution sandbox has no network access. Published claims are distinguished from runtime verification below. No software was installed, model downloaded, audio processed, or host connected to a server. The supplied issue includes one comment, the operator's clarification; no issue tracker was accessible to check for additional comments. Proposed commands and configurations below are designs, not tested instructions.

## Candidates

The target is a local stdio MCP server that reads a local file path and returns measurements as text or JSON, without uploading audio. The first two candidates are existing MCP servers; the libraries and CLIs require the proposed adapter and registration described below. Nix package attributes and uv installs are unverified; installs would require access to the relevant package sources unless cached. CPU-only assessments are based on the intended operations, not a runtime test.

| Candidate and upstream link | Existence evidence; licence and maintenance | Linux / installation | CPU and possible text measurements |
| --- | --- | --- | --- |
| [mcp-local-music-analysis](https://pypi.org/project/mcp-local-music-analysis/) | PyPI confirms existence and MIT licence; one maintainer, release 0.1.0 dated 2026-05-23 and alpha status; ongoing maintenance unknown. | Python >=3.11; publisher proposes `uvx -n mcp_local_music_analysis`; Ubuntu 24.04 and offline cached install untested. | CPU expected, GPU requirement unverified. Publisher documents local `full_analysis(file_path)`, stdio and JSON including RMS, centroid, bandwidth and MFCC; clipping, silence, RT60 and bands not documented. Offline operation and three-host compatibility untested. |
| [mcp-music-analysis](https://github.com/hugohow/mcp-music-analysis) | Upstream repository exists and states MIT; recent maintenance unknown. | Upstream documents `uv venv` and `uv pip install -e .`, or `uvx -n mcp-music-analysis`; Ubuntu 24.04 and offline cached install untested. | CPU expected, GPU requirement unverified. Upstream documents local file paths, stdio client command and centroid, onset, MFCC and duration; exact output format and offline operation untested. URL inputs also exist: restrict use to local paths. Clipping, silence, RT60 and bands not documented. |
| [FFmpeg](https://ffmpeg.org/) | Locally installed `ffmpeg` 6.1.1, Ubuntu package. Licence varies with build configuration (LGPL/GPL); exact terms and current maintenance unverified. | Local Ubuntu build present; suggested `nix shell nixpkgs#ffmpeg`, availability unverified. | CPU; filters can report levels and silence in log text; exact filter outputs and clipping detection need verification. |
| [SciPy](https://scipy.org/) | Local Python import reports 1.18.1. BSD licence and current maintenance unverified. | Local Linux import works; proposed `uv add scipy`, Ubuntu 24.04 installation unverified. | CPU; an adapter could compute STFT, band energies, peaks and decay from arrays and serialize them as JSON. |
| [NumPy](https://numpy.org/) | Local Python import reports 2.5.3. BSD licence and current maintenance unverified. | Local Linux import works; proposed `uv add numpy`, Ubuntu 24.04 installation unverified. | CPU; FFT, RMS, clipping counts and band energy require adapter code and JSON serialization. |
| [librosa](https://librosa.org/) | Upstream [repository](https://github.com/librosa/librosa) and [ISC licence](https://github.com/librosa/librosa/blob/main/LICENSE.md) verified; current maintenance unverified. | Proposed `uv add librosa`; Linux and Ubuntu 24.04 compatibility unverified. | CPU expected; STFT, onset, RMS and centroid available in principle as arrays, which an adapter would serialize; not tested. |
| [SoX](https://sox.sourceforge.net/) | [Project page](https://sourceforge.net/projects/sox/) confirms existence and lists GPLv2 and LGPLv2; last page update 2024-11-28, current maintenance unverified. | Proposed `nix shell nixpkgs#sox`; Linux and Ubuntu 24.04 support unverified. | CPU expected; statistics and silence detection in CLI output are candidate capabilities, unverified. |

FFmpeg's installed build and the Python imports establish existence only, not suitability or package provenance for deployment. The two existing MCP servers above merit evaluation before writing a wrapper; published descriptions alone cannot establish compliance with offline operation, all three hosts, or the full measurement set. The issue's AudioToolAgent, Audio-Maestro, AST, PANNs and Whisper references were not verified and are not relied upon. A model is not needed for the first slice; material classification would need separate evaluation with labelled data.

## Host registration for a proposed adapter

The CLI and library rows above use this **same hypothetical wrapper**, not direct registration of the underlying CLI or library. The existing MCP candidates use the separate registrations below. After an eventual uv installation, assume an executable named `audio-analysis-mcp` reads MCP on stdin/stdout, accesses local paths and returns JSON text. Its name, executable, protocol behavior and offline operation do not yet exist or have not been checked. Keep diagnostic logs on stderr. These host configuration shapes are illustrative and must be verified against each installed host version before use. The installed Claude help confirms `claude mcp add` supports `--transport stdio`; Codex help confirms a local command can be added, but the TOML shape below was not checked. The opencode CLI could not start because its log directory is read-only.

Claude Code:

```sh
claude mcp add --transport stdio audio-analysis -- audio-analysis-mcp
```

Codex `config.toml`:

```toml
[mcp_servers.audio-analysis]
command = "audio-analysis-mcp"
args = []
```

opencode `opencode.json`:

```json
{
  "mcp": {
    "audio-analysis": {
      "type": "local",
      "command": ["audio-analysis-mcp"],
      "enabled": true
    }
  }
}
```

The host must grant the process permission to read the requested file. A local path should be validated and confined to explicitly allowed roots; reject oversized, invalid and unsupported files. Do not invoke a shell with the path. Avoid opening URLs or transmitting file contents. Offline stdio, JSON output, and these security properties remain untested for every candidate.

### Existing MCP server registration (proposed; not tested)

Both publishers show `uvx` launch commands. After installing or pre-caching dependencies with uv, substitute an absolute executable from the prepared environment if necessary to ensure offline startup; `uvx` can otherwise access the network. For each server, these are the candidate-specific command and argument vectors:

| Server | `command` | `args` |
| --- | --- | --- |
| mcp-local-music-analysis | `uvx` | `["-n", "mcp_local_music_analysis"]` |
| mcp-music-analysis | `uvx` | `["-n", "mcp-music-analysis"]` |

For **each** row, replace `PROGRAM` with its sole argument from the table in these proposed host configurations. For Claude Code, use `claude mcp add --transport stdio audio-analysis -- uvx -n PROGRAM`. For Codex:

```toml
[mcp_servers.audio-analysis]
command = "uvx"
args = ["-n", "PROGRAM"]
```

For opencode:

```json
{"mcp":{"audio-analysis":{"type":"local","command":["uvx","-n","PROGRAM"],"enabled":true}}}
```

The local-music publisher explicitly describes stdio and local paths with JSON. The music-analysis repository shows subprocess configuration and local paths, but does not establish all output shapes. Neither publisher demonstrates these exact configurations on Claude Code, Codex and opencode, nor verifies network isolation or Ubuntu 24.04. Both therefore remain **possible fits, not proven compliant**. The music-analysis server also accepts remote inputs; using only local paths is not proof that it cannot make network requests.

## Measurements and interpretation

| Need | Useful measurements and limits |
| --- | --- |
| Footstep material | Detect transients, estimate onset/decay envelope and spectral centroid, and compare per-band energy across consistently recorded examples. These descriptors cannot establish material identity on their own; room, footwear and microphone change them. |
| Room acoustics | Estimate early reflection delays and amplitudes and RT60 from a measured impulse response, with stated sample rate, noise floor and fitting range. Extrapolating a shorter decay can be unreliable; arbitrary footstep recordings do not provide a trustworthy room impulse response by themselves. |
| Loudness and levels | Peak and frame RMS in dBFS; integrated loudness in LUFS only with a validated loudness implementation and documented channel treatment. |
| Clipping | Count full-scale or near-full-scale samples and consecutive runs per channel; thresholds are configurable, and this does not prove where distortion arose. |
| Silence | Report intervals under a specified RMS threshold and minimum duration; distinguish digital silence from quiet background. |
| Per-band energy | Integrate STFT power over stated frequency bands, window, hop, normalization and channel policy. Report units and timestamps. |

## Comparison and recommendation

FFmpeg is locally present and useful for decoding and existing statistics; parsing logs and controlling versions needs care. SciPy and NumPy provide local numerical building blocks but need an adapter and decoding support. librosa may offer higher-level features, subject to dependency and licence verification. SoX may provide concise CLI statistics but remains unverified here. The two existing servers support useful spectral analysis on local paths according to their publishers, but neither has been verified against all host, offline and measurement requirements. First evaluate mcp-local-music-analysis with a synthetic WAV and each host; its documented JSON and local-only input make it the strongest initial candidate. If it cannot meet the bounded measurements or isolation requirements, extend an appropriate existing server or build a small stdio adapter around a proven CPU library. Compatibility remains untested.

## Ready-to-file first slice

**Title:** Add a local stdio audio measurements MCP for three agent hosts

**Scope:** Build an installable CPU-only local MCP with uv or nix, using a verified library. Accept a local WAV path within configured allowed roots; return bounded JSON for duration, sample rate, channels, peak, RMS, clipping counts, silence intervals and configurable per-band energies. Document units, thresholds, window/hop and error cases. No hosted services or model downloads. Defer material classification and RT60 estimation.

**Acceptance:** Install and start on Ubuntu 24.04 with the documented uv or nix method. Provide working registration snippets for Claude Code, Codex and opencode; each starts the same stdio server, reads an allowed local WAV and returns text/JSON without a network connection. Reject invalid, out-of-root and oversized inputs cleanly. Reserve stdout for MCP, send diagnostics to stderr, and document resource limits and dependencies.

**Verification:** Generate a synthetic WAV locally with known silence, sine frequency and amplitude, plus a deliberately full-scale segment. Assert duration, RMS, peak, band selection, clipping and silence against documented tolerances; exercise invalid paths and limits. Run the self-test and a real tool call in each host with networking disabled on Ubuntu 24.04; record versions, commands and results.

## Possible uses elsewhere

Options include comparing levels between builds, finding clipped or silent assets, checking whether a sound contains expected frequency bands, and tracking measured changes to acoustic test fixtures. Each project would need its own recording conditions and thresholds.

## Unknowns and limits

- Current upstream maintenance, dependency licences, package compatibility and suitability of these and other audio MCP servers need further investigation and runtime verification.
- No installation, model or GPU run, synthetic WAV self-test, audio measurement, stdio session, offline verification or three-host integration was performed. Exact registration syntax and package availability remain to be tested.
- No labelled material dataset, classification accuracy, calibrated loudness implementation, room impulse response or reliable RT60 estimator was evaluated.
- Numeric analysis does not replace the operator listening; it cannot establish whether audio sounds right.
