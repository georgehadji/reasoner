# Context: Ports

## Directory: `src/reasoner/application/ports`

## Description
Abstract interfaces/ports defining the boundary between core application logic and infrastructure adapters.

## Files
- **`__init__.py`**: Python package initialization module.
- **`auth_port.py`**: Auth Port — Abstract interface for authentication providers.
- **`billing_deadletter_port.py`**: Billing Dead-Letter Port — Durable storage for failed webhook events.
- **`billing_port.py`**: Billing Port — Abstract interface for payment providers.
- **`email_port.py`**: Email Port — abstraction for sending transactional emails.
- **`pipeline_ownership_port.py`**: Pipeline Ownership Port — who is allowed to read/stop/resume a pipeline run.
- **`quota_repository.py`**: Quota Repository Port — Abstract interface for quota persistence.
- **`service_protocols.py`**: Protocol classes for Reasoner service dependencies.

## Subfolders
*No subfolders in this directory.*
