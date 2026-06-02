"""Run 4 method API tests sequentially."""
import asyncio, sys, time
sys.path.insert(0, r'E:\Documents\Vibe-Coding\Reasoner\src')

from reasoner.core.settings import settings
from reasoner.pipeline import ReasonerPipeline
from reasoner.application.services.preset_service import PresetService

async def run_one(method, preset_name):
    print(f'Testing: {method} ({preset_name})')
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
        print(f'  {status} ({t1-t0:.1f}s, {tokens} tokens): {sol[:120]}')
        if errors:
            print(f'  Errors: {errors}')
        
    except Exception as e:
        print(f'  FAIL: {type(e).__name__}: {str(e)[:200]}')

async def main():
    if not settings.OPENROUTER_API_KEY:
        print("SKIP: No API key")
        return
    
    tests = [
        ('jury', 'jury-budget'),
        ('socratic', 'socratic-budget'), 
        ('brainstorming', 'brainstorming-budget'),
        ('pre_mortem', 'pre-mortem-budget'),
    ]
    
    for method, preset in tests:
        await run_one(method, preset)
        print()

if __name__ == '__main__':
    asyncio.run(main())
