# MCP Jira Server

A FastAPI-based Microservice Control Plane server that integrates with Jira for issue management.

## Features

- Create, read, update Jira issues
- Search issues with advanced filtering
- Epic management with subtasks
- Personal issue tracking
- RESTful API endpoints
- Environment-based configuration
- CORS support
- Pagination support
- Comprehensive error handling

## Prerequisites

- Python 3.8+
- Jira account with API access
- Jira API token

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your Jira credentials:
   ```bash
   cp .env.example .env
   ```
5. Edit `.env` with your Jira configuration:
   - JIRA_SERVER: Your Jira instance URL
   - JIRA_USER: Your Jira email
   - JIRA_TOKEN: Your Jira API token
   - JIRA_TIMEOUT: API timeout in seconds (default: 30)
   - JIRA_MAX_RESULTS: Maximum results per page (default: 50)
   - MCP_SERVER_PORT: Server port (default: 8000)

## Running the Server

```bash
python src/main.py
```

The server will start on `http://localhost:8000`

## Main Commands/Endpoints

All commands are sent to the `/mcp` endpoint using POST requests with JSON payloads.

### 1. Create Issue
```json
{
    "command": "create_issue",
    "data": {
        "project": "PROJECT_KEY",
        "summary": "Issue title",
        "description": "Issue description",
        "issue_type": "Task"  // Optional, defaults to "Task"
    }
}
```

### 2. Get Issue
```json
{
    "command": "get_issue",
    "data": {
        "issue_key": "PROJ-123"
    }
}
```

### 3. Update Issue
```json
{
    "command": "update_issue",
    "data": {
        "issue_key": "PROJ-123",
        "summary": "New title",  // Optional
        "description": "New description"  // Optional
    }
}
```

### 4. Search Issues
```json
{
    "command": "search_issues",
    "data": {
        "search_text": "Search term",
        "title_only": false,  // Optional, search in title only
        "page": 1,  // Optional, default: 1
        "page_size": 20  // Optional, default: 20, max: 50
    }
}
```

### 5. Get Epic with Subtasks
```json
{
    "command": "get_epic_with_subtasks",
    "data": {
        "epic_name": "Epic Name",
        "page": 1,  // Optional, for subtasks pagination
        "page_size": 20  // Optional, for subtasks pagination
    }
}
```

### 6. Get My Issues
```json
{
    "command": "get_my_issues",
    "data": {
        "status": "In Progress",  // Optional
        "project": "PROJ",  // Optional
        "page": 1,  // Optional
        "page_size": 20,  // Optional
        "sort_by": "updated",  // Optional: created, updated, priority, status, duedate
        "sort_order": "desc"  // Optional: asc, desc
    }
}
```

## Response Format

All endpoints return responses in the following format:

### Success Response
```json
{
    "status": "success",
    "data": {
        // Command-specific response data
    }
}
```

### Error Response
```json
{
    "status": "error",
    "message": "Error description"
}
```

## Pagination

For endpoints that support pagination, the response includes pagination information:
```json
{
    "status": "success",
    "data": {
        "issues": [...],
        "pagination": {
            "total": 100,
            "page": 1,
            "page_size": 20,
            "total_pages": 5
        }
    }
}
```

## Security Notes

- Never commit your `.env` file
- Keep your Jira API token secure
- Use HTTPS in production
- Consider implementing additional authentication for the API endpoints

