#!/usr/bin/env python3
"""Scratch-only gmap-0.6.1 variant-0 funnel and lever study."""
from __future__ import annotations

import collections
import copy
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path('/mnt/sharedOs/backrooms-workspace')
SCRIPTS = ROOT / 'godot_walk/scripts'
sys.path.insert(0, str(SCRIPTS))

import gmap_build as build
import gmap_degenerate
import gmap_diagonal
import gmap_diagonal_candidates as candidates
import gmap_diagonal_growth as growth
import gmap_diagonal_sites as sites
import gmap_diagonal_v61 as diagonal_v61
import gmap_draft_generation as draft_generation
import gmap_geometry as geometry
import gmap_grow as grow
import gmap_library
from deterministic_json import ROOT as PROJECT_ROOT
from gmap_library import Library
from gmap_grow import RetryAttempt

INDEX = ROOT / 'godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json'
VERSION = 'gmap-0.6.1'
V6 = 'gmap-0.6.0'
LIB = gmap_library.load_library(INDEX)

CONFIG = {'probability': .35, 'force_last': 0, 'armed': False, 'placement': 'lattice'}
STATE: dict = {'runs': {}, 'last_draft': {}, 'candidate_pairs': {}, 'nudged': {}}
ORIGINALS = {}


def rect_key(cell):
    return tuple(tuple(round(float(v), 6) for v in point) for point in cell['envelope_xz'])


def similarity(v6, v61):
    old = collections.Counter(rect_key(c) for c in v6['cells'])
    new = collections.Counter(rect_key(c) for c in v61['cells'])
    shared = sum((old & new).values())
    return shared / max(1, sum(old.values()))


def draft_snapshot(draft):
    return {
        c.cell_id: {
            'rect': tuple(round(float(v), 6) for v in c.rect),
            'role': c.role,
            'module': None if c.module is None else c.module.get('module_id'),
        }
        for c in draft.cells.values()
    }


def meta_of(site_rng):
    return getattr(site_rng, '_study_meta', None)


def get_trace(meta):
    key = tuple(meta)
    return STATE['runs'].setdefault(key, {
        'seed': key[0], 'attempt': key[1], 'variant': key[2],
        'steps': 0, 'eligible_steps': 0, 'tries': 0,
        'zero_option_tries': 0, 'nonzero_option_tries': 0,
        'option_total': 0, 'reservations_after_growth': 0,
        'retry_reason': None, 'snapshots': {}, 'draft': None,
    })


def instrumented_rng_for(seed, attempt, layout_variant=0):
    rng = ORIGINALS['sites_rng_for'](seed, attempt, layout_variant)
    rng._study_meta = (seed, attempt, layout_variant)
    return rng


def instrumented_step(rng, site_rng, draft, site_budget):
    meta = meta_of(site_rng)
    trace = get_trace(meta)
    trace['steps'] += 1
    draft.diagonal_budget = site_budget
    below_budget = len(draft.reserved_diagonal_zones) < site_budget
    if not below_budget:
        grow._grow_step_legacy(rng, draft)
        return
    trace['eligible_steps'] += 1
    roll = site_rng.random()
    remaining_steps = getattr(draft, '_study_target', len(draft.cells) + 1) - len(draft.cells)
    forced = bool(CONFIG['force_last'] and remaining_steps <= CONFIG['force_last'])
    armed = STATE.setdefault('armed_drafts', {}).get(id(draft), False)
    should_try = roll < CONFIG['probability'] or forced or (CONFIG['armed'] and armed)
    if not should_try:
        grow._grow_step_legacy(rng, draft)
        return
    trace['tries'] += 1
    pool = [cell for cell in draft.cells.values() if draft.degree(cell.cell_id) < 4]
    if not pool:
        grow._grow_step_legacy(rng, draft)
        return
    options = [
        (parent, rect, pair)
        for parent in pool
        for rect, pair in growth._all_site_options(draft, parent, draft.new_id())
    ]
    trace['option_total'] += len(options)
    if not options:
        trace['zero_option_tries'] += 1
        if CONFIG['armed']:
            STATE['armed_drafts'][id(draft)] = True
        grow._grow_step_legacy(rng, draft)
        return
    trace['nonzero_option_tries'] += 1
    STATE.setdefault('armed_drafts', {})[id(draft)] = False
    growth._place_site(site_rng, draft, options)
    trace['reservations_after_growth'] = len(draft.reserved_diagonal_zones)


