import ast
import json
import os

# Pre-defined, professional folder descriptions representing senior developer architecture knowledge
FOLDER_DESCRIPTIONS = {
    "": "The root of the Reasoner project, containing configurations for environment, docker containers, python packages, build files, and architectural blueprints.",
    "audit": "Contains various system audits, executive summaries, findings registers, implementation plans, and architectural reviews documenting the health and score of the codebase.",
    "benchmarks": "Includes comparative benchmarks for evaluating reasoning methodologies, latencies, calibrations, and overhead of various providers and prompt strategies.",
    "docs": "Project documentation, architecture decision records (ADRs), mindmaps, and specialized reports on system features (e.g. agent memory, humanizer pipelines, etc.).",
    "docs/CODEMAPS": "Visual and textual code maps of specific subsystems for rapid navigation and dependency tracing.",
    "docs/adr": "Architecture Decision Records detailing key technical design decisions made throughout the life of the project.",
    "docs/audits": "Specific diagnostic audit logs and assessments compiled for security, performance, or capability analysis.",
    "docs/decisions": "Detailed studies and comparative assessments of technologies, protocols, or routing options under consideration.",
    "docs/monitoring": "Configurations, dashboards, and instructions for observability, metrics collection, and alerting setups.",
    "docs/plans": "Phased engineering and remediation roadmaps describing exact development steps for features or fixes.",
    "docs/research": "Scientific and empirical studies on model adaptabilities, vertical alignments, or specialized methodology behaviors.",
    "docs/security": "Analyses of security posture, encryption requirements, SAIF compliance checklists, and risk remediation guides.",
    "graphify": "The core engine components or configurations for the graphify knowledge graph generator tool.",
    "graphify-out": "The compiled knowledge graph artifacts, databases, reports, and a browsable wiki index representing the current codebase structure.",
    "history": "Archive files and historical logs tracking previous reasoning sessions, outputs, or state-transition records.",
    "migrations": "Alembic relational database schema migration environment and historical version scripts.",
    "migrations/alembic": "Alembic configuration and base environment scripts used for managing schema updates.",
    "migrations/alembic/versions": "Individual Alembic database migration scripts representing sequential database revisions.",
    "nginx": "Nginx reverse-proxy and gateway configuration templates for local development and production routing.",
    "plans": "Active workspace plans, design blueprints, and execution files for multi-step feature additions and system changes.",
    "scripts": "Utility automation scripts for running servers, executing specialized tests, verifying environments, or packaging builds.",
    "sdk": "The client software development kits facilitating simple programmatic interface with the Reasoner orchestrator.",
    "sdk/contract": "Language-agnostic protocol schemas, OpenAPI definitions, or API contracts defining request/response structures.",
    "sdk/typescript": "The TypeScript/Node.js client SDK for integrating Reasoner with external web services or JS-based applications.",
    "sdk/typescript/src": "Source code for the TypeScript client SDK, containing core interfaces and fetch wrappers.",
    "sdk/typescript/test": "Unit and integration test suites for verifying the TypeScript client SDK's request and response handling.",
    "skills": "Locally active agent skills containing tailored prompt directions and instructions for specialized agent tasks.",
    "src": "The backend application root directory housing the FastAPI server and Python pipeline modules.",
    "src/reasoner": "The main Python package containing the Reasoner framework architecture.",
    "src/reasoner/api": "FastAPI endpoints, middleware, websocket routers, and API server entry points.",
    "src/reasoner/api/execution": "Execution layer for handling active pipeline jobs, task queues, and asynchronous processing.",
    "src/reasoner/api/mcp": "Model Context Protocol (MCP) server integration allowing external agents to query the Reasoner codebase or invoke backend functions.",
    "src/reasoner/api/routes": "The distinct REST and SSE endpoint routers (e.g. running, configuration, billing, neuro states).",
    "src/reasoner/application": "Application-level orchestrators, workflow commands, event bus definitions, and core system services.",
    "src/reasoner/application/commands": "Command handlers implementing the CQRS write model for modifying system state.",
    "src/reasoner/application/event_bus": "Publisher-subscriber models, local memory buses, or queue integrations for system-wide event broadcasting.",
    "src/reasoner/application/flows": "High-level visual or logic pipelines coordinating distinct agent interactions.",
    "src/reasoner/application/handlers": "Specific callback or event-driven controllers handling incoming system events.",
    "src/reasoner/application/ports": "Abstract interfaces/ports defining the boundary between core application logic and infrastructure adapters.",
    "src/reasoner/application/queries": "Query handlers implementing the CQRS read model for fetching system state and analytics.",
    "src/reasoner/application/services": "Application-specific services for rendering, routing decisions, and context formatting.",
    "src/reasoner/application/services/renderers": "CLI and web-friendly data renderers formatting pipeline outputs into rich, readable formats.",
    "src/reasoner/core": "The foundational core of the reasoning framework, containing aggregates, state-machine states, and observability interfaces.",
    "src/reasoner/core/aggregates": "Domain aggregates grouping entities and enforcing transaction boundaries.",
    "src/reasoner/core/events": "System event definitions capturing structural changes in reasoning jobs or model outputs.",
    "src/reasoner/core/observability": "Framework interfaces for performance tracing, spans, and step logging.",
    "src/reasoner/core/ports": "Core-level abstract interfaces defining adapters for low-level platform features.",
    "src/reasoner/documents": "Document management and extraction modules for structuring parsed source data.",
    "src/reasoner/domain": "Domain logic models, entities, value objects, and business validation rules.",
    "src/reasoner/domain/watermark": "Watermarking entities and core validation rules for labeling generated content.",
    "src/reasoner/healing": "Self-healing algorithms and parsing repair protocols for correcting malformed model outputs on-the-fly.",
    "src/reasoner/hypergate": "Advanced multi-agent routing gateways and sub-orchestrators for managing parallel reasoning routes.",
    "src/reasoner/hypergate/sub_agents": "Hypergate sub-agent controllers coordinating specialized reasoning tasks.",
    "src/reasoner/infrastructure": "Platform and infrastructure adapters implementing the abstract application ports (databases, search, cache).",
    "src/reasoner/infrastructure/auth": "Adapters and providers managing API key verification, user sessions, and JWT tokens.",
    "src/reasoner/infrastructure/benchmarks": "Implementations for executing benchmarking suites and aggregating performance metadata.",
    "src/reasoner/infrastructure/benchmarks/suites": "Specific benchmarking implementations (e.g. latency, diversity, calibration).",
    "src/reasoner/infrastructure/billing": "Payment gateway adapters (PayPal, Stripe) and billing credit ledger managers.",
    "src/reasoner/infrastructure/documents": "Implementations for reading and extracting contents from specialized document types (PDFs, Docx, HTML).",
    "src/reasoner/infrastructure/email": "Email delivery adapters (SMTP, SendGrid) for transaction and notification alerts.",
    "src/reasoner/infrastructure/execution": "Execution environments, containerized execution workers, and sandboxing infrastructure.",
    "src/reasoner/infrastructure/execution/runners": "Specific execution runner strategies (local, container, remote).",
    "src/reasoner/infrastructure/execution/sandbox_worker": "Sandbox environment workers for isolated, secure execution of generated code.",
    "src/reasoner/infrastructure/execution/sandbox_worker/sandbox_image": "Docker configurations and build specifications for the containerized execution sandbox.",
    "src/reasoner/infrastructure/learning": "Database and algorithm adapters supporting neuro-symbolic feedback loops and recall memory systems.",
    "src/reasoner/infrastructure/llm": "Language model provider clients, extraction parsers, and constraint checkers.",
    "src/reasoner/infrastructure/llm/constraints": "Validators enforcing format rules, token budgets, or prompt structural boundaries on model outputs.",
    "src/reasoner/infrastructure/llm/extraction": "JSON repair and structured content parser implementations for cleaning non-standard LLM completions.",
    "src/reasoner/infrastructure/llm/providers": "Concrete API wrapper clients for individual providers (Anthropic, OpenAI, Mistral, Perplexity, etc.).",
    "src/reasoner/infrastructure/observability": "Telemetry exporters, structured loggers, and distributed tracing adapters.",
    "src/reasoner/infrastructure/persistence": "Relational database adapters, SQLAlchemy models, and session management configurations.",
    "src/reasoner/infrastructure/prism": "Adapter layer for unified formatting and syntax highlighting of parsed outputs.",
    "src/reasoner/infrastructure/redis": "Redis cache adapters, session stores, and rate-limiting helper implementations.",
    "src/reasoner/infrastructure/redis/scripts": "Optimized Lua scripts executed atomically inside Redis for concurrency and token buckets.",
    "src/reasoner/infrastructure/search": "Search API clients (Perplexity, Tavily, Google, Bing) executing context-vetting queries.",
    "src/reasoner/infrastructure/telemetry": "Telemetry collectors and logging pipelines sending metrics to external monitoring backends.",
    "src/reasoner/infrastructure/translation": "Translation adapter wrappers utilized during the classification or synthesis phases to adapt response languages.",
    "src/reasoner/infrastructure/valkey": "Valkey in-memory key-value database adapters and cache managers.",
    "src/reasoner/infrastructure/valkey/scripts": "Optimized Lua scripts executed inside Valkey database instances.",
    "src/reasoner/infrastructure/watermark": "Concrete utilities for watermarking generated texts, images, or documents.",
    "src/reasoner/infrastructure/watermark/image": "Watermarking implementations for applying invisible pixel tags or visual overlays on images.",
    "src/reasoner/infrastructure/watermark/pixel": "Low-level pixel-level manipulation routines for cryptographic image watermarking.",
    "src/reasoner/infrastructure/websocket": "Websocket server managers handling real-time, bi-directional event broadcasts with clients.",
    "src/reasoner/infrastructure/widgets": "Adapters and renderers for injecting rich UI widgets and dashboards in terminal/web flows.",
    "src/reasoner/neuro": "Neuro-symbolic recall, cognitive map synthesis, and memory recall systems of the agent.",
    "src/reasoner/phases": "Orchestrated prompts, inputs, and validation logic for each of the 8 reasoning pipeline phases.",
    "src/reasoner/quality": "Validators, checks, and quality-assurance systems evaluating model responses.",
    "src/reasoner/security": "Security utilities, payload sanitizers, and encryption/decryption routines for protecting cache and databases.",
    "src/reasoner/shared": "Shared types, exceptions, and constants shared across backend packages.",
    "src/reasoner/subagents": "Task-focused LLM subagents used in specific stages of the reasoning process.",
    "src/reasoner/subagents/critique": "Deploys LLMs to critique and score competing generated response options.",
    "src/reasoner/subagents/decomposition": "Deploys LLMs to deconstruct the problem and formulate research assumptions.",
    "src/reasoner/subagents/enhancement": "Deploys LLMs to enrich queries or refine search results before generations.",
    "src/reasoner/subagents/search": "Deploys LLMs to dynamically formulate search queries during the context vetting phase.",
    "src/reasoner/subagents/synthesis": "Deploys LLMs to synthesize competing viewpoints and produce a single master answer.",
    "src/reasoner/utils": "Helper modules for date-time handling, UUIDs, model parsing, and environment variables.",
    "src/reasoner/vs_vertical_configs": "Vertical configuration specifications for specialized model alignments and presets.",
    "tests": "Test configurations and base setup for the Pytest testing framework.",
    "tests/_data": "Mock payloads, sample outputs, and static dataset fixtures used by tests.",
    "tests/architecture": "Automated tests asserting code structural invariants (e.g. no core importing infrastructure, dependency lines).",
    "tests/integration": "End-to-end integration test suites verifying multi-method pipelines and API routes.",
    "tests/unit": "Surgical unit tests verifying isolated functions, parsing strategies, and utilities.",
    "tests/utils": "Test assertions and helper functions used to mock third-party dependencies during test runs.",
    "ui-next": "Root folder for the Next.js frontend, styled with Tailwind CSS.",
    "ui-next/e2e": "Playwright end-to-end browser tests asserting visual correctness of the web app.",
    "ui-next/public": "Static frontend public assets like icons, brand logos, and metadata graphics.",
    "ui-next/public/showcase": "Demonstration screenshots and interactive presentation assets for the landing page.",
    "ui-next/src": "Source directory for the Next.js React codebase.",
    "ui-next/src/app": "The visual page views, routes, layouts, and API routes of the Next.js 16 app router.",
    "ui-next/src/app/about": "Static pages and component layouts describing the Reasoner platform mission.",
    "ui-next/src/app/api": "Backend-for-frontend (BFF) HTTP endpoints exposing server functionality to client web states.",
    "ui-next/src/app/chat": "The primary chat application screen supporting live SSE streams of Reasoning steps.",
    "ui-next/src/app/dashboard": "User analytical dashboards tracking credits, token limits, history, and active pipelines.",
    "ui-next/src/app/docs": "Browsers-friendly system documentation renderer and page views.",
    "ui-next/src/app/pricing": "Product tier pricing, feature comparisons, and gateway subscriptions page.",
    "ui-next/src/components": "React visual and interactive UI components.",
    "ui-next/src/components/chat": "Interactive chat message components, streaming tokens, and reasoning process indicators.",
    "ui-next/src/components/layout": "Global web shell layouts including navigational headers, user sidebars, and footer components.",
    "ui-next/src/components/ui": "Atomic, unstyled design components (buttons, dialogs, inputs, cards) constructed with Radix/Shadcn UI.",
    "ui-next/src/hooks": "Custom React hooks used to query backend web-sockets and fetch APIs.",
    "ui-next/src/lib": "Surgical utility libraries for color schemes, API clients, and visual calculations.",
    "ui-next/src/stores": "Zustand global clientside memory stores orchestrating active chat sessions."
}

