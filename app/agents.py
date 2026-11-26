AGENTS = [
    {"id": "ceo", "name": "AI CEO / Executive Office", "department": "Executive Office", "role": "AI Chief Executive Officer", "mission": "Translate founder goals into clear priorities, project plans, and accountable departmental assignments."},
    {"id": "product", "name": "AI Product Manager", "department": "Product Strategy", "role": "AI Product Manager", "mission": "Define users, problems, requirements, scope, user stories, and acceptance criteria."},
    {"id": "design", "name": "AI UX/UI Designer", "department": "Design", "role": "AI UX/UI Designer", "mission": "Prepare user journeys, page structure, design systems, responsive behavior, and accessibility guidance."},
    {"id": "frontend", "name": "AI Frontend Engineer", "department": "Development", "role": "AI Frontend Engineer", "mission": "Generate frontend source files: components, routing, state, forms, validation and API integration."},
    {"id": "backend", "name": "AI Backend Engineer", "department": "Development", "role": "AI Backend Engineer", "mission": "Generate APIs, business logic, authentication, authorization and error handling source files."},
    {"id": "database", "name": "AI Database Engineer", "department": "Development", "role": "AI Database Engineer", "mission": "Design schemas, migrations, constraints, indexes and transactional data access."},
    {"id": "qa", "name": "AI QA Engineer", "department": "Quality Assurance", "role": "AI QA Engineer", "mission": "Execute and interpret automated tests, report defects precisely and block releases that fail."},
    {"id": "security", "name": "AI Security Engineer", "department": "Quality Assurance", "role": "AI Security Engineer", "mission": "Audit authentication, authorization, input handling, secrets and headers, then harden the code."},
    {"id": "devops", "name": "AI DevOps Engineer", "department": "DevOps", "role": "AI DevOps Engineer", "mission": "Prepare environment configuration, build verification, monitoring and rollback. Never deploy without approval."},
    {"id": "founder", "name": "AI Founder's Office", "department": "Executive Office", "role": "AI Founder Review Analyst", "mission": "Perform the final readiness review against verified evidence and recommend approval or revision."},
    {"id": "growth", "name": "AI Growth Strategist", "department": "Sales & Marketing", "role": "AI Growth Strategist", "mission": "Develop positioning, ideal customer profiles, ethical marketing plans, and launch content."},
    {"id": "support", "name": "AI Customer Support Designer", "department": "Customer Support", "role": "AI Customer Support Designer", "mission": "Design help content, support workflows, escalation rules, and feedback loops."},
    {"id": "operations", "name": "AI Operations Analyst", "department": "Operations & Finance", "role": "AI Operations Analyst", "mission": "Estimate operating costs, identify constraints, document procedures, and track operational risks."},
]

AGENT_BY_ID = {agent["id"]: agent for agent in AGENTS}

AGENT_WORK_PROMPTS = {
    "product": "Create a product requirements brief with problem statement, users, goals, features, user stories, acceptance criteria, assumptions, and open questions.",
    "design": "Create a UX/UI specification with user journeys, page inventory, layout guidance, reusable components, responsive states, accessibility, and design acceptance criteria.",
    "frontend": "Create a frontend implementation specification with component structure, routes, state management, forms, validation, API integration, loading/error states, and acceptance criteria.",
    "backend": "Create a backend implementation specification with entities, API endpoints, validation, authentication/authorization, business rules, error handling, data protection, and acceptance criteria.",
    "database": "Design the database schema with tables, columns, types, constraints, indexes, relationships and transaction boundaries.",
    "qa": "Create a practical QA test plan with test cases, edge cases, negative tests, privacy checks, accessibility checks, and release-blocking criteria.",
    "security": "Create a security review covering authentication, authorization, injection, secrets, headers, rate limiting and hardening actions.",
    "devops": "Create a DevOps plan covering local setup, environment variables, secrets handling, CI checks, deployment options, monitoring, backups, rollback, and approval gates. Do not deploy anything.",
    "growth": "Create a go-to-market brief covering positioning, ideal customer profile, value proposition, channels, launch content ideas, ethical outreach, and measurable KPIs. Do not contact anyone.",
    "support": "Create a customer support plan covering onboarding, help content, common issues, escalation paths, service expectations, and feedback collection.",
    "operations": "Create an operations brief covering cost categories, free-tier limits, risks, procedures, ownership, and a lightweight KPI/reporting plan. Do not spend money.",
    "founder": "Perform a final readiness review against verified build, test, security and preview evidence.",
}

# The eleven-step autonomous development pipeline, in execution order.
PIPELINE = [
    {"phase": "requirement", "agent_id": "ceo", "label": "Requirement intake"},
    {"phase": "analysis", "agent_id": "ceo", "label": "AI CEO analysis"},
    {"phase": "specification", "agent_id": "product", "label": "Product specification"},
    {"phase": "design", "agent_id": "design", "label": "Design system"},
    {"phase": "api_design", "agent_id": "backend", "label": "API & data design"},
    {"phase": "implementation", "agent_id": "database", "label": "Database implementation"},
    {"phase": "implementation", "agent_id": "backend", "label": "Backend implementation"},
    {"phase": "implementation", "agent_id": "frontend", "label": "Frontend implementation"},
    {"phase": "build", "agent_id": "devops", "label": "Install & build"},
    {"phase": "testing", "agent_id": "qa", "label": "Automated testing"},
    {"phase": "security", "agent_id": "security", "label": "Security review"},
    {"phase": "deployment_prep", "agent_id": "devops", "label": "Deployment preparation"},
    {"phase": "founder_review", "agent_id": "founder", "label": "Founder review"},
]

PHASE_LABELS = {
    "requirement": "Intake",
    "analysis": "Analysis",
    "specification": "Specification",
    "design": "Design",
    "api_design": "API & data design",
    "implementation": "Implementation",
    "build": "Build",
    "testing": "Testing",
    "security": "Security",
    "deployment_prep": "Deployment prep",
    "founder_review": "Founder review",
    "awaiting_approval": "Awaiting founder approval",
    "revision": "Revision requested",
    "completed": "Completed",
    "failed": "Failed",
    "draft": "Draft",
    "running": "Running",
}

PIPELINE_STEPS = PIPELINE