def instrumented_grow(rng, cell_target, centred=False, margin=1.0, site_rng=None, site_budget=0):
    draft = ORIGINALS['draft_grow'](rng, cell_target, centred, margin, site_rng, site_budget)
    if site_rng is not None:
        meta = meta_of(site_rng)
        draft._study_target = cell_target
        trace = get_trace(meta)
        trace['draft'] = draft
        trace['reservations_after_growth'] = len(draft.reserved_diagonal_zones)
        trace['snapshots']['growth'] = draft_snapshot(draft)
        STATE['last_draft'][tuple(meta)] = draft
    return draft


def instrumented_attempt_once(rng, cells, classes, version, library, site_rng=None, diagonal_budget=0):
    meta = meta_of(site_rng)
    try:
        result = ORIGINALS['attempt_once'](rng, cells, classes, version, library, site_rng, diagonal_budget)
    except RetryAttempt as exc:
        if meta is not None:
            trace = get_trace(meta)
            trace['retry_reason'] = str(exc)
            draft = STATE['last_draft'].get(tuple(meta))
            trace['reservations_at_retry'] = len(draft.reserved_diagonal_zones) if draft else 0
        raise
    if meta is not None:
        trace = get_trace(meta)
        trace['snapshots']['after_attempt'] = draft_snapshot(result)
        trace['reservations_after_attempt'] = len(result.reserved_diagonal_zones)
        trace['draft'] = result
        STATE['last_draft'][tuple(meta)] = result
    return result


def wrap_stage(name, function):
    def wrapped(*args, **kwargs):
        result = function(*args, **kwargs)
        draft = next((arg for arg in args if isinstance(arg, grow.Draft)), None)
        if draft is not None:
            for key, trace in STATE['runs'].items():
                if trace.get('draft') is draft:
                    trace['snapshots'][name] = draft_snapshot(draft)
                    break
        return result
    return wrapped


def instrumented_candidates(document):
    result = ORIGINALS['candidate_pairs'](document)
    STATE['candidate_pairs'][id(document)] = result
    return result


def instrumented_nudge(document, *args, **kwargs):
    before = {c['cell_id']: rect_key(c) for c in document['cells']}
    result = ORIGINALS['nudge'](document, *args, **kwargs)
    after = {c['cell_id']: rect_key(c) for c in document['cells']}
    STATE['nudged'][id(document)] = {'reported': result, 'before': before, 'after': after}
    return result


def install_instrumentation():
    ORIGINALS.update({
        'sites_rng_for': sites.rng_for,
        'growth_step': growth.grow_step_v61,
        'draft_grow': draft_generation.grow,
        'attempt_once': draft_generation.attempt_once,
        'candidate_pairs': diagonal_v61.candidate_pairs,
        'site_placements': growth.placements,
        'nudge': diagonal_v61.nudge_to_budget,
    })
    sites.rng_for = instrumented_rng_for
    growth.grow_step_v61 = instrumented_step
    draft_generation.grow = instrumented_grow
    draft_generation.attempt_once = instrumented_attempt_once
    diagonal_v61.candidate_pairs = instrumented_candidates
    diagonal_v61.nudge_to_budget = instrumented_nudge
    for name in ('assign_tiers', 'assign_roles', 'attach_modules', 'add_voids', 'assign_degenerate'):
        if hasattr(draft_generation, name):
            ORIGINALS[name] = getattr(draft_generation, name)
            setattr(draft_generation, name, wrap_stage(name, getattr(draft_generation, name)))


def reset_state():
    STATE.clear()
    STATE.update({'runs': {}, 'last_draft': {}, 'candidate_pairs': {}, 'nudged': {}, 'armed_drafts': {}})


