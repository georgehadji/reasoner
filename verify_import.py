import os
import sys

sys.path.insert(0, os.path.abspath("src"))

try:
    import inspect

    import reasoner.pipeline as pipeline
    print(f"File: {pipeline.__file__}")
    print(f"Absolute Path: {os.path.abspath(pipeline.__file__)}")

    source = inspect.getsource(pipeline.ReasonerPipeline.run)
    print("Source of ReasonerPipeline.run (first 200 chars):")
    print(source[:200])
except Exception as e:
    print(f"Error: {e}")
