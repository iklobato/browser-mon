# AI Agent Browser Monitoring Service

A minimal prototype for monitoring AI agents operating in browser environments.

## Overview

This prototype implements a simplified version of the browser monitoring service described in your requirements. It provides:

- A FastAPI server that can create and manage headless Chrome browser instances
- CDP (Chrome DevTools Protocol) endpoints for AI agents to connect to
- Basic monitoring of browser events (Network, Page, Runtime)
- A simple client demo using Playwright to demonstrate the functionality

## File Structure

- `server.py` - The FastAPI server application
- `client.py` - A demo client that connects to a browser session and performs actions
- `Dockerfile.server` - Docker configuration for the server
- `Dockerfile.client` - Docker configuration for the client
- `requirements.server.txt` - Python dependencies for the server
- `requirements.client.txt` - Python dependencies for the client
- `docker-compose.yml` - Docker Compose configuration to run both containers

## Running the Prototype

1. Make sure you have Docker and Docker Compose installed
2. Clone this repository
3. Run the following command in the repository directory:

```bash
docker-compose up --build
```

This will:
1. Build and start the server container
2. Build and start the client container
3. The client will automatically connect to the server, request a browser session, perform some demo actions, and display monitoring logs

## API Endpoints

- `POST /sessions` - Create a new browser session
- `GET /sessions` - List all active sessions
- `GET /sessions/{session_id}` - Get details for a specific session
- `GET /sessions/{session_id}/logs` - Get monitoring logs for a session
- `DELETE /sessions/{session_id}` - Terminate a browser session

## Next Steps for Enhancement

1. Add persistent storage for session logs
2. Implement session replay functionality
3. Add more comprehensive event monitoring
4. Create a web dashboard for visualizing sessions and logs
5. Implement policy engine for blocking unwanted actions
6. Add authentication and multi-user support
7. Deploy to cloud infrastructure

## Technical Notes

- The server runs headless Chrome instances with CDP enabled
- Communication between containers uses Docker's bridge network mode
- The client container can access the server via the hostname `server`
- Browser CDP endpoints are exposed to the client via `host.docker.internal`

