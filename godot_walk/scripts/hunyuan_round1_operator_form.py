"""Generate the local-only operator feedback page."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from hunyuan_round1_contract import ROUND_ID, VARIANTS, VIEW_IDS


def write_review_page(
    out_dir: Path,
    metrics: dict[str, Any],
    round_id: str = ROUND_ID,
    variants: tuple[str, ...] = VARIANTS,
    view_ids: tuple[str, ...] = VIEW_IDS,
) -> None:
    rows = [_view_row(view_id, metrics, variants) for view_id in view_ids]
    page = _review_html("\n".join(rows), round_id, variants, view_ids)
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def _view_row(view_id: str, metrics: dict[str, Any], variants: tuple[str, ...]) -> str:
    images = "".join(_variant_image(view_id, variant) for variant in variants)
    choices = "".join(_view_choice_option(variant) for variant in variants)
    noise = metrics["per_view_noise_ceiling_pct"][view_id]
    delta = _view_delta(metrics, view_id)
    diff_link = html.escape(delta["diff_image"] or "#")
    return (
        f"<section><h2>{html.escape(view_id)}</h2><div class='pair'>{images}</div>"
        f"<p>ODiff changed pixels: {delta['diff_pct']:.3f}%; "
        f"control repeat ceiling: {noise:.3f}%; "
        f"{html.escape(delta['interpretation'])}. "
        f"<a href='{diff_link}'>diff image</a></p>"
        f"<label>View choice <select required name='choice_{view_id}'>"
        f"<option value=''>Select</option>{choices}"
        "<option>tie</option><option>none</option></select></label>"
        f"<label>Reason <input required name='reason_{view_id}'></label></section>"
    )


def _variant_image(view_id: str, variant: str) -> str:
    path = f"captures/{variant}/repeat_1/spawn_headings/{view_id}.png"
    return (
        f"<figure><figcaption>{html.escape(variant)}</figcaption>"
        f'<a href="{path}"><img src="{path}" '
        f'alt="{html.escape(view_id)} {html.escape(variant)}"></a></figure>'
    )


def _view_choice_option(variant: str) -> str:
    value = html.escape(variant, quote=True)
    label = html.escape(variant)
    return f"<option value='{value}'>{label}</option>"


def _view_delta(metrics: dict[str, Any], view_id: str) -> dict[str, Any]:
    return next(
        item for item in metrics["variant_pixel_deltas"] if item["view_id"] == view_id
    )


def _review_html(
    view_rows: str,
    round_id: str,
    variants: tuple[str, ...],
    view_ids: tuple[str, ...],
) -> str:
    view_ids_json = json.dumps(view_ids)
    variants_json = json.dumps(variants)
    variant_fields = _variant_decision_fields(variants)
    round_number = round_id.rsplit("r", 1)[-1]
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hunyuan PSX Room | Round {html.escape(round_number)}</title>
<style>
:root{{font:15px/1.45 system-ui,sans-serif;color:#202524;background:#f3f3ed}}
body{{margin:0}}main{{max-width:1440px;margin:auto;padding:22px}}h1{{font-size:26px;margin:0 0 8px}}
h2{{font-size:18px;margin:0 0 10px}}p{{margin:8px 0}}section{{border-top:1px solid #aeb5ad;padding:16px 0}}
.pair{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
figure{{margin:0}}figcaption{{font-size:13px;font-weight:650;margin-bottom:4px}}
img{{width:100%;height:auto;aspect-ratio:16/9;object-fit:contain;background:#272a27}}
label{{display:inline-flex;gap:8px;align-items:center;margin:8px 14px 0 0}}
input,select,textarea,button{{font:inherit}}input,select,textarea{{border:1px solid #9da69f;background:white;padding:6px;max-width:100%}}
textarea{{width:100%;min-height:72px}}.review{{border-top:2px solid #4a6258;margin-top:24px;padding-top:16px}}
.decisions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
button{{background:#36594e;color:white;border:0;padding:9px 14px;cursor:pointer}}
@media(max-width:720px){{.pair,.decisions{{grid-template-columns:1fr}}main{{padding:14px}}}}
</style><main>
<h1>Hunyuan PSX Room | Round {html.escape(round_number)}</h1>
<p>Matched Hunyuan control and one authored column-box treatment over the same visual shell, route, and collision. Registration and scale remain unaccepted. No candidate is preselected.</p>
<p><a href="candidate_layout.svg">Open authored layout proposal</a> · <a href="candidate_contact_sheet.jpg">Open paired contact sheet</a> · <a href="REPORT.md">Open evidence report</a></p>
<p>Use the workspace review URL to submit directly. The download button remains available as a fallback.</p>
<img src="candidate_contact_sheet.jpg" alt="Matched Hunyuan PSX candidate contact sheet">
<form id="feedback" class="review">
<h2>Operator Decision</h2>
<p>Saved decisions load automatically when this page is served by the workspace review server. You can also import a JSON copy.</p>
<label>Load previous feedback JSON <input id="feedback_import" type="file" accept="application/json"></label>
<h2>Matched Views</h2>
{view_rows}
<h2>Variant Decisions</h2><div class="decisions">
{variant_fields}
</div><label>Confidence <select required name="confidence"><option value="">Select</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label>
<label>Overall walkthrough notes<textarea required name="overall_walkthrough_notes"></textarea></label>
<label>Remaining problems, one per line: area | severity 1-3 | description<textarea name="remaining_problems"></textarea></label>
<label>Next-round directives, one per line<textarea name="next_round_directives"></textarea></label>
<p><button type="submit">Submit feedback to workspace</button> <button id="download_feedback" type="button">Download JSON copy</button></p>
<p id="submit_status" role="status" aria-live="polite"></p></form>
</main><script>
const form=document.getElementById('feedback');
const statusLine=document.getElementById('submit_status');
document.getElementById('feedback_import').addEventListener('change',async event=>{{
const file=event.target.files[0];if(!file)return;
try{{
const imported=JSON.parse(await file.text());
applyFeedback(imported);
statusLine.textContent='Feedback JSON loaded. Review the choices, then submit to the workspace.';
}}catch(error){{alert(`Could not load feedback JSON: ${{error.message}}`);}}
}});
function applyFeedback(imported){{
if(imported.round_id!=={json.dumps(round_id)})throw new Error('This JSON belongs to a different round.');
for(const decision of imported.variant_decisions||[]){{
const id=decision.variant_id;
setValue('variant_'+id,decision.decision);setValue('variant_reason_'+id,decision.reason);
}}
setValue('confidence',imported.confidence);
setValue('overall_walkthrough_notes',imported.overall_walkthrough_notes);
setValue('remaining_problems',(imported.remaining_problems||[]).map(problem=>`${{problem.area}} | ${{problem.severity}} | ${{problem.description}}`).join('\\n'));
setValue('next_round_directives',(imported.next_round_directives||[]).join('\\n'));
for(const view of imported.view_choices||[]){{
if(view.choice!==null&&view.choice!==undefined)setValue('choice_'+view.view_id,view.choice);
if(view.reason!==null&&view.reason!==undefined)setValue('reason_'+view.view_id,view.reason);
}}
}}
function setValue(name,value){{if(value===null||value===undefined)return;const field=form.elements.namedItem(name);if(field)field.value=String(value);}}
async function loadSavedFeedback(){{
try{{
const response=await fetch('operator_feedback.json',{{cache:'no-store'}});
if(!response.ok)return;const imported=await response.json();
if(imported.status==='confirmed'){{applyFeedback(imported);statusLine.textContent='Saved operator feedback loaded.';}}
}}catch(error){{statusLine.textContent='Saved feedback could not be loaded: '+error.message;}}
}}
loadSavedFeedback();
function collectFeedback(){{
const data=new FormData(form);const choices={view_ids_json}.map(view=>({{view_id:view,choice:data.get('choice_'+view),reason:data.get('reason_'+view)}}));
const decisions={variants_json}.map(id=>({{variant_id:id,decision:data.get('variant_'+id),reason:data.get('variant_reason_'+id)}}));
const problems=String(data.get('remaining_problems')||'').split(/\\r?\\n/).filter(Boolean).map(line=>{{const [area,severity,...description]=line.split('|').map(part=>part.trim());return {{area,severity:Number(severity),description:description.join(' | ')}};}});
if(problems.some(problem=>!problem.area||!problem.description||![1,2,3].includes(problem.severity))){{alert('Each problem must be: area | severity 1-3 | description');return;}}
return {{schema_version:1,round_id:{json.dumps(round_id)},status:'confirmed',reviewer_timestamp:new Date().toISOString(),view_choices:choices,variant_decisions:decisions,overall_walkthrough_notes:data.get('overall_walkthrough_notes'),remaining_problems:problems,next_round_directives:String(data.get('next_round_directives')||'').split(/\\r?\\n/).map(v=>v.trim()).filter(Boolean),confidence:Number(data.get('confidence'))}};
}}
function downloadFeedback(feedback){{
const url=URL.createObjectURL(new Blob([JSON.stringify(feedback,null,2)+'\\n'],{{type:'application/json'}}));const link=document.createElement('a');link.href=url;link.download='operator_feedback.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}}
form.addEventListener('submit',async event=>{{event.preventDefault();if(!form.reportValidity())return;
const feedback=collectFeedback();if(!feedback)return;
statusLine.textContent='Submitting feedback to the workspace...';
try{{
const response=await fetch('/submit',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(feedback)}});
const result=await response.json();if(!response.ok)throw new Error(result.error||'Workspace submission failed.');
statusLine.textContent='Feedback saved to '+result.path+'.';
}}catch(error){{statusLine.textContent='Workspace submission failed. Use Download JSON copy as a fallback. '+error.message;}}
}});
document.getElementById('download_feedback').addEventListener('click',()=>{{
if(!form.reportValidity())return;const feedback=collectFeedback();if(feedback)downloadFeedback(feedback);
}});
</script></html>"""


def _variant_decision_fields(variants: tuple[str, ...]) -> str:
    fields = []
    for variant in variants:
        identifier = html.escape(variant, quote=True)
        fields.append(
            f"<fieldset><legend>{html.escape(variant)}</legend>"
            f"<label>Decision <select required name='variant_{identifier}'>"
            "<option value=''>Select</option><option>keep</option>"
            "<option>reject</option><option>iterate</option></select></label>"
            f"<label>Reason <input required name='variant_reason_{identifier}'></label>"
            "</fieldset>"
        )
    return "".join(fields)