def get_smart_folder_description(rel_path):
    # Perfect matching
    if rel_path in FOLDER_DESCRIPTIONS:
        return FOLDER_DESCRIPTIONS[rel_path]

    # Prefix matching (descending order of length)
    for prefix in sorted(FOLDER_DESCRIPTIONS.keys(), key=len, reverse=True):
        if prefix and rel_path.startswith(prefix + '/'):
            # Generate a custom description based on the prefix and subpath
            sub_parts = rel_path[len(prefix)+1:].split('/')
            sub_name = " ".join([p.capitalize() for p in sub_parts])
            return f"Exposes routing, templates, or integrations for {sub_name} within the '{prefix}' ecosystem."

    # Generic fallback
    folder_name = rel_path.split('/')[-1] if rel_path else 'Root'
    name_spaced = " ".join([part.capitalize() for part in folder_name.split('_')])
    return f"Contains components and resources related to {name_spaced}."

def extract_file_info(filepath):
    # Extract the first docstring or comment from a file for high signal summaries
    if not os.path.exists(filepath):
        return ""
    try:
        ext = os.path.splitext(filepath)[1]
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            content = f.read(4096)  # Read first 4KB

        # Python docstring or comments
        if ext == '.py':
            try:
                tree = ast.parse(content)
                doc = ast.get_docstring(tree)
                if doc:
                    first_line = doc.split('\n')[0].strip()
                    if first_line:
                        return first_line
            except Exception:
                pass
            # Fallback to comment blocks
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('#'):
                    if 'usr/bin' in line or 'python' in line or '-*-' in line:
                        continue
                    clean_comment = line.lstrip('# ').strip()
                    if clean_comment:
                        return clean_comment

        # JS/TS files
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            lines = [line.strip() for line in content.split('\n')]
            comment_lines = []
            in_multiline = False
            for line in lines:
                if not line:
                    continue
                if line.startswith('//'):
                    clean_comment = line.lstrip('/ ').strip()
                    if clean_comment:
                        return clean_comment
                if line.startswith('/*'):
                    if line.endswith('*/'):
                        return line[2:-2].strip('* ')
                    in_multiline = True
                    continue
                if in_multiline:
                    if line.endswith('*/'):
                        comment_lines.append(line[:-2].strip('* '))
                        break
                    comment_lines.append(line.strip('* '))
                    if len(comment_lines) > 2:
                        break
            if comment_lines:
                first_line = ' '.join(comment_lines).strip()
                if first_line:
                    return first_line

        # Markdown title
        elif ext == '.md':
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('#'):
                    return line.lstrip('# ').strip()
                if line:
                    return line

    except Exception:
        pass

    # Simple, high-quality fallbacks based on name
    filename = os.path.basename(filepath)
    if filename == 'layout.tsx':
        return "React layout component structuring the page layout and global wrappers."
    elif filename == 'page.tsx':
        return "React page view component rendering the primary route content."
    elif filename == 'route.ts':
        return "Next.js server-side route handler implementing API endpoint logic."
    elif filename == 'loading.tsx':
        return "React loading state indicator rendered during routing transitions."
    elif filename == 'error.tsx':
        return "React error boundary component rendering failure states."
    elif filename == '__init__.py':
        return "Python package initialization module."
    elif filename == 'models.py':
        return "Data validation schemas, request-response structures, and database models."
    elif filename == 'api.py':
        return "Backend API controllers and route endpoint decorators."

    return "Code or resource asset facilitating system functionality."

