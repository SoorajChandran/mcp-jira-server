import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import aiohttp
import aiohttp_cors
from aiohttp import web
from dotenv import load_dotenv
from jira import JIRA
from jira.exceptions import JIRAError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_server.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

@dataclass
class ServerConfig:
    port: int = int(os.getenv('MCP_SERVER_PORT', 8000))
    host: str = os.getenv('MCP_SERVER_HOST', '0.0.0.0')
    static_dir: str = 'static'
    cors_origins: List[str] = field(default_factory=lambda: ['*'])

@dataclass
class JiraConfig:
    server: str
    user: str
    token: str
    timeout: int = 30
    max_results: int = 50

class MCPJiraServer:
    def __init__(self):
        self.config = JiraConfig(
            server=os.getenv('JIRA_SERVER', ''),
            user=os.getenv('JIRA_USER', ''),
            token=os.getenv('JIRA_TOKEN', ''),
            timeout=int(os.getenv('JIRA_TIMEOUT', '30')),
            max_results=int(os.getenv('JIRA_MAX_RESULTS', '50'))
        )
        if not all([self.config.server, self.config.user, self.config.token]):
            raise ValueError('Missing required JIRA configuration')
        
        self.jira = JIRA(
            server=self.config.server,
            basic_auth=(self.config.user, self.config.token),
            timeout=self.config.timeout
        )
        
    async def handle_mcp_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP messages and interact with Jira."""
        try:
            command = message.get('command')
            if not command:
                return {'status': 'error', 'message': 'No command specified'}

            if command == 'create_issue':
                return await self._create_issue(message)
            elif command == 'get_issue':
                return await self._get_issue(message)
            elif command == 'update_issue':
                return await self._update_issue(message)
            elif command == 'search_issues':
                return await self._search_issues(message)
            elif command == 'get_epic_with_subtasks':
                return await self._get_epic_with_subtasks(message)
            elif command == 'get_my_issues':
                return await self._get_my_issues(message)
            elif command == 'get_transitions':
                return await self._get_transitions(message)
            else:
                return {'status': 'error', 'message': f'Unknown command: {command}'}

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    async def _create_issue(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Jira issue."""
        data = message.get('data', {})
        if not all(k in data for k in ['project', 'summary', 'description']):
            return {'status': 'error', 'message': 'Missing required fields'}

        issue_dict = {
            'project': {'key': data['project']},
            'summary': data['summary'],
            'description': data['description'],
            'issuetype': {'name': data.get('issue_type', 'Task')}
        }

        # Add parent field for subtasks
        if data.get('issue_type') == 'Subtask' and data.get('parent_issue'):
            issue_dict['parent'] = {'key': data['parent_issue']}

        issue = self.jira.create_issue(fields=issue_dict)
        return {
            'status': 'success',
            'data': {
                'issue_key': issue.key,
                'issue_id': issue.id,
                'self': issue.self
            }
        }

    async def _get_issue(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get Jira issue details."""
        issue_key = message.get('data', {}).get('issue_key')
        if not issue_key:
            return {'status': 'error', 'message': 'Missing issue key'}

        issue = self.jira.issue(issue_key)
        return {
            'status': 'success',
            'data': {
                'issue_key': issue.key,
                'summary': issue.fields.summary,
                'description': issue.fields.description,
                'status': issue.fields.status.name
            }
        }

    async def _update_issue(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing Jira issue."""
        data = message.get('data', {})
        issue_key = data.get('issue_key')
        if not issue_key:
            return {'status': 'error', 'message': 'Missing issue key'}

        update_fields = {}
        if 'summary' in data:
            update_fields['summary'] = data['summary']
        if 'description' in data:
            update_fields['description'] = data['description']

        issue = self.jira.issue(issue_key)
        
        # Handle status update
        if 'status' in data:
            transitions = self.jira.transitions(issue)
            target_status = data['status'].lower()
            transition_id = None
            available_transitions = []
            
            # Find matching transition and collect available ones
            for t in transitions:
                available_transitions.append(t['to']['name'])
                if t['to']['name'].lower() == target_status:
                    transition_id = t['id']
                    break
            
            if transition_id:
                self.jira.transition_issue(issue, transition_id)
            else:
                suggestion_msg = f"Available status transitions are: {', '.join(available_transitions)}"
                return {
                    'status': 'error',
                    'message': f'No transition found to status: {data["status"]}. {suggestion_msg}'
                }

        # Update other fields if any
        if update_fields:
            issue.update(fields=update_fields)
            
        return {'status': 'success', 'message': f'Updated issue {issue_key}'}

    async def _search_issues(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Search for Jira issues by description.
        
        Args:
            message: Dictionary containing search parameters
                - search_text: Text to search for
                - title_only: If True, only search in title
                - page: Page number (optional)
                - page_size: Results per page (optional)
        
        Returns:
            Dictionary containing search results and pagination info
        """
        data = message.get('data', {})
        search_text = data.get('search_text')
        title_only = data.get('title_only', False)
        page = max(1, int(data.get('page', 1)))  # Ensure page >= 1
        page_size = min(self.config.max_results, int(data.get('page_size', 20)))  # Limit max results
        
        if not search_text:
            return {'status': 'error', 'message': 'Missing search text'}

        try:
            # Build JQL query
            if title_only:
                jql = f'summary ~ "{search_text}" AND issuetype != Epic'
            else:
                jql = f'(summary ~ "{search_text}" OR description ~ "{search_text}") AND issuetype != Epic'

            # Calculate pagination
            start_at = (page - 1) * page_size
            
            # Fetch issues with pagination
            issues = self.jira.search_issues(
                jql,
                startAt=start_at,
                maxResults=page_size,
                validate_query=True
            )
            
            # Process results
            results = [{
                'key': issue.key,
                'summary': issue.fields.summary,
                'description': issue.fields.description,
                'status': issue.fields.status.name,
                'created': str(issue.fields.created),
                'updated': str(issue.fields.updated),
                'assignee': str(issue.fields.assignee) if issue.fields.assignee else None
            } for issue in issues]
            
            # Add pagination info
            return {
                'status': 'success',
                'data': {
                    'issues': results,
                    'pagination': {
                        'total': issues.total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (issues.total + page_size - 1) // page_size
                    }
                }
            }
            
        except JIRAError as e:
            logger.error(f'JIRA API error: {e.status_code} - {e.text}')
            return {'status': 'error', 'message': f'JIRA API error: {e.status_code} - {e.text}'}
        except ValueError as e:
            logger.error(f'Invalid input: {str(e)}')
            return {'status': 'error', 'message': f'Invalid input: {str(e)}'}
        except Exception as e:
            logger.error(f'Unexpected error in search_issues: {str(e)}')
            return {'status': 'error', 'message': 'An unexpected error occurred'}

    async def _get_epic_with_subtasks(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get an epic and all its subtasks by epic name.
        
        Args:
            message: Dictionary containing search parameters
                - epic_name: Name of the epic to search for
                - page: Page number for subtasks (optional)
                - page_size: Results per page for subtasks (optional)
        
        Returns:
            Dictionary containing epic details and its subtasks with pagination info
        """
        data = message.get('data', {})
        epic_name = data.get('epic_name')
        page = max(1, int(data.get('page', 1)))
        page_size = min(self.config.max_results, int(data.get('page_size', 20)))
        
        if not epic_name:
            return {'status': 'error', 'message': 'Missing epic name'}

        try:
            # First find the epic with exact and fuzzy match
            epic_jql = f'issuetype = Epic AND (summary ~ "{epic_name}" OR summary = "{epic_name}")'            
            epics = self.jira.search_issues(epic_jql, maxResults=5)  # Limit to top 5 matches
            
            if not epics:
                return {'status': 'error', 'message': f'No epic found with name containing "{epic_name}"'}

            # If we have multiple matches, prefer exact match or take the first one
            epic = next(
                (e for e in epics if e.fields.summary.lower() == epic_name.lower()),
                epics[0]
            )
            
            # Calculate pagination for subtasks
            start_at = (page - 1) * page_size
            
            # Then find all issues linked to this epic with pagination
            subtasks_jql = f'"Epic Link" = {epic.key} ORDER BY created DESC'
            subtasks = self.jira.search_issues(
                subtasks_jql,
                startAt=start_at,
                maxResults=page_size,
                validate_query=True
            )

            result = {
                'epic': {
                    'key': epic.key,
                    'summary': epic.fields.summary,
                    'description': epic.fields.description,
                    'status': epic.fields.status.name,
                    'created': str(epic.fields.created),
                    'updated': str(epic.fields.updated),
                    'assignee': str(epic.fields.assignee) if epic.fields.assignee else None,
                    'reporter': str(epic.fields.reporter) if epic.fields.reporter else None,
                    'priority': str(epic.fields.priority) if epic.fields.priority else None
                },
                'subtasks': {
                    'issues': [{
                        'key': task.key,
                        'summary': task.fields.summary,
                        'description': task.fields.description,
                        'status': task.fields.status.name,
                        'issuetype': task.fields.issuetype.name,
                        'created': str(task.fields.created),
                        'updated': str(task.fields.updated),
                        'assignee': str(task.fields.assignee) if task.fields.assignee else None,
                        'priority': str(task.fields.priority) if task.fields.priority else None
                    } for task in subtasks],
                    'pagination': {
                        'total': subtasks.total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (subtasks.total + page_size - 1) // page_size
                    }
                }
            }
            return {'status': 'success', 'data': result}
            
        except JIRAError as e:
            logger.error(f'JIRA API error in get_epic_with_subtasks: {e.status_code} - {e.text}')
            return {'status': 'error', 'message': f'JIRA API error: {e.status_code} - {e.text}'}
        except ValueError as e:
            logger.error(f'Invalid input in get_epic_with_subtasks: {str(e)}')
            return {'status': 'error', 'message': f'Invalid input: {str(e)}'}
        except Exception as e:
            logger.error(f'Unexpected error in get_epic_with_subtasks: {str(e)}')
            return {'status': 'error', 'message': 'An unexpected error occurred'}

    async def _get_my_issues(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get all issues assigned to the current user.
        
        Args:
            message: Dictionary containing search parameters
                - status: Optional status filter (e.g., 'In Progress', 'To Do')
                - project: Optional project key filter
                - page: Page number (optional)
                - page_size: Results per page (optional)
                - sort_by: Field to sort by (optional, default: 'updated')
                - sort_order: 'asc' or 'desc' (optional, default: 'desc')
        
        Returns:
            Dictionary containing issues assigned to the current user with pagination info
        """
        try:
            data = message.get('data', {})
            page = max(1, int(data.get('page', 1)))
            page_size = min(self.config.max_results, int(data.get('page_size', 20)))
            status = data.get('status')
            project = data.get('project')
            sort_by = data.get('sort_by', 'updated')
            sort_order = data.get('sort_order', 'DESC').upper()
            
            # Build JQL query
            jql_parts = ['assignee = currentUser()']
            
            if status:
                jql_parts.append(f'status = "{status}"')
            if project:
                jql_parts.append(f'project = "{project}"')
                
            jql = ' AND '.join(jql_parts)
            
            # Add sorting
            if sort_by in ['created', 'updated', 'priority', 'status', 'duedate']:
                jql += f' ORDER BY {sort_by} {sort_order}'
            
            # Calculate pagination
            start_at = (page - 1) * page_size
            
            # Fetch issues
            issues = self.jira.search_issues(
                jql,
                startAt=start_at,
                maxResults=page_size,
                validate_query=True
            )
            
            # Process results
            results = [{
                'key': issue.key,
                'summary': issue.fields.summary,
                'description': issue.fields.description,
                'status': issue.fields.status.name,
                'created': str(issue.fields.created),
                'updated': str(issue.fields.updated),
                'priority': str(issue.fields.priority) if issue.fields.priority else None,
                'project': {
                    'key': issue.fields.project.key,
                    'name': issue.fields.project.name
                },
                'issuetype': {
                    'name': issue.fields.issuetype.name,
                    'subtask': issue.fields.issuetype.subtask
                },
                'duedate': str(issue.fields.duedate) if hasattr(issue.fields, 'duedate') and issue.fields.duedate else None
            } for issue in issues]
            
            return {
                'status': 'success',
                'data': {
                    'issues': results,
                    'pagination': {
                        'total': issues.total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (issues.total + page_size - 1) // page_size
                    }
                }
            }
            
        except JIRAError as e:
            logger.error(f'JIRA API error in get_my_issues: {e.status_code} - {e.text}')
            return {'status': 'error', 'message': f'JIRA API error: {e.status_code} - {e.text}'}
        except ValueError as e:
            logger.error(f'Invalid input in get_my_issues: {str(e)}')
            return {'status': 'error', 'message': f'Invalid input: {str(e)}'}
        except Exception as e:
            logger.error(f'Unexpected error in get_my_issues: {str(e)}')
            return {'status': 'error', 'message': 'An unexpected error occurred'}

    async def _get_transitions(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get available transitions for a Jira issue."""
        issue_key = message.get('data', {}).get('issue_key')
        if not issue_key:
            return {'status': 'error', 'message': 'Missing issue key'}

        issue = self.jira.issue(issue_key)
        transitions = self.jira.transitions(issue)
        
        # Group transitions by current and next possible statuses
        current_status = issue.fields.status.name
        next_possible = sorted(list(set(t['to']['name'] for t in transitions)))
        
        return {
            'status': 'success',
            'data': {
                'issue_key': issue_key,
                'current_status': current_status,
                'available_transitions': {
                    'current': current_status,
                    'possible_next_statuses': next_possible,
                    'details': [
                        {
                            'id': t['id'],
                            'name': t['name'],
                            'from_status': current_status,
                            'to_status': t['to']['name']
                        }
                        for t in transitions
                    ]
                }
            }
        }

    async def test_connection(self):
        """Test Jira connection."""
        try:
            self.jira.myself()
            return True
        except Exception as e:
            logger.error(f"Jira connection test failed: {e}")
            raise

async def validate_request(request: web.Request) -> Tuple[bool, Optional[str]]:
    """Validate incoming requests."""
    if request.content_type != 'application/json':
        return False, 'Content-Type must be application/json'
        
    try:
        await request.json()
        return True, None
    except json.JSONDecodeError:
        return False, 'Invalid JSON payload'

async def handle_request(request: web.Request) -> web.Response:
    """Handle incoming HTTP requests."""
    try:
        # Validate request
        is_valid, error_message = await validate_request(request)
        if not is_valid:
            return web.json_response(
                {'status': 'error', 'message': error_message},
                status=400
            )
            
        # Process request with timeout
        try:
            data = await request.json()
            server = request.app['jira_client']
            response = await asyncio.wait_for(
                server.handle_mcp_message(data),
                timeout=30
            )
            return web.json_response(response)
        except asyncio.TimeoutError:
            logger.error('Request timed out')
            return web.json_response(
                {'status': 'error', 'message': 'Request timed out'},
                status=504
            )          
    except Exception as e:
        logger.error(f'Unexpected error in handle_request: {str(e)}')
        return web.json_response(
            {'status': 'error', 'message': 'An unexpected error occurred'},
            status=500
        )

async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    try:
        await request.app['jira_client'].test_connection()
        return web.json_response({
            'status': 'healthy',
            'jira_connection': 'ok',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return web.json_response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }, status=500)

async def shutdown(app):
    """Cleanup resources before shutdown."""
    logger.info("Shutting down MCP server...")
    # Close any open connections
    for ws in app['websockets']:
        await ws.close()

def setup_cors(app: web.Application) -> None:
    """Configure CORS."""
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["POST", "GET", "OPTIONS"]
        )
    })
    
    for route in list(app.router.routes()):
        cors.add(route)

def main():
    # Load configuration
    config = ServerConfig()
    
    # Initialize application
    app = web.Application()
    
    # Setup routes
    app.router.add_post('/mcp', handle_request)
    app.router.add_get('/health', health_check)
    app.router.add_static('/', path=os.path.join(os.path.dirname(__file__), config.static_dir))
    
    # Setup CORS
    setup_cors(app)
    
    # Initialize resources
    app['websockets'] = []
    app['jira_client'] = MCPJiraServer()
    
    # Setup cleanup
    app.on_shutdown.append(shutdown)
    
    # Create static directory
    static_dir = os.path.join(os.path.dirname(__file__), config.static_dir)
    os.makedirs(static_dir, exist_ok=True)
    
    # Start server
    logger.info(f"Starting MCP server on {config.host}:{config.port}")
    web.run_app(app, host=config.host, port=config.port)

if __name__ == '__main__':
    main()
