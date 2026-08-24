# Context: Application

## Directory: `src/reasoner/application`

## Description
Application-level orchestrators, workflow commands, event bus definitions, and core system services.

## Files
- **`__init__.py`**: Application Layer - CQRS Commands and Queries
- **`orchestrator.py`**: PipelineOrchestrator — single entry point for pipeline execution.
- **`pipeline.py`**: Author: Georgios-Chrysovalantis Chatzivantsidis

## Subfolders
- **`commands`**: Command handlers implementing the CQRS write model for modifying system state.
- **`event_bus`**: Publisher-subscriber models, local memory buses, or queue integrations for system-wide event broadcasting.
- **`flows`**: High-level visual or logic pipelines coordinating distinct agent interactions.
- **`handlers`**: Specific callback or event-driven controllers handling incoming system events.
- **`ports`**: Abstract interfaces/ports defining the boundary between core application logic and infrastructure adapters.
- **`queries`**: Query handlers implementing the CQRS read model for fetching system state and analytics.
- **`services`**: Application-specific services for rendering, routing decisions, and context formatting.