def generate_skills():
    # Load workspace map
    with open('workspace_map.json', encoding='utf-8') as f:
        workspace_map = json.load(f)

    generated_contexts_map = {}

    for rel_path, data in workspace_map.items():
        # Exclude generated CONTEXT.md from the file lists so we don't document CONTEXT.md in itself
        files = [f for f in data['files'] if f != 'CONTEXT.md' and f != 'SKILL.md']
        subdirs = data['subdirs']

        # Determine actual file path
        folder_abs_path = os.path.abspath(rel_path) if rel_path else os.path.abspath('.')
        context_file_path = os.path.join(folder_abs_path, 'CONTEXT.md')

        folder_display_name = rel_path if rel_path else "Project Root"
        folder_title = rel_path.split('/')[-1] if rel_path else "Reasoner Root"
        folder_title_clean = " ".join([part.capitalize() for part in folder_title.split('_')])

        # Generate the description
        folder_desc = get_smart_folder_description(rel_path)

        markdown_content = []
        markdown_content.append(f"# Context: {folder_title_clean}")
        markdown_content.append("")
        markdown_content.append(f"## Directory: `{folder_display_name}`")
        markdown_content.append("")
        markdown_content.append("## Description")
        markdown_content.append(folder_desc)
        markdown_content.append("")

        # Document Files
        markdown_content.append("## Files")
        if files:
            for f in files:
                file_rel = os.path.join(rel_path, f) if rel_path else f
                desc = extract_file_info(file_rel)
                markdown_content.append(f"- **`{f}`**: {desc}")
        else:
            markdown_content.append("*No files in this directory.*")
        markdown_content.append("")

        # Document Subfolders
        markdown_content.append("## Subfolders")
        if subdirs:
            for sd in subdirs:
                sd_rel = os.path.join(rel_path, sd).replace('\\', '/') if rel_path else sd
                sd_desc = get_smart_folder_description(sd_rel)
                markdown_content.append(f"- **`{sd}`**: {sd_desc}")
        else:
            markdown_content.append("*No subfolders in this directory.*")
        markdown_content.append("")

        # Write individual CONTEXT.md (or root CONTEXT.md base)
        with open(context_file_path, 'w', encoding='utf-8') as sf:
            sf.write("\n".join(markdown_content))

        generated_contexts_map[rel_path] = context_file_path

    print(f"Generated {len(generated_contexts_map)} CONTEXT.md files successfully.")

    # Construct the beautiful, nested tree of all the CONTEXT.md files
    map_lines = ["## Workspace CONTEXT.md Map", ""]
    map_lines.append("To aid AI agents and developers in codebase navigation, each directory in this project contains a `CONTEXT.md` file summarizing its files, functioning, and subfolders. Below is the complete hierarchical map of these documents:")
    map_lines.append("")

    # Sort paths so they are hierarchical
    for rel_path in sorted(generated_contexts_map.keys()):
        # Determine depth based on nesting level
        depth = rel_path.count('/') if rel_path else 0
        indent = "  " * depth
        folder_name = rel_path.split('/')[-1] if rel_path else "Project Root"
        clean_name = " ".join([part.capitalize() for part in folder_name.split('_')])

        # Construct link to the CONTEXT.md
        context_link_path = os.path.join(rel_path, 'CONTEXT.md').replace('\\', '/') if rel_path else 'CONTEXT.md'
        map_lines.append(f"{indent}- [{clean_name}]({context_link_path})")

    map_lines.append("")

    # Write the complete map directly inside the root CONTEXT.md
    root_context_path = generated_contexts_map[""]
    with open(root_context_path, encoding='utf-8') as rcf:
        root_context_base = rcf.read().rstrip()

    with open(root_context_path, 'w', encoding='utf-8') as rcf:
        rcf.write(root_context_base + "\n\n---\n\n" + "\n".join(map_lines))
    print("Master map successfully appended to the root CONTEXT.md file.")

    # Pointer text to insert into CLAUDE.md and GEMINI.md
    pointer_text = (
        "## Workspace CONTEXT.md Map\n\n"
        "To easily navigate the codebase, explore directory structures, and understand file roles, please "
        "refer to the root [CONTEXT.md](CONTEXT.md) file. This file contains a complete hierarchical map and "
        "points to individual `CONTEXT.md` files detailing the contents and functioning of every single folder "
        "in the project."
    )

    # Read and update GEMINI.md content with the pointer
    with open('GEMINI.md', encoding='utf-8') as f:
        gemini_content = f.read()

    target_header = "## Workspace CONTEXT.md Map"
    if "## Workspace SKILL.md Map" in gemini_content:
        parts = gemini_content.split("## Workspace SKILL.md Map")
        new_gemini_content = parts[0] + pointer_text
    elif target_header in gemini_content:
        parts = gemini_content.split(target_header)
        new_gemini_content = parts[0] + pointer_text
    else:
        new_gemini_content = gemini_content.rstrip() + "\n\n" + pointer_text

    with open('GEMINI.md', 'w', encoding='utf-8') as f:
        f.write(new_gemini_content)
    print("Clean direction pointer integrated into GEMINI.md")

    # Read and update CLAUDE.md content with the pointer
    if os.path.exists('CLAUDE.md'):
        with open('CLAUDE.md', encoding='utf-8') as f:
            claude_content = f.read()

        if "## Workspace SKILL.md Map" in claude_content:
            parts = claude_content.split("## Workspace SKILL.md Map")
            new_claude_content = parts[0] + pointer_text
        elif target_header in claude_content:
            parts = claude_content.split(target_header)
            new_claude_content = parts[0] + pointer_text
        else:
            new_claude_content = claude_content.rstrip() + "\n\n" + pointer_text

        with open('CLAUDE.md', 'w', encoding='utf-8') as f:
            f.write(new_claude_content)
        print("Clean direction pointer integrated into CLAUDE.md")

if __name__ == '__main__':
    generate_skills()
