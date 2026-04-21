#!/usr/bin/env python3
"""
Create example templates for SkillWeave Next Level.
"""

import os
import yaml
from pathlib import Path

def create_example_templates(templates_dir: Path):
    """Create three example templates: web app, API service, CLI tool."""
    
    # Ensure directory exists
    templates_dir.mkdir(exist_ok=True, parents=True)
    
    # Template 1: Web App
    web_app_template = {
        "name": "web_app_starter",
        "type": "web_app",
        "description": "Starter template for a modern web application",
        "content": {
            "project_type": "web_app",
            "stack": {
                "frontend": "${frontend_framework}",
                "backend": "${backend_framework}",
                "database": "${database}",
                "deployment": "${deployment_platform}"
            },
            "structure": {
                "src": {
                    "components": ["${component_list}"],
                    "pages": ["${page_list}"],
                    "styles": ["${style_framework}"]
                },
                "public": ["index.html", "assets"],
                "package.json": {
                    "dependencies": {
                        "${frontend_framework}": "^latest",
                        "react-router-dom": "^6.0",
                        "axios": "^1.0"
                    },
                    "scripts": {
                        "start": "npm run dev",
                        "build": "npm run build",
                        "dev": "vite"
                    }
                }
            },
            "development": {
                "environment_variables": {
                    "API_URL": "${api_url}",
                    "ENV": "development"
                },
                "scripts": {
                    "setup": "npm install",
                    "test": "npm test"
                }
            },
            "deployment": {
                "platform": "${deployment_platform}",
                "steps": [
                    "Build application",
                    "Deploy to ${deployment_platform}",
                    "Configure environment variables"
                ]
            }
        },
        "variables": [
            "frontend_framework",
            "backend_framework",
            "database",
            "deployment_platform",
            "component_list",
            "page_list",
            "style_framework",
            "api_url"
        ]
    }
    
    # Template 2: API Service
    api_service_template = {
        "name": "api_service_starter",
        "type": "api_service",
        "description": "Starter template for a RESTful API service",
        "content": {
            "project_type": "api_service",
            "stack": {
                "framework": "${api_framework}",
                "language": "${language}",
                "database": "${database}",
                "authentication": "${auth_method}"
            },
            "structure": {
                "src": {
                    "controllers": ["${controller_list}"],
                    "models": ["${model_list}"],
                    "routes": ["${route_list}"],
                    "middleware": ["${middleware_list}"],
                    "utils": ["${utility_list}"]
                },
                "tests": {
                    "unit": ["${unit_test_files}"],
                    "integration": ["${integration_test_files}"]
                },
                "package.json": {
                    "dependencies": {
                        "${api_framework}": "^latest",
                        "express": "^4.18",
                        "mongoose": "^7.0",
                        "jsonwebtoken": "^9.0"
                    },
                    "scripts": {
                        "start": "node src/index.js",
                        "dev": "nodemon src/index.js",
                        "test": "jest"
                    }
                }
            },
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/${resource_name}",
                    "description": "Get all ${resource_name}"
                },
                {
                    "method": "GET",
                    "path": "/api/${resource_name}/:id",
                    "description": "Get single ${resource_name}"
                },
                {
                    "method": "POST",
                    "path": "/api/${resource_name}",
                    "description": "Create ${resource_name}"
                }
            ],
            "development": {
                "environment_variables": {
                    "PORT": "${port}",
                    "DB_URL": "${database_url}",
                    "JWT_SECRET": "${jwt_secret}"
                }
            }
        },
        "variables": [
            "api_framework",
            "language",
            "database",
            "auth_method",
            "controller_list",
            "model_list",
            "route_list",
            "middleware_list",
            "utility_list",
            "unit_test_files",
            "integration_test_files",
            "resource_name",
            "port",
            "database_url",
            "jwt_secret"
        ]
    }
    
    # Template 3: CLI Tool
    cli_tool_template = {
        "name": "cli_tool_starter",
        "type": "cli_tool",
        "description": "Starter template for a command-line interface tool",
        "content": {
            "project_type": "cli_tool",
            "stack": {
                "language": "${language}",
                "cli_framework": "${cli_framework}",
                "package_manager": "${package_manager}"
            },
            "structure": {
                "src": {
                    "commands": ["${command_list}"],
                    "utils": ["${utility_list}"],
                    "config": ["${config_files}"]
                },
                "bin": {
                    "${tool_name}": "Entry point script"
                },
                "package.json": {
                    "name": "${tool_name}",
                    "version": "1.0.0",
                    "bin": {
                        "${tool_name}": "./bin/${tool_name}"
                    },
                    "dependencies": {
                        "${cli_framework}": "^latest",
                        "commander": "^11.0",
                        "chalk": "^5.0",
                        "inquirer": "^9.0"
                    },
                    "scripts": {
                        "start": "node src/index.js",
                        "test": "jest",
                        "build": "npm run build"
                    }
                }
            },
            "commands": [
                {
                    "name": "${command_name}",
                    "description": "${command_description}",
                    "options": [
                        {
                            "flag": "--verbose",
                            "description": "Enable verbose output"
                        }
                    ]
                }
            ],
            "development": {
                "environment_variables": {
                    "DEBUG": "${debug_flag}"
                },
                "testing": {
                    "framework": "${test_framework}",
                    "coverage": "${coverage_tool}"
                }
            }
        },
        "variables": [
            "language",
            "cli_framework",
            "package_manager",
            "command_list",
            "utility_list",
            "config_files",
            "tool_name",
            "command_name",
            "command_description",
            "debug_flag",
            "test_framework",
            "coverage_tool"
        ]
    }
    
    # Write templates to YAML files
    templates = [
        ("web_app_starter.yaml", web_app_template),
        ("api_service_starter.yaml", api_service_template),
        ("cli_tool_starter.yaml", cli_tool_template)
    ]
    
    for filename, template in templates:
        filepath = templates_dir / filename
        with open(filepath, 'w') as f:
            yaml.dump(template, f, default_flow_style=False, sort_keys=False)
        print(f"Created template: {filepath}")
    
    print(f"\nCreated {len(templates)} example templates in {templates_dir}")

if __name__ == "__main__":
    # Determine project root (go up from examples/ directory)
    project_root = Path(__file__).parent.parent
    templates_dir = project_root / ".skillweave" / "templates"
    
    create_example_templates(templates_dir)
    
    # Also create templates in examples/templates for reference
    examples_dir = project_root / "examples" / "templates"
    create_example_templates(examples_dir)