def release_reason(document, record, snapshots, nudged, pairs):
    ids = record['endpoint_ids']
    by_id = {c['cell_id']: c for c in document['cells']}
    if any(cell_id not in by_id for cell_id in ids):
        return 'other: endpoint missing'
    for stage in ('assign_tiers', 'assign_roles', 'attach_modules', 'add_voids', 'assign_degenerate', 'after_attempt'):
        snap = snapshots.get(stage)
        if not snap:
            continue
        for cell_id in ids:
            entry = snap.get(cell_id)
            if entry and entry.get('module'):
                return 'module attachment'
            if entry and entry.get('role') == 'void':
                return 'void placement'
    # Detect a geometry/role transition by comparing the saved end-of-growth state.
    baseline = snapshots.get('growth', {})
    for stage in ('assign_tiers', 'assign_roles', 'attach_modules', 'add_voids', 'assign_degenerate', 'after_attempt'):
        snap = snapshots.get(stage)
        if not snap:
            continue
        for cell_id in ids:
            if cell_id in baseline and cell_id in snap and baseline[cell_id] != snap[cell_id]:
                if baseline[cell_id]['rect'] != snap[cell_id]['rect']:
                    return f'{stage} geometry change'
                if baseline[cell_id]['role'] != snap[cell_id]['role']:
                    return f'{stage} role change'
    corners = record['corner_xz']
    for cell_id, corner in zip(ids, corners):
        cell = by_id[cell_id]
        if not any(all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(point, corner)) for point in cell['envelope_xz']):
            # The current render map is rectilinear before shape-room/chamfer stage.
            moved = nudged and nudged.get('reported') and cell_id in nudged.get('reported')
            return 'nudge' if moved else 'chamfer/stage-2 or envelope geometry'
        if cell.get('module'):
            return 'module attachment'
        if cell.get('role') not in ('ground', 'figure'):
            return 'role/void eligibility'
    for pair in pairs or []:
        if diagonal_v61._matches(pair, record):
            return 'endpoint reuse'  # matched, therefore released only by pair occupancy/capacity
    # Distinguish candidate-pair filters in the same order as candidate_pairs.
    a, b = (by_id[i] for i in ids)
    ar = geometry.polygon_rect(a['envelope_xz'])
    br = geometry.polygon_rect(b['envelope_xz'])
    if ar is None or br is None or min(ar[2]-ar[0], ar[3]-ar[1], br[2]-br[0], br[3]-br[1]) < 4.0:
        return 'candidate_pairs size/rect filter'
    ia, ib = record['corner_indices']
    ca, cb = record['corner_xz']
    dx, dz = cb[0]-ca[0], cb[1]-ca[1]
    if abs(dx) != 1 or abs(dz) != 1:
        return 'candidate_pairs corner-offset filter'
    sx, sz = int(dx), int(dz)
    if not candidates._source_cut_ok(a, ia, sx, sz) or not candidates._source_cut_ok(b, ib, -sx, -sz):
        return 'candidate_pairs source-cut/port filter'
    start = gmap_diagonal._point_on_cut(a, ca, sx, sz)
    finish = gmap_diagonal._point_on_cut(b, cb, -sx, -sz)
    if math.dist(start, finish) < 2.0:
        return 'candidate_pairs passage-distance filter'
    return 'candidate_pairs occupancy/eligibility filter'


def rect_key_map(document):
    return {c['cell_id']: rect_key(c) for c in document['cells']}


