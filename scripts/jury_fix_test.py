"""Quick jury fix verification."""
import asyncio, sys, time
sys.path.insert(0, r'E:\Documents\Vibe-Coding\Reasoner\src')
from reasoner.core.settings import settings
from reasoner.pipeline import ReasonerPipeline
from reasoner.application.services.preset_service import PresetService

async def main():
    if not settings.OPENROUTER_API_KEY:
        print('SKIP: No API key'); return
    service = PresetService()
    _, router = service.build_router('jury-budget')
    pipeline = ReasonerPipeline(router=router, top_k=2, parallel_perspectives=False,
                                 verbose=False, preset_name='jury-budget', source_type='general')
    t0 = time.monotonic()
    state = await pipeline.run('What is 2+2? Answer in one sentence.')
    t1 = time.monotonic()
    sol = getattr(state.final_solution, 'core_solution', '') or ''
    tokens = sum(t.get('total', 0) for t in state.phase_tokens.values())
    errors = state.errors
    status = 'PASS' if sol and not errors else 'FAIL' if errors else 'WARN'
    print(f'STATUS: {status} | TIME: {t1-t0:.1f}s | TOKENS: {tokens}')
    print(f'SOLUTION: {sol[:150]}')
    if errors:
        for e in errors[:3]: print(f'  ERROR: {e[:200]}')

asyncio.run(main())
