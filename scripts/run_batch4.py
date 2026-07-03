#!/usr/bin/env python3
import sys, asyncio, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
for n in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(n).setLevel(logging.ERROR)

from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.domain.pipeline_state import PipelineState
from reasoner.pipeline import ReasonerPipeline

P = [
    ("pot-budget","PoT",(
        "Write a Python function that takes a list of daily temperatures (Fahrenheit) "
        "for a city over 10 years (3652 values) and: (1) identifies all 7-day periods "
        "where the average temperature was more than 2 standard deviations above the "
        "10-year mean, (2) computes the rolling 30-day average, and (3) returns the "
        "longest consecutive streak of days above 90F. Include type hints and docstring. "
        "Execute the code on a realistic Phoenix AZ 10-year pattern with 0.5F/decade "
        "warming trend and report results."
    )),
    ("self-discover-budget","Self-Discover",(
        "A global shipping company needs to redesign its supply chain to be resilient "
        "against three simultaneous disruption types: geopolitical (port closures), "
        "climate (hurricane seasons intensifying), and economic (fuel price volatility "
        "of +/-40% year-over-year). The company operates 47 ports across 31 countries "
        "with a fleet of 280 vessels. Before solving, determine the optimal reasoning "
        "strategy. Should decomposition be spatial, temporal, or structural? Select and "
        "adapt reasoning modules from: decomposition, multi-perspective analysis, "
        "probabilistic modeling, adversarial stress-testing, and systems thinking. "
        "Implement your chosen strategy to produce a resilience framework."
    )),
    ("iterative-critique-budget","Iterative-Critique",(
        "Draft a policy proposal for a city implementing a Universal Basic Mobility "
        "program: every resident receives a monthly $150 transit credit usable on buses, "
        "light rail, bike-share, and ride-hail services. Address: funding mechanism, "
        "eligibility verification, fraud prevention, impact on existing transit revenue, "
        "equity across neighborhoods, and a 3-year phase-in plan. After your initial "
        "draft, critically evaluate it for logical flaws, missing stakeholders, "
        "implementation gaps, and unsupported assumptions. Revise to address each "
        "weakness. Repeat critique-revise one more time for a refined final proposal."
    )),
]

class A:
    routing = ""; top_k = 2; sequential = False; quiet = True
    force_pipeline = False; source_type = "general"; domain = None; enhance_prompt = False

async def run_one(method, prompt, name):
    class PA(A): preset = method; problem = prompt
    ps = PresetService(); pls = PipelineService()
    orch = PipelineOrchestrator(ps, pls)
    state = PipelineState(problem=prompt, preset_name=method)
    t0 = time.monotonic()
    pf = await asyncio.wait_for(orch.preflight(PA(), state), timeout=60)
    if pf.action != "pipeline":
        return {"status":"skipped","error":f"routed to {pf.action}","duration":time.monotonic()-t0}
    pipeline = ReasonerPipeline(router=pf.router, initial_state=state, top_k=2,
        parallel_perspectives=True, preset_name=pf.effective_preset_name, source_type="general")
    try:
        result = await asyncio.wait_for(pipeline.run(prompt), timeout=300)
        dt = time.monotonic()-t0
        if result.errors: return {"status":"errors","error":"; ".join(result.errors[:3]),"duration":dt}
        if result.final_solution: return {"status":"success","output":result.final_solution.core_solution,"duration":dt}
        return {"status":"no_output","error":"no final_solution","duration":dt}
    except asyncio.TimeoutError:
        return {"status":"timeout","error":"300s timeout","duration":time.monotonic()-t0}
    except Exception as e:
        return {"status":"exception","error":f"{type(e).__name__}: {str(e)[:150]}","duration":time.monotonic()-t0}

async def main():
    for method, name, prompt in P:
        print(f"\n{'='*50}\n  {name} — {method}\n{'='*50}")
        r = await run_one(method, prompt, name)
        i = {"success":"✅","errors":"⚠️","timeout":"⏱️","exception":"❌","skipped":"⏭️"}.get(r["status"],"❓")
        print(f"  {i} {r['status']} ({r['duration']:.0f}s)")
        if r.get("error"): print(f"  Error: {r['error'][:150]}")
        if r.get("output"): print(f"  Output: {r['output'][:250]}...")

asyncio.run(main())
