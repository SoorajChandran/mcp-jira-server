# MCP Jira Server

An MCP server that integrates with Jira for issue management.

Vibecoded by [Sooraj Chandran](https://x.com/soorajchandran_)

## Features

- Create, read, update Jira issues
- Search issues
- Epic management with subtasks
- Personal issue tracking

## Other use cases
- Create issues from PRDs


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


## Security Notes

- Never commit your `.env` file
- Keep your Jira API token secure
- Use HTTPS in production
- Consider implementing additional authentication for the API endpoints

