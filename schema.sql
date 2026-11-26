CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  business_line VARCHAR(30) NOT NULL DEFAULT 'both',
  status VARCHAR(40) NOT NULL DEFAULT 'planning',
  created_at DATETIME NOT NULL
);

CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  department VARCHAR(80) NOT NULL,
  agent_role VARCHAR(100) NOT NULL,
  agent_id VARCHAR(40) NOT NULL DEFAULT 'backend',
  title VARCHAR(200) NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  result TEXT,
  status VARCHAR(40) NOT NULL DEFAULT 'queued',
  created_at DATETIME NOT NULL
);
