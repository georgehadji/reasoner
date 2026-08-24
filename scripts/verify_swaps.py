"""Verify model swaps fix the budget preset JSON format issues."""
import asyncio
import sys
import time

sys.path.insert(0, r'E:\Documents\Vibe-Coding\Reasoner\src')

from reasoner.application.services.preset_service import PresetService
from reasoner.core.settings import settings
from reasoner.pipeline import ReasonerPipeline


async def run_one(method, preset_name):
    print(f'\n{"="*50}')
    print(f'{method} ({preset_name})')
    print(f'{"="*50}')
    try:
        service = PresetService()
        _, router = service.build_router(preset_name)

        pipeline = ReasonerPipeline(
            router=router, top_k=2, parallel_perspectives=False,
            verbose=False, preset_name=preset_name, source_type='general',
        )

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
            print(f'ERRORS ({len(errors)}):')
            for e in errors[:3]:
                print(f'  {e[:200]}')

    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {str(e)[:300]}')

async def main():
    if not settings.OPENROUTER_API_KEY:
        print('SKIP: No API key')
        return

    tests = [
        ('jury', 'jury-budget'),              # was: mistral-small scoring
        ('socratic', 'socratic-budget'),       # was: qwen3-max destructive + gpt-4o-mini classification
        ('brainstorming', 'brainstorming-budget'), # was: gpt-4o-mini classification
        ('dialectical', 'dialectical-budget'), # bonus: uses same models
    ]

    for method, preset in tests:
        await run_one(method, preset)

    print(f'\n{"="*50}')
    print('DONE')

asyncio.run(main())