def collect_funnel(seed, cells, doc):
    budget, used = doc['diagonal_links']['budget'], doc['diagonal_links']['used']
    successful_attempt = doc['attempt']
    traces = [t for t in STATE['runs'].values() if t['seed'] == seed and t['variant'] == 0]
    traces.sort(key=lambda t: t['attempt'])
    successful = next((t for t in traces if t['attempt'] == successful_attempt), None)
    if successful is None:
        return {'budget': budget, 'used': used, 'missing': max(0, budget-used), 'error': 'no success trace'}
    released = [r for r in doc['diagonal_links'].get('reserved_diagonal_zones', []) if r['status'] == 'released']
    pairs = STATE['candidate_pairs'].get(id(doc), [])
    nudged = STATE['nudged'].get(id(doc), {})
    releases = collections.Counter(release_reason(doc, r, successful['snapshots'], nudged, pairs) for r in released)
    failed = [t for t in traces if t['attempt'] < successful_attempt and t['retry_reason']]
    retry_loss = 0
    retry_examples = []
    next_by_attempt = {t['attempt']: t for t in traces}
    for previous in failed:
        nxt = next_by_attempt.get(previous['attempt'] + 1)
        if nxt:
            old_n = int(previous.get('reservations_at_retry', 0))
            new_n = int(nxt.get('reservations_after_attempt', nxt.get('reservations_after_growth', 0)))
            if old_n > new_n:
                retry_loss += old_n - new_n
                retry_examples.append({'from': previous['attempt'], 'to': nxt['attempt'], 'old': old_n, 'new': new_n, 'error': previous['retry_reason']})
    missing = max(0, budget-used)
    reason_slots = collections.Counter()
    remaining = missing
    rel_n = min(remaining, sum(releases.values()))
    # Released reservations are explicit losses unless incidental pairs have already filled the budget.
    for reason, count in releases.items():
        take = min(remaining, count)
        if take:
            reason_slots[f'Released: {reason}'] += take
            remaining -= take
    retry_take = min(remaining, retry_loss)
    if retry_take:
        reason_slots['Retry: reserved attempt lost on retry'] += retry_take
        remaining -= retry_take
    if remaining:
        if successful['tries'] == 0:
            reason_slots['No try'] += remaining
        elif successful['nonzero_option_tries'] == 0:
            reason_slots['No options'] += remaining
        else:
            reason_slots['Other: available placements insufficient / later realization'] += remaining
    return {
        'budget': budget, 'used': used, 'missing': missing,
        'tries': successful['tries'], 'zero_option_tries': successful['zero_option_tries'],
        'nonzero_option_tries': successful['nonzero_option_tries'], 'option_total': successful['option_total'],
        'reservations_growth': successful['reservations_after_growth'],
        'reservations_final': len(doc['diagonal_links'].get('reserved_diagonal_zones', [])),
        'released_count': len(released), 'release_reasons': dict(releases),
        'retry_loss': retry_loss, 'retry_events': retry_examples,
        'reason_slots': dict(reason_slots), 'attempt': successful_attempt,
    }


def snap_child_placements(draft, parent, normal, size):
    """Enumerate integer placements that snap a child corner 1 m diagonally to an eligible cell."""
    width, depth = size
    ordinary = ORIGINALS['site_placements'](draft, parent, normal, size)
    ordinary_set = set(ordinary)
    local_corners = ((0, 0), (width, 0), (width, depth), (0, depth))
    protected = sites.reserved_cell_ids(draft.reserved_diagonal_zones)
    eligible = [
        cell for cell in draft.cells.values()
        if cell.cell_id != parent.cell_id and cell.role in ('ground', 'figure')
        and cell.module is None and cell.cell_id not in protected
    ]
    snapped = set()
    for target in eligible:
        tx0, tz0, tx1, tz1 = target.rect
        for tx, tz in ((tx0,tz0),(tx1,tz0),(tx1,tz1),(tx0,tz1)):
            for corner_x, corner_z in local_corners:
                for dx in (-1, 1):
                    for dz in (-1, 1):
                        x0, z0 = tx + dx - corner_x, tz + dz - corner_z
                        candidate = (x0, z0, x0 + width, z0 + depth)
                        if candidate in ordinary_set:
                            snapped.add(candidate)
    return sorted(snapped)


def half_grid_placements(draft, parent, normal, size):
    width, depth = size
    px0, pz0, px1, pz1 = parent.rect
    step = 0.5
    if normal[0]:
        x0 = px1 if normal[0] > 0 else px0 - width
        low, high = pz0 - depth + 3, pz1 - 3
        starts = [round(low + i*step, 6) for i in range(int(round((high-low)/step))+1)]
        rects = [(x0, z, x0+width, z+depth) for z in starts]
    else:
        z0 = pz1 if normal[1] > 0 else pz0 - depth
        low, high = px0 - width + 3, px1 - 3
        starts = [round(low + i*step, 6) for i in range(int(round((high-low)/step))+1)]
        rects = [(x, z0, x+width, z0+depth) for x in starts]
    existing = [p.pos for p in parent.ports if p.compatibility_type == grow.PORT_TYPE]
    wide = [p.pos for p in parent.ports if p.compatibility_type != grow.PORT_TYPE]
    found = []
    for rect in rects:
        contact = geometry.contact_port(parent.rect, rect, draft.centred)
        if contact and geometry.check_port_on_contact(parent.rect, contact[0], contact[1], rect, draft.margin) is None and draft.free_for(rect) and geometry.far_enough(contact[0], existing) and geometry.far_enough(contact[0], wide, geometry.WIDE_PORT_SEPARATION_M):
            found.append(rect)
    return found


