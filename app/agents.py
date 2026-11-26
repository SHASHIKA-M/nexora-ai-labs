AGENTS = [
    {"id": "ceo", "name": "AI CEO / Executive Office", "department": "Executive Office", "role": "AI Chief Executive Officer", "mission": "Translate founder goals into clear priorities, project plans, and accountable departmental assignments."},
    {"id": "product", "name": "AI Product Manager", "department": "Product Strategy", "role": "AI Product Manager", "mission": "Define users, problems, requirements, scope, user stories, and acceptance criteria."},
    {"id": "design", "name": "AI UX/UI Designer", "department": "Design", "role": "AI UX/UI Designer", "mission": "Prepare user journeys, page structure, design systems, responsive behavior, and accessibility guidance."},
    {"id": "frontend", "name": "AI Frontend Engineer", "department": "Development", "role": "AI Frontend Engineer", "mission": "Plan frontend architecture, components, state, forms, validation, and integration points."},
    {"id": "backend", "name": "AI Backend Engineer", "department": "Development", "role": "AI Backend Engineer", "mission": "Plan APIs, data models, authentication, authorization, business logic, and integrations."},
    {"id": "qa", "name": "AI QA & Security Analyst", "department": "Quality Assurance", "role": "AI QA & Security Analyst", "mission": "Prepare functional, edge-case, accessibility, privacy, and security test plans."},
    {"id": "devops", "name": "AI DevOps Engineer", "department": "DevOps", "role": "AI DevOps Engineer", "mission": "Prepare local development, CI/CD, hosting, environment, monitoring, backup, and rollback plans. Never deploy."},
    {"id": "growth", "name": "AI Growth Strategist", "department": "Sales & Marketing", "role": "AI Growth Strategist", "mission": "Develop positioning, ideal customer profiles, ethical marketing plans, and launch content."},
    {"id": "support", "name": "AI Customer Support Designer", "department": "Customer Support", "role": "AI Customer Support Designer", "mission": "Design help content, support workflows, escalation rules, and feedback loops."},
    {"id": "operations", "name": "AI Operations Analyst", "department": "Operations & Finance", "role": "AI Operations Analyst", "mission": "Estimate operating costs, identify constraints, document procedures, and track operational risks."},
]

AGENT_BY_ID = {agent["id"]: agent for agent in AGENTS}

AGENT_WORK_PROMPTS = {
    "product": "Create a product requirements brief with problem statement, users, goals, features, user stories, acceptance criteria, assumptions, and open questions.",
    "design": "Create a UX/UI specification with user journeys, page inventory, layout guidance, reusable components, responsive states, accessibility, and design acceptance criteria.",
    "frontend": "Create a frontend implementation specification with recommended component structure, routes, state management, forms, validation, API integration, loading/error states, and acceptance criteria. Do not claim code was changed.",
    "backend": "Create a backend implementation specification with entities, API endpoints, validation, authentication/authorization, business rules, error handling, data protection, and acceptance criteria. Do not claim code was changed.",
    "qa": "Create a practical QA and security test plan with test cases, edge cases, negative tests, privacy checks, accessibility checks, and release-blocking criteria.",
    "devops": "Create a DevOps plan covering local setup, environment variables, secrets handling, CI checks, deployment options, monitoring, backups, rollback, and approval gates. Do not deploy anything.",
    "growth": "Create a go-to-market brief covering positioning, ideal customer profile, value proposition, channels, launch content ideas, ethical outreach, and measurable KPIs. Do not contact anyone.",
    "support": "Create a customer support plan covering onboarding, help content, common issues, escalation paths, service expectations, and feedback collection.",
    "operations": "Create an operations brief covering cost categories, free-tier limits, risks, procedures, ownership, and a lightweight KPI/reporting plan. Do not spend money.",
}