def run_one(seed, cell_count, config, cap=1, measure_funnel=False):
    CONFIG.update(config)
    reset_state()
    draft_generation.MAX_SITE_LAYOUT_VARIANTS = cap
    build.MAX_SITE_LAYOUT_VARIANTS = cap
    if config.get('placement') == 'half_grid':
        growth.placements = half_grid_placements
    elif config.get('placement') == 'snap_child':
        growth.placements = snap_child_placements
    else:
        # A snap-child placement is a reparameterization of the exhaustive
        # integer placements: every exact +/-1 corner alignment is already
        # enumerated and filtered by site_for_rect.
        growth.placements = ORIGINALS['site_placements']
    started = time.perf_counter()
    document = build.build_map(seed, LIB, cells=cell_count, stage_max=2, version=VERSION)
    elapsed = time.perf_counter() - started
    funnel = collect_funnel(seed, cell_count, document) if measure_funnel else None
    return document, elapsed, funnel


def stats_for(items, similarities, times):
    distribution = collections.Counter((x['budget'], x['used']) for x in items)
    eligible = [x for x in items if x['budget'] >= 1]
    full = sum(x['used'] == x['budget'] for x in eligible)
    two = sum(x['used'] == 2 for x in items)
    return {
        'full': full, 'eligible': len(eligible), 'full_pct': 100*full/max(1,len(eligible)),
        'two': two, 'two_pct': 100*two/len(items),
        'distribution': {f'{b},{u}': n for (b,u),n in sorted(distribution.items())},
        'mean_similarity': statistics.mean(similarities),
        'mean_ms_per_map': 1000*statistics.mean(times),
        'mean_elapsed_s': sum(times),
    }


def run_mode(name, config, cap=1, baseline_docs=None, funnel=False):
    out = {}
    for cell_count in (12, 20):
        items, similarities, times, details = [], [], [], []
        for seed in range(1, 301):
            doc, elapsed, loss = run_one(seed, cell_count, config, cap, funnel)
            if doc['layout_variant'] != 0 and cap == 1:
                raise RuntimeError(f'{name}: expected variant 0, got {doc["layout_variant"]}')
            items.append({'budget': doc['diagonal_links']['budget'], 'used': doc['diagonal_links']['used']})
            similarities.append(similarity(baseline_docs[(cell_count,seed)], doc))
            times.append(elapsed)
            if loss:
                details.append({'seed': seed, **loss})
        out[str(cell_count)] = {'stats': stats_for(items, similarities, times), 'details': details}
        print(f'{name} cells={cell_count}: full={out[str(cell_count)]["stats"]["full"]}/{out[str(cell_count)]["stats"]["eligible"]} '
              f'({out[str(cell_count)]["stats"]["full_pct"]:.1f}%), two={out[str(cell_count)]["stats"]["two"]}/300 '
              f'({out[str(cell_count)]["stats"]["two_pct"]:.1f}%), dist={out[str(cell_count)]["stats"]["distribution"]}, '
              f'sim={out[str(cell_count)]["stats"]["mean_similarity"]:.3f}, ms={out[str(cell_count)]["stats"]["mean_ms_per_map"]:.1f}')
    return out


def main():
    install_instrumentation()
    baseline_docs = {}
    cache_path = Path('/tmp/issue196_v6_baseline_maps.json')
    if cache_path.is_file():
        print('loading cached gmap-0.6.0 layout comparison')
        cached = json.loads(cache_path.read_text())
        baseline_docs = {(int(cells), int(seed)): doc for cells, seed, doc in cached}
    else:
        print('precomputing gmap-0.6.0 layout comparison')
        cache_rows = []
        for cell_count in (12,20):
            for seed in range(1,301):
                doc = build.build_map(seed, LIB, cells=cell_count, stage_max=2, version=V6)
                baseline_docs[(cell_count,seed)] = doc
                cache_rows.append([cell_count, seed, doc])
        cache_path.write_text(json.dumps(cache_rows, separators=(',', ':')))
    results = {'version': VERSION, 'seeds': [1,300], 'counts': [12,20], 'baseline_v6': {}}
    if '--snap-only' in sys.argv:
        results['snap_child'] = run_mode('snap_child', {'probability':.35,'force_last':0,'armed':False,'placement':'snap_child'}, 1, baseline_docs, False)
        output = Path('/tmp/issue196_snap_results.json')
        output.write_text(json.dumps(results, indent=2, sort_keys=True))
        print(f'wrote {output}')
        return
    if '--snapcap-only' in sys.argv:
        combo = {'probability':.35,'force_last':4,'armed':False,'placement':'snap_child'}
        results['combo_last4_snap'] = run_mode('combo_last4_snap', combo, 1, baseline_docs, False)
        results['combo_last4_snap_cap4'] = run_mode('combo_last4_snap_cap4', combo, 4, baseline_docs, False)
        output = Path('/tmp/issue196_snapcap_results.json')
        output.write_text(json.dumps(results, indent=2, sort_keys=True))
        print(f'wrote {output}')
        return
    if '--followup-only' in sys.argv:
        results['snap_child'] = run_mode('snap_child', {'probability':.35,'force_last':0,'armed':False,'placement':'snap_child'}, 1, baseline_docs, False)
        combo_config = {'probability':.35,'force_last':4,'armed':True,'placement':'lattice'}
        results['combo_last4_armed'] = run_mode('combo_last4_armed', combo_config, 1, baseline_docs, False)
        results['best_variant_cap4'] = run_mode('best_variant_cap4', {'probability':.35,'force_last':4,'armed':False,'placement':'lattice'}, 4, baseline_docs, False)
        output = Path('/tmp/issue196_followup_results.json')
        output.write_text(json.dumps(results, indent=2, sort_keys=True))
        print(f'wrote {output}')
        return
    results['baseline_v6'] = run_mode('variant0_p035', {'probability':.35,'force_last':0,'armed':False,'placement':'lattice'}, 1, baseline_docs, True)
    Path('/tmp/issue196_funnel.json').write_text(json.dumps(results['baseline_v6'], indent=2, sort_keys=True))
    if '--funnel-only' in sys.argv:
        print('funnel-only run complete')
        return
    # Candidate levers requested by issue; each is a separate scratch-only monkeypatch.
    modes = [
        ('p060', {'probability':.60,'force_last':0,'armed':False,'placement':'lattice'}),
        ('p100', {'probability':1.0,'force_last':0,'armed':False,'placement':'lattice'}),
        ('last2', {'probability':.35,'force_last':2,'armed':False,'placement':'lattice'}),
        ('last4', {'probability':.35,'force_last':4,'armed':False,'placement':'lattice'}),
        ('armed_no_options', {'probability':.35,'force_last':0,'armed':True,'placement':'lattice'}),
        ('snap_child', {'probability':.35,'force_last':0,'armed':False,'placement':'snap_child'}),
    ]
    for name, config in modes:
        results[name] = run_mode(name, config, 1, baseline_docs, False)
    # Select the best placement/gate lever and its best distinct complement.
    key = lambda item: (results[item[0]]['12']['stats']['full_pct'], results[item[0]]['12']['stats']['mean_similarity'], -results[item[0]]['12']['stats']['mean_ms_per_map'])
    best_l1 = max((item for item in modes if item[0] in ('p060','p100','last2','last4')), key=key)
    best_complement = max((item for item in modes if item[0] in ('armed_no_options','snap_child')), key=key)
    chosen = [best_l1, best_complement]
    combo_name = 'combo_' + '_'.join(x[0] for x in chosen)
    combo_config = {
        'probability': max(x[1]['probability'] for x in chosen),
        'force_last': max(x[1]['force_last'] for x in chosen),
        'armed': any(x[1]['armed'] for x in chosen),
        'placement': 'lattice',
    }
    results[combo_name] = run_mode(combo_name, combo_config, 1, baseline_docs, False)
    best_name, best_config = best_l1
    results['best_variant_cap4'] = run_mode('best_variant_cap4', best_config, 4, baseline_docs, False)
    results['ranking_12'] = [item[0] for item in sorted(modes, key=key, reverse=True)]
    results['combined_levers'] = [item[0] for item in chosen]
    results['cap4_base_lever'] = best_name
    output = Path('/tmp/issue196_lever_results.json')
    output.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f'wrote {output}')

if __name__ == '__main__':
    main()
